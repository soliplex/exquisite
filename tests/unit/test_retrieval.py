"""Unit tests for `exquisite.retrieval`:  scoring and checking searches."""

import json

import pytest

from exquisite import manifest
from exquisite import retrieval

ISO = manifest.Document(uri="file:///iso.pdf", sha256="h", source_url="u")
#: Byte-identical copies at two paths.
COPY_1 = manifest.Document(uri="file:///a/readme.txt", sha256="c")
COPY_2 = manifest.Document(uri="file:///b/readme.txt", sha256="c")
#: Known by its source URL alone.
IEC = manifest.Document(uri="file:///iec.pdf", source_url="https://x/iec")
#: An attachment shares its parent's hash:  only the fragment tells them
#: apart.
ATTACHED = manifest.Document(
    uri="file:///bulletin.pdf#attachment=a.pdf", sha256="p"
)

CORPUS = manifest.Corpus(
    database="std", documents=[ISO, COPY_1, COPY_2, IEC, ATTACHED]
)


def hit(uri, **metadata):
    return retrieval.Hit(uri, metadata)


def case(key, relevant=("file:///iso.pdf",), retrieved=(), score=None):
    """A `CaseResult`, scored from ``retrieved`` unless ``score`` says."""
    relevant = list(relevant)
    retrieved = list(retrieved)

    if score is None and relevant:
        score = retrieval.reciprocal_rank(retrieved, set(relevant))

    return retrieval.CaseResult(
        key=key,
        question=f"question {key}",
        relevant=relevant,
        retrieved=retrieved,
        score=score,
    )


def run(*cases, **fields):
    return retrieval.Run(
        question_set="questions/set.json",
        corpus="std",
        ingestion="std",
        cases=list(cases),
        **fields,
    )


@pytest.mark.parametrize(
    "found, expected",
    [
        # Matched by sha256, at a path the manifest does not use.
        (hit("file:///moved/iso.pdf", sha256="h"), "file:///iso.pdf"),
        # By source URL, when the database records no hash.
        (
            hit("s3://bucket/iec.pdf", source_url="https://x/iec"),
            "file:///iec.pdf",
        ),
        # A copy:  the one at the hit's own URI.
        (hit("file:///b/readme.txt", sha256="c"), "file:///b/readme.txt"),
        # A copy found elsewhere:  the first the manifest lists.
        (hit("file:///c/readme.txt", sha256="c"), "file:///a/readme.txt"),
        # Unknown to the manifest:  the database's own URI.
        (hit("file:///other.pdf", sha256="z"), "file:///other.pdf"),
        (hit("file:///iso.pdf"), "file:///iso.pdf"),
        # An attachment, matched with its fragment ...
        (
            hit("file:///x/bulletin.pdf#attachment=a.pdf", sha256="p"),
            "file:///bulletin.pdf#attachment=a.pdf",
        ),
        # ... and not its sibling, though they share the parent's hash.
        (
            hit("file:///x/bulletin.pdf#attachment=b.pdf", sha256="p"),
            "file:///x/bulletin.pdf#attachment=b.pdf",
        ),
    ],
)
def test_identify(found, expected):
    result = retrieval.identify(found, CORPUS)

    assert result == expected


def test_ranked_identifies_and_deduplicates_in_rank_order():
    hits = [
        hit("file:///other.pdf"),
        hit("file:///moved/iso.pdf", sha256="h"),
        hit("file:///iso.pdf"),
        hit("file:///other.pdf"),
    ]

    result = retrieval.ranked(hits, CORPUS)

    assert result == ["file:///other.pdf", "file:///iso.pdf"]


@pytest.mark.parametrize(
    "retrieved, expected",
    [
        (["a", "b", "c"], 1.0),
        (["x", "b", "c"], 0.5),
        (["x", "y", "c"], 1 / 3),
        (["x", "y"], 0.0),
        ([], 0.0),
    ],
)
def test_reciprocal_rank_of_the_first_relevant(retrieved, expected):
    result = retrieval.reciprocal_rank(retrieved, {"b", "c", "a"})

    assert result == pytest.approx(expected)


