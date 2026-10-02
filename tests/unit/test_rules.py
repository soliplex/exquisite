"""Unit tests for `exquisite.rules`."""

import hashlib
import json

import pytest

from exquisite import rules

EXAMPLE = {
    "designators": {
        "rewrite": [{"pattern": r"^\s*std\.?\s+", "replace": ""}],
        "series": {"OldName": ["NewName", "interim"]},
        "location_words": ["clause", "annex"],
    },
    "references": {"placeholders": ["TBD"]},
    "relations": [{"pattern": r"^amd\d", "label": "amendment"}],
    "attachments": {
        "parent_notes": [
            {"pattern": "^bulletin-", "note": "parent is a bulletin"}
        ]
    },
}


def test_default_is_the_builtins_alone():
    found = rules.Rules.default()

    assert found is rules.BUILTIN_RULES
    assert found.provenance == "built-ins only"
    assert found.not_references == rules.BUILTIN_PLACEHOLDERS
    assert found.canonical_series("iso") == "iso"


def test_from_mapping_compiles_every_kind_of_rule():
    found = rules.Rules.from_mapping(EXAMPLE)

    assert [r.replace for r in found.rewrite] == [""]
    assert found.rewrite[0].pattern.search("STD. 12")
    assert found.series == (("newname", "oldname"), ("interim", "oldname"))
    assert found.location_words == ("clause", "annex")
    assert found.placeholders == frozenset({"TBD"})
    assert [r.label for r in found.relations] == ["amendment"]
    assert [n.note for n in found.parent_notes] == ["parent is a bulletin"]


def test_builtin_digest_is_pinned():
    # This fails whenever the built-in tables or `NORMALIZATION_CHANGES`
    # change.  That is the point:  a new digest regenerates every worksheet
    # on its next refresh, and flags validated ones for re-validation, so it
    # should be a deliberate change noted in the release.  Update the value
    # here when it is.  `test_normalization_golden` is what forces a new
    # `NORMALIZATION_CHANGES` entry when built-in output changes.
    result = rules.BUILTIN_RULES.digest

    assert result == "a6597c4a4571"


def test_digest_covers_version_builtins_and_caller_in_any_key_order():
    found = rules.Rules.from_mapping(dict(reversed(EXAMPLE.items())))

    payload = {
        "changes": rules.NORMALIZATION_CHANGES,
        "builtin": {
            "rewrite": rules.BUILTIN_REWRITES,
            "location_words": rules.BUILTIN_LOCATION_WORDS,
            "placeholders": sorted(rules.BUILTIN_PLACEHOLDERS),
            "relations": rules.BUILTIN_RELATIONS,
        },
        "caller": EXAMPLE,
    }
    canonical = json.dumps(payload, sort_keys=True).encode()
    assert found.digest == hashlib.sha256(canonical).hexdigest()[:12]
    assert found.provenance == "built-ins + caller rules"


def test_effective_rules_put_the_callers_first():
    found = rules.Rules.from_mapping(EXAMPLE)

    rewrites = [r.replace for r in found.effective_rewrites]
    labels = [r.label for r in found.effective_relations]

    assert rewrites == ["", "v", "supp"]
    assert labels == ["amendment", "supplement", "volume", "sub-publication"]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("ISO 9001 Clause 4", 9),
        ("ISO 9001 Annex A", 9),
        ("ISO 9001 Sec 4", 9),
        ("ISO 9001", None),
    ],
)
def test_location_extends_the_builtin_words(text, expected):
    found = rules.Rules.from_mapping(EXAMPLE)

    match = found.location.search(text)

    assert (match.start() if match else None) == expected


def test_location_words_are_literal_not_patterns():
    found = rules.Rules.from_mapping(
        {"designators": {"location_words": ["a.b"]}}
    )

    match = found.location.search("ISO axb")

    assert match is None


@pytest.mark.parametrize(
    "name, expected",
    [("newname", "oldname"), ("interim", "oldname"), ("other", "other")],
)
def test_canonical_series_resolves_aliases(name, expected):
    found = rules.Rules.from_mapping(EXAMPLE)

    result = found.canonical_series(name)

    assert result == expected


