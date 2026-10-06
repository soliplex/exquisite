"""Checking a RAG database's retrieval against a bound question set.

Where an evaluation asks an agent and judges its answer, this only searches:
one search per question, returning the top K results, scored by the
reciprocal rank of the first relevant document (`RETRIEVAL_MRR`).  No
answering model and no judge, so a run is fast and its scores are stable from
run to run -- which is what checking a freshly ingested database needs.  (Only
stable, not bit-identical:  the embedder and reranker can reorder near-tied
results.)

A question's relevant documents are the ones `bind` labels it with:  every
document its citation names in the ingestion's manifest -- byte-identical
copies at several paths, say.  The answer can be in any one of them, so
retrieving any one is a *hit*;  retrieving none is a *miss*.

Search results are matched to the manifest by the durable identity `bind`
uses:  the ``sha256``, then the ``source_url``, that the database records for
each document, and only failing both by URI.  So a database whose documents
sit at different paths from the manifest's -- a corpus moved, or a manifest
with synthetic URIs -- is still checked, where comparing URIs alone would
read as every question missing.

The checks depend on the reference run, if any:

- Without one, a question fails when it misses.
- Against a prior run (``--compare``), a question fails when it *loses*:  the
  reference hit and this run does not.  The rest is reported, never failed:
  a change of rank (the embedder and reranker can reorder near-tied results
  between two runs on the same database), a relevant document dropping out
  while another still hits, and the mean `RETRIEVAL_MRR` falling by more than
  a tolerance.  A question the reference does not have is checked for a miss
  instead.

Any saved run can be a reference:  a failing one is saved too, so someone
who has read its report can adopt it as the next reference.

A reference taken with a different embedder, reranker or top K is refused:
against it, most questions would differ for reasons that have nothing to do
with the database.  So is one whose question under a case's key differs from
the question set's.  Different versions of the substrate only warn.

Cases without relevant documents -- unresolved, or citing nothing -- are
*ineligible*:  skipped, and counted.

Nothing here touches haiku-rag;  `exquisite.search` does the searching.
"""

import dataclasses
import json
import pathlib

from exquisite import bind as bind_mod
from exquisite import corpus as corpus_mod
from exquisite import manifest

#: The score:  the reciprocal rank of the first relevant document, which fits
#: "any one is a hit" -- average precision would divide by every copy.
RETRIEVAL_MRR = "retrieval_mrr"

#: What a results file says it is, so a file of some other shape is refused.
FORMAT = "exquisite check-retrieval 1"

#: How many results each search returns.  Deliberately more than a room's
#: search limit:  a newly ingested document that is relevant to a question
#: can push a labelled one out of a short list although nothing is broken.
DEFAULT_TOP_K = 30

#: How far the mean `RETRIEVAL_MRR` may fall below the reference's before the
#: report says so.  It scales with the question set:  one question's document
#: slipping from first to second moves the mean by 0.5 / N.
DEFAULT_MRR_TOLERANCE = 0.02

#: Slack for comparing two averages of the same ranks computed on different
#: runs;  a real drop is at least one rank's worth.
TOLERANCE = 1e-9

#: How many of a miss's results `details` names.
SHOWN_ON_MISS = 3

#: Settings that, differing, make a reference incomparable.
COMPARED_SETTINGS = (
    ("embedder", "configured embedder"),
    # No reranker is a setting too.
    ("reranker", "reranker"),
    ("top_k", "top K"),
)


class NotAResultsFile(ValueError):
    """A ``--compare`` file that is not a `check-retrieval` results file."""

    def __init__(self, path: pathlib.Path):
        self.path = path
        super().__init__(
            f"{path} is not a check-retrieval results file "
            f"(no `format: {FORMAT}`)"
        )


class IncomparableReference(ValueError):
    """A reference run that this one cannot meaningfully be compared with."""


class SettingsDiffer(IncomparableReference):
    """The reference searched differently, by design."""

    def __init__(self, reference: str, problems: list[str]):
        self.reference = reference
        self.problems = problems
        super().__init__(
            f"cannot compare against {reference}:  " + ";  ".join(problems)
        )


class QuestionsDiffer(IncomparableReference):
    """The reference asked a different question under some case's key."""

    def __init__(self, reference: str, keys: list[str]):
        self.reference = reference
        self.keys = keys
        shown = ", ".join(keys[:5])
        more = f" and {len(keys) - 5} more" if len(keys) > 5 else ""
        super().__init__(
            f"cannot compare against {reference}:  {len(keys)} question(s) "
            f"differ under the same key ({shown}{more});  the question set "
            "changed since the reference was taken, so save a new reference"
        )


