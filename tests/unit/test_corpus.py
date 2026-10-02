"""Unit tests for `exquisite.corpus`."""

import _builders
import pytest

from exquisite import corpus
from exquisite import manifest


@pytest.mark.parametrize(
    "stem, is_pruned",
    [
        ("iso-9001", False),
        ("iso-9001_pruned", True),
    ],
)
def test_question_set_names_itself_and_knows_if_pruned(
    data_root, stem, is_pruned
):
    path = data_root / "questions" / f"{stem}.json"

    found = corpus.QuestionSet(path, data_root)

    assert found.name == stem
    assert found.is_pruned is is_pruned
    assert found.relative == f"questions/{stem}.json"


@pytest.mark.parametrize(
    "include_pruned, expected",
    [
        (False, ["a"]),
        (True, ["a", "a_pruned"]),
    ],
)
def test_question_sets_leave_out_pruned_ones_unless_asked(
    data_root, include_pruned, expected
):
    _builders.question_set(data_root, "a", [])
    _builders.question_set(data_root, "a_pruned", [])

    found = corpus.question_sets(data_root, include_pruned=include_pruned)

    assert [item.name for item in found] == expected


@pytest.mark.parametrize("name", ["a_pruned", "a_pruned.json"])
def test_find_question_set_with_or_without_the_suffix(data_root, name):
    _builders.question_set(data_root, "a", [])
    _builders.question_set(data_root, "a_pruned", [])

    found = corpus.find_question_set(data_root, name)

    assert found.name == "a_pruned"


def test_find_question_set_names_the_sets_it_has(data_root):
    _builders.question_set(data_root, "a", [])
    _builders.question_set(data_root, "a_pruned", [])

    with pytest.raises(corpus.UnknownQuestionSet) as raised:
        corpus.find_question_set(data_root, "b")

    assert raised.value.name == "b"
    assert raised.value.known == "a"
    assert isinstance(raised.value, FileNotFoundError)


def test_corpus_dir_lists_its_worksheets_and_ingestions(data_root):
    _builders.worksheet(data_root, "std", "b", "")
    _builders.worksheet(data_root, "std", "a", "")
    _builders.ingestion(data_root, "std", "std-v2", [])
    _builders.ingestion(data_root, "std", "std-v1", [])
    corpus_dir = corpus.CorpusDir(data_root / "corpus" / "std", data_root)
    question_set = corpus.QuestionSet(
        data_root / "questions/a.json", data_root
    )

    worksheets = corpus_dir.worksheets()

    assert corpus_dir.name == "std"
    assert [path.stem for path in worksheets] == ["a", "b"]
    assert corpus_dir.worksheet_for(question_set) == worksheets[0]
    assert [path.stem for path in corpus_dir.ingestions()] == [
        "std-v1",
        "std-v2",
    ]


@pytest.mark.parametrize(
    "stems, name, expected",
    [
        (["std-v1"], None, "std-v1"),
        (["std-v1", "std-v2"], "std-v2", "std-v2"),
    ],
)
def test_ingestion_picks_the_only_one_or_the_named_one(
    data_root, stems, name, expected
):
    for stem in stems:
        _builders.ingestion(
            data_root, "std", stem, [manifest.Document(uri="u")]
        )
    corpus_dir = corpus.find(data_root, "std")

    found = corpus_dir.ingestion(name)

    assert found.stem == expected


@pytest.mark.parametrize(
    "stems, name, error, message",
    [
        (
            ["std-v1"],
            "std-v9",
            corpus.UnknownIngestion,
            "std: no ingestion 'std-v9'; have std-v1",
        ),
        ([], None, corpus.NoIngestion, "std: no ingestion manifest"),
        (
            ["std-v1", "std-v2"],
            None,
            corpus.AmbiguousIngestion,
            "std: 2 ingestions -- name one of std-v1, std-v2",
        ),
    ],
)
def test_ingestion_refuses_to_guess(data_root, stems, name, error, message):
    (data_root / "corpus" / "std").mkdir()
    for stem in stems:
        _builders.ingestion(data_root, "std", stem, [])
    corpus_dir = corpus.find(data_root, "std")

    with pytest.raises(error) as raised:
        corpus_dir.ingestion(name)

    assert str(raised.value) == message


def test_discover_finds_corpus_directories_only(data_root):
    (data_root / "corpus" / "b").mkdir()
    (data_root / "corpus" / "a").mkdir()
    (data_root / "corpus" / "README.md").write_text("")

    found = corpus.discover(data_root)

    assert [item.name for item in found] == ["a", "b"]


def test_find_names_the_corpora_it_has(data_root):
    (data_root / "corpus" / "a").mkdir()

    with pytest.raises(corpus.UnknownCorpus) as raised:
        corpus.find(data_root, "b")

    assert str(raised.value) == "no corpus 'b'; have a"
    assert (raised.value.name, raised.value.known) == ("b", "a")