def test_not_references_adds_to_the_builtins():
    found = rules.Rules.from_mapping(EXAMPLE)

    result = found.not_references

    assert result == rules.BUILTIN_PLACEHOLDERS | {"TBD"}


def test_an_empty_section_is_allowed():
    found = rules.Rules.from_mapping({"designators": None})

    assert found.rewrite == ()
    assert found.digest != rules.BUILTIN_RULES.digest


@pytest.mark.parametrize(
    "text, provenance",
    [
        ("", "built-ins only"),
        ("references:\n  placeholders: [TBD]\n", "built-ins + caller rules"),
    ],
)
def test_load_reads_a_file(tmp_path, text, provenance):
    path = tmp_path / rules.FILENAME
    path.write_text(text)

    found = rules.Rules.load(path)

    assert found.provenance == provenance


def test_find_uses_an_explicit_path(tmp_path):
    path = tmp_path / "elsewhere.yaml"
    path.write_text("references:\n  placeholders: [TBD]\n")

    found = rules.find(tmp_path, path)

    assert found.placeholders == frozenset({"TBD"})


def test_find_uses_the_root_file_when_present(tmp_path):
    (tmp_path / rules.FILENAME).write_text(
        "references:\n  placeholders: [X]\n"
    )

    found = rules.find(tmp_path)

    assert found.placeholders == frozenset({"X"})


def test_find_falls_back_to_the_builtins(tmp_path):
    found = rules.find(tmp_path)

    assert found is rules.BUILTIN_RULES


def test_find_refuses_a_missing_explicit_path(tmp_path):
    with pytest.raises(FileNotFoundError):
        rules.find(tmp_path, tmp_path / "absent.yaml")


@pytest.mark.parametrize(
    "data, error, message",
    [
        (["rewrite"], rules.RulesNotAMapping, "the rules must be a mapping"),
        ({"designator": {}}, rules.UnknownRulesKey, "'designator'"),
        (
            {"designators": {"rewrites": []}},
            rules.UnknownRulesKey,
            "'designators.rewrites'",
        ),
        (
            {"designators": []},
            rules.MalformedRules,
            "designators must be a mapping",
        ),
        (
            {"relations": {"pattern": "x"}},
            rules.MalformedRules,
            "relations must be a list",
        ),
        (
            {"relations": [{"pattern": "x"}]},
            rules.MalformedRules,
            "relations[0] must be a mapping of 'pattern' and 'label' strings",
        ),
        (
            {"relations": [{"pattern": "x", "label": "y", "note": "z"}]},
            rules.MalformedRules,
            "relations[0] must be a mapping",
        ),
        (
            {"relations": [{"pattern": "x", "label": 3}]},
            rules.MalformedRules,
            "relations[0] must be a mapping",
        ),
        (
            {"relations": ["x"]},
            rules.MalformedRules,
            "relations[0] must be a mapping",
        ),
        (
            {"designators": {"rewrite": [{"pattern": "(", "replace": ""}]}},
            rules.InvalidPattern,
            "designators.rewrite[0]: invalid pattern '('",
        ),
        (
            {"designators": {"location_words": "clause"}},
            rules.MalformedRules,
            "designators.location_words must be a list",
        ),
        (
            {"references": {"placeholders": [None]}},
            rules.MalformedRules,
            "references.placeholders[0] must be a string",
        ),
        (
            {"designators": {"series": ["x"]}},
            rules.MalformedRules,
            "designators.series must be a mapping",
        ),
        (
            {"designators": {"series": {"x": "y"}}},
            rules.MalformedRules,
            "designators.series.x must be a list of strings",
        ),
        (
            {"designators": {"series": {"x": [1]}}},
            rules.MalformedRules,
            "designators.series.x must be a list of strings",
        ),
    ],
)
def test_refuses_what_it_cannot_use(data, error, message):
    with pytest.raises(error) as raised:
        rules.Rules.from_mapping(data)

    assert message in str(raised.value)
    assert isinstance(raised.value, rules.RulesError)
