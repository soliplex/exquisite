"""Unit tests for `exquisite.worksheets`."""

import hashlib
import json

import _builders
import pytest
import yaml

from exquisite import corpus as corpus_mod
from exquisite import designators
from exquisite import manifest
from exquisite import rules as rules_mod
from exquisite import worksheets


def doc(name, identifier="", source="", certainty=None, sha256=None):
    return manifest.Document(
        uri=f"file:///downloads/{name}",
        sha256=sha256 or f"sha-{name}",
        document_identifier=identifier,
        identifier_source=source,
        identifier_certainty=certainty,
    )


def make_corpus(*docs):
    return manifest.Corpus(database="corpus", documents=list(docs))


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
    def test_names_how_an_extending_identifier_relates(
        self, identifier, expected
    ):
        key = designators.collapsed_key("IEC 61508")

        result = worksheets.relation(key, identifier)

        assert result == expected

    def test_a_volume(self):
        result = worksheets.relation(
            designators.collapsed_key("IEC 61508"), "IEC 61508 Vol 2"
        )

        assert result == "volume"


class TestFindCandidates:
    def test_identifier_tier_is_exact_and_extensions_are_related(self):
        corpus = make_corpus(
            doc("base.pdf", "IEC 61508", "override"),
            doc("supp.pdf", "IEC 61508 Supplement", "override"),
            doc("part.pdf", "IEC 61508-3", "override"),
        )
        key = designators.collapsed_key("IEC 61508")

        found = worksheets.find_candidates(key, {"iec"}, corpus)

        assert found["identifier"] == ["file:///downloads/base.pdf"]
        assert found["identifier_related"] == {
            "file:///downloads/part.pdf": "sub-publication",
            "file:///downloads/supp.pdf": "supplement",
        }

    def test_a_shared_numeric_prefix_is_not_related(self):
        corpus = make_corpus(doc("sp800-53.pdf", "NIST SP 800-53", "override"))

        found = worksheets.find_candidates(
            designators.collapsed_key("NIST SP 800-5"), {"nist"}, corpus
        )

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
            {
                "identifier": [],
                "matched": ["file:///downloads/a.pdf"],
            },  # filename only
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

        entries = {
            e["designator"]: e for e in yaml.safe_load(text)["designators"]
        }
        assert (
            entries["NIST SP 800-61"]["documents"][0]["name"] == "sp800-61.pdf"
        )
        assert (
            "llm certainty 5"
            in entries["NIST SP 800-61"][worksheets.PROVISIONAL]
        )
        assert entries["NIST SP 800-30"]["documents"] == worksheets.UNFILLED

    def test_without_the_flag_nothing_is_filled(self):
        corpus = make_corpus(doc("sp800-61.pdf", "NIST SP 800-61", "llm", 5))

        text = render(corpus, make_cases("NIST SP 800-61"))

        entry = yaml.safe_load(text)["designators"][0]
        assert entry["documents"] == worksheets.UNFILLED

    def test_an_existing_answer_is_kept_over_a_provisional_one(self):
        corpus = make_corpus(doc("sp800-61.pdf", "NIST SP 800-61", "llm", 5))
        previous = {
            "NIST SP 800-61": {"documents": [], "unresolved": "superseded"}
        }

        text = render(
            corpus,
            make_cases("NIST SP 800-61"),
            previous=previous,
            provisional=True,
        )

        entry = yaml.safe_load(text)["designators"][0]
        assert entry["unresolved"] == "superseded"
        assert worksheets.PROVISIONAL not in entry

    def test_candidates_lead_with_identifier_and_evidence(self):
        corpus = make_corpus(doc("sp800-61.pdf", "NIST SP 800-61", "llm", 4))

        text = render(corpus, make_cases("NIST SP 800-61"))

        lines = text.splitlines()
        first = next(line for line in lines if "document_identifier:" in line)
        assert first.strip().startswith(
            '- document_identifier: "NIST SP 800-61"'
        )
        assert first.endswith("# llm certainty 4")

    def test_notes_a_group_also_cited_under_another_key(self):
        corpus = make_corpus(doc("en-iso-9001.pdf", "EN ISO 9001", "override"))
        cases = make_cases("EN ISO 9001", "ISO 9001")

        text = render(corpus, cases)

        assert "  # also cited as: EN ISO 9001" in text
        assert "  # also cited as: ISO 9001" in text

    def test_preserved_provisional_answers_survive_a_refresh(self, tmp_path):
        corpus = make_corpus(doc("sp800-61.pdf", "NIST SP 800-61", "llm", 5))
        path = tmp_path / "set.yaml"
        path.write_text(
            render(corpus, make_cases("NIST SP 800-61"), provisional=True)
        )

        previous, _ = worksheets.preserved_answers(path)

        assert worksheets.PROVISIONAL in previous["NIST SP 800-61"]


