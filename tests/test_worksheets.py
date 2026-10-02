"""Unit tests for `exquisite.worksheets`."""

import pytest
import yaml

from exquisite import worksheets
from exquisite.designators import collapsed_key
from exquisite.manifest import Corpus, Document


def doc(name, identifier="", source="", certainty=None, sha256=None):
    return Document(
        uri=f"file:///downloads/{name}",
        sha256=sha256 or f"sha-{name}",
        document_identifier=identifier,
        identifier_source=source,
        identifier_certainty=certainty,
    )


def make_corpus(*docs):
    return Corpus(database="corpus", documents=list(docs))


def make_cases(*references):
    return [{"metadata": {"reference": text}} for text in references]


def render(corpus, cases, **kwargs):
    return worksheets.render(
        question_set="questions/set.json",
        database="corpus",
        corpus_documents=len(corpus.documents),
        substrate="unknown",
        generated="2026-10-01",
        cases=cases,
        corpus=corpus,
        **kwargs,
    )


class TestRelation:
    @pytest.mark.parametrize(
        "identifier, expected",
        [
            ("IEC 61508 Supplement", "supplement"),
            ("IEC 61508-3 Supplement", "supplement"),
            ("IEC 61508-3", "sub-publication"),
            ("IEC 61509", None),
        ],
    )
    def test_names_how_an_extending_identifier_relates(self, identifier, expected):
        key = collapsed_key("IEC 61508")

        result = worksheets.relation(key, identifier)

        assert result == expected

    def test_a_volume(self):
        result = worksheets.relation(collapsed_key("IEC 61508"), "IEC 61508 Vol 2")

        assert result == "volume"


class TestFindCandidates:
    def test_identifier_tier_is_exact_and_extensions_are_related(self):
        corpus = make_corpus(
            doc("base.pdf", "IEC 61508", "override"),
            doc("supp.pdf", "IEC 61508 Supplement", "override"),
            doc("part.pdf", "IEC 61508-3", "override"),
        )
        key = collapsed_key("IEC 61508")

        found = worksheets.find_candidates(key, {"iec"}, corpus)

        assert found["identifier"] == ["file:///downloads/base.pdf"]
        assert found["identifier_related"] == {
            "file:///downloads/part.pdf": "sub-publication",
            "file:///downloads/supp.pdf": "supplement",
        }

    def test_a_shared_numeric_prefix_is_not_related(self):
        corpus = make_corpus(doc("sp800-53.pdf", "NIST SP 800-53", "override"))

        found = worksheets.find_candidates(collapsed_key("NIST SP 800-5"), {"nist"}, corpus)

        assert "identifier_related" not in found
        assert found["identifier"] == []


class TestProvisionalAnswer:
    def test_answers_from_trusted_exact_matches_only(self):
        trusted = doc("a.pdf", "NIST SP 800-61", "llm", 5)
        weak = doc("b.pdf", "NIST SP 800-61", "llm", 3)
        corpus = make_corpus(trusted, weak)
        found = {"identifier": [trusted.uri, weak.uri]}

        answer = worksheets.provisional_answer(found, corpus)

        assert answer["documents"] == [trusted.durable()]
        assert "llm certainty 5" in answer[worksheets.PROVISIONAL]

    @pytest.mark.parametrize(
        "found",
        [
            {"identifier": []},
            {"identifier": ["file:///downloads/b.pdf"]},  # only a weak match
            {"identifier": ["file:///downloads/c.pdf"]},  # unrecorded
            {"identifier": [], "matched": ["file:///downloads/a.pdf"]},  # filename only
        ],
    )
    def test_makes_nothing_without_a_trusted_exact_match(self, found):
        corpus = make_corpus(
            doc("a.pdf", "", ""),
            doc("b.pdf", "NIST SP 800-61", "llm", 3),
            doc("c.pdf", "NIST SP 800-61", "unrecorded"),
        )

        answer = worksheets.provisional_answer(found, corpus)

        assert answer is None