@dataclasses.dataclass(frozen=True)
class Hit:
    """One search result:  the URI the database stores its document under,
    and that document's metadata."""

    uri: str
    metadata: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class Question:
    """A question to search, and the documents that answer it."""

    key: str
    question: str
    relevant: tuple[str, ...] = ()


@dataclasses.dataclass
class CaseResult:
    """One question's search, and how it scored."""

    key: str
    question: str
    #: The manifest URIs `bind` labelled the question with.
    relevant: list[str] = dataclasses.field(default_factory=list)
    #: One per distinct document, in rank order:  its manifest URI where the
    #: manifest holds it, else the database's own.
    retrieved: list[str] = dataclasses.field(default_factory=list)
    #: `RETRIEVAL_MRR`;  None for an ineligible question, not zero.
    score: float | None = None

    @property
    def eligible(self) -> bool:
        return self.score is not None

    @property
    def found(self) -> list[str]:
        """The relevant documents the search retrieved."""
        retrieved = set(self.retrieved)

        return [uri for uri in self.relevant if uri in retrieved]

    @property
    def rank(self) -> int | None:
        """Where the first relevant document came;  None for a miss, or an
        ineligible question."""
        relevant = set(self.relevant)

        for rank, uri in enumerate(self.retrieved, start=1):
            if uri in relevant:
                return rank

        return None


@dataclasses.dataclass
class Run:
    """A whole check:  what was searched, how, and what came back."""

    question_set: str
    corpus: str
    #: The manifest's database name:  the ingestion the labels were bound to.
    ingestion: str
    #: Embedder, reranker, top K and a hash of the haiku-rag configuration.
    settings: dict = dataclasses.field(default_factory=dict)
    #: What the database held:  the embedder it was stored with, its size,
    #: and when it was last written.
    database: dict = dataclasses.field(default_factory=dict)
    #: Versions of the packages that decide what the run measured.
    substrate: dict = dataclasses.field(default_factory=dict)
    started: str = ""
    finished: str = ""
    cases: list[CaseResult] = dataclasses.field(default_factory=list)

    @property
    def eligible(self) -> list[CaseResult]:
        return [case for case in self.cases if case.eligible]

    def mean(self) -> float | None:
        return mean([case.score for case in self.eligible])

    def to_json(self) -> dict:
        return {"format": FORMAT, **dataclasses.asdict(self)}

    @classmethod
    def from_json(cls, data: dict) -> "Run":
        fields = {key: value for key, value in data.items() if key != "format"}
        fields["cases"] = [CaseResult(**case) for case in data["cases"]]

        return cls(**fields)


def save(run: Run, path: pathlib.Path) -> None:
    path.write_text(
        json.dumps(run.to_json(), indent=2, ensure_ascii=False) + "\n"
    )


def load(path: pathlib.Path) -> Run:
    data = json.loads(path.read_text())

    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise NotAResultsFile(path)

    return Run.from_json(data)


def case_key(case: corpus_mod.QuestionCase, index: int) -> str:
    """A case's identity across runs:  its ``metadata.uuid``, else its name,
    else its position -- which shifts when a question is added before it."""
    return case.metadata.get("uuid") or case.name or f"Case {index}"


def questions(cases: list[corpus_mod.QuestionCase]) -> list[Question]:
    """The bound question set's cases, as questions to search."""
    return [
        Question(
            key=case_key(case, index),
            question=str(case.inputs),
            relevant=tuple(case.metadata.get(bind_mod.LABEL_KEY) or ()),
        )
        for index, case in enumerate(cases, start=1)
    ]


def identify(hit: Hit, corpus: manifest.Corpus) -> str:
    """The manifest URI of the document a search hit came from.

    Resolved as `bind` resolves a worksheet's documents:  by ``sha256``, then
    ``source_url``.  Of byte-identical copies, the one at the hit's own URI
    is preferred.  A document the manifest does not hold keeps the
    database's URI, which then matches a label only if it is the same string.
    """
    found = manifest.from_metadata(hit.uri, hit.metadata)
    documents, _ = manifest.resolve(corpus, found.durable())
    uris = [doc.uri for doc in documents]

    if not uris or hit.uri in uris:
        return hit.uri

    return uris[0]


def ranked(hits: list[Hit], corpus: manifest.Corpus) -> list[str]:
    """The distinct documents of ``hits``, identified, in rank order."""
    uris: list[str] = []

    for hit in hits:
        uri = identify(hit, corpus)

        if uri not in uris:
            uris.append(uri)

    return uris


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    """1 / the rank of the first relevant document (0.0 when none is)."""
    for rank, uri in enumerate(retrieved, start=1):
        if uri in relevant:
            return 1.0 / rank

    return 0.0


