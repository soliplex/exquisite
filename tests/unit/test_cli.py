"""Unit tests for the ``exquisite`` command (`exquisite/__init__.py`)."""

import argparse
import json
import sys

import _builders
import pytest

from exquisite import cli
from exquisite import corpus
from exquisite import manifest
from exquisite import retrieval
from exquisite import rules
from exquisite import search
from exquisite import worksheets

ISO = manifest.Document(
    uri="file:///iso.pdf",
    sha256="h",
    source_url="https://x/iso",
    document_identifier="ISO 9001",
    identifier_source="override",
)

ANSWERED = """\
designators:
- designator: "ISO 9001"
  documents:
  - name: "iso.pdf"
    sha256: "{sha256}"
    source_url: "https://x/iso"
- designator: "IEC 61508"
  documents:
  - name: "iec.pdf"
    sha256: "gone"
apply_keys:
  "ISO 9001 Sec 4": "ISO 9001"
  "IEC 61508": "IEC 61508"
"""


@pytest.fixture
def std(data_root):
    """A corpus holding ISO 9001, and a question set citing two standards."""
    _builders.ingestion(data_root, "std", "std", [ISO])
    _builders.question_set(data_root, "set", ["ISO 9001 Sec 4", "IEC 61508"])

    return data_root


def run(monkeypatch, root, command, *args):
    """Run ``exquisite <command> --root <root> <args>``; its exit status."""
    argv = ["exquisite", command, "--root", str(root), "--date", "2026-10-02"]
    monkeypatch.setattr(sys, "argv", [*argv, *args])

    with pytest.raises(SystemExit) as exited:
        cli.main()

    return exited.value.code


def test_data_root_resolves_a_directory_holding_both(data_root):
    result = cli._data_root(str(data_root))

    assert result == data_root.resolve()


def test_data_root_names_what_is_missing(tmp_path):
    (tmp_path / "corpus").mkdir()

    with pytest.raises(cli.NotADataRoot) as raised:
        cli._data_root(str(tmp_path))

    assert raised.value.missing == ["questions"]
    assert isinstance(raised.value, argparse.ArgumentTypeError)
    assert str(raised.value) == (
        f"{tmp_path.resolve()} has no questions/; run from a data "
        "repository, or pass --root / set EXQUISITE_ROOT"
    )


def test_refresh_with_no_worksheets_says_how_to_pair(monkeypatch, capsys, std):
    status = run(monkeypatch, std, "refresh-worksheets")

    assert status == 0
    assert capsys.readouterr().out == (
        "no worksheets found; use `add-worksheet` to pair a question set\n"
    )


def test_add_worksheet_reports_what_it_created(monkeypatch, capsys, std):
    args = ["--corpus", "std", "--questions", "set", "--provisional"]

    status = run(monkeypatch, std, "add-worksheet", *args)

    assert status == 0
    assert capsys.readouterr().out == "created corpus/std/worksheet/set.yaml\n"


def test_add_worksheet_refuses_an_existing_pairing(monkeypatch, capsys, std):
    _builders.worksheet(std, "std", "set", "")
    args = ["--corpus", "std", "--questions", "set"]

    status = run(monkeypatch, std, "add-worksheet", *args)

    assert status == 1
    assert "already exists; refresh it instead" in capsys.readouterr().err


@pytest.fixture
def paired(std):
    """`std`, with a worksheet holding a provisional answer for ISO 9001."""

    worksheets.create(
        root=std,
        corpus_dir=corpus.find(std, "std"),
        question_set=corpus.find_question_set(std, "set"),
        ingestion=None,
        generated="2026-10-01",
        provisional=True,
    )

    return std


@pytest.mark.parametrize(
    "references, expected",
    [
        (None, "1 worksheet(s) already current\n"),
        (
            ["ISO 9001 Sec 4", "IEC 61508", "IEC 61508-3"],
            "   3 designators     1 answers kept  "
            "corpus/std/worksheet/set.yaml\n",
        ),
        (
            ["NIST SP 800-30"],
            "   1 designators     0 answers kept  1 answer(s) dropped  "
            "corpus/std/worksheet/set.yaml\n",
        ),
    ],
)
def test_refresh_reports_each_worksheet(
    monkeypatch, capsys, paired, references, expected
):
    if references is not None:
        _builders.question_set(paired, "set", references)

    status = run(monkeypatch, paired, "refresh-worksheets", "--corpus", "std")

    assert status == 0
    assert capsys.readouterr().out == expected


