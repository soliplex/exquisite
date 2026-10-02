"""Unit tests for `exquisite.designators`."""

import pytest

from exquisite.designators import collapsed_key, extension


class TestCollapsedKey:
    @pytest.mark.parametrize(
        "a, b",
        [
            ("ISO 9001 Supplement", "ISO 9001 SUPP"),
            ("ISO 9001 Suppl", "ISO 9001 SUPP"),
            ("ISO_9001_Sup", "ISO 9001 SUPP"),
            ("IEC 61508 Volume 3", "IEC 61508 V3"),
            ("NIST SP 800-53 Vol. 2", "NIST SP 800-53 V2"),
            ("ISO/IEC 27001:2022", "ISO IEC 27001 2022"),
        ],
    )
    def test_folds_spellings_identify_normalizes(self, a, b):
        # The right-hand spellings are the forms `identify` writes.
        result = collapsed_key(a)

        assert result == collapsed_key(b)

    def test_leaves_words_merely_starting_with_sup_alone(self):
        result = collapsed_key("Support Manual")

        assert result == "supportmanual"


class TestExtension:
    @pytest.mark.parametrize(
        "designator, identifier, expected",
        [
            ("IEC 61508", "IEC 61508-3 Supplement", "3supp"),
            ("IEC 61508", "IEC 61508-3", "3"),
            ("NIST SP 800-53", "NIST SP 800-53A", "a"),
            ("IEC 61508", "IEC 61508 V3", "v3"),
        ],
    )
    def test_returns_what_extends_the_key_at_a_boundary(
        self, designator, identifier, expected
    ):
        result = extension(collapsed_key(designator), identifier)

        assert result == expected

    @pytest.mark.parametrize(
        "designator, identifier",
        [
            ("NIST SP 800-5", "NIST SP 800-53"),  # a different number, not a part
            ("NIST SP 800-53A", "NIST SP 800-53AB"),  # a different word
            ("IEC 61508", "IEC 61508"),  # identical, not extended
            ("ISO 9001", "NIST SP 800-53"),  # unrelated
        ],
    )
    def test_refuses_what_only_shares_a_prefix(self, designator, identifier):
        result = extension(collapsed_key(designator), identifier)

        assert result is None