def test_questions_key_cases_by_uuid_then_name_then_position():
    cases = [
        {
            "inputs": "q1",
            "name": "named",
            "metadata": {"uuid": "u1", "relevant_uris": ["file:///iso.pdf"]},
        },
        {"inputs": "q2", "name": "named", "metadata": {}},
        {"inputs": 3},
    ]

    result = retrieval.questions(cases)

    assert result == [
        retrieval.Question("u1", "q1", ("file:///iso.pdf",)),
        retrieval.Question("named", "q2", ()),
        retrieval.Question("Case 3", "3", ()),
    ]


def test_score_a_labelled_question():
    asked = retrieval.Question("k", "q", ("file:///iso.pdf",))
    hits = [hit("file:///other.pdf"), hit("file:///x/iso.pdf", sha256="h")]

    result = retrieval.score(asked, hits, CORPUS)

    assert result == retrieval.CaseResult(
        key="k",
        question="q",
        relevant=["file:///iso.pdf"],
        retrieved=["file:///other.pdf", "file:///iso.pdf"],
        score=0.5,
    )
    assert result.eligible
    assert result.found == ["file:///iso.pdf"]


def test_score_leaves_an_unlabelled_question_ineligible():
    asked = retrieval.Question("k", "q")

    result = retrieval.score(asked, [], CORPUS)

    assert result.score is None
    assert not result.eligible


def test_results_round_trip_through_a_file(tmp_path):
    path = tmp_path / "results.json"
    original = run(
        case("k", retrieved=["file:///iso.pdf"]),
        case("u", relevant=()),
        settings={"top_k": 30},
        database={"documents": 1},
        substrate={"exquisite": "0.2"},
        started="2026-10-03T09:00:00",
        finished="2026-10-03T09:00:05",
    )
    retrieval.save(original, path)

    result = retrieval.load(path)

    assert result == original
    assert json.loads(path.read_text())["format"] == retrieval.FORMAT


@pytest.mark.parametrize(
    "data", [[], {"cases": []}, {"format": "something else", "cases": []}]
)
def test_load_refuses_another_kind_of_file(tmp_path, data):
    path = tmp_path / "results.json"
    path.write_text(json.dumps(data))

    with pytest.raises(retrieval.NotAResultsFile) as raised:
        retrieval.load(path)

    assert raised.value.path == path
    assert retrieval.FORMAT in str(raised.value)


def test_mean_over_eligible_questions_only():
    checked = run(case("a", score=1.0), case("b", score=0.5), case("c", ()))

    result = checked.mean()

    assert result == 0.75


def test_check_without_a_reference_fails_on_misses():
    checked = run(
        case("hit", retrieved=["file:///iso.pdf"]),
        case("miss", retrieved=["file:///other.pdf"]),
        case("ineligible", relevant=()),
    )

    outcome = retrieval.check(checked)

    assert outcome.misses == [
        retrieval.Miss("miss", "question miss", ["file:///iso.pdf"])
    ]
    assert outcome.n_eligible == 2
    assert outcome.n_failing == 1
    assert outcome.failed
    assert not outcome.mean_fell


