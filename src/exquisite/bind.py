"""Binding a populated worksheet to one ingestion of its corpus.

Resolution is exact string lookup, in two steps and with no normalization:

    designator = worksheet["apply_keys"][case["metadata"]["reference"]]
    documents  = worksheet["designators"][designator]["documents"]
    uris       = [resolve(corpus, d)[0][0].uri for d in documents]

That is the whole reason worksheets carry every verbatim ``reference`` string.
If this had to re-derive designators it would need to reproduce
``exquisite.designators`` exactly, and any drift would leave cases quietly
unlabelled -- which reads as "nobody labelled this", not as a bug.

Three outcomes per case, and the difference between the last two matters:

- **labelled** -- ``metadata.relevant_uris`` written.
- **unresolved** -- the designator was reviewed and no document matched, so no
  key is written.  The case is *ineligible* and scores nothing, which is the
  intended, harmless outcome.
- **unfilled** -- the designator was never reviewed.  This is an error, not an
  outcome; applying a half-filled worksheet would look identical to one where
  the SME decided those documents do not exist.

A *provisional* answer -- made by the generator from a trusted identifier
match, and marked with a ``provisional:`` line -- counts as unreviewed too.
Confirming it is deleting that line.
"""

import json
import pathlib

import yaml

from exquisite import corpus as corpus_mod
from exquisite import manifest
from exquisite import rules as rules_mod
from exquisite import worksheets

#: Written alongside the existing prose `reference`, never replacing it.
LABEL_KEY = "relevant_uris"

#: Suffix marking a question set derived from another by filtering.
PRUNED_SUFFIX = "_pruned"


class WorksheetError(Exception):
    """The worksheet cannot be applied as it stands."""


class NoWorksheet(WorksheetError):
    """No worksheet pairs the question set with the corpus."""

    def __init__(self, corpus_name: str, question_set: str):
        self.corpus_name = corpus_name
        self.question_set = question_set
        super().__init__(
            f"{corpus_name} has no worksheet for {question_set!r}; "
            "create one with `add-worksheet`"
        )


class NoParentWorksheet(WorksheetError):
    """A pruned set's parent has no worksheet to label it from."""

    def __init__(self, corpus_name: str, parent: str, question_set: str):
        self.corpus_name = corpus_name
        self.parent = parent
        self.question_set = question_set
        super().__init__(
            f"{corpus_name} has no worksheet for {parent!r}, which is "
            f"what would label {question_set!r}"
        )


def _entries(worksheet: dict) -> dict[str, dict]:
    return {entry["designator"]: entry for entry in worksheet["designators"]}


def check(worksheet: dict) -> list[str]:
    """Everything that would stop this worksheet being applied."""
    problems = []
    entries = _entries(worksheet)

    for designator, entry in sorted(entries.items()):
        documents = entry.get("documents")

        if documents == worksheets.UNFILLED or documents is None:
            problems.append(f"{designator!r}: documents not filled in")
        elif entry.get(worksheets.PROVISIONAL):
            problems.append(
                f"{designator!r}: provisional answer not yet confirmed -- "
                f"check it, then delete its `{worksheets.PROVISIONAL}:` line"
            )
        elif isinstance(documents, str):
            problems.append(
                f"{designator!r}: documents must be a list, got a string"
            )
        elif not documents and not (entry.get("unresolved") or "").strip():
            problems.append(
                f"{designator!r}: empty documents needs "
                "`unresolved` to say why"
            )
        else:
            for item in documents:
                if not isinstance(item, dict):
                    problems.append(
                        f"{designator!r}: each document must be a mapping"
                    )
                elif not (item.get("sha256") or item.get("source_url")):
                    problems.append(
                        f"{designator!r}: "
                        f"{item.get('name', '?')!r} has neither "
                        "sha256 nor source_url, so it cannot be bound"
                    )

    for reference, designator in sorted(worksheet["apply_keys"].items()):
        if designator not in entries:
            problems.append(
                f"apply_key {reference!r} names unknown designator "
                f"{designator!r}"
            )

    return problems