def score(
    question: Question, hits: list[Hit], corpus: manifest.Corpus
) -> CaseResult:
    """One question's result:  what came back, and how it scored."""
    retrieved = ranked(hits, corpus)
    relevant = list(question.relevant)

    return CaseResult(
        key=question.key,
        question=question.question,
        relevant=relevant,
        retrieved=retrieved,
        score=(
            reciprocal_rank(retrieved, set(relevant)) if relevant else None
        ),
    )


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


@dataclasses.dataclass
class Miss:
    """A question whose results left out every relevant document."""

    key: str
    question: str
    missing: list[str]


@dataclasses.dataclass
class Loss:
    """A question the reference hit, and this run missed."""

    key: str
    question: str
    #: The relevant documents the reference found.
    lost: list[str]


@dataclasses.dataclass
class Dropout:
    """Relevant documents the reference retrieved and this run did not.

    Another relevant document still hits, so this is reported, not failed.
    """

    key: str
    question: str
    dropped: list[str]
    kept: list[str]


@dataclasses.dataclass
class Drop:
    """A question whose first relevant document now ranks lower than in the
    reference.  Reported, not failed:  rank order is not stable enough
    between runs."""

    key: str
    question: str
    reference: float
    current: float


@dataclasses.dataclass
class Outcome:
    run: Run
    misses: list[Miss] = dataclasses.field(default_factory=list)
    losses: list[Loss] = dataclasses.field(default_factory=list)
    #: The rest are reported, but not failures.
    dropouts: list[Dropout] = dataclasses.field(default_factory=list)
    drops: list[Drop] = dataclasses.field(default_factory=list)
    #: Eligible questions the reference has no score for.
    unreferenced: list[str] = dataclasses.field(default_factory=list)
    mrr_tolerance: float = DEFAULT_MRR_TOLERANCE
    #: Mean `RETRIEVAL_MRR` over the questions paired with the reference.
    reference_mean: float | None = None
    current_mean: float | None = None

    @property
    def n_eligible(self) -> int:
        return len(self.run.eligible)

    @property
    def n_failing(self) -> int:
        """Questions that fail the check."""
        return len(self.misses) + len(self.losses)

    @property
    def failed(self) -> bool:
        if self.n_eligible == 0:
            return True

        return self.n_failing > 0

    @property
    def mean_fell(self) -> bool:
        if self.reference_mean is None or self.current_mean is None:
            return False

        return self.current_mean < self.reference_mean - self.mrr_tolerance


def find_misses(cases: list[CaseResult]) -> list[Miss]:
    return [
        Miss(case.key, case.question, case.relevant)
        for case in cases
        if not case.found
    ]


def find_losses(
    cases: list[CaseResult], reference: dict[str, CaseResult]
) -> tuple[list[Loss], list[Dropout]]:
    """Questions that lost the reference's hit, and relevant documents that
    dropped out of one that still hits."""
    losses = []
    dropouts = []

    for case in cases:
        before = reference[case.key].found

        if not before:
            continue

        after = case.found

        if not after:
            losses.append(Loss(case.key, case.question, before))
            continue

        dropped = [uri for uri in before if uri not in after]

        if dropped:
            dropouts.append(Dropout(case.key, case.question, dropped, after))

    return losses, dropouts


def find_drops(
    cases: list[CaseResult], reference: dict[str, CaseResult]
) -> list[Drop]:
    drops = []

    for case in cases:
        before = reference[case.key].score

        if case.score < before - TOLERANCE:
            drops.append(Drop(case.key, case.question, before, case.score))

    return drops


def check(
    run: Run,
    reference: Run | None = None,
    mrr_tolerance: float = DEFAULT_MRR_TOLERANCE,
) -> Outcome:
    """Apply the checks to a completed run."""
    eligible = run.eligible

    if reference is None:
        return Outcome(
            run, misses=find_misses(eligible), mrr_tolerance=mrr_tolerance
        )

    scored = {case.key: case for case in reference.eligible}
    paired = [case for case in eligible if case.key in scored]
    unpaired = [case for case in eligible if case.key not in scored]
    losses, dropouts = find_losses(paired, scored)

    return Outcome(
        run,
        misses=find_misses(unpaired),
        losses=losses,
        dropouts=dropouts,
        drops=find_drops(paired, scored),
        unreferenced=[case.key for case in unpaired],
        mrr_tolerance=mrr_tolerance,
        reference_mean=mean([scored[case.key].score for case in paired]),
        current_mean=mean([case.score for case in paired]),
    )


