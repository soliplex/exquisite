# NIST SP 800 example corpus

A small data repository holding a dated snapshot of the NIST publications as
they might be used by an agency's security program, run under the
Risk Management Framework (RMF).

Initially, the snapshot consists of document editions current on 2020-06-30.

This corpus is not meant to cover the entire SP 800 series.

See:

- [#3](https://github.com/soliplex/exquisite/issues/3)
- [#31](https://github.com/soliplex/exquisite/issues/31)

Run `exquisite` against it with `--root`, naming the snapshot:

```bash
uv run exquisite refresh-worksheets --root data/nist-sp-800 --ingestion sp800-2020
```

`tests/unit/test_data_nist_sp_800.py` pins the snapshot, and what the rules
make of NIST citations.

## Contents

```text
exquisite.yaml                     normalization rules for NIST spellings
corpus/sp800/
  ingestion/sp800-2020.{csv,yaml}  editions current on 2020-06-30
  worksheet/sp800-2020.yaml        map citations to documents
questions/sp800-2020.json          16 questions, as might be asked in mid-2020
```

The question set is written against the 2020 snapshot: each question cites
an edition current then, and every question binds to a document in that
snapshot. The questions are numbered as first written: 11 and 12 moved to the
separate corpus line ([#29](https://github.com/soliplex/exquisite/issues/29)),
and 19 and 20 left with SP 800-57, which issue #31 dropped as extraneous
to the purpose of the corpus.

## The documents

Nineteen publications, as downloaded from `nvlpubs.nist.gov` on 2026-10-02
and 2026-10-04. The documents themselves are not committed: the manifest
records each one's official URL as `source_url`, and the `sha256` of the file
ingested.

The snapshot holds the documents current on its `as_of` date, recorded in
its sidecar. Their status today:

| Publication | Published | Status |
| --- | --- | --- |
| SP 800-18 Rev. 1 | 2006-02 | withdrawn 2026-06-30; superseded by Rev. 2 |
| SP 800-30 Rev. 1 | 2012-09 | final |
| SP 800-34 Rev. 1 | 2010-05 | final |
| SP 800-37 Rev. 2 | 2018-12 | final |
| SP 800-39 | 2011-03 | final |
| SP 800-40 Rev. 3 | 2013-07 | withdrawn 2022-04-06; superseded by Rev. 4 |
| SP 800-53 Rev. 4 | 2013-04 | withdrawn 2021-09-23; superseded by Rev. 5 |
| SP 800-53A Rev. 4 | 2014-12 | withdrawn 2023-01-25; superseded by Rev. 5 |
| SP 800-60 Vol. 1 Rev. 1 | 2008-08 | final |
| SP 800-60 Vol. 2 Rev. 1 | 2008-08 | final |
| SP 800-61 Rev. 2 | 2012-08 | withdrawn (notice dated 2025-04-03); superseded by Rev. 3 |
| SP 800-63-3 | 2017-06 | withdrawn 2025-08-01; superseded by SP 800-63-4 |
| SP 800-63A | 2017-06 | withdrawn 2025-08-01; superseded by SP 800-63A-4 |
| SP 800-63B | 2017-06 | withdrawn 2025-08-01; superseded by SP 800-63B-4 |
| SP 800-128 | 2011-08 | final |
| SP 800-137 | 2011-09 | final |
| SP 800-137A | 2020-05 | final |
| FIPS 199 | 2004-02 | final |
| FIPS 200 | 2006-03 | final |

FIPS 199 and 200 aren't in the SP 800 series: they are included because they
form the foundation for the RMF.

**Withdrawn publications are stripped of their notice.**

When NIST withdraws a publication, it adds a one-page withdrawal notice to
the front of its PDF, and serves only that copy afterwards. The notice
would be anachronistic in a 2020 snapshot, so for the seven publications
withdrawn and stamped since, the snapshot holds a copy with that page removed
(`<file>.as-of-2020-06-30.pdf`); its text is otherwise identical. Their
`sha256` is of the stripped copy, so it differs from that of the file at
their `source_url`. SP 800-18 Rev. 1 is withdrawn but not yet stamped.

The publication dates come from NIST's CSRC pages; the manifests do not
record them yet (see [#25](https://github.com/soliplex/exquisite/issues/25)).

**The manifest is synthetic.**

It was written by hand, not extracted from a RAG database, so its URIs
(`file:///data/nist-sp-800/…`) are shaped like an ingester's, and its sidecar
records no substrate.

However, the hashes and source URLs are real. Every identifier is recorded as
`override`, mapped by hand.

## What the rules handle

`exquisite.yaml` folds the ways the snapshot's publications are cited, and
nothing more: spellings that only later editions use will be added with the
snapshots that hold them.

Each row is tested against the rules, citation by citation.

| Convention | Citations that collapse together |
| --- | --- |
| The `NIST` / `Special Publication` prefix | `NIST Special Publication 800-30 Revision 1`, `NIST SP 800-30 Rev. 1`, `SP 800-30r1` |
| Roman-numeral volumes | `NIST SP 800-60 Volume I`, `NIST SP 800-60 Vol. 1` |
| `Control` and `Appendix` as location words | `NIST SP 800-53 Rev. 4, Control AC-2` is `NIST SP 800-53 Rev. 4` |

And the one relation it labels, between a citation and a publication whose
identifier extends it:

| Citation | Document | Relation |
| --- | --- | --- |
| `NIST SP 800-30` | SP 800-30 Rev. 1 | `revision` |
