"""A corpus manifest: what one ingestion of a corpus contains.

Two files that are a pair, sharing a stem:

    ingestion/<corpus_name>.csv    one row per document, every field quoted
    ingestion/<corpus_name>.yaml   what this ingestion is; where it came from

The CSV is purely tabular --
``"uri","sha256","source_url","document_identifier"`` -- because a table is
what diffs well:  one line per document means a re-ingest adding three
documents is a three-line diff.  Everything that describes the ingestion as a
whole (the source database and its path, when it was extracted, and the
embedding and chunking substrate it was built with) lives in the YAML sidecar,
where it is written once instead of being smeared across every row.

The sidecar's ``documents:`` count must match the CSV's row count.  That is
cheap and catches a truncated extraction, which would otherwise look exactly
like a corpus that had shrunk.

Quoting is unconditional so that an empty column is visibly `""` rather than
inferred from delimiter counting -- these manifests are committed and read as
diffs, and some ingestions record no hashes at all while others record no
source URLs, so empty columns are routine rather than exotic.

`uri` is where *this* ingestion put the document, and is the only column that
is not durable -- re-ingesting under a different source root rewrites every
one of them, which is how labels recorded as URIs silently stop matching
anything.  `sha256` and `source_url` survive that; a worksheet records
those, and binding resolves them back to whatever `uri` the current ingestion
uses.

Neither durable column is universally populated, but a document needs at
least one of them:  the pair is complete where either alone is not.

`document_identifier` is the publication designator (`"ISO/IEC 27001:2022"`).
Where present it is far better evidence than any filename comparison, but not
all of it is equally good, so two more columns say where it came from:

- `identifier_source` -- ``llm`` when the ingestion-time identifier inference
  supplied it, ``override`` when someone mapped it by hand, ``unrecorded`` when
  an identifier is present with no recorded source, and empty when there is no
  identifier at all.  An ``unrecorded`` identifier has no recorded source, and
  is therefore not trusted.
- `identifier_certainty` -- the inference's 0-5 score:  5 means the identifier
  appears verbatim in the text, 3 that only the filename supports it, 1 that
  the document is a supplement.  Empty unless the source is ``llm``.

Manifests written before those two columns existed still load;  their
identifiers have an unknown source, and so are never `trusted_identifier`.
"""

import collections
import csv
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from exquisite.rules import BUILTIN_RULES
from exquisite.rules import Rules

COLUMNS = (
    "uri",
    "sha256",
    "source_url",
    "document_identifier",
    "identifier_source",
    "identifier_certainty",
)

#: `identifier_source` for an identifier present with no recorded provenance.
#: Shown, matched, never trusted:  nothing says how it was arrived at.
UNRECORDED = "unrecorded"

#: Sources trusted whatever the certainty:  mapped by hand.
TRUSTED_SOURCES = frozenset({"override"})

#: The lowest ``llm`` certainty trusted:  4 is "an expanded name in the text
#: maps to it", 3 only "the filename supports it".
TRUSTED_CERTAINTY = 4

#: Manifests are written with every field quoted; see the module docstring.
QUOTING = csv.QUOTE_ALL


def write(path: Path, documents) -> None:
    """Write a manifest CSV, quoting every field."""
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, quoting=QUOTING)
        writer.writeheader()

        for doc in documents:
            writer.writerow(
                {
                    "uri": doc.uri,
                    "sha256": doc.sha256,
                    "source_url": doc.source_url,
                    "document_identifier": doc.document_identifier,
                    "identifier_source": doc.identifier_source,
                    "identifier_certainty": (
                        ""
                        if doc.identifier_certainty is None
                        else str(doc.identifier_certainty)
                    ),
                }
            )


