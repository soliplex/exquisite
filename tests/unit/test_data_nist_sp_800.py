"""The NIST SP 800 example corpus (`data/nist-sp`).

A curated subset of the SP 800 series, and the rules for how its
publications are cited:  spelling variants, revisions written several ways,
Roman-numeral volumes, and location words.  These tests pin the
corpus and what the rules make of those citations.
"""

import datetime
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


@pytest.mark.parametrize("stem", ["sp800"])
def test_manifests_load_with_trusted_identifiers(stem):
    loaded = manifest.load(INGESTIONS / f"{stem}.csv")

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
        # Roman-numeral volumes.
        ("NIST SP 800-60 Volume I Revision 1, Section 3.1.1", "sp80060v1r1"),
        ("NIST SP 800-60 Vol. II Rev. 1, Appendix C", "sp80060v2r1"),
        ("NIST SP 800-60 Vol. 1 Rev. 1", "sp80060v1r1"),
        # Location words the rules add.
        ("NIST SP 800-53 Rev. 4, Control AC-2", "sp80053r4"),
        ("NIST SP 800-60 Volume II Revision 1, Appendix C", "sp80060v2r1"),
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
        # A citation without its revision, as the worksheet shows it.
        ("sp80030", "NIST SP 800-30 Rev. 1", "revision"),
        ("sp80053", "NIST SP 800-53 Rev. 4", "revision"),
        # Another publication altogether.
        ("sp80030", "NIST SP 800-39", None),
    ],
)
def test_relations(rules, key, identifier, expected):
    result = worksheets.relation(key, identifier, rules)

    assert result == expected


@pytest.mark.parametrize("stem", ["sp800"])
def test_corpus_records_its_date(stem):
    loaded = manifest.load(INGESTIONS / f"{stem}.csv")

    assert type(loaded.about["as_of"]) is datetime.date


def test_every_question_cites_a_designator_the_worksheet_answers(rules):
    question_set = corpus_mod.find_question_set(DATA, "sp800")

    answers, _ = worksheets.preserved_answers(WORKSHEETS / "sp800.yaml")

    cited = {
        designators.designator(case.metadata["reference"], rules)
        for case in question_set.dataset.cases
    }
    assert cited == set(answers)
    assert all(answer.get("documents") for answer in answers.values())


def test_binding_labels_every_question_against_its_corpus(rules):
    corpus_dir = corpus_mod.find(DATA, "sp800")
    corpus = manifest.load(corpus_dir.ingestion("sp800"))

    document, tally = bind.bind_file(
        corpus_dir=corpus_dir,
        question_set=corpus_mod.find_question_set(DATA, "sp800"),
        root=DATA,
        corpus=corpus,
        rules=rules,
    )

    uris = {doc.uri for doc in corpus.documents}
    labels = [case.metadata.get(bind.LABEL_KEY) for case in document.cases]
    assert tally["labelled"] == len(document.cases)
    assert not tally["unbound"]
    assert all(label and set(label) <= uris for label in labels)
