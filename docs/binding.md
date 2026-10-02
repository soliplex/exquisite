# Binding

Binding writes a question set out with `relevant_uris` filled in from one
ingestion:

```bash
exquisite bind --corpus standards --questions quality-basics > labelled.json
exquisite bind --corpus standards --questions quality-basics --out labelled.json
```

The labelled set goes to stdout, or to the `--out` file. Diagnostics always
go to stderr, so a redirect yields a usable dataset and a readable report at
once. Each case's metadata gains the URIs its documents have in this
ingestion:

```json
{
  "uuid": "a1",
  "reference": "ISO 9001 Sec 4",
  "relevant_uris": ["file:///data/standards/iso-9001-2015.pdf"]
}
```

`bind` refuses a worksheet that is not finished, listing every problem:

```text
quality-basics.yaml is not ready to bind:
  'ISO 9001': provisional answer not yet confirmed -- check it, then delete its `provisional:` line
  'NIST SP 800-53 Rev. 5': documents not filled in
```

Binding half a worksheet would be indistinguishable from someone having
decided those documents do not exist. Each document is found by its
`sha256`, falling back to its `source_url`:

- **changed:** the hash misses but the `source_url` hits. The file at that
  location is no longer the one that was approved, so look at it again.
- **unbound:** both miss. The document is not in this ingestion.

`bind` exits with status 1 when a reference has no apply key or a document
is unbound. A bound set is never stored: it goes stale as soon as its
ingestion is replaced, so produce it when it is wanted.
