"""Unit tests for `exquisite.resolve`."""

import _builders
import pytest
import yaml

from exquisite import corpus as corpus_mod
from exquisite import manifest
from exquisite import resolve
from exquisite import rules as rules_mod
from exquisite import worksheets

REFERENCE = "file:///downloads/std/iso-9001.pdf"


def uri_worksheet(*references):
    """A worksheet whose designators are the references' filenames."""
    keys = {text: text.rsplit("/", 1)[-1] for text in references}

    return {
        "designators": [{"designator": name} for name in set(keys.values())],
        "apply_keys": keys,
    }


def make_corpus(*uris):
    return manifest.Corpus(
        database="std",
        documents=[
            manifest.Document(uri=uri, sha256=f"sha-{uri}") for uri in uris
        ],
    )


@pytest.mark.parametrize(
    "uri, expected",
    [
        ("file:///downloads/std/iso%209001.pdf", "iso 9001.pdf"),
        (
            "file:///downloads/std/iec.pdf#attachment=Annex%20A.pdf",
            "Annex A.pdf",
        ),
    ],
)
def test_basename_decodes_and_prefers_the_attachment(uri, expected):
    result = resolve._basename(uri)

    assert result == expected


@pytest.mark.parametrize(
    "uris, how, note",
    [
        ([REFERENCE], "exact", "resolved from the reference URI"),
        (
            ["file:///elsewhere/iso-9001.pdf"],
            "moved",
            "resolved by filename; the corpus moved and the reference path "
            "is stale",
        ),
    ],
)
def test_resolves_by_uri_then_by_unique_filename(uris, how, note):
    corpus = make_corpus(*uris)

    answers, tally = resolve.resolve_worksheet(
        uri_worksheet(REFERENCE), corpus
    )

    assert answers == {
        "iso-9001.pdf": {
            "documents": [corpus.documents[0].durable()],
            "notes": note,
        }
    }
    assert tally[how] == 1
    assert tally["unresolved"] == []


@pytest.mark.parametrize(
    "uris, reason",
    [
        (["file:///elsewhere/other.pdf"], "no document with that filename"),
        (
            ["file:///a/iso-9001.pdf", "file:///b/iso-9001.pdf"],
            "several documents share that filename",
        ),
    ],
)
def test_leaves_absent_or_ambiguous_references_for_a_person(uris, reason):
    corpus = make_corpus(*uris)

    answers, tally = resolve.resolve_worksheet(
        uri_worksheet(REFERENCE), corpus
    )

    assert answers == {}
    assert tally == {
        "exact": 0,
        "moved": 0,
        "unresolved": [f"iso-9001.pdf: {reason}"],
    }


@pytest.mark.parametrize(
    "worksheet",
    [
        {
            "designators": [{"designator": "ISO 9001"}],
            "apply_keys": {"ISO 9001 Sec 4": "ISO 9001"},
        },
        {},
    ],
)
def test_prose_references_are_not_its_business(worksheet):
    answers, tally = resolve.resolve_worksheet(worksheet, make_corpus())

    assert answers == {}
    assert tally == {"exact": 0, "moved": 0, "unresolved": []}


def write_worksheet(root, references, documents):
    qpath = _builders.question_set(root, "uris", references)
    qset = corpus_mod.QuestionSet(root=root, path=qpath)
    cases = qset.dataset.cases

    path = _builders.ingestion(root, "std", "std", documents)
    corpus = manifest.Corpus(database="std", documents=documents)
    text = worksheets.render(
        question_set="questions/uris.yaml",
        database="std",
        corpus_documents=len(documents),
        substrate="unknown",
        generated="2026-10-01",
        cases=cases,
        corpus=corpus,
    )

    return _builders.worksheet(root, "std", "uris", text), path, corpus


def test_resolve_file_fills_in_and_rewrites_the_worksheet(data_root):
    document = manifest.Document(uri=REFERENCE, sha256="h")
    path, _, corpus = write_worksheet(data_root, [REFERENCE], [document])

    tally = resolve.resolve_file(
        worksheet_path=path,
        root=data_root,
        corpus=corpus,
        generated="2026-10-02",
    )

    entry = yaml.safe_load(path.read_text())["designators"][0]
    assert tally == {"exact": 1, "moved": 0, "unresolved": []}
    assert entry["documents"] == [
        {"name": "iso-9001.pdf", "sha256": "h", "source_url": None}
    ]
    assert entry["notes"] == "resolved from the reference URI"


def test_resolve_file_skips_a_prose_referenced_worksheet(data_root):
    document = manifest.Document(uri=REFERENCE, sha256="h")
    path, _, corpus = write_worksheet(data_root, ["ISO 9001"], [document])
    before = path.read_text()

    tally = resolve.resolve_file(
        worksheet_path=path,
        root=data_root,
        corpus=corpus,
        generated="2026-10-02",
    )

    assert tally["skipped"] == (
        "references are not URIs; use the worksheet interview"
    )
    assert path.read_text() == before


def test_resolve_file_records_the_rules_it_rendered_under(data_root):
    rules = rules_mod.Rules.from_mapping(
        {"references": {"placeholders": ["TBD"]}}
    )
    document = manifest.Document(uri=REFERENCE, sha256="h")
    path, _, corpus = write_worksheet(data_root, [REFERENCE], [document])

    resolve.resolve_file(
        worksheet_path=path,
        root=data_root,
        corpus=corpus,
        generated="2026-10-02",
        rules=rules,
    )

    assert f"rules: {rules.digest}" in path.read_text()