def _certainty(value) -> int | None:
    """An `identifier_certainty`, or None when absent or unreadable."""
    if value in (None, ""):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def from_metadata(uri: str, metadata: dict) -> "Document":
    """A manifest row from a ``document_meta`` row's ``uri`` and ``metadata``.

    The one place the provenance rule lives, so every extraction applies it the
    same way:  an identifier with no recorded `identifier_source` is
    ``unrecorded``, and a source or certainty without an identifier is dropped
    -- ``identify`` stores a block even for documents it could not identify, so
    a lone source means nothing.
    """
    identifier = (metadata.get("document_identifier") or "").strip()
    source = (metadata.get("identifier_source") or "") if identifier else ""

    return Document(
        uri=uri,
        sha256=metadata.get("sha256") or "",
        source_url=metadata.get("source_url") or "",
        document_identifier=identifier,
        identifier_source=(source or UNRECORDED) if identifier else "",
        identifier_certainty=(
            _certainty(metadata.get("identifier_certainty"))
            if identifier
            else None
        ),
    )


@dataclass(frozen=True)
class Document:
    uri: str
    sha256: str = ""
    source_url: str = ""
    document_identifier: str = ""
    identifier_source: str = ""
    identifier_certainty: int | None = None

    @property
    def trusted_identifier(self) -> bool:
        """Whether the identifier is good enough to act on without a person.

        Mapped by hand, or inferred with certainty of at least
        `TRUSTED_CERTAINTY`.  An ``unrecorded`` identifier is not trusted, and
        neither is one from a manifest predating the provenance columns.
        """
        if not self.document_identifier:
            return False

        if self.identifier_source in TRUSTED_SOURCES:
            return True

        return (
            self.identifier_source == "llm"
            and self.identifier_certainty is not None
            and self.identifier_certainty >= TRUSTED_CERTAINTY
        )

    @property
    def identifier_evidence(self) -> str:
        """Where the identifier came from, for people: ``llm certainty 5``."""
        if not self.document_identifier:
            return ""

        if not self.identifier_source:
            return "source unknown"

        if self.identifier_certainty is not None:
            return (
                f"{self.identifier_source} certainty "
                f"{self.identifier_certainty}"
            )

        return self.identifier_source

    @property
    def attachment(self) -> str:
        """The `#attachment=` fragment, decoded, or "" for a whole document.

        Load-bearing, not decoration:  an attachment inherits its *parent's*
        `sha256` and `source_url`, so one hash can cover a document plus dozens
        of attachments.  So the fragment is the only thing distinguishing an
        attachment from its parent and from its siblings, and it must be part
        of the identity or binding will silently resolve to the wrong document.

        The fragment derives from the attachment's own name rather than the
        ingestion's file layout, so it survives re-ingestion as the durable
        columns do.
        """
        import urllib.parse

        if "#attachment=" not in self.uri:
            return ""

        return urllib.parse.unquote(self.uri.split("#attachment=", 1)[1])

    @property
    def name(self) -> str:
        """The document's basename, decoded, for a reader of a worksheet."""
        import os
        import urllib.parse

        return self.attachment or urllib.parse.unquote(
            os.path.basename(self.uri)
        )

    def durable(self) -> dict:
        """The identity a worksheet stores:  stable across re-ingestion."""
        found = {
            "name": self.name,
            "sha256": self.sha256 or None,
            "source_url": self.source_url or None,
        }

        if self.attachment:
            found["attachment"] = self.attachment

        return found


class ManifestError(Exception):
    """The manifest pair is inconsistent or incomplete."""


class MissingSidecar(ManifestError):
    """A manifest CSV without its YAML sidecar."""

    def __init__(self, table: str, sidecar: str):
        self.table = table
        self.sidecar = sidecar
        super().__init__(
            f"{table} has no sidecar {sidecar}; the two are a pair, "
            "so regenerate both rather than reading the table alone"
        )


class RowCountMismatch(ManifestError):
    """The CSV's row count disagrees with the sidecar's ``documents:``."""

    def __init__(self, table: str, rows: int, sidecar: str, declared: int):
        self.table = table
        self.rows = rows
        self.sidecar = sidecar
        self.declared = declared
        super().__init__(
            f"{table} holds {rows} rows but {sidecar} declares {declared} "
            "documents -- a truncated extraction looks exactly like a corpus "
            "that shrank, so this is refused"
        )


