# NIST SP 800 example corpus

A small data repository holding two dated snapshots of a subset of the NIST
Special Publications. Between them, editions are superseded, companions and
drafts appear, and publications are cited in many spellings. It is not meant
to cover the SP 800 series. See
[#3](https://github.com/soliplex/exquisite/issues/3).

Run `exquisite` against it with `--root`, naming the snapshot:

```bash
uv run exquisite refresh-worksheets --root data/nist-sp-800 --ingestion sp800-2020
```

`tests/unit/test_data_nist_sp_800.py` pins the snapshots, and what the rules
make of NIST citations.

## Contents

```text
exquisite.yaml                          normalization rules for NIST spellings
corpus/sp800/
  ingestion/sp800-2020.{csv,yaml}       the editions current on 2020-06-30
  ingestion/sp800-2026.{csv,yaml}       the editions current on 2026-10-02
  worksheet/sp800-2020.yaml             which documents each citation means
questions/sp800-2020.json               20 questions, as asked in mid-2020
```

The question set is written against the 2020 snapshot: each question cites
an edition current then. Its worksheet is validated, and every question
binds to a document in that snapshot.

## The documents

Seventeen publications, as downloaded from `nvlpubs.nist.gov` on 2026-10-02.
The documents themselves are not committed: each manifest records the
official URL as `source_url`, and the `sha256` of the downloaded file.

Each snapshot holds the documents current on its `as_of` date, recorded in
its sidecar.

| Publication | Published | `sp800-2020` | `sp800-2026` | Status |
| --- | --- | :-: | :-: | --- |
| SP 800-30 Rev. 1 | 2012-09 | ✓ | ✓ | final |
| SP 800-53 Rev. 4 | 2013-04 | ✓ | | withdrawn 2021-09; superseded by Rev. 5 |
| SP 800-53 Rev. 5 | 2020-09 | | ✓ | final |
| SP 800-53A Rev. 5 | 2022-01 | | ✓ | final; a companion of SP 800-53 |
| SP 800-53B | 2020-12 | | ✓ | final; a companion of SP 800-53 |
| SP 800-57 Part 1 Rev. 5 | 2020-05 | ✓ | ✓ | final |
| SP 800-57 Part 1 Rev. 6 (initial public draft) | 2025-12 | | ✓ | draft |
| SP 800-60 Vol. 1 Rev. 1 | 2008-08 | ✓ | ✓ | final |
| SP 800-60 Vol. 2 Rev. 1 | 2008-08 | ✓ | ✓ | final |
| SP 800-61 Rev. 2 | 2012-08 | ✓ | | withdrawn; superseded by Rev. 3 |
| SP 800-61 Rev. 3 | 2025-04 | | ✓ | final |
| SP 800-63-4 | 2025-07 | | ✓ | final |
| SP 800-63B | 2017-06 | ✓ | | withdrawn 2025-08; superseded by SP 800-63B-4 |
| SP 800-63B-4 | 2025-07 | | ✓ | final |
| SP 800-171 Rev. 2 | 2020-02 | ✓ | | withdrawn 2024-05; superseded by Rev. 3 |
| SP 800-171 Rev. 3 | 2024-05 | | ✓ | final |
| SP 800-171A Rev. 3 | 2024-05 | | ✓ | final; a companion of SP 800-171 |

The publication dates come from NIST's CSRC pages; the manifests do not
record them yet ([#25](https://github.com/soliplex/exquisite/issues/25)).

**The ingestions are synthetic.** No RAG database has ingested this corpus
yet, so the URIs (`file:///data/nist-sp-800/…`) are shaped like an
ingester's, and the sidecars record no substrate. The hashes and source URLs
are real. Every identifier is recorded as `override`, mapped by hand.

## What the rules handle

`exquisite.yaml` folds the ways NIST publications are cited. Each row is
tested against the rules, citation by citation.

| Convention | Citations that collapse together |
| --- | --- |
| The `NIST` / `Special Publication` prefix | `NIST Special Publication 800-30 Revision 1`, `NIST SP 800-30 Rev. 1`, `SP 800-30r1` |
| SP 800-63's suffix revision | `NIST SP 800-63B-4`, `NIST Special Publication 800-63B Revision 4` |
| A supplement | `NIST SP 800-63Bsup1`, `NIST SP 800-63B Supplement 1` |
| Roman-numeral volumes | `NIST SP 800-60 Volume I`, `NIST SP 800-60 Vol. 1` |
| `Control` as a location word | `NIST SP 800-53 Control AC-2` is `NIST SP 800-53` |

And the relations it labels, between a citation and a document whose
identifier extends it:

| Citation | Document | Relation |
| --- | --- | --- |
| `NIST SP 800-53` | SP 800-53 Rev. 5 | `revision` |
| `NIST SP 800-53` | SP 800-53A Rev. 5, SP 800-53B | `companion` |
| `NIST SP 800-63B` | SP 800-63B-4 | `revision` |
| `NIST SP 800-57 Part 1` | SP 800-57 Part 1 Rev. 6 (initial public draft) | `draft revision` |

SP 800-63-4 is a sibling of SP 800-63B-4, not a revision of SP 800-63B, and
the rules keep them apart. A draft cited without its part, as CSRC's own
listing spells it (`NIST SP 800-57 Rev. 6`), does not collapse with
`NIST SP 800-57 Part 1 Rev. 6`: the missing part is a real ambiguity, for a
person to resolve.