@pytest.fixture
def uri_cited(data_root):
    """A worksheet whose question set cites documents by URI."""

    _builders.ingestion(data_root, "std", "std", [ISO])
    _builders.question_set(
        data_root, "uris", ["file:///iso.pdf", "file:///absent.pdf"]
    )
    _builders.question_set(data_root, "prose", ["ISO 9001"])

    for name in ("uris", "prose"):
        worksheets.create(
            root=data_root,
            corpus_dir=corpus.find(data_root, "std"),
            question_set=corpus.find_question_set(data_root, name),
            ingestion=None,
            generated="2026-10-01",
        )

    return data_root


def test_resolve_references_reports_and_fails_on_the_unresolved(
    monkeypatch, capsys, uri_cited
):
    status = run(monkeypatch, uri_cited, "resolve-references")

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == (
        "   1 exact     0 moved     1 unresolved  "
        "corpus/std/worksheet/uris.yaml\n"
    )
    assert captured.err == (
        "       absent.pdf: no document with that filename\n"
    )


def test_bind_writes_the_labelled_set_to_stdout(monkeypatch, capsys, std):
    _builders.worksheet(std, "std", "set", ANSWERED.format(sha256="h"))
    args = ["--corpus", "std", "--questions", "set"]

    status = run(monkeypatch, std, "bind", *args)

    captured = capsys.readouterr()
    cases = json.loads(captured.out)["cases"]
    assert status == 1
    assert cases[0]["metadata"]["relevant_uris"] == ["file:///iso.pdf"]
    assert captured.err == "'IEC 61508': iec.pdf -- not in this ingestion\n"


def test_bind_to_a_file_reports_changes_and_unknown_references(
    monkeypatch, capsys, std
):
    _builders.question_set(
        std, "set", ["ISO 9001 Sec 4", "IEC 61508", "NIST SP 800-30", None]
    )
    _builders.worksheet(std, "std", "set", ANSWERED.format(sha256="old"))
    out = std / "bound.json"
    args = ["--corpus", "std", "--questions", "set", "--out", str(out)]

    status = run(monkeypatch, std, "bind", *args)

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == (
        f"   1 labelled     1 unresolved    1 no-reference  -> {out}\n"
    )
    assert captured.err == (
        "no apply_key for reference 'NIST SP 800-30'\n"
        "'IEC 61508': iec.pdf -- not in this ingestion\n"
        "CHANGED since validation: 'ISO 9001': iso.pdf\n"
    )
    assert "relevant_uris" in out.read_text()


def test_bind_refuses_an_unready_worksheet(monkeypatch, capsys, paired):
    args = ["--corpus", "std", "--questions", "set"]

    status = run(monkeypatch, paired, "bind", *args)

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == ""
    assert captured.err.startswith("set.yaml is not ready to bind:\n")


RULES = "references:\n  placeholders: [TBD]\n"


def created_rules_line(root):
    text = (root / "corpus" / "std" / "worksheet" / "set.yaml").read_text()

    return next(
        line for line in text.splitlines() if line.startswith("rules:")
    )


def test_add_worksheet_uses_the_roots_rules_file(monkeypatch, std):
    (std / rules.FILENAME).write_text(RULES)
    args = ["--corpus", "std", "--questions", "set"]

    status = run(monkeypatch, std, "add-worksheet", *args)

    expected = rules.Rules.load(std / rules.FILENAME).digest
    assert status == 0
    assert created_rules_line(std).startswith(f"rules: {expected} ")


def test_an_explicit_rules_file_wins(monkeypatch, std, tmp_path):
    (std / rules.FILENAME).write_text("relations: []\n")
    explicit = tmp_path / "explicit.yaml"
    explicit.write_text(RULES)
    args = ["--corpus", "std", "--questions", "set", "--rules", str(explicit)]

    status = run(monkeypatch, std, "add-worksheet", *args)

    expected = rules.Rules.load(explicit).digest
    assert status == 0
    assert created_rules_line(std).startswith(f"rules: {expected} ")


