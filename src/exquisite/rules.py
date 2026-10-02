"""Normalization rules:  the built-ins, extended by the data repository's own.

The built-in rules cover only conventions that hold across publishers:  dash
folding, ``Vol 3`` for ``v3``, supplement spellings, the words that begin a
citation's location, and the placeholder a question set leaves where a
reference belongs.  A corpus following a publisher's own scheme -- a series
renamed over time, a prefix some citations carry and others omit, an extra
kind of sub-publication, a filename marking a container document -- supplies
the rest in an ``exquisite.yaml`` beside ``questions/`` and ``corpus/``::

    designators:
      rewrite:            # regex -> replacement, applied in order
        - {pattern: '^\\s*std\\.?\\s+', replace: ''}
      series:             # canonical series: names it has also gone by
        oldname: [newname, interim]
      location_words: [clause, annex]
    references:
      placeholders: ["TBD"]
    relations:            # extra kinds of extension, matched on the remainder
      - {pattern: '^amd\\d', label: amendment}
    attachments:
      parent_notes:       # note on attachments whose parent filename matches
        - {pattern: '^bulletin-', note: 'parent is a bulletin'}

Caller rules *extend* the built-ins, never replace them:  rewrites run before
the built-in folding, and relations are tried before the built-in
``supplement`` / ``volume`` / ``sub-publication``.  Every pattern is compiled
once, case-insensitively, when the file is loaded;  an unknown key or a bad
pattern is refused with the key that holds it, never skipped.

A worksheet records a digest of the rules in effect -- the built-ins *and* the
caller's -- so a release that changes the built-ins changes the digest too.
The built-in tables below are digested as data, along with
`NORMALIZATION_CHANGES`, which gains an entry whenever built-in output
changes.
"""

import functools
import hashlib
import json
import re
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

#: The rules file, at the root of a data repository.
FILENAME = "exquisite.yaml"

#: What each generation of the built-in normalization changed, and why.  Add
#: an entry whenever what the built-ins produce changes -- an edit to the
#: tables below, or to logic they do not capture, such as
#: `designators.extension`'s boundary test or where a citation's location is
#: cut off.  `tests/unit/test_normalization_golden.py` pins the output of each
#: version and fails until the entry is made.
#:
#: Append-only:  each entry describes what a released version did, so never
#: reword or remove one.  The notes are digested along with everything else,
#: so editing one changes every worksheet's `rules:` digest.
NORMALIZATION_CHANGES = {
    1: (
        "Initial built-ins: dash folding; 'Vol'/'Volume' and supplement "
        "spellings folded; generic location words; the '[To Be Filled Out]' "
        "placeholder; supplement, volume and sub-publication relations."
    ),
}

#: The current generation:  the latest entry in `NORMALIZATION_CHANGES`.
NORMALIZATION_VERSION = max(NORMALIZATION_CHANGES)

#: Built-in rewrites, ``(pattern, replacement)``, applied after a caller's.
BUILTIN_REWRITES = (
    (r"\bvol(?:ume)?\.?\s*", "v"),  # "Vol 3" -> "v3"
    # "Supplement", "Suppl", "Sup" -> "supp", as `identify` writes it.
    (r"\b(?:sup|supp|suppl|supplement)\b", "supp"),
)

#: Built-in relations, ``(pattern, label)``, tried after a caller's.  The
#: last matches anything:  an extension that is nothing more specific is a
#: sub-publication.
BUILTIN_RELATIONS = (
    ("supp", "supplement"),
    (r"^v\d", "volume"),
    ("", "sub-publication"),
)

#: Words that begin the *location* half of a citation.
BUILTIN_LOCATION_WORDS = (
    "chap",
    "chapter",
    "para",
    "paragraph",
    "pg",
    "pgs",
    "page",
    "pages",
    "table",
    "figure",
    "fig",
    r"attach\w*",
    "attch",
    "att",
    "sec",
    "section",
    "note",
)

#: Values a question set leaves where a reference belongs.
BUILTIN_PLACEHOLDERS = frozenset({"", "[To Be Filled Out]"})

#: Every key a rules file may hold, by section.
_SCHEMA = {
    "designators": {"rewrite", "series", "location_words"},
    "references": {"placeholders"},
    "relations": None,
    "attachments": {"parent_notes"},
}


