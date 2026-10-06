"""Finding question sets, corpora, and the worksheets that pair them.

Question sets are canonical and live once, at the top level:

    questions/<corpus_name>.{yaml,json}
    questions/<corpus_name>_pruned.{yaml,json}

A corpus holds what varies per corpus -- the manifests of its ingestions, and
one worksheet per question set it is scored against:

    corpus/<corpus_name>/
      ingestion/<corpus_name>.csv     documents in one ingestion
      ingestion/<corpus_name>.yaml    what that ingestion is
      worksheet/<corpus_name>.yaml

A question set therefore belongs to no corpus.  Two soliplex rooms can run
byte-identical prompts over different databases -- a full corpus and a curated
subset of it, say -- so that the corpus is the only variable.  The same
question set is then the natural test set for both, and pinning it inside one
corpus directory would force a false choice.

**A worksheet's existence is what declares the pairing.**  Nothing derives that
a question set is relevant to a corpus; someone decided it, so it is
recorded by creating the worksheet (`add-worksheet`) rather than in a list that
could drift from the worksheets beside it.  Refreshing thereafter operates on
whatever worksheets exist.

The tie in the other direction is the worksheet's own ``question_set:`` field,
which names the set it maps.  Matching filenames are a convenience for someone
reading the directory, not the linkage.
"""

import dataclasses
import json
import pathlib
import typing

import yaml
from pydantic_evals import dataset as pe_dataset

PRUNED_SUFFIX = "_pruned"

QUESTION_SET_SUFFIXES = [
    ".yaml",
    ".yml",
    ".json",
]

QuestionDataset = pe_dataset.Dataset[str, str, dict[str, typing.Any]]
QuestionCase = pe_dataset.Case[str, str, dict[str, typing.Any]]


class InvalidQuestionSet(ValueError):
    """Questions that are missing metadata, or can't be told apart.

    Every problem in the set is reported at once, so fixing them doesn't take
    one run per problem.  A copied question, for one, keeps its original's
    ``metadata.uuid``, and anything keyed by it then silently conflates the
    two:  `check-retrieval` scores both against one of their searches.

    A question is named by its ``name``;  one without a name, by its position
    in the file (``#3``), which is not its ``question_number``.
    """

    def __init__(self, qs_path: pathlib.Path, problems: list[str]):
        self.qs_path = qs_path
        self.problems = problems
        listed = "".join(f"\n  {problem}" for problem in problems)
        super().__init__(f"{qs_path}: {len(problems)} problem(s){listed}")


#: Metadata that identifies one question, so must not repeat within a set.
UNIQUE_METADATA = ("uuid", "question_number")


def _label(index: int, case: dict) -> str:
    return case.get("name") or f"#{index}"


def _value(value: typing.Any) -> str:
    """A value for comparison:  surrounding whitespace doesn't count."""
    return str(value or "").strip()


def question_set_problems(cases: list) -> list[str]:
    """What's wrong with ``cases``, as read from a question set's file.

    Every question needs metadata, and no two may share a ``name`` or a
    `UNIQUE_METADATA` value.  Missing or empty values are optional, so never
    repeat anything.  Entries that aren't mappings are left for pydantic-evals
    to refuse.
    """
    problems = []
    groups: dict[str, dict[str, list[tuple[int, dict]]]] = {
        field: {} for field in ("name", *UNIQUE_METADATA)
    }

    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            continue

        metadata = case.get("metadata")

        if not metadata:
            problems.append(f"no metadata: {_label(index, case)}")

        values = {"name": _value(case.get("name"))}

        if isinstance(metadata, dict):
            for field in UNIQUE_METADATA:
                values[field] = _value(metadata.get(field))

        for field, value in values.items():
            if value:
                groups[field].setdefault(value, []).append((index, case))

    for field, found in groups.items():
        for value, questions in found.items():
            if len(questions) < 2:
                continue

            if field == "name":
                listed = ", ".join(f"#{index}" for index, _ in questions)
                problems.append(f"duplicate name {value!r}: {listed}")
            else:
                listed = ", ".join(_label(*question) for question in questions)
                problems.append(
                    f"duplicate metadata.{field} {value!r}: {listed}"
                )

    return problems


def _read_cases(path: pathlib.Path) -> list:
    """The raw ``cases`` of a question set's file, or ``[]`` if malformed.

    A malformed file is left for pydantic-evals to refuse, with its own
    message.
    """
    text = path.read_text()
    data = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    cases = data.get("cases") if isinstance(data, dict) else None

    return cases if isinstance(cases, list) else []


class UnknownQuestionSet(FileNotFoundError):
    """No question set has the requested name."""

    def __init__(self, name: str, known: str):
        self.name = name
        self.known = known
        super().__init__(f"no question set {name!r}; have {known}")