@pytest.mark.parametrize(
    "text, message",
    [
        ("relation: []\n", "unknown key 'relation' in the rules"),
        ("relations: [\n", "while parsing"),
        (None, "No such file or directory"),
    ],
)
def test_unusable_rules_are_a_usage_error(
    monkeypatch, capsys, std, tmp_path, text, message
):
    path = tmp_path / "rules.yaml"
    if text is not None:
        path.write_text(text)
    args = ["--corpus", "std", "--questions", "set", "--rules", str(path)]

    status = run(monkeypatch, std, "add-worksheet", *args)

    captured = capsys.readouterr()
    assert status == 2
    assert "cannot use the rules:" in captured.err
    assert message in captured.err


SETTINGS = {"embedder": "e", "reranker": None, "top_k": 30}


def run_check(monkeypatch, root, *args):
    """Run ``exquisite check-retrieval`` on the `std` question set."""
    argv = ["exquisite", "check-retrieval", "--root", str(root)]
    argv += ["--corpus", "std", "--questions", "set", "--db", "db.lancedb"]
    monkeypatch.setattr(sys, "argv", [*argv, *args])

    with pytest.raises(SystemExit) as exited:
        cli.main()

    return exited.value.code


class FakeSearch:
    """Stands in for the database:  each search returns ``hits``."""

    def __init__(self, hits):
        self.hits = hits
        self.searched = []

    def describe(self, location, config, top_k):
        settings = {**SETTINGS, "top_k": top_k}
        database = {"location": location, "documents": 1, "chunks": 3}

        return settings, database

    def search(self, location, config, questions, top_k):
        self.searched.append((location, [q.key for q in questions], top_k))

        return [list(self.hits) for _ in questions]


@pytest.fixture
def bound(std):
    """`std`, with its worksheet answered:  one question binds, one can't."""
    _builders.worksheet(std, "std", "set", ANSWERED.format(sha256="h"))

    return std


def found(monkeypatch, *hits):
    """Replace the database with one whose searches return ``hits``."""
    fake = FakeSearch(hits)
    monkeypatch.setattr(search, "describe", fake.describe)
    monkeypatch.setattr(search, "search", fake.search)

    return fake


ISO_MOVED = retrieval.Hit("file:///moved/iso.pdf", {"sha256": "h"})


def test_check_retrieval_refuses_an_unready_worksheet(
    monkeypatch, capsys, paired
):
    status = run_check(monkeypatch, paired)

    assert status == 1
    assert capsys.readouterr().err.startswith(
        "set.yaml is not ready to bind:\n"
    )


def test_check_retrieval_passes_and_saves_the_run(monkeypatch, capsys, bound):
    fake = found(monkeypatch, ISO_MOVED)
    out = bound / "results.json"

    status = run_check(monkeypatch, bound, "--out", str(out), "--top-k", "5")

    captured = capsys.readouterr()
    saved = retrieval.load(out)
    assert status == 0
    assert captured.out == (
        f"results saved to {out}\n"
        "1 question(s) ineligible:  no relevant documents\n"
        "1/1 questions passed;  mean retrieval_mrr 1.000\n"
    )
    # Binding's problems are reported, and leave their question ineligible.
    assert captured.err == "'IEC 61508': iec.pdf -- not in this ingestion\n"
    assert fake.searched == [("db.lancedb", ["uuid-0"], 5)]
    assert saved.question_set == "questions/set.json"
    assert saved.settings == {**SETTINGS, "top_k": 5}
    retrieved = [case.retrieved for case in saved.cases]
    assert retrieved == [["file:///iso.pdf"], []]
    assert saved.started
    assert saved.finished


def test_check_retrieval_fails_on_a_miss(monkeypatch, capsys, bound):
    found(monkeypatch, retrieval.Hit("file:///other.pdf"))
    out = bound / "results.json"

    status = run_check(monkeypatch, bound, "--out", str(out))

    assert status == 1
    assert "MISS uuid-0: question 0\n" in capsys.readouterr().out


def test_check_retrieval_names_the_databases_its_path_displaces(
    monkeypatch, capsys, bound
):
    found(monkeypatch, ISO_MOVED)
    config = bound / "haiku.rag.yaml"
    config.write_text("lancedb:\n  databases:\n    prod: /srv/prod\n")
    args = ["--config", str(config), "--out", str(bound / "results.json")]

    status = run_check(monkeypatch, bound, *args)

    assert status == 0
    assert capsys.readouterr().out.startswith(
        "searching db.lancedb instead of the configuration's databases "
        "(prod)\n"
    )