class RulesError(ValueError):
    """A rules file that cannot be used as it stands."""


class UnknownRulesKey(RulesError):
    """A key the rules format does not define:  a typo, most likely."""

    def __init__(self, key: str):
        self.key = key
        super().__init__(f"unknown key {key!r} in the rules")


class MalformedRules(RulesError):
    """A value of the wrong shape."""

    def __init__(self, key: str, expected: str):
        self.key = key
        self.expected = expected
        super().__init__(f"{key} must be {expected}")


class RulesNotAMapping(RulesError):
    """A rules file whose top level is not a mapping."""

    def __init__(self):
        super().__init__("the rules must be a mapping")


class InvalidPattern(RulesError):
    """A pattern that does not compile."""

    def __init__(self, key: str, pattern: str, reason: str):
        self.key = key
        self.pattern = pattern
        super().__init__(f"{key}: invalid pattern {pattern!r}: {reason}")


@dataclass(frozen=True)
class Rewrite:
    pattern: re.Pattern
    replace: str


@dataclass(frozen=True)
class Relation:
    pattern: re.Pattern
    label: str


@dataclass(frozen=True)
class ParentNote:
    pattern: re.Pattern
    note: str


@dataclass(frozen=True)
class Rules:
    """The rules in effect:  the built-ins plus a caller's, compiled."""

    rewrite: tuple[Rewrite, ...] = ()
    #: ``(alias, canonical)`` pairs:  a series named by an alias is the
    #: canonical one.
    series: tuple[tuple[str, str], ...] = ()
    location_words: tuple[str, ...] = ()
    placeholders: frozenset[str] = frozenset()
    relations: tuple[Relation, ...] = ()
    parent_notes: tuple[ParentNote, ...] = ()
    #: The caller's rules as written, for the digest.
    source: dict = field(default_factory=dict, compare=False, hash=False)

    @classmethod
    def default(cls) -> "Rules":
        """The built-in rules alone."""
        return BUILTIN_RULES

    @classmethod
    def load(cls, path: Path) -> "Rules":
        """The built-ins extended by the rules file at ``path``."""
        import yaml

        return cls.from_mapping(yaml.safe_load(path.read_text()) or {})

    @classmethod
    def from_mapping(cls, data) -> "Rules":
        """The built-ins extended by ``data``, a rules file's contents."""
        _check_keys(data)
        designators = data.get("designators") or {}
        references = data.get("references") or {}
        attachments = data.get("attachments") or {}

        return cls(
            rewrite=tuple(
                Rewrite(pattern, replace)
                for pattern, replace in _entries(
                    designators, "rewrite", "replace", prefix="designators"
                )
            ),
            series=_series(designators.get("series") or {}),
            location_words=tuple(
                re.escape(word)
                for word in _strings(
                    designators, "location_words", prefix="designators"
                )
            ),
            placeholders=frozenset(
                _strings(references, "placeholders", prefix="references")
            ),
            relations=tuple(
                Relation(pattern, label)
                for pattern, label in _entries(data, "relations", "label")
            ),
            parent_notes=tuple(
                ParentNote(pattern, note)
                for pattern, note in _entries(
                    attachments, "parent_notes", "note", prefix="attachments"
                )
            ),
            source=data,
        )

    @property
    def effective_rewrites(self) -> tuple[Rewrite, ...]:
        """The caller's rewrites, then the built-in ones."""
        return self.rewrite + _BUILTIN_REWRITES

    @property
    def effective_relations(self) -> tuple[Relation, ...]:
        """The caller's relations, then the built-in ones."""
        return self.relations + _BUILTIN_RELATIONS

    @functools.cached_property
    def location(self) -> re.Pattern:
        """Where the location half of a citation begins."""
        words = "|".join((*BUILTIN_LOCATION_WORDS, *self.location_words))

        return re.compile(rf"[,;]|\b(?:{words})\b", re.I)

    @property
    def not_references(self) -> frozenset[str]:
        """Values that stand where a reference belongs but are none."""
        return BUILTIN_PLACEHOLDERS | self.placeholders

    def canonical_series(self, name: str) -> str:
        """The series ``name`` is, once its aliases are resolved."""
        return dict(self.series).get(name, name)

    @property
    def digest(self) -> str:
        """A short digest of the rules in effect, recorded on worksheets.

        Rules decide how designators are grouped, so a worksheet generated
        under different ones is a different worksheet;  recording which
        makes that visible instead of a silent regrouping.  The digest
        covers the built-ins and `NORMALIZATION_CHANGES` as well as the
        caller's rules, so it moves when a release changes normalization,
        not only when ``exquisite.yaml`` does.
        """
        payload = json.dumps(
            {
                "changes": NORMALIZATION_CHANGES,
                "builtin": _BUILTIN_SOURCE,
                "caller": self.source,
            },
            sort_keys=True,
        )

        return hashlib.sha256(payload.encode()).hexdigest()[:12]

    @property
    def provenance(self) -> str:
        """Which rules are in effect, for a person reading a worksheet."""
        return "built-ins + caller rules" if self.source else "built-ins only"


