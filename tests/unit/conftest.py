import pytest


@pytest.fixture
def data_root(tmp_path):
    """An empty data repository:  ``questions/`` and ``corpus/``."""
    (tmp_path / "questions").mkdir()
    (tmp_path / "corpus").mkdir()

    return tmp_path