def check_settings(
    run: Run, reference: Run, reference_name: str = "the reference"
) -> list[str]:
    """Refuse a reference whose searches differ from these by design.

    ``run`` need only carry its settings, database and substrate:  this is
    called before searching, so a bad reference fails before the work does.
    Returns the differences that only warrant a warning:  substrate versions,
    which a check across an upgrade is meant to span.
    """
    problems = []

    for field, what in COMPARED_SETTINGS:
        before = reference.settings.get(field)
        after = run.settings.get(field)

        if before != after:
            problems.append(f"the {what} differs ({before} vs. {after})")

    before = reference.database.get("embedder")
    after = run.database.get("embedder")

    if before and before != after:
        problems.append(
            "the database was stored with a different embedder "
            f"({before} vs. {after})"
        )

    if problems:
        raise SettingsDiffer(reference_name, problems)

    warnings = []

    for name in sorted(set(reference.substrate) | set(run.substrate)):
        before = reference.substrate.get(name)
        after = run.substrate.get(name)

        if before and after and before != after:
            warnings.append(f"`{name}` differs ({before} vs. {after})")

    return warnings


def check_pairing(
    asked: list[Question],
    reference: Run,
    reference_name: str = "the reference",
) -> None:
    """Refuse a reference that asked a different question under a key."""
    before = {case.key: case.question for case in reference.cases}
    mismatched = [
        question.key
        for question in asked
        if question.key in before and before[question.key] != question.question
    ]

    if mismatched:
        raise QuestionsDiffer(reference_name, mismatched)


def corpus_change(run: Run, reference: Run) -> str | None:
    """The database's size in the reference and now, when both recorded it."""
    before = reference.database
    after = run.database

    if before.get("documents") is None or after.get("documents") is None:
        return None

    return (
        f"{before['documents']} -> {after['documents']} documents, "
        f"{before.get('chunks')} -> {after.get('chunks')} chunks"
    )


def _names(uris: list[str]) -> str:
    """Documents by name, for a person:  the full URIs are in the results."""
    return ", ".join(manifest.Document(uri=uri).name for uri in uris)


def details(run: Run) -> list[str]:
    """One line per question, in question-set order:  where its first
    relevant document ranked, and what came ahead of it or, for a miss,
    what came first."""
    lines = ["rank  mrr    question"]

    for case in run.cases:
        if not case.eligible:
            lines.append(f"   -  -      {case.question}")
            lines.append("             ineligible:  no relevant documents")
            continue

        rank = case.rank

        if rank is None:
            lines.append(f"   -  0.000  {case.question}")
            shown = case.retrieved[:SHOWN_ON_MISS]
            lines.append(f"             top: {_names(shown) or '(nothing)'}")
            continue

        lines.append(f"{rank:4d}  {case.score:.3f}  {case.question}")

        if rank > 1:
            ahead = case.retrieved[: rank - 1]
            lines.append(f"             after: {_names(ahead)}")

    return lines


def report(outcome: Outcome, reference_name: str | None = None) -> list[str]:
    """The outcome, as lines for a person."""
    if outcome.n_eligible == 0:
        return [
            f"no question carries `{bind_mod.LABEL_KEY}`:  nothing was checked"
        ]

    lines = []
    n_ineligible = len(outcome.run.cases) - outcome.n_eligible

    if n_ineligible:
        lines.append(
            f"{n_ineligible} question(s) ineligible:  no relevant documents"
        )

    if outcome.unreferenced:
        lines.append(
            f"{len(outcome.unreferenced)} question(s) not scored in "
            f"{reference_name};  checked for misses instead"
        )

    for miss in outcome.misses:
        lines.append(f"MISS {miss.key}: {miss.question}")
        lines.append(f"     not retrieved: {', '.join(miss.missing)}")

    for loss in outcome.losses:
        lines.append(f"LOSS {loss.key}: {loss.question}")
        lines.append(f"     no longer retrieved: {', '.join(loss.lost)}")

    for dropout in outcome.dropouts:
        lines.append(f"DROPPED {dropout.key}: {dropout.question}")
        lines.append(
            f"     no longer retrieved: {', '.join(dropout.dropped)} "
            f"(still retrieved: {', '.join(dropout.kept)})"
        )

    for drop in outcome.drops:
        lines.append(f"RANK {drop.key}: {drop.question}")
        lines.append(
            f"     {RETRIEVAL_MRR} {drop.reference:.3f} -> {drop.current:.3f}"
        )

    if outcome.mean_fell:
        lines.append(
            f"mean {RETRIEVAL_MRR} over the questions in {reference_name} "
            f"fell {outcome.reference_mean:.3f} -> "
            f"{outcome.current_mean:.3f}, by more than "
            f"{outcome.mrr_tolerance}"
        )

    passed = outcome.n_eligible - outcome.n_failing
    lines.append(
        f"{passed}/{outcome.n_eligible} questions "
        f"passed;  mean {RETRIEVAL_MRR} {outcome.run.mean():.3f}"
    )

    return lines