class TestRenderCandidates:
    @pytest.fixture
    def text(self):
        corpus = make_corpus(
            doc("iec-61508.pdf", "IEC 61508", "override"),
            doc("iec-61508-3.pdf", "IEC 61508-3", "llm", 5),
            doc("bundle.pdf#attachment=iec-61508-annex.pdf"),
            doc("nist-csf.pdf"),
            *[doc(f"iso-9001-2015-{i}.pdf") for i in range(13)],
        )
        cases = [
            *make_cases("IEC 61508 Sec 1", "IEC-61508 Sec 2"),
            *make_cases("NIST SP 800-30", "ISO 9001", "[To Be Filled Out]"),
            {},
        ]

        return render(corpus, cases)

    def test_groups_spellings_of_one_key_together(self, text):
        group = text.split("  # iec61508\n", 1)[1].split("\n\n", 1)[0]

        assert '- designator: "IEC 61508"' in group
        assert '- designator: "IEC-61508"' in group

    def test_identifier_tiers_carry_their_evidence(self, text):
        assert '    - document_identifier: "IEC 61508"   # override' in text
        assert (
            '    - document_identifier: "IEC 61508-3"'
            "   # llm certainty 5; sub-publication"
        ) in text

    def test_attachments_are_flagged_and_matched_by_their_own_name(self, text):
        assert '    - name: "iec-61508-annex.pdf"   # attachment' in text

    def test_long_related_lists_are_truncated(self, text):
        assert "    related:   # truncated to 12" in text

    def test_same_series_appears_only_when_nothing_else_did(self, text):
        group = text.split('  "nistsp80030":\n', 1)[1].split("\n\n", 1)[0]

        assert "    same_series:" in group
        assert '    - name: "nist-csf.pdf"' in group

    def test_placeholder_references_get_no_apply_key(self, text):
        apply_keys = yaml.safe_load(text)["apply_keys"]

        assert sorted(apply_keys) == [
            "IEC 61508 Sec 1",
            "IEC-61508 Sec 2",
            "ISO 9001",
            "NIST SP 800-30",
        ]


def test_a_document_matching_its_own_group_links_nothing():
    trusted = doc("x-1.pdf", "X 1", "override")
    found_by_key = {
        "x1": {"identifier": [trusted.uri], "matched": [trusted.uri]}
    }

    linked = worksheets.cross_references(found_by_key, make_corpus(trusted))

    assert linked == {}


def test_substrate_digest_of_an_unrecorded_substrate():
    corpus = manifest.Corpus(database="std")

    result = worksheets.substrate_digest(corpus)

    assert result == "unknown"


def test_substrate_digest_ignores_key_order():
    substrate = {"processing": {"chunk_size": 256}, "embeddings": {"n": "e"}}
    corpus = manifest.Corpus(database="std", about={"substrate": substrate})
    canonical = json.dumps(substrate, sort_keys=True).encode()

    result = worksheets.substrate_digest(corpus)

    assert result == hashlib.sha256(canonical).hexdigest()[:12]


@pytest.mark.parametrize(
    "validated, expected",
    [
        (
            None,
            [
                "validated_by:      # FILL ME IN",
                "validated_on:      # FILL ME IN",
            ],
        ),
        (
            {
                "validated_by": "A. Person",
                "validated_on": "2026-10-01",
                "substrate": "abc",
                "rules": "def",
            },
            ["validated_by: 'A. Person'", "validated_on: 2026-10-01"],
        ),
        (
            {"validated_by": "A. Person", "substrate": "old"},
            [
                "validated_by: 'A. Person'",
                "validated_on: ",
                "validated_against_substrate: old   # THE CORPUS HAS BEEN "
                "REBUILT SINCE; RE-VALIDATE",
            ],
        ),
        (
            {"validated_by": "A. Person", "substrate": "abc", "rules": "old"},
            [
                "validated_by: 'A. Person'",
                "validated_on: ",
                "validated_against_rules: old   # THE NORMALIZATION RULES "
                "HAVE CHANGED SINCE; RE-VALIDATE",
            ],
        ),
    ],
)
def test_validation_lines_flag_a_rebuilt_corpus_or_new_rules(
    validated, expected
):
    result = worksheets._validation_lines(validated, "abc", "def")

    assert result == expected


