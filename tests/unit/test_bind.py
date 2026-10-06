"""Unit tests for `exquisite.bind`."""

import _builders
import pytest

from exquisite import bind
from exquisite import corpus as corpus_mod
from exquisite import manifest
from exquisite import rules as rules_mod
from exquisite import worksheets

LABEL = bind.LABEL_KEY


def worksheet(**entry):
    return {
        "designators": [{"designator": "NIST SP 800-61", **entry}],
        "apply_keys": {"NIST SP 800-61": "NIST SP 800-61"},
    }


class TestCheck:
    def test_refuses_a_provisional_answer(self):
        sheet = worksheet(
            documents=[{"name": "sp800-61.pdf", "sha256": "h"}],
            **{
                worksheets.PROVISIONAL: (
                    "identifier match (llm certainty 5): NIST SP 800-61"
                )
            },
        )

        problems = bind.check(sheet)

        assert problems == [
            "'NIST SP 800-61': provisional answer not yet confirmed -- "
            f"check it, then delete its `{worksheets.PROVISIONAL}:` line"
        ]

    def test_accepts_it_once_the_line_is_deleted(self):
        sheet = worksheet(documents=[{"name": "sp800-61.pdf", "sha256": "h"}])

        problems = bind.check(sheet)

        assert problems == []

    @pytest.mark.parametrize(
        "entry, problem",
        [
            ({"documents": worksheets.UNFILLED}, "documents not filled in"),
            ({}, "documents not filled in"),
            ({"documents": "a.pdf"}, "documents must be a list, got a string"),
            (
                {"documents": []},
                "empty documents needs `unresolved` to say why",
            ),
            ({"documents": ["a.pdf"]}, "each document must be a mapping"),
            (
                {"documents": [{"name": "a.pdf"}]},
                "'a.pdf' has neither sha256 nor source_url, so it cannot be "
                "bound",
            ),
        ],
    )
    def test_reports_what_stops_an_entry_binding(self, entry, problem):
        sheet = worksheet(**entry)

        problems = bind.check(sheet)

        assert problems == [f"'NIST SP 800-61': {problem}"]

    def test_accepts_an_empty_answer_that_says_why(self):
        sheet = worksheet(documents=[], unresolved="withdrawn")

        problems = bind.check(sheet)

        assert problems == []

    def test_reports_an_apply_key_naming_no_designator(self):
        sheet = worksheet(documents=[{"name": "a.pdf", "sha256": "h"}])
        sheet["apply_keys"]["ISO 9001 Sec 4"] = "ISO 9001"

        problems = bind.check(sheet)

        assert problems == [
            "apply_key 'ISO 9001 Sec 4' names unknown designator 'ISO 9001'"
        ]


def _make_case(metadata):
    return corpus_mod.QuestionCase(
        inputs="Test Input",
        expected_output="Test Output",
        metadata=metadata,
    )


class TestBind:
    def test_labels_resolved_cases_and_tallies_the_rest(self):
        corpus = manifest.Corpus(
            database="std",
            documents=[
                manifest.Document(
                    uri="file:///new/a.pdf", sha256="h", source_url="u"
                )
            ],
        )
        sheet = {
            "designators": [
                {
                    "designator": "A",
                    "documents": [{"name": "a", "sha256": "h"}],
                },
                {
                    "designator": "B",
                    "documents": [
                        {"name": "b", "sha256": "old", "source_url": "u"}
                    ],
                },
                {
                    "designator": "C",
                    "documents": [{"name": "c", "sha256": "x"}],
                },
                {"designator": "D", "documents": [], "unresolved": "gone"},
            ],
            "apply_keys": {"A 1": "A", "B 1": "B", "C 1": "C", "D 1": "D"},
        }
        cases = [
            _make_case(metadata={"reference": "A 1"}),
            _make_case(metadata={"reference": "B 1"}),
            _make_case(metadata={"reference": "C 1", LABEL: ["stale"]}),
            _make_case(metadata={"reference": "D 1"}),
            _make_case(metadata={"reference": "[To Be Filled Out]"}),
            _make_case(metadata={"reference": "Z 1"}),
        ]

        cases, tally = bind.bind(sheet, cases, corpus=corpus)

        assert [case.metadata.get(LABEL) for case in cases] == [
            ["file:///new/a.pdf"],
            ["file:///new/a.pdf"],
            None,
            None,
            None,
            None,
        ]
        assert tally == {
            "labelled": 2,
            "unresolved": 2,
            "no_reference": 1,
            "unknown_reference": ["Z 1"],
            "unbound": ["'C': c -- not in this ingestion"],
            "changed": ["'B': b"],
        }


