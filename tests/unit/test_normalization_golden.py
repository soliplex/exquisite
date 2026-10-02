"""Built-in normalization output, pinned to `NORMALIZATION_VERSION`.

Worksheets record a digest of the rules in effect, and the digest includes
`exquisite.rules.NORMALIZATION_CHANGES`.  Its latest entry is the only thing
that tells a refresh that the built-in normalization -- its tables *or* its
logic -- now groups designators differently.  Nothing else forces an entry to
be added, so this test does:  it runs the built-in rules over samples chosen
for their edge cases, and checks the output against the hash recorded for the
current version.

When this fails because a change to normalization was intended:

1. add an entry to `NORMALIZATION_CHANGES` saying what changed and why
   (which makes it the new `NORMALIZATION_VERSION`);
2. add an entry to `GOLDEN` for the same version, with the hash the failure
   reports;
3. note in the release that worksheets regenerate on their next refresh,
   and that validated ones are flagged for re-validation.

Never edit an existing entry in either:  each records what a released
version did.
A case missing here can still change unnoticed, so when a change exposes one,
add it to the samples -- which itself changes the hash, and so the version.
"""

import hashlib
import json

from exquisite import designators
from exquisite import rules
from exquisite import worksheets

#: The hash of `_outputs()` under each released normalization version.
GOLDEN = {
    1: "e29c65e48b543326",
}

DESIGNATORS = [
    "ISO/IEC 27001:2022 Sec 6.1.2",
    "Ref: ISO 9001, Clause 4",
    "IEC 61508–3 Table 2",  # an en dash
    "NIST SP 800-53 Rev. 5 Chapter 3",
    "ISO 9001; Annex A",
    "RFC 9110 §8.3",  # no built-in location word
    "Section 8.3 of RFC 9110",  # location first:  nothing survives
    "file:///downloads/iso%209001.pdf",
    "file:///downloads/iec.pdf#attachment=Annex%20A.pdf",
]

KEYS = [
    "ISO_9001 Suppl",
    "ISO 9001 Sup",
    "IEC 61508 Volume 3",
    "NIST SP 800-53 Vol. 2",
    "ISO/IEC 27001:2022",
    "Support Manual",
]

EXTENSIONS = [
    ("IEC 61508", "IEC 61508-3"),
    ("IEC 61508", "IEC 61508-3 Supplement"),
    ("IEC 61508", "IEC 61508 V3"),
    ("NIST SP 800-53", "NIST SP 800-53A"),
    ("NIST SP 800-5", "NIST SP 800-53"),
    ("NIST SP 800-53A", "NIST SP 800-53AB"),
    ("IEC 61508", "IEC 61508"),
    ("IEC 61508", "IEC 615"),
]

SERIES = [
    "nist-incident-handling.pdf",
    "61508-3",
    "ISO 9001",
    "isoiec-27001.pdf",
]

RELATIONS = [
    ("IEC 61508", "IEC 61508 Vol 2"),
    ("IEC 61508", "IEC 61508 Supplement"),
    ("IEC 61508", "IEC 61508-3 Supplement"),
    ("IEC 61508", "IEC 61508-3"),
    ("IEC 61508", "IEC 61509"),
]


def _outputs() -> dict:
    """What the built-in rules make of every sample."""
    return {
        "designator": [designators.designator(text) for text in DESIGNATORS],
        "collapsed_key": [designators.collapsed_key(text) for text in KEYS],
        "extension": [
            designators.extension(designators.collapsed_key(key), text)
            for key, text in EXTENSIONS
        ],
        "series": [designators.series(name) for name in SERIES],
        "relation": [
            worksheets.relation(designators.collapsed_key(key), text)
            for key, text in RELATIONS
        ],
    }


def test_builtin_normalization_matches_its_version():
    outputs = _outputs()

    found = hashlib.sha256(
        json.dumps(outputs, sort_keys=True).encode()
    ).hexdigest()[:16]

    assert GOLDEN.get(rules.NORMALIZATION_VERSION) == found, (
        f"built-in normalization output hashes to {found!r}, but "
        f"GOLDEN[{rules.NORMALIZATION_VERSION}] is "
        f"{GOLDEN.get(rules.NORMALIZATION_VERSION)!r}.  "
        "If the change is intended, add a NORMALIZATION_CHANGES entry and "
        "record this hash as the matching GOLDEN entry; see this module's "
        "docstring."
    )


def test_every_version_has_a_note_and_a_hash():
    versions = sorted(rules.NORMALIZATION_CHANGES)

    assert versions == sorted(GOLDEN)
    assert versions == list(range(1, rules.NORMALIZATION_VERSION + 1))
    assert all(note.strip() for note in rules.NORMALIZATION_CHANGES.values())
