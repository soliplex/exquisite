"""Unit tests for `exquisite.search`:  the haiku-rag side of the check.

No database is opened and no embedder called:  haiku-rag's client and its
database info are replaced with fakes.
"""

import importlib.metadata

import pytest
from haiku.rag import config as config_mod
from haiku.rag.store import exceptions
from haiku.rag.store import info as info_mod
from haiku.rag.store.models import chunk

from exquisite import retrieval
from exquisite import search

CONFIG = """\
embeddings:
  model:
    provider: vllm
    name: embedder-1b
    vector_dim: 2048
lancedb:
  databases:
    prod: /srv/prod.lancedb
    stage: /srv/stage.lancedb
"""


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "haiku.rag.yaml"
    path.write_text(CONFIG)

    return path


@pytest.fixture
def database(tmp_path):
    """A local path with something there (what, doesn't matter)."""
    path = tmp_path / "db.lancedb"
    path.mkdir()

    return str(path)


def test_load_config_defaults_to_haiku_rags_own():
    result = search.load_config(None)

    assert result == config_mod.AppConfig()


def test_load_config_reads_a_file(config_file):
    result = search.load_config(config_file)

    assert result.embeddings.model.name == "embedder-1b"


def test_for_path_drops_and_names_configured_databases(config_file):
    config = search.load_config(config_file)

    result, displaced = search.for_path(config)

    assert result.lancedb.databases == {}
    assert result.embeddings == config.embeddings
    assert displaced == ["prod", "stage"]


def test_for_path_keeps_a_configuration_naming_none():
    config = config_mod.AppConfig()

    result, displaced = search.for_path(config)

    assert result is config
    assert displaced == []


def test_is_missing_a_local_path_with_nothing_there(tmp_path):
    result = search.is_missing(str(tmp_path / "typo.lancedb"))

    assert result


def test_is_missing_not_a_local_path_with_something_there(database):
    result = search.is_missing(database)

    assert not result


def test_is_missing_never_a_remote_location():
    result = search.is_missing("s3://bucket/typo.lancedb")

    assert not result


def test_config_hash_is_stable_and_follows_the_settings(config_file):
    default = search.config_hash(config_mod.AppConfig())

    result = search.config_hash(search.load_config(config_file))

    assert len(result) == 64
    assert result != default
    assert search.config_hash(config_mod.AppConfig()) == default


@pytest.mark.parametrize(
    "reranking, expected",
    [
        (None, None),
        (
            {"model": {"provider": "vllm", "name": "ranker"}},
            "vllm:ranker",
        ),
    ],
)
def test_settings(config_file, reranking, expected):
    config = search.load_config(config_file)

    if reranking is not None:
        config = config.model_copy(
            update={
                "reranking": config_mod.RerankingConfig(**reranking),
            }
        )

    result = search.settings(config, 30)

    assert result == {
        "embedder": "vllm:embedder-1b (dim 2048)",
        "reranker": expected,
        "top_k": 30,
        "config_hash": search.config_hash(config),
    }


def test_substrate_skips_what_is_not_installed(monkeypatch):
    monkeypatch.setattr(
        search, "SUBSTRATE_DISTRIBUTIONS", ("exquisite", "no-such-thing")
    )

    result = search.substrate()

    assert result == {"exquisite": importlib.metadata.version("exquisite")}


def gathered(found):
    """A stand-in for `gather_database_info`, returning ``found``."""

    async def gather(location, config):
        return found

    return gather


PRESENT = info_mod.DatabaseInfo(
    path="db",
    exists=True,
    stored_version="0.89.0",
    embeddings=info_mod.EmbeddingsInfo(
        provider="vllm", name="embedder-1b", vector_dim=2048
    ),
    tables=[
        info_mod.TableInfo(
            name="documents",
            exists=True,
            num_rows=8,
            latest_version_at="2026-10-03T01:54:08",
        ),
        info_mod.TableInfo(
            name="chunks",
            exists=True,
            num_rows=5502,
            latest_version_at="2026-10-03T01:54:07",
        ),
        info_mod.TableInfo(name="settings", exists=True, num_rows=1),
    ],
)


