# Question sets

A question set is a [pydantic-evals](https://ai.pydantic.dev/evals/)
dataset. `exquisite` reads two keys from each case's `metadata`:

```json
{
  "cases": [
    {
      "inputs": "What does clause 4 of ISO 9001 cover?",
      "expected_output": "Context of the organization",
      "metadata": {"uuid": "a1", "reference": "ISO 9001 Sec 4"}
    }
  ]
}
```

- `reference` is the source citation as written. `exquisite` never modifies
  it: it is the provenance, and what a worksheet is regenerated from when a
  corpus is rebuilt. A reference may also be a document URI, for a set whose
  author picked the files directly (see
  [references that are already URIs](worksheets.md#references-that-are-already-uris)).
- `uuid` identifies the case. A *pruned* set, whose name ends in `_pruned`,
  is a subset of the set it is named for. It needs no worksheet of its own:
  binding labels it from its parent's worksheet, matching cases by `uuid`.

The question set itself is never written to. Binding produces a labelled
copy on demand (see [Binding](binding.md)).
