# Worksheets

A worksheet maps the designators a question set cites to documents in one
corpus. It is generated, then completed by someone who knows the corpus.

Pair a question set with a corpus once:

```bash
exquisite add-worksheet --corpus standards --questions quality-basics
```

Thereafter, rebuild the generated parts against the current ingestion,
keeping the answers already given:

```bash
exquisite refresh-worksheets                    # every corpus
exquisite refresh-worksheets --corpus standards
```

A refresh touches only worksheets that already exist, and reports how many
answers it kept and how many it dropped; a drop means the question set no
longer cites that designator. A worksheet whose content would not change is
left as it is. When a corpus has several manifests, name one with
`--ingestion`.

## What a worksheet holds

The header records what the worksheet was generated from:

```yaml
version: 1
question_set: questions/quality-basics.json
database: standards
generated: 2026-10-02
corpus_documents: 3   # at generation; a mismatch means recheck
substrate: f65934c5bbcc   # embedder/chunking digest of the ingestion
rules: a6597c4a4571   # normalization v1, built-ins only
validated_by:      # FILL ME IN
validated_on:      # FILL ME IN
```

Below it are three sections:

- **`designators:`** is the part a person edits. There is one entry per
  designator, grouped by collapsed key, so spelling variants of one document
  sit together:

  ```yaml
    # iso9001
  - designator: "ISO 9001"
    questions: 2
    documents: FILL ME IN   # a list of {name, sha256, source_url};
                            # or [] with `unresolved` filled in
    unresolved:        # reason, if it genuinely cannot be resolved
    notes:
  ```

- **`candidates:`** is generated and advisory: the documents that resemble
  each group, in tiers, strongest evidence first. `identifier` lists
  documents whose own identifier collapses to the group's key.
  `identifier_related` lists those whose identifier extends it (a
  supplement, a volume, a part), which are never the answer by themselves.
  `matched`, `related` and `same_series` rest on filename resemblance alone.
  Each tier is alphabetical rather than ranked.
- **`apply_keys:`** is generated: every verbatim `reference` string, mapped
  to its designator, so that binding is exact string lookup.

Never edit `candidates:` or `apply_keys:`; a refresh rebuilds them.

## Filling one in

For each group, record the documents it means, by their durable identity:

```yaml
- designator: "ISO 9001"
  questions: 2
  documents:
  - name: "iso-9001-2015.pdf"
    sha256: "3f1c…"
    source_url: "https://example.org/iso-9001-2015.pdf"
```

Copy `name`, `sha256` and `source_url` from the document's entry under
`candidates:`. Binding finds the document by `sha256`, then `source_url`;
`name` is for people. An attachment also needs the `attachment:` line shown
there, since it shares its parent's hash. Two designators meaning one
document simply get the same `documents:`.

When no document answers a group, write `documents: []` and say why in
`unresolved:`. **An absent label beats a wrong one.** A case with no
documents is *ineligible* and scores nothing, while a wrong document makes
correct retrieval look like a failure.

When the worksheet is complete, the person who checked it records their name
and the date in `validated_by:` and `validated_on:`. A worksheet refreshed
after its corpus was rebuilt with a different substrate, or under different
normalization rules, keeps that attestation. It gains a
`validated_against_substrate:` or `validated_against_rules:` line recording
what it was actually checked against.

## Provisional answers

With `--provisional`, `add-worksheet` and `refresh-worksheets` pre-fill each
unanswered group that has a trusted `identifier` match:

```yaml
  documents:
  - name: "iso-9001-2015.pdf"
    sha256: "3f1c…"
    source_url: "https://example.org/iso-9001-2015.pdf"
  provisional: "identifier match (llm certainty 5): ISO 9001 -- confirm, then delete this line"
```

Weaker evidence never becomes an answer. `bind` refuses a worksheet while
any `provisional:` line remains; confirming an answer means deleting the
line.

## References that are already URIs

When a question set cites document URIs rather than prose, the author
already chose the files, and nothing needs deciding. Fill such worksheets in
mechanically:

```bash
exquisite resolve-references --corpus standards
```

Each reference resolves as **exact** when it is a document URI in this
ingestion, or as **moved** when it is not, but exactly one document has that
filename (the corpus was re-ingested under a different root). Anything
ambiguous or absent is left for a person, with the reason, and the command
exits with status 1. `validated_by:` stays blank either way.