@dataclass
class Corpus:
    database: str
    documents: list[Document] = field(default_factory=list)
    #: The sidecar, verbatim:  database path, extraction time, substrate.
    about: dict = field(default_factory=dict)

    @property
    def substrate(self) -> dict:
        """Embedding and chunking settings the corpus was ingested with.

        Two ingestions differing here are not comparable however similar their
        document lists look -- a different embedder or chunk size makes a
        different database out of the same documents.
        """
        return self.about.get("substrate") or {}

    def by_sha256(self) -> dict[tuple[str, str], list[Document]]:
        """Keyed by ``(sha256, attachment)`` -- a hash alone is not unique.

        The value is a *list*:  a corpus can hold byte-identical documents at
        several paths (one `README.txt` copied into several directories, say),
        and retrieval returning any of them is equally correct, so a label must
        bind to all.
        """
        found: dict[tuple[str, str], list[Document]] = collections.defaultdict(
            list
        )

        for doc in self.documents:
            if doc.sha256:
                found[(doc.sha256, doc.attachment)].append(doc)

        return dict(found)

    def by_source_url(self) -> dict[tuple[str, str], list[Document]]:
        """Keyed by ``(source_url, attachment)``, for the same reasons."""
        found: dict[tuple[str, str], list[Document]] = collections.defaultdict(
            list
        )

        for doc in self.documents:
            if doc.source_url:
                found[(doc.source_url, doc.attachment)].append(doc)

        return dict(found)

    def by_identifier(
        self, rules: Rules = BUILTIN_RULES
    ) -> dict[str, list[Document]]:
        """Keyed by each identifier's collapsed key under ``rules``."""
        from exquisite.designators import collapsed_key

        found: dict[str, list[Document]] = collections.defaultdict(list)

        for doc in self.documents:
            if doc.document_identifier:
                key = collapsed_key(doc.document_identifier, rules)
                found[key].append(doc)

        return dict(found)


def load(path: Path) -> Corpus:
    """Read a manifest CSV and its YAML sidecar as one `Corpus`."""
    import yaml

    sidecar = path.with_suffix(".yaml")

    if not sidecar.exists():
        raise MissingSidecar(path.name, sidecar.name)

    about = yaml.safe_load(sidecar.read_text()) or {}
    documents = []

    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            documents.append(
                Document(
                    uri=row["uri"],
                    sha256=row.get("sha256") or "",
                    source_url=row.get("source_url") or "",
                    document_identifier=row.get("document_identifier") or "",
                    identifier_source=row.get("identifier_source") or "",
                    identifier_certainty=_certainty(
                        row.get("identifier_certainty")
                    ),
                )
            )

    declared = about.get("documents")

    if declared is not None and declared != len(documents):
        raise RowCountMismatch(
            path.name, len(documents), sidecar.name, declared
        )

    return Corpus(
        database=about.get("database") or path.stem,
        documents=documents,
        about=about,
    )


def resolve(corpus: Corpus, wanted: dict) -> tuple[list[Document], str]:
    """Find the documents a worksheet entry names, and say how.

    Returns ``(documents, how)`` where ``how`` is ``"sha256"``,
    ``"source_url"``, ``"changed"``, or a reason nothing was found.  The
    distinction matters:  a `sha256` miss with a `source_url` hit means the
    document at that location *changed*, which the SME should look at, while
    both missing means it is gone.

    More than one document comes back when the corpus holds byte-identical
    copies at different paths.
    """
    by_hash = corpus.by_sha256()
    by_url = corpus.by_source_url()
    wanted_hash = wanted.get("sha256")
    wanted_url = wanted.get("source_url")
    attachment = wanted.get("attachment") or ""

    if wanted_hash and (wanted_hash, attachment) in by_hash:
        return by_hash[(wanted_hash, attachment)], "sha256"

    if wanted_url and (wanted_url, attachment) in by_url:
        return (
            by_url[(wanted_url, attachment)],
            "source_url" if not wanted_hash else "changed",
        )

    if not wanted_hash and not wanted_url:
        return [], "no durable identifier recorded"

    return [], "not in this ingestion"