def reference_run(
    bound,
    *,
    top_k=30,
    retrieved=("file:///iso.pdf",),
    database=(("documents", 2), ("chunks", 4)),
):
    """Save a prior run against `bound`'s question set;  its path."""
    path = bound / "reference.json"
    retrieval.save(
        retrieval.Run(
            question_set="questions/set.json",
            corpus="std",
            ingestion="std",
            settings={**SETTINGS, "top_k": top_k},
            database=dict(database),
            substrate={"exquisite": "0.0"},
            cases=[
                retrieval.CaseResult(
                    key="uuid-0",
                    question="question 0",
                    relevant=["file:///iso.pdf"],
                    retrieved=list(retrieved),
                    score=1.0 if retrieved else 0.0,
                )
            ],
        ),
        path,
    )

    return path


def test_check_retrieval_fails_on_a_loss_against_a_reference(
    monkeypatch, capsys, bound
):
    found(monkeypatch, retrieval.Hit("file:///other.pdf"))
    reference = reference_run(bound)
    args = ["--compare", str(reference), "--out", str(bound / "now.json")]

    status = run_check(monkeypatch, bound, *args)

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out.startswith("2 -> 1 documents, 4 -> 3 chunks\n")
    assert "LOSS uuid-0: question 0\n" in captured.out
    assert f"{reference}: `exquisite` differs (0.0 vs. " in captured.err


def test_check_retrieval_passes_against_a_reference(
    monkeypatch, capsys, bound
):
    found(monkeypatch, ISO_MOVED)
    reference = reference_run(bound, database=())
    out = bound / "now.json"
    args = ["--compare", str(reference), "--out", str(out)]

    status = run_check(monkeypatch, bound, *args)

    assert status == 0
    assert capsys.readouterr().out == (
        f"results saved to {out}\n"
        "1 question(s) ineligible:  no relevant documents\n"
        "1/1 questions passed;  mean retrieval_mrr 1.000\n"
    )


def incomparable(bound):
    return reference_run(bound, top_k=10)


def not_results(bound):
    path = bound / "reference.json"
    path.write_text('{"cases": []}')

    return path


@pytest.mark.parametrize(
    "setup, message",
    [
        (incomparable, "the top K differs (10 vs. 30)"),
        (not_results, "is not a check-retrieval results file"),
    ],
)
def test_check_retrieval_refuses_a_reference_before_searching(
    monkeypatch, capsys, bound, setup, message
):
    fake = found(monkeypatch, ISO_MOVED)
    reference = setup(bound)
    args = ["--compare", str(reference), "--out", str(bound / "now.json")]

    status = run_check(monkeypatch, bound, *args)

    assert status == 1
    assert message in capsys.readouterr().err
    assert fake.searched == []
    assert not (bound / "now.json").exists()


def test_check_retrieval_never_opens_a_missing_database(
    monkeypatch, capsys, bound
):
    monkeypatch.chdir(bound)

    status = run_check(monkeypatch, bound, "--out", str(bound / "now.json"))

    assert status == 1
    assert "no database at db.lancedb" in capsys.readouterr().err
    assert not (bound / "db.lancedb").exists()


def test_check_retrieval_writes_nothing_without_out(
    monkeypatch, capsys, bound
):
    found(monkeypatch, ISO_MOVED)
    monkeypatch.chdir(bound)
    before = sorted(bound.rglob("*"))

    status = run_check(monkeypatch, bound)

    assert status == 0
    assert "results saved" not in capsys.readouterr().out
    assert sorted(bound.rglob("*")) == before


def test_check_retrieval_refuses_an_existing_out_before_searching(
    monkeypatch, capsys, bound
):
    fake = found(monkeypatch, ISO_MOVED)
    out = bound / "results.json"
    out.write_text("keep me")

    status = run_check(monkeypatch, bound, "--out", str(out))

    assert status == 1
    assert capsys.readouterr().err == (
        f"{out} exists;  pass --force to replace it\n"
    )
    assert fake.searched == []
    assert out.read_text() == "keep me"


def test_check_retrieval_replaces_an_existing_out_when_forced(
    monkeypatch, bound
):
    found(monkeypatch, ISO_MOVED)
    out = bound / "results.json"
    out.write_text("replace me")

    status = run_check(monkeypatch, bound, "--out", str(out), "--force")

    assert status == 0
    assert retrieval.load(out).cases[0].retrieved == ["file:///iso.pdf"]
