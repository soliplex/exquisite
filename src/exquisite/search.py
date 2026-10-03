"""Searching a haiku-rag database:  the part of `check-retrieval` needing it.

Everything that uses haiku-rag lives here, so `exquisite.retrieval` holds
the checks without it.  Some of what is used sits below haiku-rag's client
(database info, connection mode), which is why the dependency pins a tested
version range.

The database is only ever opened read-only, and a local path that does not
exist is never connected to:  connecting creates an empty database there,
which a mistyped ``--db`` must not leave behind.
"""

import asyncio
import hashlib
import importlib.metadata
import json
import pathlib

from haiku.rag import client as client_mod
from haiku.rag import config as config_mod
from haiku.rag.store import engine
from haiku.rag.store import exceptions
from haiku.rag.store import info as info_mod

from exquisite import retrieval

#: Distributions whose versions decide what a run measured.  The full
#: ``haiku-rag`` distribution depends on the slim one, so both are covered.
SUBSTRATE_DISTRIBUTIONS = ("exquisite", "haiku-rag-slim")

#: Fields `fingerprint` records, all None for a database that isn't there.
FINGERPRINT_FIELDS = (
    "embedder",
    "documents",
    "chunks",
    "written_at",
    "version",
)


class NoDatabase(FileNotFoundError):
    """A local ``--db`` path with nothing there."""

    def __init__(self, location: str):
        self.location = location
        super().__init__(
            f"no database at {location};  not opening it, since that would "
            "create an empty one"
        )


class CannotSearch(RuntimeError):
    """haiku-rag will not search the database as it stands:  it needs
    migrating to the installed version, say, or was stored with settings
    the configuration contradicts."""

    def __init__(self, location: str, reason: Exception):
        self.location = location
        self.reason = reason
        super().__init__(f"cannot search {location}:  {reason}")


#: What haiku-rag raises opening a database it will not search as it stands.
#: Never fixed here:  migrating would write to the database.
REFUSALS = (exceptions.MigrationRequiredError, exceptions.ConfigMismatchError)


def load_config(path: pathlib.Path | None) -> config_mod.AppConfig:
    """A haiku-rag configuration, or haiku-rag's defaults.

    Pointing this at the file the database was ingested with is what makes
    the searches use the same embedder.
    """
    if path is None:
        return config_mod.AppConfig()

    loaded = config_mod.load_yaml_config(path)

    return config_mod.AppConfig.model_validate(loaded)


def for_path(
    config: config_mod.AppConfig,
) -> tuple[config_mod.AppConfig, list[str]]:
    """The configuration, minus any databases it names;  and their names.

    haiku-rag refuses a database path beside configured databases as
    ambiguous, and the point of ``--db`` is to search that one database with
    the configuration otherwise as it is.
    """
    displaced = sorted(config.lancedb.databases)

    if not displaced:
        return config, []

    lancedb = config.lancedb.model_copy(update={"databases": {}})

    return config.model_copy(update={"lancedb": lancedb}), displaced


def is_missing(location: str) -> bool:
    """Whether ``location`` is a local path with nothing there."""
    local = engine.ConnectionMode.of(location) == engine.ConnectionMode.LOCAL

    return local and not pathlib.Path(location).exists()


def config_hash(config: config_mod.AppConfig) -> str:
    """SHA-256 of the resolved configuration."""
    dumped = json.dumps(config.model_dump(mode="json"), sort_keys=True)

    return hashlib.sha256(dumped.encode()).hexdigest()


def settings(config: config_mod.AppConfig, top_k: int) -> dict:
    """How the searches are made:  what a reference must share."""
    embeddings = config.embeddings.model
    reranking = config.reranking.model

    return {
        "embedder": (
            f"{embeddings.provider}:{embeddings.name}"
            f" (dim {embeddings.vector_dim})"
        ),
        "reranker": (
            f"{reranking.provider}:{reranking.name}" if reranking else None
        ),
        "top_k": top_k,
        "config_hash": config_hash(config),
    }


def substrate() -> dict[str, str]:
    """Versions of the packages that decide what a run measured."""
    versions = {}

    for name in SUBSTRATE_DISTRIBUTIONS:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue

    return versions


async def fingerprint(location: str, config: config_mod.AppConfig) -> dict:
    """What a database holds:  the embedder its chunks were stored with, its
    size, and when it was last written."""
    found = await info_mod.gather_database_info(location, config)

    if not found.exists:
        return dict.fromkeys(FINGERPRINT_FIELDS)

    embeddings = found.embeddings
    rows = {table.name: table.num_rows for table in found.tables}
    written = [
        table.latest_version_at
        for table in found.tables
        if table.latest_version_at
    ]

    return {
        "embedder": (
            None
            if embeddings.provider == "unknown"
            else f"{embeddings.provider}:{embeddings.name}"
            f" (dim {embeddings.vector_dim})"
        ),
        "documents": rows.get("documents"),
        "chunks": rows.get("chunks"),
        "written_at": max(written) if written else None,
        "version": found.stored_version,
    }


async def _search(
    location: str,
    config: config_mod.AppConfig,
    questions: list[retrieval.Question],
    top_k: int,
) -> list[list[retrieval.Hit]]:
    found = []

    async with client_mod.HaikuRAG(
        location, config=config, read_only=True
    ) as rag:
        for question in questions:
            results = await rag.search(
                question.question, limit=top_k, include_images=False
            )
            found.append(
                [
                    retrieval.Hit(result.document_uri, result.document_meta)
                    for result in results
                    if result.document_uri
                ]
            )

    return found


def describe(
    location: str, config: config_mod.AppConfig, top_k: int
) -> tuple[dict, dict]:
    """``(settings, fingerprint)`` for searching ``location``.

    Raises `NoDatabase` rather than look at a local path with nothing there.
    """
    if is_missing(location):
        raise NoDatabase(location)

    found = asyncio.run(fingerprint(location, config))

    return settings(config, top_k), {"location": location, **found}


def search(
    location: str,
    config: config_mod.AppConfig,
    questions: list[retrieval.Question],
    top_k: int,
) -> list[list[retrieval.Hit]]:
    """One search per question, returning its top ``top_k`` hits."""
    if is_missing(location):
        raise NoDatabase(location)

    try:
        return asyncio.run(_search(location, config, questions, top_k))
    except REFUSALS as exc:
        raise CannotSearch(location, exc) from exc