_BUILTIN_REWRITES = tuple(
    Rewrite(re.compile(pattern, re.I), replace)
    for pattern, replace in BUILTIN_REWRITES
)

_BUILTIN_RELATIONS = tuple(
    Relation(re.compile(pattern, re.I), label)
    for pattern, label in BUILTIN_RELATIONS
)

#: The built-in tables, as the digest sees them.
_BUILTIN_SOURCE = {
    "rewrite": BUILTIN_REWRITES,
    "location_words": BUILTIN_LOCATION_WORDS,
    "placeholders": sorted(BUILTIN_PLACEHOLDERS),
    "relations": BUILTIN_RELATIONS,
}

#: The built-in rules alone:  the default wherever rules are taken.
BUILTIN_RULES = Rules()


def find(root: Path, path: Path | None = None) -> Rules:
    """The rules for the data repository at ``root``.

    ``path`` names a rules file explicitly, and must exist;  without it,
    ``exquisite.yaml`` at the root is used when present, and the built-ins
    alone when not.
    """
    if path is not None:
        return Rules.load(path)

    default = root / FILENAME

    return Rules.load(default) if default.exists() else Rules.default()


def _check_keys(data) -> None:
    if not isinstance(data, dict):
        raise RulesNotAMapping()

    for section, value in data.items():
        if section not in _SCHEMA:
            raise UnknownRulesKey(section)

        allowed = _SCHEMA[section]

        if allowed is None or value is None:
            continue

        if not isinstance(value, dict):
            raise MalformedRules(section, "a mapping")

        for key in value:
            if key not in allowed:
                raise UnknownRulesKey(f"{section}.{key}")


def _list(section: dict, key: str, prefix: str | None) -> tuple[str, list]:
    name = f"{prefix}.{key}" if prefix else key
    value = section.get(key) or []

    if not isinstance(value, list):
        raise MalformedRules(name, "a list")

    return name, value


def _strings(section: dict, key: str, *, prefix: str) -> list[str]:
    name, value = _list(section, key, prefix)

    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise MalformedRules(f"{name}[{index}]", "a string")

    return value


def _entries(section: dict, key: str, field_: str, *, prefix=None) -> list:
    """``(compiled pattern, field)`` for each ``{pattern, field}`` entry."""
    name, value = _list(section, key, prefix)
    found = []

    for index, item in enumerate(value):
        where = f"{name}[{index}]"

        if (
            not isinstance(item, dict)
            or set(item) != {"pattern", field_}
            or not all(isinstance(text, str) for text in item.values())
        ):
            raise MalformedRules(
                where, f"a mapping of 'pattern' and {field_!r} strings"
            )

        try:
            compiled = re.compile(item["pattern"], re.I)
        except re.error as exc:
            raise InvalidPattern(where, item["pattern"], str(exc)) from exc

        found.append((compiled, item[field_]))

    return found


def _series(value) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, dict):
        raise MalformedRules("designators.series", "a mapping")

    pairs = []

    for canonical, aliases in value.items():
        where = f"designators.series.{canonical}"

        if not isinstance(aliases, list) or not all(
            isinstance(alias, str) for alias in aliases
        ):
            raise MalformedRules(where, "a list of strings")

        pairs += [
            (alias.casefold(), canonical.casefold()) for alias in aliases
        ]

    return tuple(pairs)
