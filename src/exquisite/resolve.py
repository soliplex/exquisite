"""Resolving a question set whose references are already document URIs.

Some sets cite their sources this way.  Their references name a file outright
-- ``file:///downloads/<corpus_name>/<doc_id>.pdf`` -- so there is nothing for
an SME to decide:  the author already picked the document.  What is needed is a
*translation* into the durable form a worksheet records, so the label survives
the corpus being re-ingested under different paths.

That is not the "never auto-assign" case.  Inferring a document from
``NIST SP 800-53 Rev. 5`` is a guess, and a wrong guess makes correct retrieval
read as failure.  Re-expressing a URI the author wrote as that same file's
sha256 is neither.  A human still signs the worksheet; they just do not have to
re-make decisions that were already made.

Resolution is tried in two steps, and the difference is recorded:

- **exact** -- the reference is a document URI in this ingestion.
- **moved** -- it is not, but exactly one document has that filename.  The
  corpus was re-ingested under a different source root, which otherwise loses
  every reference silently.

Anything ambiguous or absent is left unresolved with the reason, because those
are the cases that genuinely need a person.
"""

import json
import os
import pathlib
import urllib.parse

import yaml

from exquisite import corpus as corpus_mod
from exquisite import rules as rules_mod
from exquisite import worksheets


def _basename(uri: str) -> str:
    head = uri.split("#attachment=", 1)

    return os.path.basename(
        urllib.parse.unquote(head[-1] if len(head) > 1 else head[0])
    )


def resolve_worksheet(worksheet: dict, corpus) -> tuple[dict, dict]:
    """Answers for every designator whose reference resolves, plus a tally."""
    by_uri = {doc.uri: doc for doc in corpus.documents}
    by_name: dict[str, list] = {}

    for doc in corpus.documents:
        by_name.setdefault(_basename(doc.uri), []).append(doc)

    references: dict[str, set[str]] = {}

    for reference, name in (worksheet.get("apply_keys") or {}).items():
        references.setdefault(name, set()).add(reference)

    answers: dict[str, dict] = {}
    tally = {"exact": 0, "moved": 0, "unresolved": []}

    for entry in worksheet.get("designators") or []:
        name = entry["designator"]
        uris = [text for text in references.get(name, ()) if "://" in text]

        if not uris:
            continue

        found = [by_uri[uri] for uri in uris if uri in by_uri]
        how = "exact"

        if not found:
            candidates = [by_name.get(_basename(uri)) or [] for uri in uris]
            unique = [group[0] for group in candidates if len(group) == 1]

            if len(unique) == len(uris) and unique:
                found, how = unique, "moved"
            else:
                empty = sum(1 for group in candidates if not group)
                tally["unresolved"].append(
                    f"{name}: "
                    + (
                        "no document with that filename"
                        if empty
                        else "several documents share that filename"
                    )
                )
                continue

        note = (
            "resolved from the reference URI"
            if how == "exact"
            else "resolved by filename; the corpus moved and the reference "
            "path is stale"
        )
        answers[name] = {
            "documents": [doc.durable() for doc in found],
            "notes": note,
        }
        tally[how] += 1

    return answers, tally


def resolve_file(
    *,
    worksheet_path: pathlib.Path,
    root,
    corpus,
    generated: str,
    rules: rules_mod.Rules = rules_mod.BUILTIN_RULES,
) -> dict:
    """Fill in a URI-referenced worksheet, leaving the attestation blank."""

    loaded = yaml.safe_load(worksheet_path.read_text())
    answers, tally = resolve_worksheet(loaded, corpus)

    if not answers and not tally["unresolved"]:
        tally["skipped"] = (
            "references are not URIs; use the worksheet interview"
        )

        return tally

    previous, validated = worksheets.preserved_answers(worksheet_path)
    previous.update(answers)
    question_set = corpus_mod.find_question_set(root, worksheet_path.stem)
    cases = json.loads(question_set.path.read_text())["cases"]

    worksheet_path.write_text(
        worksheets.render(
            question_set=question_set.relative,
            database=corpus.database,
            corpus_documents=len(corpus.documents),
            substrate=worksheets.substrate_digest(corpus),
            generated=generated,
            cases=cases,
            corpus=corpus,
            previous=previous,
            validated=validated,
            rules=rules,
        )
    )

    return tally
