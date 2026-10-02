# The data repository

`exquisite` is installed separately from the data it manages. It works on a
*data repository*: a directory, usually under version control, laid out like
this:

```text
exquisite.yaml                     normalization rules (optional)
questions/
  quality-basics.json              a question set
  quality-basics_pruned.json       a subset of it
corpus/
  standards/                       one corpus
    ingestion/
      standards.csv                one ingestion's documents
      standards.yaml               what that ingestion is
    worksheet/
      quality-basics.yaml          which documents the set cites
```

Every command takes `--root`; without it, the root is `$EXQUISITE_ROOT`, or
else the working directory. A root lacking `questions/` or `corpus/` is
refused.

A few rules shape the layout:

- **A question set belongs to no corpus.** Two databases built from
  different documents can be scored with the same questions, so a set lives
  once, under `questions/`.
- **A corpus directory is named for its documents, not for a database.**
  Re-ingesting the same documents under a new database name adds a manifest
  to `ingestion/`, rather than starting a new directory.
- **A worksheet's existence declares the pairing.** Nothing derives that a
  question set should be scored against a corpus; someone decided it, and
  creating the worksheet records the decision.
