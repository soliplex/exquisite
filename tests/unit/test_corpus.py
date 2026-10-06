"""Unit tests for `exquisite.corpus`."""

import json
import uuid

import _builders
import pytest
import yaml

from exquisite import corpus
from exquisite import manifest

QUESTION_NAME = "test-question"
QUESTION_INPUTS = "What is the airspeed velocity of an unladen sparrow?"
QUESTION_EXPECTED = "African or European?"
QUESTION_UUID = str(uuid.uuid4())
QUESTION_NUMBER = "123"
QUESTION_TYPE = "qa"
QUESTION_REF = "Ency. Brit. 1893 Vol Aa - An, 'African Swallow'"
QUESTION_SET = {
    "$schema": "https://schema.pydantic.dev/evals/dataset.json",
    "cases": [
        {
            "name": QUESTION_NAME,
            "inputs": QUESTION_INPUTS,
            "expected_output": QUESTION_EXPECTED,
            "metadata": {
                "uuid": QUESTION_UUID,
                "question_number": QUESTION_NUMBER,
                "type": QUESTION_TYPE,
                "reference": QUESTION_REF,
            },
        },
    ],
}
WO_METADATA_QUESTION_SET = {
    "$schema": "https://schema.pydantic.dev/evals/dataset.json",
    "cases": [
        {
            "name": QUESTION_NAME,
            "inputs": QUESTION_INPUTS,
            "expected_output": QUESTION_EXPECTED,
        },
    ],
}


@pytest.mark.parametrize(
    "stem, is_pruned",
    [
        ("iso-9001", False),
        ("iso-9001_pruned", True),
    ],
)
@pytest.mark.parametrize("suffix", [".yaml", ".json"])
def test_question_set_names_itself_and_knows_if_pruned(
    data_root,
    stem,
    is_pruned,
    suffix,
):
    path = data_root / "questions" / f"{stem}{suffix}"

    found = corpus.QuestionSet(path, data_root)

    assert found.name == stem
    assert found.is_pruned is is_pruned
    assert found.relative == f"questions/{stem}{suffix}"


@pytest.mark.parametrize(
    "filename, dumper",
    [
        ("test-questions.json", json.dumps),
        ("test-questions.yaml", yaml.dump),
    ],
)
def test_question_set_dataset_wo_metadata(
    tmp_path,
    filename,
    dumper,
):
    to_dump = dumper(WO_METADATA_QUESTION_SET)
    qset_file = tmp_path / filename
    qset_file.write_text(to_dump)

    qset = corpus.QuestionSet(root=tmp_path, path=qset_file)

    with pytest.raises(corpus.QuestionHasNoMetadata):
        _dset = qset.dataset


@pytest.mark.parametrize(
    "filename, dumper",
    [
        ("test-questions.json", json.dumps),
        ("test-questions.yaml", yaml.dump),
        ("test-questions.yml", yaml.dump),
    ],
)
def test_question_set_dataset(
    tmp_path,
    filename,
    dumper,
):
    to_dump = dumper(QUESTION_SET)
    qset_file = tmp_path / filename
    qset_file.write_text(to_dump)
    qset = corpus.QuestionSet(root=tmp_path, path=qset_file)

    dset = qset.dataset

    assert isinstance(dset, corpus.QuestionDataset)

    assert dset.name == "test-questions"

    (case,) = dset.cases
    assert case.name == QUESTION_NAME
    assert case.inputs == QUESTION_INPUTS
    assert case.expected_output == QUESTION_EXPECTED
    assert case.metadata["uuid"] == QUESTION_UUID
    assert case.metadata["question_number"] == QUESTION_NUMBER
    assert case.metadata["type"] == QUESTION_TYPE
    assert case.metadata["reference"] == QUESTION_REF


@pytest.mark.parametrize(
    "include_pruned, expected",
    [
        (False, ["a"]),
        (True, ["a", "a_pruned"]),
    ],
)
@pytest.mark.parametrize("suffix", [".yaml", ".yml"])
def test_question_sets_leave_out_pruned_ones_unless_asked(
    data_root,
    suffix,
    include_pruned,
    expected,
):
    _builders.question_set(data_root, "a", [], suffix=suffix)
    _builders.question_set(data_root, "a_pruned", [], suffix=suffix)

    found = corpus.question_sets(data_root, include_pruned=include_pruned)

    assert [item.name for item in found] == expected


@pytest.mark.parametrize(
    "name",
    [
        "a_pruned",
        "a_pruned.yaml",
        "a_pruned.yml",
        "a_pruned.json",
    ],
)
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