def test_answer_lines_re_emit_every_kind_of_value():
    kept = {
        "documents": [{"name": "a.pdf", "sha256": "h"}],
        "unresolved": "partly",
        "notes": ["first", "second"],
    }

    result = worksheets._answer_lines(kept)

    assert result == [
        "  documents:",
        '  - name: "a.pdf"',
        '    sha256: "h"',
        "    source_url:",
        '  unresolved: "partly"',
        "  notes:",
        "  - first",
        "  - second",
    ]


def test_preserved_answers_of_a_missing_worksheet(tmp_path):
    result = worksheets.preserved_answers(tmp_path / "absent.yaml")

    assert result == ({}, {})


@pytest.fixture
def paired(data_root):
    """A corpus, a question set, and the worksheet pairing them."""
    _builders.ingestion(
        data_root,
        "std",
        "std",
        [
            manifest.Document(
                uri="file:///iso.pdf",
                sha256="h",
                document_identifier="ISO 9001",
                identifier_source="override",
            )
        ],
    )
    _builders.question_set(data_root, "set", ["ISO 9001 Sec 4", "IEC 61508"])
    corpus_dir = corpus_mod.find(data_root, "std")
    path = worksheets.create(
        root=data_root,
        corpus_dir=corpus_dir,
        question_set=corpus_mod.find_question_set(data_root, "set"),
        ingestion=None,
        generated="2026-10-01",
        provisional=True,
    )

    return corpus_dir, path


class TestCreate:
    def test_writes_the_worksheet_with_provisional_answers(self, paired):
        _, path = paired

        loaded = yaml.safe_load(path.read_text())

        entries = {e["designator"]: e for e in loaded["designators"]}
        assert entries["ISO 9001"][worksheets.PROVISIONAL]
        assert entries["IEC 61508"]["documents"] == worksheets.UNFILLED
        assert str(loaded["generated"]) == "2026-10-01"

    def test_refuses_to_recreate_a_pairing(self, data_root, paired):
        corpus_dir, path = paired

        with pytest.raises(worksheets.WorksheetExists) as raised:
            worksheets.create(
                root=data_root,
                corpus_dir=corpus_dir,
                question_set=corpus_mod.find_question_set(data_root, "set"),
                ingestion=None,
                generated="2026-10-02",
            )

        assert (
            str(raised.value) == f"{path} already exists; refresh it instead"
        )

    def test_refuses_a_set_with_nothing_to_map(self, data_root, paired):
        corpus_dir, _ = paired
        _builders.question_set(
            data_root, "empty", [None, "[To Be Filled Out]"]
        )

        with pytest.raises(worksheets.NoReferences) as raised:
            worksheets.create(
                root=data_root,
                corpus_dir=corpus_dir,
                question_set=corpus_mod.find_question_set(data_root, "empty"),
                ingestion=None,
                generated="2026-10-02",
            )

        assert raised.value.question_set == "empty"


class TestRefresh:
    def refresh(self, data_root, corpus_dir):
        return worksheets.refresh(
            root=data_root,
            corpora=[corpus_dir],
            ingestion=None,
            generated="2026-10-02",
        )

    def test_a_current_worksheet_is_left_alone(self, data_root, paired):
        corpus_dir, path = paired
        before = path.read_text()

        done = self.refresh(data_root, corpus_dir)

        assert done == [("corpus/std/worksheet/set.yaml", 2, 0, 0, False)]
        assert path.read_text() == before

    def test_reports_answers_kept_and_dropped(self, data_root, paired):
        corpus_dir, path = paired
        _builders.question_set(data_root, "set", ["NIST SP 800-30"])

        done = self.refresh(data_root, corpus_dir)

        assert done == [("corpus/std/worksheet/set.yaml", 1, 0, 1, True)]
        assert (
            str(yaml.safe_load(path.read_text())["generated"]) == "2026-10-02"
        )