class TestCrossReferences:
    def test_links_a_filename_match_to_the_group_its_identifier_names(self):
        adopted = doc("en-iso-9001.pdf", "EN ISO 9001", "override")
        corpus = make_corpus(adopted)
        found_by_key = {
            "eniso9001": {"identifier": [adopted.uri], "matched": []},
            "iso9001": {"identifier": [], "matched": [adopted.uri]},
            "other": {"identifier": [], "matched": []},
        }

        linked = worksheets.cross_references(found_by_key, corpus)

        assert linked == {
            "eniso9001": ["iso9001"],
            "iso9001": ["eniso9001"],
        }

    def test_an_untrusted_identifier_links_nothing(self):
        weak = doc("x-1.pdf", "X 1", "llm", 2)
        corpus = make_corpus(weak)
        found_by_key = {
            "x1": {"identifier": [weak.uri], "matched": []},
            "y1": {"identifier": [], "matched": [weak.uri]},
        }

        linked = worksheets.cross_references(found_by_key, corpus)

        assert linked == {}


class TestRender:
    def test_provisional_fills_only_trusted_designators(self):
        corpus = make_corpus(doc("sp800-61.pdf", "NIST SP 800-61", "llm", 5))
        cases = make_cases("NIST SP 800-61 Sec 3", "NIST SP 800-30 Sec 2")

        text = render(corpus, cases, provisional=True)

        entries = {e["designator"]: e for e in yaml.safe_load(text)["designators"]}
        assert entries["NIST SP 800-61"]["documents"][0]["name"] == "sp800-61.pdf"
        assert "llm certainty 5" in entries["NIST SP 800-61"][worksheets.PROVISIONAL]
        assert entries["NIST SP 800-30"]["documents"] == worksheets.UNFILLED

    def test_without_the_flag_nothing_is_filled(self):
        corpus = make_corpus(doc("sp800-61.pdf", "NIST SP 800-61", "llm", 5))

        text = render(corpus, make_cases("NIST SP 800-61"))

        entry = yaml.safe_load(text)["designators"][0]
        assert entry["documents"] == worksheets.UNFILLED

    def test_an_existing_answer_is_kept_over_a_provisional_one(self):
        corpus = make_corpus(doc("sp800-61.pdf", "NIST SP 800-61", "llm", 5))
        previous = {"NIST SP 800-61": {"documents": [], "unresolved": "superseded"}}

        text = render(corpus, make_cases("NIST SP 800-61"), previous=previous, provisional=True)

        entry = yaml.safe_load(text)["designators"][0]
        assert entry["unresolved"] == "superseded"
        assert worksheets.PROVISIONAL not in entry

    def test_candidates_lead_with_identifier_and_evidence(self):
        corpus = make_corpus(doc("sp800-61.pdf", "NIST SP 800-61", "llm", 4))

        text = render(corpus, make_cases("NIST SP 800-61"))

        lines = text.splitlines()
        first = next(line for line in lines if "document_identifier:" in line)
        assert first.strip().startswith('- document_identifier: "NIST SP 800-61"')
        assert first.endswith("# llm certainty 4")

    def test_notes_a_group_also_cited_under_another_key(self):
        corpus = make_corpus(
            doc("en-iso-9001.pdf", "EN ISO 9001", "override")
        )
        cases = make_cases("EN ISO 9001", "ISO 9001")

        text = render(corpus, cases)

        assert "  # also cited as: EN ISO 9001" in text
        assert "  # also cited as: ISO 9001" in text

    def test_preserved_provisional_answers_survive_a_refresh(self, tmp_path):
        corpus = make_corpus(doc("sp800-61.pdf", "NIST SP 800-61", "llm", 5))
        path = tmp_path / "set.yaml"
        path.write_text(render(corpus, make_cases("NIST SP 800-61"), provisional=True))

        previous, _ = worksheets.preserved_answers(path)

        assert worksheets.PROVISIONAL in previous["NIST SP 800-61"]
