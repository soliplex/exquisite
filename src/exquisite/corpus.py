"""Finding question sets, corpora, and the worksheets that pair them.

Question sets are canonical and live once, at the top level:

    questions/<corpus_name>.json
    questions/<corpus_name>_pruned.json

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

from dataclasses import dataclass
from pathlib import Path

PRUNED_SUFFIX = "_pruned"


@dataclass(frozen=True)
class QuestionSet:
    path: Path
    root: Path

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


def question_sets(root: Path, *, include_pruned: bool = False) -> list[QuestionSet]:
    found = [
        QuestionSet(path, root) for path in sorted((root / "questions").glob("*.json"))
    ]

    return [item for item in found if include_pruned or not item.is_pruned]


def find_question_set(root: Path, name: str) -> QuestionSet:
    """Locate a set by stem, with or without the ``.json``."""
    stem = name[:-5] if name.endswith(".json") else name

    for item in question_sets(root, include_pruned=True):
        if item.name == stem:
            return item

    known = ", ".join(item.name for item in question_sets(root))

    raise FileNotFoundError(f"no question set {stem!r}; have {known}")


@dataclass(frozen=True)
class CorpusDir:
    path: Path
    root: Path

    @property
    def name(self) -> str:
        return self.path.name

    def worksheets(self) -> list[Path]:
        return sorted((self.path / "worksheet").glob("*.yaml"))

    def worksheet_for(self, question_set: QuestionSet) -> Path:
        return self.path / "worksheet" / f"{question_set.name}.yaml"

    def ingestions(self) -> list[Path]:
        return sorted((self.path / "ingestion").glob("*.csv"))

    def ingestion(self, name: str | None = None) -> Path:
        """The manifest to work against.

        With several present an explicit name is required:  silently picking
        one would bind labels to an ingestion nobody chose.
        """
        found = self.ingestions()

        if name is not None:
            wanted = self.path / "ingestion" / f"{name}.csv"

            if not wanted.exists():
                raise FileNotFoundError(
                    f"{self.name}: no ingestion {name!r}; have "
                    + ", ".join(path.stem for path in found)
                )

            return wanted

        if not found:
            raise FileNotFoundError(f"{self.name}: no ingestion manifest")

        if len(found) > 1:
            raise ValueError(
                f"{self.name}: {len(found)} ingestions -- name one of "
                + ", ".join(path.stem for path in found)
            )

        return found[0]


def discover(root: Path) -> list[CorpusDir]:
    base = root / "corpus"

    return [CorpusDir(path, root) for path in sorted(base.iterdir()) if path.is_dir()]


def find(root: Path, name: str) -> CorpusDir:
    path = root / "corpus" / name

    if not path.is_dir():
        known = ", ".join(item.name for item in discover(root))

        raise FileNotFoundError(f"no corpus {name!r}; have {known}")

    return CorpusDir(path, root)
