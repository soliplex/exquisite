"""The NIST SP 800 example corpus (`data/nist-sp-800`), end to end.

The corpus exists to exercise the pitfalls real corpora present: spelling
variants of one publication, citations of superseded editions or of no
edition, companions, supplements, volumes, parts, and drafts.  These tests
pin what `exquisite` makes of it, so a change to the corpus or to
normalization that alters any of it is deliberate.
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

DATA = pathlib.Path(__file__).parents[2] / "data" / "nist-sp-800"
INGESTIONS = DATA / "corpus" / "sp800" / "ingestion"


@pytest.fixture
def rules():
    return rules_mod.Rules.load(DATA / rules_mod.FILENAME)


@pytest.mark.parametrize(
    "stem, count",
    [("sp800-2020", 10), ("sp800-2026", 13)],
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


def test_the_worksheet_is_current(rules, tmp_path):
    root = tmp_path / "nist-sp-800"
    shutil.copytree(DATA, root)

    done = worksheets.refresh(
        root=root,
        corpora=[corpus_mod.find(root, "sp800")],
        ingestion="sp800-2026",
        generated="2099-01-01",
        rules=rules,
    )

    assert done == [
        ("corpus/sp800/worksheet/sp800-pitfalls.yaml", 25, 0, 0, False)
    ]


def _unbound(*pairs):
    """`bind`'s report for each ``(designator, filename)`` it cannot bind."""
    return {
        f"{designator!r}: {filename} -- not in this ingestion"
        for designator, filename in pairs
    }


SUPERSEDED = _unbound(
    ("NIST SP 800-171 Rev. 2", "NIST.SP.800-171r2.pdf"),
    ("NIST SP 800-53", "NIST.SP.800-53r4.pdf"),
    ("NIST SP 800-61 Rev. 2", "NIST.SP.800-61r2.pdf"),
    ("NIST SP 800-61r2", "NIST.SP.800-61r2.pdf"),
    ("NIST SP 800-63B Supplement 1", "NIST.SP.800-63Bsup1.pdf"),
    ("NIST SP 800-63B", "NIST.SP.800-63b.pdf"),
    ("NIST SP 800-63Bsup1", "NIST.SP.800-63Bsup1.pdf"),
    ("NIST Special Publication 800-53 Revision 4", "NIST.SP.800-53r4.pdf"),
)

NOT_YET = _unbound(
    ("NIST SP 800-171A Rev. 3", "NIST.SP.800-171Ar3.pdf"),
    ("NIST SP 800-171r3", "NIST.SP.800-171r3.pdf"),
    ("NIST SP 800-53 Rev. 5", "NIST.SP.800-53r5.pdf"),
    ("NIST SP 800-53", "NIST.SP.800-53r5.pdf"),
    ("NIST SP 800-53A Rev. 5", "NIST.SP.800-53Ar5.pdf"),
    (
        "NIST SP 800-57 Rev. 6 (Initial Public Draft)",
        "NIST.SP.800-57pt1r6.ipd.pdf",
    ),
    ("NIST SP 800-61", "NIST.SP.800-61r3.pdf"),
    ("NIST SP 800-61r3", "NIST.SP.800-61r3.pdf"),
    ("NIST SP 800-63-4", "NIST.SP.800-63-4.pdf"),
    ("NIST SP 800-63B-4", "NIST.SP.800-63b-4.pdf"),
    ("NIST Special Publication 800-63B Revision 4", "NIST.SP.800-63b-4.pdf"),
)


@pytest.mark.parametrize(
    "stem, labelled, unbound",
    [
        # Today's ingestion cannot label citations of superseded editions.
        ("sp800-2026", 18, SUPERSEDED),
        # The older one cannot label citations of editions not yet issued.
        ("sp800-2020", 15, NOT_YET),
    ],
)
def test_binding_labels_what_each_ingestion_holds(
    rules, stem, labelled, unbound
):
    corpus_dir = corpus_mod.find(DATA, "sp800")

    document, tally = bind.bind_file(
        corpus_dir=corpus_dir,
        question_set=corpus_mod.find_question_set(DATA, "sp800-pitfalls"),
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
        (DATA / "questions" / "sp800-pitfalls.json").read_text()
    )["cases"]
    sheet = DATA / "corpus" / "sp800" / "worksheet" / "sp800-pitfalls.yaml"

    answers, _ = worksheets.preserved_answers(sheet)

    cited = {
        designators.designator(case["metadata"]["reference"], rules)
        for case in cases
    }
    assert cited == set(answers)
    assert all(answer.get("documents") for answer in answers.values())
