# NIST SP 800 example corpus

A small data repository of NIST Special Publications, built to exercise the
ways a real corpus misleads: one publication under many spellings,
citations of superseded editions or of no edition at all, companions,
supplements, volumes, parts, and drafts. It is not meant to cover the
SP 800 series. See [#3](https://github.com/soliplex/exquisite/issues/3).

Run `exquisite` against it with `--root`:

```bash
uv run exquisite refresh-worksheets --root data/nist-sp-800 --ingestion sp800-2026
uv run exquisite bind --root data/nist-sp-800 --corpus sp800 \
    --questions sp800-pitfalls --ingestion sp800-2026
```

`tests/unit/test_data_nist_sp_800.py` pins what `exquisite` makes of it.

## Contents

```text
exquisite.yaml                          normalization rules for NIST spellings
questions/sp800-pitfalls.json           25 questions, each citing a pitfall
corpus/sp800/
  ingestion/sp800-2020.{csv,yaml}       the editions current in 2020
  ingestion/sp800-2026.{csv,yaml}       the editions current in 2026
  worksheet/sp800-pitfalls.yaml         which documents each citation means
```

## The documents

Eighteen publications, as downloaded from `nvlpubs.nist.gov` on 2026-10-02.
The documents themselves are not committed: each manifest records the
official URL as `source_url`, and the `sha256` of the downloaded file.

| Publication | `sp800-2020` | `sp800-2026` | Status |
| --- | :-: | :-: | --- |
| SP 800-30 Rev. 1 | ✓ | ✓ | final |
| SP 800-53 Rev. 4 | ✓ | | withdrawn; superseded by Rev. 5 |
| SP 800-53 Rev. 5 | | ✓ | final |
| SP 800-53A Rev. 5 | | ✓ | final; a companion of SP 800-53 |
| SP 800-53B | ✓ | ✓ | final; a companion of SP 800-53 |
| SP 800-57 Part 1 Rev. 5 | ✓ | ✓ | final |
| SP 800-57 Part 1 Rev. 6 (initial public draft) | | ✓ | draft |
| SP 800-60 Vol. 1 Rev. 1 | ✓ | ✓ | final |
| SP 800-60 Vol. 2 Rev. 1 | ✓ | ✓ | final |
| SP 800-61 Rev. 2 | ✓ | | withdrawn; superseded by Rev. 3 |
| SP 800-61 Rev. 3 | | ✓ | final |
| SP 800-63-4 | | ✓ | final |
| SP 800-63B | ✓ | | withdrawn; superseded by SP 800-63B-4 |
| SP 800-63B-4 | | ✓ | final |
| SP 800-63Bsup1 | ✓ | | withdrawn 2025-07-31 |
| SP 800-171 Rev. 2 | ✓ | | withdrawn; superseded by Rev. 3 |
| SP 800-171 Rev. 3 | | ✓ | final |
| SP 800-171A Rev. 3 | | ✓ | final; a companion of SP 800-171 |

**The ingestions are synthetic.** No RAG database has ingested this corpus
yet, so the URIs (`file:///data/nist-sp-800/…`) are shaped like an
ingester's, and the sidecars record no substrate. The hashes and source URLs
are real. Every identifier is recorded as `override`, mapped by hand.

## The pitfalls

Each question's citation is spelled to provoke one of these. Every answer
was checked against the cited section of the document.

| Pitfall | Citations |
| --- | --- |
| One publication, several spellings | `NIST SP 800-30 Rev. 1`, `NIST Special Publication 800-30 Revision 1`, `SP 800-30r1` |
| A superseded edition | `NIST SP 800-61 Rev. 2`, `NIST Special Publication 800-53 Revision 4`, `NIST SP 800-171 Rev. 2`, `NIST SP 800-63B` |
| No edition, true of only one | `NIST SP 800-61, Section 2.1`: six CSF 2.0 Functions, true only of Rev. 3 |
| No edition, true of every one | `NIST SP 800-53 Control AC-2`: Account Management in both Rev. 4 and Rev. 5 |
| A companion, not the publication | `NIST SP 800-53A Rev. 5`, `NIST SP 800-53B`, `NIST SP 800-171A Rev. 3` |
| Editions whose answers differ | SP 800-171: fourteen families in Rev. 2, 17 in Rev. 3. SP 800-63B: 8-character secrets in the 2017 edition, 15 for single-factor passwords in SP 800-63B-4 |
| A revision as a suffix | `NIST SP 800-63B-4` and `NIST Special Publication 800-63B Revision 4` |
| A sibling, not a revision | `NIST SP 800-63-4` beside SP 800-63B-4 |
| A supplement, two spellings | `NIST SP 800-63Bsup1` and `NIST SP 800-63B Supplement 1` |
| Roman-numeral volumes | `NIST SP 800-60 Volume I Revision 1`, `NIST SP 800-60 Vol. II Rev. 1` |
| A draft cited without its part | `NIST SP 800-57 Rev. 6 (Initial Public Draft)`, as CSRC's own listing spells it, for the draft of Part 1 |

## What binding shows

The worksheet records the document each citation actually means, so neither
ingestion binds every question:

- `sp800-2026` labels 18 of 25. It cannot label the citations of superseded
  editions, nor the withdrawn supplement.
- `sp800-2020` labels 15 of 25. It cannot label the citations of editions
  not yet issued.

Comparing the two ingestions is the test case for the ingestion diff
proposed in [discussion #20](https://github.com/soliplex/exquisite/discussions/20).

## The worksheet

The answers were drafted by an agent from the documents' text, and have not
been reviewed by a person:  `validated_by:` is deliberately blank.