CALLER = rules_mod.Rules.from_mapping(
    {
        "designators": {
            "rewrite": [{"pattern": r"^\s*std\.?\s+", "replace": ""}]
        },
        "references": {"placeholders": ["TBD"]},
        "relations": [{"pattern": r"^amd\d", "label": "amendment"}],
        "attachments": {
            "parent_notes": [
                {"pattern": "^bulletin-", "note": "parent is a bulletin"}
            ]
        },
    }
)


@pytest.mark.parametrize(
    "rules, identifier, expected",
    [
        (rules_mod.BUILTIN_RULES, "ISO 9001 Amd 1", "sub-publication"),
        (CALLER, "ISO 9001 Amd 1", "amendment"),
        (CALLER, "ISO 9001-3", "sub-publication"),  # no caller rule matches
    ],
)
def test_caller_relations_are_tried_first(rules, identifier, expected):
    result = worksheets.relation("iso9001", identifier, rules)

    assert result == expected


@pytest.mark.parametrize(
    "rules, uri, expected",
    [
        (
            rules_mod.BUILTIN_RULES,
            "file:///d/bulletin-7.pdf#attachment=a.pdf",
            "   # attachment",
        ),
        (
            CALLER,
            "file:///d/bulletin-7.pdf#attachment=a.pdf",
            "   # attachment; parent is a bulletin",
        ),
        (CALLER, "file:///d/report.pdf#attachment=a.pdf", "   # attachment"),
    ],
)
def test_parent_notes_mark_matching_attachments(rules, uri, expected):
    result = worksheets._flags(uri, rules)

    assert result == expected


@pytest.mark.parametrize(
    "rules, expected",
    [(rules_mod.BUILTIN_RULES, ["TBD", "ISO 9001"]), (CALLER, ["ISO 9001"])],
)
def test_caller_placeholders_are_not_references(rules, expected):
    cases = make_cases("TBD", "ISO 9001", "[To Be Filled Out]")

    result = worksheets.references(cases, rules)

    assert result == expected


@pytest.mark.parametrize(
    "rules, expected",
    [(rules_mod.BUILTIN_RULES, []), (CALLER, ["file:///downloads/std.pdf"])],
)
def test_identifier_tier_collapses_under_the_rules(rules, expected):
    corpus = make_corpus(doc("std.pdf", "STD 9001", "override"))
    key = designators.collapsed_key("9001", rules)

    found = worksheets.find_candidates(key, set(), corpus, rules)

    assert found["identifier"] == expected


@pytest.mark.parametrize(
    "rules, provenance",
    [
        (rules_mod.BUILTIN_RULES, "built-ins only"),
        (CALLER, "built-ins + caller rules"),
    ],
)
def test_render_records_the_rules_digest(rules, provenance):
    corpus = make_corpus()

    text = render(corpus, make_cases("ISO 9001"), rules=rules)

    line = f"rules: {rules.digest}   # normalization v1, {provenance}"
    assert f"\n{line}\n" in text


def test_render_groups_designators_under_the_rules():
    cases = make_cases("STD. 9001", "9001")

    text = render(make_corpus(), cases, rules=CALLER)

    group = text.split("\n  # 9001\n", 1)[1].split("\n\n", 1)[0]
    assert '- designator: "9001"' in group
    assert '- designator: "STD. 9001"' in group


def test_refresh_regenerates_a_worksheet_made_under_other_rules(
    data_root, paired
):
    corpus_dir, path = paired

    done = worksheets.refresh(
        root=data_root,
        corpora=[corpus_dir],
        ingestion=None,
        generated="2026-10-02",
        rules=CALLER,
    )

    assert done[0][4] is True
    assert f"rules: {CALLER.digest}" in path.read_text()


def test_refresh_flags_a_validated_worksheet_after_a_rules_change(
    data_root, paired
):
    corpus_dir, path = paired
    text = path.read_text().replace(
        "validated_by:      # FILL ME IN", "validated_by: 'A. Person'"
    )
    path.write_text(text)

    worksheets.refresh(
        root=data_root,
        corpora=[corpus_dir],
        ingestion=None,
        generated="2026-10-02",
        rules=CALLER,
    )

    loaded = yaml.safe_load(path.read_text())
    assert loaded["rules"] == CALLER.digest
    assert loaded["validated_against_rules"] == rules_mod.BUILTIN_RULES.digest
