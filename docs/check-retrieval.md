# Checking retrieval

A validated worksheet says which documents answer each question.
`check-retrieval` checks that a RAG database actually returns them: it binds
the question set to one ingestion, as `bind` does, then runs one search per
question against a [haiku-rag](https://github.com/ggozad/haiku.rag) database,
and looks for the bound documents among the results.

There is no answering model and no judge, so a run is fast, and its scores
are stable from run to run. That's what checking a freshly ingested database
needs. It checks documents, not passages: a hit means a chunk of a relevant
document came back, not that the chunk holds the answer.

## Running a check

```bash
exquisite check-retrieval --root data/nist-sp-800 --corpus sp800 \
    --questions sp800-2020 --ingestion sp800-2020 \
    --db sp800-2020.lancedb --config haiku.rag.yaml
```

- `--db` is the database to search: a local path, or a URI haiku-rag
  accepts. It is opened read-only. A local path with nothing there is
  refused, never opened, since opening it would create an empty database.
- `--config` is the haiku-rag configuration the database was ingested with,
  so the searches use the same embedder. Any databases it names are set
  aside in favour of `--db`, and the command says so.
- `--top-k` is how many results each search returns (default 30). It is
  deliberately more than a chat agent's search limit: a newly ingested
  document relevant to a question can push a labelled one out of a short
  list without anything being broken.
- `-v` / `--verbose` shows each question's result, as well as the summary.
- `--out` saves the results to a file, to compare a later run against. An
  existing file is refused, before any searching, unless `--force` is
  passed too. Without `--out`, nothing is written.

Binding problems are reported on stderr, as `bind` reports them. A
worksheet that isn't ready to bind is refused.

## What counts as a hit

A question is a *hit* when any of its bound documents is among the results,
and a *miss* when none is. Each question is scored by `retrieval_mrr`, the
reciprocal rank of its first relevant document: 1.0 at rank 1, 0.5 at rank
2, and 0.0 for a miss. Questions with no bound documents (unresolved, or
citing nothing) are *ineligible*: counted, not checked.

Results are matched to the manifest the way `bind` matches documents: by the
`sha256` the database records for each document, then its `source_url`, and
only failing both by URI. So a database whose documents sit at different
paths from the manifest's is still checked correctly.

```text
20/20 questions passed;  mean retrieval_mrr 0.975
```

With `--verbose`, each question gets a line first, in question-set order:
the rank of its first relevant document, its `retrieval_mrr`, and the
question. Below a question not at rank 1 are the documents that came ahead
of it. Below a miss are the first few that came back instead:

```text
rank  mrr    question
   1  1.000  What are the steps of a risk assessment?
   ...
   2  0.500  What levels of potential impact are used to categorize information and systems?
             after: NIST.SP.800-53r4.pdf
   ...
20/20 questions passed;  mean retrieval_mrr 0.975
```

Documents are shown by name; the results file has their full URIs.

## Comparing with an earlier run

`--compare` names the results of an earlier run. Against it, a question
fails when it *loses*: the earlier run hit, and this one misses. The rest
is reported, but never fails:

- `RANK`: the first relevant document ranks lower than before. The embedder
  and reranker can reorder near-tied results between two runs on the same
  database.
- `DROPPED`: a relevant document dropped out while another still hits.
- the mean `retrieval_mrr` over the questions both runs scored fell by more
  than `--mrr-tolerance` (default 0.02).

A question the earlier run doesn't have is checked for a miss instead.

The earlier run is refused, before any searching, when its searches differ
by design: a different configured embedder, reranker or top K, or a database
stored with a different embedder. So is one that asked a different question
under some case's key, the question's `metadata.uuid`. Different versions of
`exquisite` or haiku-rag only warn: a check across an upgrade is meant to
span them.

Any run saved with `--out` can be a reference, including one that failed:
read its report, then compare the next run against it.

## Exit status

`check-retrieval` exits with status 0 when every eligible question passes.
It exits with status 1 when:

- a question misses, or loses against `--compare`;
- no question is eligible;
- the worksheet isn't ready to bind;
- the database is missing, or haiku-rag won't search it as it stands (it
  needs migrating to the installed haiku-rag, say);
- the `--compare` file isn't a results file, or is refused;
- the `--out` file exists, and `--force` wasn't passed.

## The results file

With `--out`, a run that searches saves its results, whatever its outcome:

```json
{
  "format": "exquisite check-retrieval 1",
  "question_set": "questions/sp800-2020.json",
  "corpus": "sp800",
  "ingestion": "sp800-2020",
  "settings": {
    "embedder": "vllm:nvidia/llama-nemotron-embed-vl-1b-v2 (dim 2048)",
    "reranker": null,
    "top_k": 30,
    "config_hash": "5f8a9bfe…"
  },
  "database": {
    "location": "sp800-2020.lancedb",
    "embedder": "vllm:nvidia/llama-nemotron-embed-vl-1b-v2 (dim 2048)",
    "documents": 8,
    "chunks": 5502,
    "written_at": "2026-10-03T01:54:08.941536",
    "version": "0.89.0"
  },
  "substrate": {"exquisite": "0.2", "haiku-rag-slim": "0.89.0"},
  "started": "2026-10-03T08:58:41",
  "finished": "2026-10-03T08:58:45",
  "cases": [
    {
      "key": "33e57977-…",
      "question": "What levels of potential impact are used to categorize information and systems?",
      "relevant": ["file:///data/nist-sp-800/nistspecialpublication800-60v1r1.pdf"],
      "retrieved": [
        "file:///data/nist-sp-800/NIST.SP.800-53r4.pdf",
        "file:///data/nist-sp-800/nistspecialpublication800-60v1r1.pdf"
      ],
      "score": 0.5
    }
  ]
}
```

- `settings`: how the searches were made. `config_hash` is a SHA-256 of the
  whole haiku-rag configuration.
- `database`: what the database held: the embedder it was stored with, its
  size, when it was last written, and its haiku-rag version.
- `substrate`: the installed versions of `exquisite` and haiku-rag.
- `cases`: one per question. `retrieved` lists one entry per distinct
  document, in rank order: its manifest URI when the manifest holds it,
  else the database's own. `score` is `null` for an ineligible question.

It is the file `--compare` reads.
