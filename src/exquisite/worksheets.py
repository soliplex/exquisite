"""Generating the designator -> document_uri worksheets an SME fills in.

One worksheet per question set, in three parts:

- ``designators:``  the part a human edits -- one entry per designator, grouped
  by collapsed key so spelling variants of one document are neighbours.
- ``candidates:``   generated, advisory, keyed by the same collapsed key.  It
  is never an answer:  the closest-looking match is often a notice amending the
  publication rather than the publication.
- ``apply_keys:``   generated, machine-read.  Every verbatim
  ``metadata.reference`` string mapped to its designator, so applying a
  worksheet is exact lookup with no normalization.

Corpus URIs come from a TSV (``<database>\\t<document_uri>``) rather than from
LanceDB directly, so this runs anywhere.  See the README for producing one.
"""

import collections
import functools
import hashlib
import json
import os
import pathlib
import re

import yaml

from exquisite import corpus as corpus_mod
from exquisite import designators
from exquisite import manifest as manifest_mod
from exquisite import rules as rules_mod

#: Placeholder left for the SME.  Deliberately not a list, so an applier fails
#: loudly on an unfilled entry rather than reading it as "no documents".
UNFILLED = "FILL ME IN"

#: Cap on advisory lists, which are a convenience rather than a result.
MAX_ADVISORY = 12

#: Key marking a machine-made answer that a person has not yet confirmed.
#: `bind` refuses a worksheet while any designator carries it;  confirming an
#: answer is deleting the line.
PROVISIONAL = "provisional"


#: Comment block heading every worksheet; ``{database}`` is filled in.
_HEADER = """\
# Map document designators (as cited in the question set) to document URIs
# (as stored in the `{database}` corpus).  Fill in `documents:` on each entry.
#
# Entries are grouped by a "collapsed key" -- the designator with
# "Vol 3" read as "v3", "Supplement" as "supp", and all
# punctuation and spacing removed.  The comment above each group is that key;
# `candidates:` below is keyed by the same thing; jump down and back.
# Designators sharing a key are spelling variants of what is probably one
# document; if so, give them the same `documents:`.  Nothing needs merging.
# An `also cited as` note links two groups with different keys:  one group's
# filenames match a document whose trusted identifier names the other.  They
# are probably one publication too.
# A `provisional:` line marks an answer made from a trusted identifier match;
# check it, then delete the line.  `bind` refuses the worksheet until then.
"""

#: Lines left under a designator nobody has answered yet.
_UNFILLED_LINES = [
    f"  documents: {UNFILLED}   # a list of {{name, sha256, source_url}};",
    "                          # or [] with `unresolved` filled in",
    "  unresolved:        # reason, if it genuinely cannot be resolved",
    "  notes:",
]

#: Comment block above the generated `candidates:`; ``{database}`` is filled.
_CANDIDATES_LEGEND = """\
# ---------------------------------------------------------------------------
# Generated below this line -- do not edit.
# ---------------------------------------------------------------------------

# Documents in `{database}` resembling each designator, keyed by the same
# collapsed key as above.  ADVISORY ONLY -- nothing here is an answer, and
# lists are alphabetical, not ranked, deliberately:  the closest-looking
# match is often a notice amending the publication, not the publication.
# `identifier` = the document's own publication identifier
# collapses to this key; each entry leads with it, and with where it came
# from and how sure that source was.  `identifier_related` = the identifier
# extends this key (a supplement, volume or sub-publication):
# never the answer by itself.  `matched` = name matches and the digit run
# is identical; `related` = name or digits overlap but differ (other
# volumes, parts, addenda); `same_series` appears only when nothing
# else did.
"""

#: Comment block above the generated `apply_keys:`.
_APPLY_KEYS_LEGEND = """\
# Every distinct `metadata.reference` string, mapped to the designator above
# that covers it.  This is the apply key:  a script looks up a case's verbatim
# `reference` here, then takes that designator's `documents:`.
"""


class WorksheetExists(FileExistsError):
    """The pairing already exists, so it is refreshed, never re-created."""

    def __init__(self, path: pathlib.Path):
        self.path = path
        super().__init__(f"{path} already exists; refresh it instead")


