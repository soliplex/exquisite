# exquisite

`exquisite` labels evaluation question sets with the documents that answer
them, so that a retrieval-augmented generation (RAG) system can be scored on
*retrieval* as well as on its answers.

A question set cites its sources the way people do, in prose such as
`ISO 9001 Sec 4`. A RAG database stores documents under URIs such as
`file:///data/standards/iso-9001-2015.pdf`. Something has to connect the two,
and has to keep doing so when the database is rebuilt. `exquisite` does
that:

1. it describes each ingestion of a corpus in a *manifest*;
2. it generates a *worksheet* in which a person who knows the corpus records
   which documents each citation means;
3. it *binds* the question set to one ingestion, writing the documents'
   current URIs into each question as `metadata.relevant_uris`.

## Contents

- [Installation](installation.md)
- [The data repository](data-repository.md): how a repository of
  question sets and corpora is laid out
- [Question sets](question-sets.md): what `exquisite` reads from them
- [Ingestion manifests](manifests.md): describing one ingestion of a corpus
- [Worksheets](worksheets.md): recording which documents each citation
  means
- [Binding](binding.md): labelling a question set for one ingestion
- [Normalization rules](rules.md): how citations are grouped, and how to
  extend the rules
- [Development](development.md)

The name comes from the [exquisite corpse](https://en.wikipedia.org/wiki/Exquisite_corpse),
a drawing made by several people, each adding a part without seeing the
whole.