WORKSHEET = """\
designators:
- designator: "ISO 9001"
  documents:
  - name: "iso.pdf"
    sha256: "h"
apply_keys:
  "ISO 9001 Sec 4": "ISO 9001"
  "ISO 9001 Sec 5": "ISO 9001"
"""


@pytest.fixture
def std(data_root):
    """A corpus holding ISO 9001, and a question set citing it twice."""
    _builders.ingestion(
        data_root,
        "std",
        "std",
        [manifest.Document(uri="file:///iso.pdf", sha256="h")],
    )
    _builders.question_set(
        data_root, "set", ["ISO 9001 Sec 4", "ISO 9001 Sec 5"]
    )
    _builders.question_set(
        data_root, "set_pruned", [None, None], uuids=["uuid-1", "uuid-9"]
    )

    return corpus_mod.find(data_root, "std")


class TestWorksheetFor:
    def test_a_set_with_its_own_worksheet(self, data_root, std):
        own = _builders.worksheet(data_root, "std", "set", WORKSHEET)
        question_set = corpus_mod.find_question_set(data_root, "set")

        found = bind.worksheet_for(std, question_set)

        assert found == (own, None)

    def test_a_pruned_set_uses_its_parents(self, data_root, std):
        parent = _builders.worksheet(data_root, "std", "set", WORKSHEET)
        question_set = corpus_mod.find_question_set(data_root, "set_pruned")

        path, source = bind.worksheet_for(std, question_set)

        assert (path, source.name) == (parent, "set")

    @pytest.mark.parametrize(
        "name, error, message",
        [
            (
                "set",
                bind.NoWorksheet,
                "std has no worksheet for 'set'; create one with "
                "`add-worksheet`",
            ),
            (
                "set_pruned",
                bind.NoParentWorksheet,
                "std has no worksheet for 'set', which is what would label "
                "'set_pruned'",
            ),
        ],
    )
    def test_says_which_worksheet_is_missing(
        self, data_root, std, name, error, message
    ):
        question_set = corpus_mod.find_question_set(data_root, name)

        with pytest.raises(error) as raised:
            bind.worksheet_for(std, question_set)

        assert str(raised.value) == message


class TestBindFile:
    def bind_file(self, data_root, std, name):
        return bind.bind_file(
            corpus_dir=std,
            question_set=corpus_mod.find_question_set(data_root, name),
            root=data_root,
            corpus=manifest.load(std.ingestion()),
        )

    def test_labels_the_set_without_writing_anything(self, data_root, std):
        _builders.worksheet(data_root, "std", "set", WORKSHEET)
        before = (data_root / "questions" / "set.yaml").read_text()

        document, tally = self.bind_file(data_root, std, "set")

        labels = [case.metadata[LABEL] for case in document.cases]

        assert labels == [["file:///iso.pdf"], ["file:///iso.pdf"]]
        assert tally["labelled"] == 2
        assert tally["question_set"] == "questions/set.yaml"
        assert tally["worksheet"] == "corpus/std/worksheet/set.yaml"
        assert (data_root / "questions" / "set.yaml").read_text() == before

    def test_a_pruned_set_carries_its_parents_labels_by_uuid(
        self, data_root, std
    ):
        _builders.worksheet(data_root, "std", "set", WORKSHEET)

        document, tally = self.bind_file(data_root, std, "set_pruned")

        labels = [case.metadata.get(LABEL) for case in document.cases]

        assert labels == [["file:///iso.pdf"], None]
        assert (tally["carried"], tally["labelled"]) == (1, 1)

    def test_refuses_a_worksheet_that_is_not_ready(self, data_root, std):
        _builders.worksheet(
            data_root, "std", "set", WORKSHEET.replace('    sha256: "h"\n', "")
        )

        with pytest.raises(bind.WorksheetError) as raised:
            self.bind_file(data_root, std, "set")

        assert str(raised.value) == (
            "set.yaml is not ready to bind:\n"
            "  'ISO 9001': 'iso.pdf' has neither sha256 nor source_url, so it "
            "cannot be bound"
        )


@pytest.mark.parametrize(
    "rules, tally",
    [
        (
            rules_mod.BUILTIN_RULES,
            {"no_reference": 0, "unknown_reference": ["TBD"]},
        ),
        (
            rules_mod.Rules.from_mapping(
                {"references": {"placeholders": ["TBD"]}}
            ),
            {"no_reference": 1, "unknown_reference": []},
        ),
    ],
)
def test_bind_treats_caller_placeholders_as_no_reference(rules, tally):
    sheet = worksheet(documents=[{"name": "a.pdf", "sha256": "h"}])
    corpus = manifest.Corpus(database="std")

    cases = [_make_case({"reference": "TBD"})]

    _, found = bind.bind(sheet, cases, corpus=corpus, rules=rules)

    assert {key: found[key] for key in tally} == tally
