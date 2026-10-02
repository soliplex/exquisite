"""Unit tests for `exquisite.bind`."""

from exquisite import bind
from exquisite.worksheets import PROVISIONAL


def worksheet(**entry):
    return {
        "designators": [{"designator": "NIST SP 800-61", **entry}],
        "apply_keys": {"NIST SP 800-61": "NIST SP 800-61"},
    }


class TestCheck:
    def test_refuses_a_provisional_answer(self):
        sheet = worksheet(
            documents=[{"name": "sp800-61.pdf", "sha256": "h"}],
            **{PROVISIONAL: "identifier match (llm certainty 5): NIST SP 800-61"},
        )

        problems = bind.check(sheet)

        assert problems == [
            "'NIST SP 800-61': provisional answer not yet confirmed -- check it, "
            f"then delete its `{PROVISIONAL}:` line"
        ]

    def test_accepts_it_once_the_line_is_deleted(self):
        sheet = worksheet(documents=[{"name": "sp800-61.pdf", "sha256": "h"}])

        problems = bind.check(sheet)

        assert problems == []
