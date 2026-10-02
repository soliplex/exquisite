"""The IETF HTTP RFC example corpus (`data/ietf-http-rfcs`), end to end.

RFCs are never revised in place:  each edition gets a new number, and
editions split and merge.  This corpus exercises what that does to labelling,
and these tests pin what `exquisite` makes of it.
"""

import json
import pathlib
import shutil

import pytest

from exquisite import bind
from exquisite import corpus as corpus_mod
from exquisite import designators
from exquisite import manifest
from exquisite import rules as rules_mod
from exquisite import worksheets

DATA = pathlib.Path(__file__).parents[2] / "data" / "ietf-http-rfcs"
INGESTIONS = DATA / "corpus" / "http" / "ingestion"


@pytest.fixture
def rules():
    return rules_mod.Rules.load(DATA / rules_mod.FILENAME)


@pytest.mark.parametrize(
    "stem, count",
    [("http-2015", 8), ("http-2022", 7)],
)
def test_manifests_load_with_trusted_identifiers(stem, count):
    loaded = manifest.load(INGESTIONS / f"{stem}.csv")

    assert len(loaded.documents) == count
    assert all(doc.trusted_identifier for doc in loaded.documents)
    assert all(
        doc.source_url.startswith(
            (
                "https://www.rfc-editor.org/rfc/",
                "https://www.ietf.org/archive/id/",
            )
        )
        for doc in loaded.documents
    )


@pytest.mark.parametrize(
    "reference, key",
    [
        ("RFC 9110, Section 9.2.1", "rfc9110"),
        ("RFC9110 Section 15.5.5", "rfc9110"),
        # STD numbers are aliases for the RFCs that hold them.
        ("STD 97, Section 9.2.2", "rfc9110"),
        ("STD 98, Section 5.2", "rfc9111"),
        ("STD 99, Section 9.3", "rfc9112"),
        # Successors share no key with what they obsolete.
        ("RFC 7231, Section 4.2.1", "rfc7231"),
        (
            "draft-ietf-httpbis-semantics-19, Section 9.2.1",
            "draftietfhttpbissemantics19",
        ),
        (
            "draft-ietf-httpbis-semantics, Section 9.2.2",
            "draftietfhttpbissemantics",
        ),
    ],
)
def test_citations_collapse_under_the_rules(rules, reference, key):
    result = designators.collapsed_key(
        designators.designator(reference, rules), rules
    )

    assert result == key


@pytest.mark.parametrize(
    "key, identifier, expected",
    [
        (
            "draftietfhttpbissemantics",
            "draft-ietf-httpbis-semantics-19",
            "draft revision",
        ),
        # No string relates an RFC to its successor:  that needs lineage.
        ("rfc7231", "RFC 9110", None),
        ("rfc911", "RFC 9110", None),
    ],
)
def test_relations(rules, key, identifier, expected):
    result = worksheets.relation(key, identifier, rules)

    assert result == expected


def test_the_worksheet_is_current(rules, tmp_path):
    root = tmp_path / "ietf-http-rfcs"
    shutil.copytree(DATA, root)

    done = worksheets.refresh(
        root=root,
        corpora=[corpus_mod.find(root, "http")],
        ingestion="http-2022",
        generated="2099-01-01",
        rules=rules,
    )

    assert done == [
        ("corpus/http/worksheet/http-pitfalls.yaml", 19, 0, 0, False)
    ]


def _unbound(*pairs):
    """`bind`'s report for each ``(designator, filename)`` it cannot bind."""
    return {
        f"{designator!r}: {filename} -- not in this ingestion"
        for designator, filename in pairs
    }


OBSOLETED = _unbound(
    ("RFC 2068", "rfc2068.txt"),
    ("RFC 2616", "rfc2616.txt"),
    ("RFC 2818", "rfc2818.txt"),
    ("RFC 7230", "rfc7230.txt"),
    ("RFC 7231", "rfc7231.txt"),
    ("RFC 7234", "rfc7234.txt"),
    ("RFC 7540", "rfc7540.txt"),
)

NOT_YET = _unbound(
    ("RFC 9110", "rfc9110.txt"),
    ("RFC 9111", "rfc9111.txt"),
    ("RFC 9112", "rfc9112.txt"),
    ("RFC 9113", "rfc9113.txt"),
    ("RFC 9114", "rfc9114.txt"),
    ("RFC9110", "rfc9110.txt"),
    ("STD 97", "rfc9110.txt"),
    ("STD 98", "rfc9111.txt"),
    ("STD 99", "rfc9112.txt"),
    ("draft-ietf-httpbis-semantics", "draft-ietf-httpbis-semantics-19.txt"),
    ("draft-ietf-httpbis-semantics-19", "draft-ietf-httpbis-semantics-19.txt"),
)


@pytest.mark.parametrize(
    "stem, labelled, unbound",
    [
        # Today's ingestion cannot label citations of obsoleted RFCs.
        ("http-2022", 14, OBSOLETED),
        # The older one cannot label citations of RFCs not yet published.
        ("http-2015", 11, NOT_YET),
    ],
)
def test_binding_labels_what_each_ingestion_holds(
    rules, stem, labelled, unbound
):
    corpus_dir = corpus_mod.find(DATA, "http")

    document, tally = bind.bind_file(
        corpus_dir=corpus_dir,
        question_set=corpus_mod.find_question_set(DATA, "http-pitfalls"),
        root=DATA,
        corpus=manifest.load(corpus_dir.ingestion(stem)),
        rules=rules,
    )

    labels = [
        case["metadata"].get(bind.LABEL_KEY) for case in document["cases"]
    ]
    assert tally["labelled"] == labelled
    assert set(tally["unbound"]) == unbound
    assert sum(1 for label in labels if label) == labelled


def test_every_question_cites_a_designator_the_worksheet_answers(rules):
    cases = json.loads(
        (DATA / "questions" / "http-pitfalls.json").read_text()
    )["cases"]
    sheet = DATA / "corpus" / "http" / "worksheet" / "http-pitfalls.yaml"

    answers, _ = worksheets.preserved_answers(sheet)

    cited = {
        designators.designator(case["metadata"]["reference"], rules)
        for case in cases
    }
    assert cited == set(answers)
    assert all(answer.get("documents") for answer in answers.values())
