# exquisite

Ref: [Exquisite Corpse](https://en.wikipedia.org/wiki/Exquisite_corpse)

`exquisite` labels evaluation question sets with the documents that answer
them, so that a retrieval-augmented generation (RAG) system can be scored on
*retrieval* as well as on its answers. It describes each ingestion of a
corpus in a *manifest*, generates *worksheets* in which a person who knows
the corpus records which documents each citation means, and *binds* a
question set to one ingestion by writing the documents' current URIs into
each question. It can then check that a haiku-rag database's searches return
those documents.

**Documentation:** <https://soliplex.github.io/exquisite/>

## Installation

`exquisite` needs Python 3.13 or later:

```bash
uv tool install exquisite
```

## Development

```bash
uv sync --group dev
uv run pytest
uv run ruff check
uv run --group docs zensical serve    # preview the docs locally
```

See [Development](docs/development.md) for more.

## License

MIT; see [LICENSE](LICENSE).
