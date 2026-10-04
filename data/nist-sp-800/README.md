# NIST SP 800 example corpus

A small data repository holding a dated snapshot of a subset of the NIST
Special Publications: the editions current on 2020-06-30. It is not meant to
cover the SP 800 series. See
[#3](https://github.com/soliplex/exquisite/issues/3).

Run `exquisite` against it with `--root`, naming the snapshot:

```bash
uv run exquisite refresh-worksheets --root data/nist-sp-800 --ingestion sp800-2020
```

`tests/unit/test_data_nist_sp_800.py` pins the snapshot, and what the rules
make of NIST citations.

## Contents

```text
exquisite.yaml                          normalization rules for NIST spellings
corpus/sp800/
  ingestion/sp800-2020.{csv,yaml}       the editions current on 2020-06-30
  worksheet/sp800-2020.yaml             which documents each citation means
questions/sp800-2020.json               20 questions, as asked in mid-2020
```

The question set is written against the 2020 snapshot: each question cites
an edition current then. Its worksheet is validated, and every question
binds to a document in that snapshot.

## The documents

Eight publications, as downloaded from `nvlpubs.nist.gov` on 2026-10-02.
The documents themselves are not committed: the manifest records each one's
official URL as `source_url`, and the `sha256` of the downloaded file.

The snapshot holds the documents current on its `as_of` date, recorded in
its sidecar. Their status today:

| Publication | Published | Status |
| --- | --- | --- |
| SP 800-30 Rev. 1 | 2012-09 | final |
| SP 800-53 Rev. 4 | 2013-04 | withdrawn 2021-09-23; superseded by Rev. 5 |
| SP 800-57 Part 1 Rev. 5 | 2020-05 | final |
| SP 800-60 Vol. 1 Rev. 1 | 2008-08 | final |
| SP 800-60 Vol. 2 Rev. 1 | 2008-08 | final |
| SP 800-61 Rev. 2 | 2012-08 | withdrawn; superseded by Rev. 3 |
| SP 800-63B | 2017-06 | withdrawn 2025-08-01; superseded by SP 800-63B-4 |
| SP 800-171 Rev. 2 | 2020-02 | withdrawn 2024-05-14; superseded by Rev. 3 |

The publication dates come from NIST's CSRC pages; the manifests do not
record them yet ([#25](https://github.com/soliplex/exquisite/issues/25)).

**The manifest is synthetic.** It was written by hand, not extracted from a
RAG database, so its URIs (`file:///data/nist-sp-800/…`) are shaped like an
ingester's, and its sidecar records no substrate. The hashes and source URLs
are real. Every identifier is recorded as `override`, mapped by hand.

## What the rules handle

`exquisite.yaml` folds the ways the snapshot's publications are cited, and
nothing more: spellings that only later editions use are added with the
snapshots that hold them. Each row is tested against the rules, citation by
citation.

| Convention | Citations that collapse together |
| --- | --- |
| The `NIST` / `Special Publication` prefix | `NIST Special Publication 800-30 Revision 1`, `NIST SP 800-30 Rev. 1`, `SP 800-30r1` |
| A part, spelled out or abbreviated | `NIST SP 800-57 Part 1 Rev. 5`, `NIST SP 800-57 Pt. 1 Rev. 5` |
| Roman-numeral volumes | `NIST SP 800-60 Volume I`, `NIST SP 800-60 Vol. 1` |
| `Control` and `Appendix` as location words | `NIST SP 800-53 Rev. 4, Control AC-2` is `NIST SP 800-53 Rev. 4` |

And the one relation it labels, between a citation and a publication whose
identifier extends it:

| Citation | Document | Relation |
| --- | --- | --- |
| `NIST SP 800-30` | SP 800-30 Rev. 1 | `revision` |