@pytest.mark.parametrize(
    "found, expected",
    [
        (
            PRESENT,
            {
                "embedder": "vllm:embedder-1b (dim 2048)",
                "documents": 8,
                "chunks": 5502,
                "written_at": "2026-10-03T01:54:08",
                "version": "0.89.0",
            },
        ),
        (
            info_mod.DatabaseInfo(path="db", exists=True),
            {
                "embedder": None,
                "documents": None,
                "chunks": None,
                "written_at": None,
                "version": "unknown",
            },
        ),
        (
            info_mod.DatabaseInfo(path="db", exists=False),
            dict.fromkeys(search.FINGERPRINT_FIELDS),
        ),
    ],
)
def test_describe(monkeypatch, database, found, expected):
    monkeypatch.setattr(info_mod, "gather_database_info", gathered(found))
    config = config_mod.AppConfig()

    settings, fingerprint = search.describe(database, config, 10)

    assert settings == search.settings(config, 10)
    assert fingerprint == {"location": database, **expected}


@pytest.mark.parametrize(
    "act",
    [
        lambda location, config: search.describe(location, config, 10),
        lambda location, config: search.search(location, config, [], 10),
    ],
    ids=["describe", "search"],
)
def test_a_missing_local_database_is_never_opened(tmp_path, act):
    location = str(tmp_path / "typo.lancedb")

    with pytest.raises(search.NoDatabase) as raised:
        act(location, config_mod.AppConfig())

    assert raised.value.location == location
    assert not (tmp_path / "typo.lancedb").exists()


def result(uri, **meta):
    return chunk.SearchResult(
        content="text", score=0.5, document_uri=uri, document_meta=meta
    )


class FakeRAG:
    """Stands in for `HaikuRAG`:  answers each question from ``answers``."""

    def __init__(self, answers, refusal=None):
        self.answers = answers
        self.refusal = refusal
        self.opened = []
        self.searched = []

    def __call__(self, location, **options):
        self.opened.append((location, options))

        return self

    async def __aenter__(self):
        if self.refusal is not None:
            raise self.refusal

        return self

    async def __aexit__(self, *exc_info):
        return None

    async def search(self, question, **options):
        self.searched.append((question, options))

        return self.answers[question]


def test_search_returns_each_questions_hits(monkeypatch, database):
    rag = FakeRAG(
        {
            "q1": [result("file:///a.pdf", sha256="h"), result(None)],
            "q2": [],
        }
    )
    monkeypatch.setattr(search.client_mod, "HaikuRAG", rag)
    config = config_mod.AppConfig()
    asked = [retrieval.Question("k1", "q1"), retrieval.Question("k2", "q2")]

    found = search.search(database, config, asked, 7)

    assert found == [[retrieval.Hit("file:///a.pdf", {"sha256": "h"})], []]
    assert rag.opened == [(database, {"config": config, "read_only": True})]
    assert rag.searched == [
        ("q1", {"limit": 7, "include_images": False}),
        ("q2", {"limit": 7, "include_images": False}),
    ]


@pytest.mark.parametrize(
    "refusal",
    [
        exceptions.MigrationRequiredError("migrate from 0.89.0 to 0.92.0"),
        exceptions.ConfigMismatchError("stored with another embedder"),
    ],
)
def test_search_reports_a_database_haiku_rag_refuses(
    monkeypatch, database, refusal
):
    monkeypatch.setattr(
        search.client_mod, "HaikuRAG", FakeRAG({}, refusal=refusal)
    )

    with pytest.raises(search.CannotSearch) as raised:
        search.search(database, config_mod.AppConfig(), [], 7)

    assert raised.value.reason is refusal
    assert str(raised.value) == f"cannot search {database}:  {refusal}"