def test_check_against_a_reference():
    both = ("file:///iso.pdf", "file:///iec.pdf")
    reference = run(
        case("lost", retrieved=["file:///iso.pdf"]),
        case("dropped", relevant=both, retrieved=list(both)),
        case("slipped", retrieved=["file:///iso.pdf"]),
        case("steady", retrieved=["file:///iso.pdf"]),
        case("never", retrieved=[]),
    )
    checked = run(
        case("lost", retrieved=[]),
        case("dropped", relevant=both, retrieved=["file:///iec.pdf"]),
        case("slipped", retrieved=["x", "file:///iso.pdf"]),
        case("steady", retrieved=["file:///iso.pdf"]),
        case("never", retrieved=[]),
        case("new", retrieved=[]),
    )

    outcome = retrieval.check(checked, reference, mrr_tolerance=0.1)

    assert outcome.losses == [
        retrieval.Loss("lost", "question lost", ["file:///iso.pdf"])
    ]
    assert outcome.dropouts == [
        retrieval.Dropout(
            "dropped",
            "question dropped",
            ["file:///iso.pdf"],
            ["file:///iec.pdf"],
        )
    ]
    assert outcome.drops == [
        retrieval.Drop("lost", "question lost", 1.0, 0.0),
        retrieval.Drop("slipped", "question slipped", 1.0, 0.5),
    ]
    # A question the reference never hit cannot be lost;  one it lacks is
    # checked for a miss.
    assert outcome.misses == [
        retrieval.Miss("new", "question new", ["file:///iso.pdf"])
    ]
    assert outcome.unreferenced == ["new"]
    assert outcome.reference_mean == pytest.approx(0.8)
    assert outcome.current_mean == pytest.approx(0.5)
    assert outcome.mean_fell
    assert outcome.failed


@pytest.mark.parametrize(
    "cases, expected",
    [
        ([case("hit", retrieved=["file:///iso.pdf"])], False),
        ([case("miss")], True),
        # Nothing eligible is a failure.
        ([case("x", relevant=())], True),
        ([], True),
    ],
)
def test_outcome_failed(cases, expected):
    outcome = retrieval.check(run(*cases))

    result = outcome.failed

    assert result is expected


SETTINGS = {"embedder": "e", "reranker": None, "top_k": 30}


@pytest.mark.parametrize(
    "changed, message",
    [
        ({"embedder": "f"}, "the configured embedder differs (e vs. f)"),
        ({"reranker": "r"}, "the reranker differs (None vs. r)"),
        ({"top_k": 10}, "the top K differs (30 vs. 10)"),
    ],
)
def test_check_settings_refuses_different_searches(changed, message):
    reference = run(settings=SETTINGS)
    checked = run(settings={**SETTINGS, **changed})

    with pytest.raises(retrieval.SettingsDiffer) as raised:
        retrieval.check_settings(checked, reference, "ref.json")

    assert raised.value.problems == [message]
    assert str(raised.value).startswith("cannot compare against ref.json:  ")


def test_check_settings_refuses_a_database_stored_differently():
    reference = run(settings=SETTINGS, database={"embedder": "e"})
    checked = run(settings=SETTINGS, database={"embedder": "f"})

    with pytest.raises(retrieval.SettingsDiffer) as raised:
        retrieval.check_settings(checked, reference)

    assert raised.value.problems == [
        "the database was stored with a different embedder (e vs. f)"
    ]


def test_check_settings_warns_of_substrate_versions():
    reference = run(
        settings=SETTINGS,
        database={"embedder": None},
        substrate={"exquisite": "0.1", "haiku-rag-slim": "0.89", "old": "1"},
    )
    checked = run(
        settings=SETTINGS,
        database={"embedder": "e"},
        substrate={"exquisite": "0.1", "haiku-rag-slim": "0.92", "new": "1"},
    )

    result = retrieval.check_settings(checked, reference)

    assert result == ["`haiku-rag-slim` differs (0.89 vs. 0.92)"]


def test_check_pairing_accepts_the_same_questions():
    reference = run(case("a"), case("gone"))
    asked = [
        retrieval.Question("a", "question a"),
        retrieval.Question("b", "never asked before"),
    ]

    retrieval.check_pairing(asked, reference)


@pytest.mark.parametrize(
    "count, shown",
    [(1, "(k0)"), (7, "(k0, k1, k2, k3, k4 and 2 more)")],
)
def test_check_pairing_refuses_different_questions_under_a_key(count, shown):
    keys = [f"k{i}" for i in range(count)]
    reference = run(*(case(key) for key in keys))
    asked = [retrieval.Question(key, "something else") for key in keys]

    with pytest.raises(retrieval.QuestionsDiffer) as raised:
        retrieval.check_pairing(asked, reference, "ref.json")

    assert raised.value.keys == keys
    assert f"{count} question(s) differ under the same key {shown}" in str(
        raised.value
    )


