# Ingestion manifests

A manifest describes one ingestion of one corpus, as two files sharing a
stem: a CSV listing its documents, and a YAML *sidecar* describing the
ingestion as a whole.

## The CSV

One row per document, with every field quoted, so that an empty column reads
as `""` rather than being inferred from delimiters:

```text
"uri","sha256","source_url","document_identifier","identifier_source","identifier_certainty"
"file:///data/standards/iso-9001-2015.pdf","3f1c…","https://example.org/iso-9001-2015.pdf","ISO 9001","llm","5"
"file:///data/standards/sp800-53r5.pdf","9a2e…","","NIST SP 800-53 Rev. 5","llm","3"
```

| Column | Meaning |
| --- | --- |
| `uri` | Where *this* ingestion stored the document. |
| `sha256` | The document's content hash. |
| `source_url` | Where the document was fetched from. |
| `document_identifier` | The publication's designator, e.g. `ISO 9001`. |
| `identifier_source` | `llm` (inferred at ingestion), `override` (mapped by hand), `unrecorded`, or empty when there is no identifier. |
| `identifier_certainty` | The inference's 0–5 score, for `llm` identifiers: 5 means the identifier appears verbatim in the text. |

`uri` is the only column that is not durable: re-ingesting under a different
source root rewrites every URI. `sha256` and `source_url` survive that, so
worksheets record those instead. Neither is always populated, but every
document needs at least one of them.

An identifier is *trusted* when its source is `override`, or `llm` with a
certainty of 4 or 5. Only trusted identifiers produce provisional answers
and cross-references between worksheet groups. An `unrecorded` identifier is
shown and matched, but not trusted.

## The sidecar

```yaml
database: standards
database_path: /lancedb/standards.lancedb
extracted_at: 2026-10-02T12:00:00+00:00
documents: 3
chunks: 4210
substrate:
  embeddings: {provider: ollama, name: example-embedder, vector_dim: 1024}
  processing: {chunk_size: 256, converter: docling}
```

- `database` names the database; when absent, the manifest's stem is used.
- `documents`, when present, must equal the CSV's row count, or the manifest
  is refused: a truncated extraction would otherwise look exactly like a
  corpus that shrank.
- `substrate` records how the corpus was ingested: the embedding model and
  the chunking. It matters as much as the document list, since the same
  documents ingested with a different embedder or chunk size make a different
  database. Worksheets record a digest of it.

The other keys are for people reading the file.

## Producing a manifest

Build the CSV from each document's URI and metadata, as the RAG database
stores them. `exquisite.manifest.from_metadata` applies the provenance rule
for the identifier columns, so every extraction applies it the same way:

```python
import json
import pathlib

from exquisite import manifest

# One {"uri": ..., "metadata": {...}} object per line, dumped from wherever
# the database is reachable.
rows = [json.loads(line) for line in open("standards.jsonl")]
manifest.write(
    pathlib.Path("corpus/standards/ingestion/standards.csv"),
    [manifest.from_metadata(row["uri"], row["metadata"]) for row in rows],
)
```

Write the sidecar alongside it, from the database's own settings and row
counts.