class NoReferences(ValueError):
    """A question set with no usable references:  nothing to map."""

    def __init__(self, question_set: str):
        self.question_set = question_set
        super().__init__(
            f"{question_set} records no usable references, so there is "
            "nothing to map; an empty worksheet would read as work done"
        )


def _quote(text: str) -> str:
    """Always quote:  a collapsed key like ``0025172`` reads as octal bare."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _document_lines(
    fields: dict,
    indent: str,
    flags: str = "",
    order: tuple[str, ...] | None = None,
) -> list[str]:
    """One document as a YAML mapping, with every string value quoted.

    Quoting unconditionally rather than only when YAML requires it:  a filename
    may begin with ``-``, or contain ``: `` or `` #``, and unquoted those
    change what the parser sees.  A reader should not have to work out which
    lines are safe, and anyone hand-editing an unquoted one is a character away
    from a silent change of meaning.
    """
    order = order or (
        "name",
        "sha256",
        "source_url",
        "attachment",
        "document_identifier",
    )
    keys = [key for key in order if fields.get(key)]
    lines = []

    for position, key in enumerate(keys):
        suffix = flags if position == 0 else ""
        lines.append(
            f"{indent}{'- ' if position == 0 else '  '}{key}: "
            f"{_quote(str(fields[key]))}{suffix}"
        )

    for key in ("sha256", "source_url"):
        if not fields.get(key) and key in order:
            lines.append(f"{indent}  {key}:")

    return lines


def _flags(uri: str, rules: rules_mod.Rules = rules_mod.BUILTIN_RULES) -> str:
    notes = []

    if "#attachment=" in uri:
        notes.append("attachment")
        parent = os.path.basename(uri.split("#attachment=", 1)[0])
        notes += [
            rule.note
            for rule in rules.parent_notes
            if rule.pattern.search(parent)
        ]

    return ("   # " + "; ".join(notes)) if notes else ""


def _match_name(uri: str) -> str:
    """The name to match a designator against.

    An ``#attachment=`` URI is matched on the attachment's own name, not its
    parent's:  the parent is usually a bulletin or notice whose name says
    nothing about what it carries.
    """
    if "#attachment=" in uri:
        return os.path.basename(uri.split("#attachment=")[1])

    return re.sub(r"\.[a-z0-9]{2,5}$", "", os.path.basename(uri), flags=re.I)


def _is_subsequence(wanted: list[str], within: list[str]) -> bool:
    stream = iter(within)

    return all(item in stream for item in wanted)


def relation(
    key: str, identifier: str, rules: rules_mod.Rules = rules_mod.BUILTIN_RULES
) -> str | None:
    """How a document whose identifier extends a designator's key relates.

    None when the identifier does not extend the key (see
    `designators.extension`), else what the extra part says:  the label of the
    first relation matching it, the caller's tried before the built-in
    ``supplement``, ``volume`` and ``sub-publication``.  The last built-in
    matches anything, so some label always applies.
    """
    rest = designators.extension(key, identifier, rules)

    if rest is None:
        return None

    return next(
        rule.label
        for rule in rules.effective_relations
        if rule.pattern.search(rest)
    )


def find_candidates(
    key: str,
    seriess: set[str],
    corpus: manifest_mod.Corpus,
    rules: rules_mod.Rules = rules_mod.BUILTIN_RULES,
) -> dict:
    """Documents resembling a collapsed key, in tiers, strongest first.

    ``identifier`` -- the document's publication designator
    (`document_identifier`) collapses to exactly this key.  This is real
    evidence rather than a filename resemblance, so it leads;  each entry says
    where the identifier came from, and how sure that source was.  Its absence
    means nothing, since not every document carries one.

    ``identifier_related`` -- the identifier *extends* the key at a boundary:
    a supplement to it, a volume or a part of it.  Never the answer by itself,
    and kept apart from ``identifier`` so it cannot be mistaken for one --
    lumping them together offers a standard's supplements and parts as
    matches for the standard.

    Then filename tiers:  ``matched`` (name contains the key and the digit run
    is identical), ``related`` (name or digits overlap but differ -- other
    volumes, parts, addenda), and ``same_series`` (only when nothing else
    hit).

    Tiers are facts, not a ranking, and each is alphabetical.
    ``identifier_related`` maps each URI to its relation.
    """
    uris = [doc.uri for doc in corpus.documents]
    identified = sorted(
        {doc.uri for doc in corpus.by_identifier(rules).get(key, [])}
    )
    extending: dict[str, str] = {}

    for doc in corpus.documents:
        if not doc.document_identifier or doc.uri in identified:
            continue

        how = relation(key, doc.document_identifier, rules)

        if how:
            extending[doc.uri] = how

    core = re.sub(r"^[a-z]+", "", key)
    wanted = designators.numbers(key)
    # An empty series means "no series word", e.g. `61508-3`.  It must never
    # match another empty one, or every digit-initial document in the corpus --
    # including URL-encoded attachment names -- becomes a candidate.
    seriess = {name for name in seriess if name}
    matched, related = [], []

    for uri in uris:
        name = _match_name(uri)
        squashed = re.sub(r"[^a-z0-9]", "", name.casefold())

        if core and core in squashed:
            (
                matched if designators.numbers(squashed) == wanted else related
            ).append(uri)
        elif (
            designators.series(name, rules) in seriess
            and wanted
            and _is_subsequence(wanted, designators.numbers(squashed))
        ):
            related.append(uri)

    matched = sorted(set(matched) - set(identified) - set(extending))
    related = sorted(
        set(related) - set(matched) - set(identified) - set(extending)
    )
    found = {"identifier": identified, "matched": matched}

    if extending:
        found["identifier_related"] = dict(sorted(extending.items()))

    if related:
        found["related"] = related[:MAX_ADVISORY]
        found["truncated"] = len(related) > MAX_ADVISORY
    elif not matched and not identified and seriess:
        found["same_series"] = sorted(
            {
                uri
                for uri in uris
                if designators.series(_match_name(uri), rules) in seriess
            }
        )[:MAX_ADVISORY]

    return found


def provisional_answer(
    found: dict, corpus: manifest_mod.Corpus
) -> dict | None:
    """A machine-made answer for one designator group, or None.

    Made only from exact ``identifier`` matches whose identifier is trusted --
    mapped by hand, or inferred with high certainty (see
    `Document.trusted_identifier`).  Anything weaker stays ``FILL ME IN`` for a
    person, and so does everything when no exact trusted match exists:  a
    filename resemblance is never turned into an answer.

    The answer carries `PROVISIONAL`, saying what it rests on.  `bind` refuses
    it until someone confirms it by deleting that line.
    """
    by_uri = {doc.uri: doc for doc in corpus.documents}
    trusted = [
        by_uri[uri]
        for uri in found.get("identifier") or []
        if by_uri[uri].trusted_identifier
    ]

    if not trusted:
        return None

    evidence = sorted({doc.identifier_evidence for doc in trusted})
    identifiers = sorted({doc.document_identifier for doc in trusted})

    return {
        "documents": [doc.durable() for doc in trusted],
        PROVISIONAL: (
            f"identifier match ({'; '.join(evidence)}): "
            f"{', '.join(identifiers)}"
            " -- confirm, then delete this line"
        ),
    }


def cross_references(
    found_by_key: dict[str, dict], corpus: manifest_mod.Corpus
) -> dict[str, list[str]]:
    """Groups that very likely name the same publication under different keys.

    Designator spellings that do not collapse to one key -- ``ISO 9001`` and
    the European adoption ``EN ISO 9001``, say -- land in separate groups, and
    each would be decided on its own.  A document can be an *exact* identifier
    match for only one key, so the link is made through the other tiers:  when
    a document is a trusted exact match for group A and also turns up in group
    B's `matched` filename candidates, A and B are told about each other. Keyed
    by group key;  each value lists the linked groups' keys, sorted.
    """
    by_uri = {doc.uri: doc for doc in corpus.documents}
    owner: dict[str, set[str]] = collections.defaultdict(set)

    for key, found in found_by_key.items():
        for uri in found.get("identifier") or []:
            if by_uri[uri].trusted_identifier:
                owner[uri].add(key)

    linked: dict[str, set[str]] = collections.defaultdict(set)

    for key, found in found_by_key.items():
        for uri in found.get("matched") or []:
            for other in owner.get(uri, ()):
                if other != key:
                    linked[key].add(other)
                    linked[other].add(key)

    return {key: sorted(others) for key, others in linked.items()}


def references(
    cases: list[dict], rules: rules_mod.Rules = rules_mod.BUILTIN_RULES
) -> list[str]:
    """Every usable ``metadata.reference``, one per case that has one."""
    found = []

    for case in cases:
        text = case.metadata.get("reference") or ""

        if text.strip() not in rules.not_references:
            found.append(text)

    return found


def _validation_lines(
    validated: dict | None, substrate: str, rules: str
) -> list[str]:
    """The `validated_by` / `validated_on` block, carried across a refresh.

    An attestation is not discarded on refresh -- that would throw away real
    information -- but neither is it silently carried onto a corpus that has
    been rebuilt with a different embedder or chunk size.  When the substrate
    has moved, the substrate it *was* validated against is recorded beside it,
    so the discrepancy lives in the file rather than in someone's memory.

    Likewise the normalization ``rules`` (their digest):  a change can merge
    or split the designator groups the SME attested to.
    """
    if not validated or not validated.get("validated_by"):
        return [
            "validated_by:      # FILL ME IN",
            "validated_on:      # FILL ME IN",
        ]

    lines = [
        f"validated_by: {validated['validated_by']!r}",
        f"validated_on: {validated.get('validated_on') or ''}",
    ]
    was = validated.get("substrate")

    if was and was != substrate:
        lines.append(
            f"validated_against_substrate: {was}"
            "   # THE CORPUS HAS BEEN REBUILT"
            " SINCE; RE-VALIDATE"
        )

    was = validated.get("rules")

    if was and was != rules:
        lines.append(
            f"validated_against_rules: {was}"
            "   # THE NORMALIZATION RULES HAVE CHANGED SINCE; RE-VALIDATE"
        )

    return lines


def preserved_answers(path: pathlib.Path) -> tuple[dict, dict]:
    """An existing worksheet's answers, keyed by designator, plus its header.

    Refreshing a worksheet regenerates `candidates:` and `apply_keys:` against
    the current ingestion.  It must not touch what the SME decided:  running a
    regenerate over a filled-in worksheet would otherwise destroy the only part
    of it that took human judgement.
    """

    if not path.exists():
        return {}, {}

    loaded = yaml.safe_load(path.read_text()) or {}
    answers = {}

    for entry in loaded.get("designators") or []:
        keep = {
            key: entry.get(key)
            for key in ("documents", "unresolved", "notes", PROVISIONAL)
            if entry.get(key) not in (None, "", UNFILLED)
        }

        if keep:
            answers[entry["designator"]] = keep

    header = {
        "validated_by": loaded.get("validated_by"),
        "validated_on": loaded.get("validated_on"),
        "substrate": loaded.get("validated_against_substrate")
        or loaded.get("substrate"),
        "rules": loaded.get("validated_against_rules") or loaded.get("rules"),
        "generated": loaded.get("generated"),
    }

    return answers, header


def _answer_lines(kept: dict) -> list[str]:
    """Re-emit a preserved answer, indented to sit under its designator."""

    out = []

    for key in ("documents", PROVISIONAL, "unresolved", "notes"):
        if key not in kept:
            continue

        value = kept[key]

        if (
            key == "documents"
            and isinstance(value, list)
            and all(isinstance(item, dict) for item in value)
        ):
            out.append(f"  {key}:")

            for item in value:
                out += _document_lines(item, indent="  ")
        elif isinstance(value, list):
            out.append(f"  {key}:")
            dumped = yaml.safe_dump(
                value, sort_keys=False, default_flow_style=False
            )
            out += ["  " + line for line in dumped.rstrip("\n").split("\n")]
        else:
            out.append(f"  {key}: {_quote(str(value))}")

    return out


def substrate_digest(corpus) -> str:
    """A short digest of the substrate a corpus was ingested with.

    Recorded on a worksheet so that "validated against which build" is
    checkable rather than inferred from a document count.  A count can stay
    identical across a re-ingest that changed the embedder or the chunk size,
    and that changes what every document *is* without changing how many there
    are.
    """

    if not corpus.substrate:
        return "unknown"

    payload = json.dumps(corpus.substrate, sort_keys=True)

    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def render(
    *,
    question_set: str,
    database: str,
    corpus_documents: int,
    substrate: str,
    generated: str,
    cases: list[dict],
    corpus: manifest_mod.Corpus,
    previous: dict | None = None,
    validated: dict | None = None,
    provisional: bool = False,
    rules: rules_mod.Rules = rules_mod.BUILTIN_RULES,
) -> str:
    """The worksheet text for one question set.

    With ``provisional``, a designator that has no answer yet gets a
    `provisional_answer` where one can be made.  Answers already present --
    including earlier provisional ones -- are always kept as they are.

    ``rules`` decide how designators group and which documents are
    candidates;  the worksheet records their digest.
    """
    cited = references(cases, rules)
    counts = collections.Counter(
        designators.designator(text, rules) for text in cited
    )
    by_reference = {
        text: designators.designator(text, rules) for text in set(cited)
    }
    ordered = sorted(
        counts,
        key=lambda name: (
            designators.collapsed_key(name, rules),
            name.casefold(),
            name,
        ),
    )

    groups: dict[str, list[str]] = collections.OrderedDict()
    for name in ordered:
        groups.setdefault(designators.collapsed_key(name, rules), []).append(
            name
        )

    found_by_key = {
        key: find_candidates(
            key,
            {designators.series(name, rules) for name in names},
            corpus,
            rules,
        )
        for key, names in groups.items()
    }
    linked = cross_references(found_by_key, corpus)

    out = [
        *_HEADER.format(database=database).splitlines(),
        "version: 1",
        f"question_set: {question_set}",
        f"database: {database}",
        f"generated: {generated}",
        f"corpus_documents: {corpus_documents}"
        "   # at generation; a mismatch means recheck",
        f"substrate: {substrate}"
        "   # embedder/chunking digest of the ingestion",
        f"rules: {rules.digest}"
        f"   # normalization v{rules_mod.NORMALIZATION_VERSION}, "
        f"{rules.provenance}",
        *_validation_lines(validated, substrate, rules.digest),
        "",
        "designators:",
    ]

    seen = None
    for name in ordered:
        key = designators.collapsed_key(name, rules)

        if key != seen:
            out += ["", f"  # {key}"]

            if linked.get(key):
                cited = "; ".join(
                    ", ".join(groups[other]) for other in linked[key]
                )
                out.append(f"  # also cited as: {cited}")

            seen = key

        out += [
            f"- designator: {_quote(name)}",
            f"  questions: {counts[name]}",
        ]
        kept = (previous or {}).get(name)

        if not kept and provisional:
            kept = provisional_answer(found_by_key[key], corpus)

        if kept:
            out += _answer_lines(kept)
        else:
            out += _UNFILLED_LINES

    out += [
        "",
        *_CANDIDATES_LEGEND.format(database=database).splitlines(),
        "candidates:",
    ]

    by_uri = {doc.uri: doc for doc in corpus.documents}

    def entries(uris, relations: dict | None = None) -> list[str]:
        lines = []

        for uri in uris:
            doc = by_uri[uri]
            notes = []

            if doc.document_identifier:
                notes.append(doc.identifier_evidence)

            if relations and uri in relations:
                notes.append(relations[uri])

            flags = _flags(uri, rules)

            if notes:
                flags = (flags + "; " if flags else "   # ") + "; ".join(notes)

            lines += _document_lines(
                {
                    "name": doc.name,
                    "sha256": doc.sha256,
                    "source_url": doc.source_url,
                    "attachment": doc.attachment,
                    "document_identifier": doc.document_identifier,
                },
                indent="    ",
                flags=flags,
                order=(
                    "document_identifier",
                    "name",
                    "sha256",
                    "source_url",
                    "attachment",
                ),
            )

        return lines

    for key, names in groups.items():
        found = found_by_key[key]

        out += ["", f"  # {', '.join(names)}", f"  {_quote(key)}:"]

        out.append(
            "    identifier:" + (" []" if not found.get("identifier") else "")
        )
        out += entries(found.get("identifier") or [])

        if found.get("identifier_related"):
            out.append("    identifier_related:")
            out += entries(
                found["identifier_related"], found["identifier_related"]
            )

        out.append(
            "    matched:" + (" []" if not found.get("matched") else "")
        )
        out += entries(found.get("matched") or [])

        if found.get("related"):
            suffix = (
                f"   # truncated to {MAX_ADVISORY}"
                if found.get("truncated")
                else ""
            )
            out.append("    related:" + suffix)
            out += entries(found["related"])

        if found.get("same_series"):
            out.append("    same_series:")
            out += entries(found["same_series"])

    out += [
        "",
        *_APPLY_KEYS_LEGEND.splitlines(),
        "apply_keys:",
    ]
    out += [
        f"  {_quote(text)}: {_quote(by_reference[text])}"
        for text in sorted(by_reference, key=lambda s: (s.casefold(), s))
    ]

    return "\n".join(out) + "\n"


def refresh(
    *,
    root: pathlib.Path,
    corpora: list,
    ingestion: str | None,
    generated: str,
    provisional: bool = False,
    rules: rules_mod.Rules = rules_mod.BUILTIN_RULES,
) -> list[tuple[str, int, int, int, bool]]:
    """Regenerate the machine-written parts of every existing worksheet.

    Only worksheets that already exist are touched:  their existence is what
    declares that a question set is scored against this corpus.  Use
    ``create`` to add a new pairing.

    The SME's answers are carried across;  `candidates:` and `apply_keys:` are
    rebuilt against the named ingestion.  Returns, per worksheet, the counts of
    designators, answers kept, and answers dropped -- a drop means a designator
    that no longer appears in the question set, which is worth reporting rather
    than doing quietly.

    With ``provisional``, designators still unanswered get a
    `provisional_answer` where a trusted identifier match allows one.  A
    worksheet generated under other ``rules`` is regenerated, since its
    recorded digest no longer matches.
    """

    done = []

    for corpus_dir in corpora:
        manifest_path = corpus_dir.ingestion(ingestion)
        corpus = manifest_mod.load(manifest_path)

        for path in corpus_dir.worksheets():
            previous, validated = preserved_answers(path)
            question_set = corpus_mod.find_question_set(root, path.stem)
            cases = question_set.dataset.cases

            rendered = functools.partial(
                render,
                question_set=question_set.relative,
                database=corpus.database,
                corpus_documents=len(corpus.documents),
                substrate=substrate_digest(corpus),
                cases=cases,
                corpus=corpus,
                previous=previous,
                validated=validated,
                provisional=provisional,
                rules=rules,
            )

            # `generated:` records when the content was last actually
            # regenerated, not when the command last ran.  Rendering first with
            # the date already in the file makes a no-op refresh compare equal,
            # so it writes nothing -- otherwise every run produces a diff and
            # "did anything change?" stops being answerable by looking.
            before = validated.get("generated")
            text = rendered(generated=before or generated)

            if text == path.read_text():
                done.append(
                    (
                        str(path.relative_to(root)),
                        text.count("- designator:"),
                        0,
                        0,
                        False,
                    )
                )
                continue

            text = rendered(generated=generated)
            path.write_text(text)
            names = {
                designators.designator(text_, rules)
                for text_ in references(cases, rules)
            }
            kept = sum(1 for name in previous if name in names)
            done.append(
                (
                    str(path.relative_to(root)),
                    text.count("- designator:"),
                    kept,
                    len(previous) - kept,
                    True,
                )
            )

    return done


def create(
    *,
    root: pathlib.Path,
    corpus_dir,
    question_set,
    ingestion: str | None,
    generated: str,
    provisional: bool = False,
    rules: rules_mod.Rules = rules_mod.BUILTIN_RULES,
) -> pathlib.Path:
    """Declare that ``question_set`` is scored against ``corpus_dir``.

    Writing the worksheet *is* the declaration:  nothing derives which sets a
    corpus should be scored against, so it is recorded where the work will
    happen rather than in a separate list that could drift from it.
    """

    path = corpus_dir.worksheet_for(question_set)

    if path.exists():
        raise WorksheetExists(path)

    corpus = manifest_mod.load(corpus_dir.ingestion(ingestion))
    cases = question_set.dataset.cases

    if not references(cases, rules):
        raise NoReferences(question_set.name)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render(
            question_set=question_set.relative,
            database=corpus.database,
            corpus_documents=len(corpus.documents),
            substrate=substrate_digest(corpus),
            generated=generated,
            cases=cases,
            corpus=corpus,
            provisional=provisional,
            rules=rules,
        )
    )

    return path