def bind(
    worksheet: dict,
    cases: list[dict],
    *,
    corpus: manifest.Corpus,
    rules: rules_mod.Rules = rules_mod.BUILTIN_RULES,
) -> tuple[list[dict], dict]:
    """Return ``(cases, tally)`` with ``relevant_uris`` written where resolved.

    Each worksheet document is resolved against ``corpus`` by sha256, falling
    back to source_url, and the *current* ingestion's URI is written.  That is
    why binding happens before an eval run rather than being stored:  a
    set's labels go stale when its corpus moves, and unchecked they would score
    every case zero and read as total retrieval failure.

    A document whose hash misses but whose source_url hits is reported as
    ``changed`` -- the file at that location is not the one the SME approved.

    A case whose reference is one of the ``rules``' placeholders counts as
    having none, matching the worksheet, which gave it no apply key.
    """
    keys = worksheet["apply_keys"]
    tally = {
        "labelled": 0,
        "unresolved": 0,
        "no_reference": 0,
        "unknown_reference": [],
        "unbound": [],
        "changed": [],
    }

    bound: dict[str, list[str]] = {}

    for entry in worksheet["designators"]:
        uris = []

        for item in entry.get("documents") or []:
            documents, how = manifest.resolve(corpus, item)

            if not documents:
                tally["unbound"].append(
                    f"{entry['designator']!r}: "
                    f"{item.get('name', '?')} -- {how}"
                )
                continue

            if how == "changed":
                tally["changed"].append(
                    f"{entry['designator']!r}: {item.get('name', '?')}"
                )

            uris.extend(doc.uri for doc in documents)

        bound[entry["designator"]] = uris

    for case in cases:
        metadata = case.setdefault("metadata", {})
        reference = (metadata.get("reference") or "").strip()

        if reference in rules.not_references:
            tally["no_reference"] += 1
            continue

        designator = keys.get(metadata["reference"])

        if designator is None:
            tally["unknown_reference"].append(metadata["reference"])
            continue

        uris = bound.get(designator) or []

        if not uris:
            metadata.pop(LABEL_KEY, None)
            tally["unresolved"] += 1
            continue

        metadata[LABEL_KEY] = list(uris)
        tally["labelled"] += 1

    tally["unbound"] = sorted(set(tally["unbound"]))
    tally["changed"] = sorted(set(tally["changed"]))

    return cases, tally


def worksheet_for(corpus_dir, question_set):
    """The worksheet whose answers label ``question_set``.

    A pruned set has none of its own:  it is a strict `metadata.uuid` subset of
    its parent, so it is labelled from the parent's worksheet by join.  That is
    not merely convenient:  pruning may have blanked a set's references (moving
    them aside under another key), leaving nothing to bind it by directly.
    """
    own = corpus_dir.worksheet_for(question_set)

    if own.exists():
        return own, None

    if not question_set.is_pruned:
        raise NoWorksheet(corpus_dir.name, question_set.name)

    parent = corpus_mod.find_question_set(
        question_set.root, question_set.name[: -len(PRUNED_SUFFIX)]
    )
    path = corpus_dir.worksheet_for(parent)

    if not path.exists():
        raise NoParentWorksheet(
            corpus_dir.name, parent.name, question_set.name
        )

    return path, parent


def bind_file(
    *,
    corpus_dir,
    question_set,
    root: pathlib.Path,
    corpus: manifest.Corpus,
    rules: rules_mod.Rules = rules_mod.BUILTIN_RULES,
) -> tuple[dict, dict]:
    """Bind one question set to one ingestion:  ``(document, tally)``.

    Nothing is written here.  The canonical question set holds no
    corpus-specific data by design -- the same set is scored against more than
    one corpus, so a binding is one of several possible readings of it rather
    than a property of it -- and a binding goes stale as soon as its ingestion
    is replaced.  So it is produced when wanted and handed to the caller.
    """

    worksheet_path, parent = worksheet_for(corpus_dir, question_set)
    worksheet = yaml.safe_load(worksheet_path.read_text())
    problems = check(worksheet)

    if problems:
        raise WorksheetError(
            f"{worksheet_path.name} is not ready to bind:\n  "
            + "\n  ".join(problems)
        )

    document = json.loads(question_set.path.read_text())

    if parent is None:
        _, tally = bind(
            worksheet, document["cases"], corpus=corpus, rules=rules
        )
    else:
        source = json.loads(parent.path.read_text())
        _, tally = bind(worksheet, source["cases"], corpus=corpus, rules=rules)
        tally["carried"] = _carry_labels(source["cases"], document["cases"])
        tally["labelled"] = tally["carried"]

    tally["question_set"] = question_set.relative
    tally["worksheet"] = str(worksheet_path.relative_to(root))

    return document, tally


def _carry_labels(parent: list[dict], derived: list[dict]) -> int:
    """Copy parent cases' `relevant_uris` onto their derived counterparts."""
    labels = {
        (case.get("metadata") or {}).get("uuid"): (
            case.get("metadata") or {}
        ).get(LABEL_KEY)
        for case in parent
    }
    carried = 0

    for case in derived:
        metadata = case.setdefault("metadata", {})
        found = labels.get(metadata.get("uuid"))

        if found:
            metadata[LABEL_KEY] = list(found)
            carried += 1
        else:
            metadata.pop(LABEL_KEY, None)

    return carried
