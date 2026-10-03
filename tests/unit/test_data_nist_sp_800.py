"""The NIST SP 800 example corpus (`data/nist-sp-800`).

Two snapshots of a subset of the SP 800 series, and the rules for how NIST
publications are cited:  spelling variants, revisions written several ways,
companions, supplements, Roman-numeral volumes, parts, and drafts.  These
tests pin the snapshots and what the rules make of those citations.
"""

import json
import pathlib

import pytest

from exquisite import bind
from exquisite import corpus as corpus_mod
from exquisite import designators
from exquisite import manifest
from exquisite import rules as rules_mod
from exquisite import worksheets

DATA = pathlib.Path(__file__).parents[2] / "data" / "nist-sp-800"
INGESTIONS = DATA / "corpus" / "sp800" / "ingestion"
WORKSHEETS = DATA / "corpus" / "sp800" / "worksheet"


@pytest.fixture
def rules():
    return rules_mod.Rules.load(DATA / rules_mod.FILENAME)


@pytest.mark.parametrize(
    "stem, count",
    [("sp800-2020", 8), ("sp800-2026", 13)],
)
def test_manifests_load_with_trusted_identifiers(stem, count):
    loaded = manifest.load(INGESTIONS / f"{stem}.csv")

    assert len(loaded.documents) == count
    assert all(doc.trusted_identifier for doc in loaded.documents)
    assert all(
        doc.source_url.startswith("https://nvlpubs.nist.gov/nistpubs/")
        for doc in loaded.documents
    )


@pytest.mark.parametrize(
    "reference, key",
    [
        # One publication, three spellings.
        ("NIST SP 800-30 Rev. 1, Chapter 3", "sp80030r1"),
        ("NIST Special Publication 800-30 Revision 1 Sec 2.1", "sp80030r1"),
        ("SP 800-30r1 Chapter 3", "sp80030r1"),
        # SP 800-63's suffix revision, and the same spelled out.
        ("NIST SP 800-63B-4 Sec 3.1.1.2", "sp80063br4"),
        (
            "NIST Special Publication 800-63B Revision 4, Section 3.1.1.2",
            "sp80063br4",
        ),
        # A sibling, not a revision.
        ("NIST SP 800-63-4 Sec 1.2", "sp80063r4"),
        # A supplement, two ways.
        ("NIST SP 800-63Bsup1 Sec 3", "sp80063bsupp1"),
        ("NIST SP 800-63B Supplement 1, Section 3", "sp80063bsupp1"),
        # Roman-numeral volumes.
        ("NIST SP 800-60 Volume I Revision 1, Section 3.1.1", "sp80060v1r1"),
        ("NIST SP 800-60 Vol. II Rev. 1, Appendix C", "sp80060v2r1"),
        ("NIST SP 800-60 Vol. 1 Rev. 1", "sp80060v1r1"),
        # A location word the rules add.
        ("NIST SP 800-53 Control AC-2", "sp80053"),
        # A draft cited without its part does not collapse with its document.
        (
            "NIST SP 800-57 Rev. 6 (Initial Public Draft), Note to Reviewers",
            "sp80057r6ipd",
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
        ("sp80053", "NIST SP 800-53 Rev. 5", "revision"),
        ("sp80053", "NIST SP 800-53A Rev. 5", "companion"),
        ("sp80053", "NIST SP 800-53B", "companion"),
        ("sp80063b", "NIST SP 800-63B-4", "revision"),
        (
            "sp80057pt1",
            "NIST SP 800-57 Part 1 Rev. 6 (Initial Public Draft)",
            "draft revision",
        ),
        ("sp80063b", "NIST SP 800-63-4", None),
    ],
)
def test_relations(rules, key, identifier, expected):
    result = worksheets.relation(key, identifier, rules)

    assert result == expected


@pytest.mark.parametrize(
    "stem, as_of",
    [("sp800-2020", "2020-06-30"), ("sp800-2026", "2026-10-02")],
)
def test_each_snapshot_records_its_date(stem, as_of):
    loaded = manifest.load(INGESTIONS / f"{stem}.csv")

    assert str(loaded.about["as_of"]) == as_of


def test_every_question_cites_a_designator_the_worksheet_answers(rules):
    cases = json.loads((DATA / "questions" / "sp800-2020.json").read_text())[
        "cases"
    ]

    answers, _ = worksheets.preserved_answers(WORKSHEETS / "sp800-2020.yaml")

    cited = {
        designators.designator(case["metadata"]["reference"], rules)
        for case in cases
    }
    assert cited == set(answers)
    assert all(answer.get("documents") for answer in answers.values())


def test_binding_labels_every_question_against_its_snapshot(rules):
    corpus_dir = corpus_mod.find(DATA, "sp800")
    snapshot = manifest.load(corpus_dir.ingestion("sp800-2020"))

    document, tally = bind.bind_file(
        corpus_dir=corpus_dir,
        question_set=corpus_mod.find_question_set(DATA, "sp800-2020"),
        root=DATA,
        corpus=snapshot,
        rules=rules,
    )

    uris = {doc.uri for doc in snapshot.documents}
    labels = [
        case["metadata"].get(bind.LABEL_KEY) for case in document["cases"]
    ]
    assert tally["labelled"] == len(document["cases"]) == 20
    assert not tally["unbound"]
    assert all(label and set(label) <= uris for label in labels)