@pytest.mark.parametrize(
    "before, after, expected",
    [
        (
            {"documents": 8, "chunks": 100},
            {"documents": 9, "chunks": 120},
            "8 -> 9 documents, 100 -> 120 chunks",
        ),
        ({}, {"documents": 9}, None),
        ({"documents": 8}, {"documents": None}, None),
    ],
)
def test_corpus_change(before, after, expected):
    result = retrieval.corpus_change(run(database=after), run(database=before))

    assert result == expected


def test_report_with_nothing_eligible():
    outcome = retrieval.check(run(case("x", relevant=())))

    result = retrieval.report(outcome)

    assert result == [
        "no question carries `relevant_uris`:  nothing was checked"
    ]


def test_report_a_clean_run():
    outcome = retrieval.check(run(case("a", retrieved=["file:///iso.pdf"])))

    result = retrieval.report(outcome)

    assert result == ["1/1 questions passed;  mean retrieval_mrr 1.000"]


def test_report_against_a_reference():
    both = ("file:///iso.pdf", "file:///iec.pdf")
    reference = run(
        case("lost", retrieved=["file:///iso.pdf"]),
        case("dropped", relevant=both, retrieved=list(both)),
    )
    checked = run(
        case("lost", retrieved=[]),
        case("dropped", relevant=both, retrieved=["file:///iec.pdf"]),
        case("new", retrieved=[]),
        case("unlabelled", relevant=()),
    )
    outcome = retrieval.check(checked, reference)

    result = retrieval.report(outcome, "ref.json")

    assert result == [
        "1 question(s) ineligible:  no relevant documents",
        "1 question(s) not scored in ref.json;  checked for misses instead",
        "MISS new: question new",
        "     not retrieved: file:///iso.pdf",
        "LOSS lost: question lost",
        "     no longer retrieved: file:///iso.pdf",
        "DROPPED dropped: question dropped",
        "     no longer retrieved: file:///iso.pdf "
        "(still retrieved: file:///iec.pdf)",
        "RANK lost: question lost",
        "     retrieval_mrr 1.000 -> 0.000",
        "mean retrieval_mrr over the questions in ref.json fell "
        "1.000 -> 0.500, by more than 0.02",
        "1/3 questions passed;  mean retrieval_mrr 0.333",
    ]


@pytest.mark.parametrize(
    "relevant, retrieved, expected",
    [
        (("a",), ["a", "b"], 1),
        (("b", "c"), ["a", "c", "b"], 2),
        (("a",), ["x", "y"], None),
        ((), ["a"], None),
    ],
)
def test_rank_of_the_first_relevant_document(relevant, retrieved, expected):
    found = case("k", relevant=relevant, retrieved=retrieved)

    result = found.rank

    assert result == expected


def test_details_one_line_per_question_in_order():
    checked = run(
        case("first", retrieved=["file:///iso.pdf"]),
        case(
            "third",
            retrieved=[
                "file:///a/x%20y.pdf",
                "file:///bulletin.pdf#attachment=a.pdf",
                "file:///iso.pdf",
            ],
        ),
        case(
            "missed",
            retrieved=["file:///1.pdf", "file:///2.pdf", "file:///3.pdf", "4"],
        ),
        case("nothing", retrieved=[]),
        case("unlabelled", relevant=()),
    )

    result = retrieval.details(checked)

    assert result == [
        "rank  mrr    question",
        "   1  1.000  question first",
        "   3  0.333  question third",
        "             after: x y.pdf, a.pdf",
        "   -  0.000  question missed",
        "             top: 1.pdf, 2.pdf, 3.pdf",
        "   -  0.000  question nothing",
        "             top: (nothing)",
        "   -  -      question unlabelled",
        "             ineligible:  no relevant documents",
    ]
