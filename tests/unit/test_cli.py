"""Unit tests for the ``exquisite`` command (`exquisite/__init__.py`)."""

import argparse
import json
import sys

import _builders
import pytest

import exquisite
from exquisite.manifest import Document

ISO = Document(
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
        exquisite.main()

    return exited.value.code


def test_data_root_resolves_a_directory_holding_both(data_root):
    result = exquisite._data_root(str(data_root))

    assert result == data_root.resolve()


def test_data_root_names_what_is_missing(tmp_path):
    (tmp_path / "corpus").mkdir()

    with pytest.raises(exquisite.NotADataRoot) as raised:
        exquisite._data_root(str(tmp_path))

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
    from exquisite import corpus
    from exquisite import worksheets

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
    from exquisite import corpus
    from exquisite import worksheets

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