class UnknownCorpus(FileNotFoundError):
    """No corpus directory has the requested name."""

    def __init__(self, name: str, known: str):
        self.name = name
        self.known = known
        super().__init__(f"no corpus {name!r}; have {known}")


class NoIngestion(FileNotFoundError):
    """A corpus directory holds no ingestion manifest."""

    def __init__(self, corpus_name: str):
        self.corpus_name = corpus_name
        super().__init__(f"{corpus_name}: no ingestion manifest")


class UnknownIngestion(FileNotFoundError):
    """A corpus has no ingestion manifest of the requested name."""

    def __init__(self, corpus_name: str, name: str, known: list[str]):
        self.corpus_name = corpus_name
        self.name = name
        self.known = known
        super().__init__(
            f"{corpus_name}: no ingestion {name!r}; have " + ", ".join(known)
        )


class AmbiguousIngestion(ValueError):
    """Several ingestions, and none named:  picking one would be a guess."""

    def __init__(self, corpus_name: str, known: list[str]):
        self.corpus_name = corpus_name
        self.known = known
        super().__init__(
            f"{corpus_name}: {len(known)} ingestions -- name one of "
            + ", ".join(known)
        )


@dataclasses.dataclass(frozen=True)
class QuestionSet:
    path: pathlib.Path
    root: pathlib.Path

    @property
    def name(self) -> str:
        return self.path.stem

    @property
    def is_pruned(self) -> bool:
        """Derived from another set by filtering.

        Shares `metadata.uuid` values with its parent, so its labels come from
        the parent's worksheet by join rather than from its own review.
        """
        return self.name.endswith(PRUNED_SUFFIX)

    @property
    def relative(self) -> str:
        return str(self.path.relative_to(self.root))

    @property
    def dataset(self) -> QuestionDataset:
        """The set's questions, refusing any `question_set_problems`.

        The file is checked as read, before pydantic-evals loads it:
        pydantic-evals refuses duplicate names itself, but stops at the first.
        """
        problems = question_set_problems(_read_cases(self.path))

        if problems:
            raise InvalidQuestionSet(self.path, problems)

        return QuestionDataset.from_file(self.path)


def question_sets(
    root: pathlib.Path, *, include_pruned: bool = False
) -> list[QuestionSet]:
    found = []

    for suffix in QUESTION_SET_SUFFIXES:
        for path in sorted((root / "questions").glob(f"*{suffix}")):
            found.append(QuestionSet(path, root))

    return [item for item in found if include_pruned or not item.is_pruned]


def find_question_set(root: pathlib.Path, name: str) -> QuestionSet:
    """Locate a set by stem, with or without the suffix."""
    stem = name

    for suffix in QUESTION_SET_SUFFIXES:
        if name.endswith(suffix):
            stem = name[: -len(suffix)]

    for item in question_sets(root, include_pruned=True):
        if item.name == stem:
            return item

    known = ", ".join(item.name for item in question_sets(root))

    raise UnknownQuestionSet(stem, known)


@dataclasses.dataclass(frozen=True)
class CorpusDir:
    path: pathlib.Path
    root: pathlib.Path

    @property
    def name(self) -> str:
        return self.path.name

    def worksheets(self) -> list[pathlib.Path]:
        return sorted((self.path / "worksheet").glob("*.yaml"))

    def worksheet_for(self, question_set: QuestionSet) -> pathlib.Path:
        return self.path / "worksheet" / f"{question_set.name}.yaml"

    def ingestions(self) -> list[pathlib.Path]:
        return sorted((self.path / "ingestion").glob("*.csv"))

    def ingestion(self, name: str | None = None) -> pathlib.Path:
        """The manifest to work against.

        With several present an explicit name is required:  silently picking
        one would bind labels to an ingestion nobody chose.
        """
        found = self.ingestions()

        if name is not None:
            wanted = self.path / "ingestion" / f"{name}.csv"

            if not wanted.exists():
                raise UnknownIngestion(
                    self.name, name, [path.stem for path in found]
                )

            return wanted

        if not found:
            raise NoIngestion(self.name)

        if len(found) > 1:
            raise AmbiguousIngestion(self.name, [path.stem for path in found])

        return found[0]


def discover(root: pathlib.Path) -> list[CorpusDir]:
    base = root / "corpus"

    return [
        CorpusDir(path, root)
        for path in sorted(base.iterdir())
        if path.is_dir()
    ]


def find(root: pathlib.Path, name: str) -> CorpusDir:
    path = root / "corpus" / name

    if not path.is_dir():
        known = ", ".join(item.name for item in discover(root))

        raise UnknownCorpus(name, known)

    return CorpusDir(path, root)
