# Reviewing `sp800-pitfalls`

Each question in `sp800-pitfalls.json` cites a section of one NIST
publication, and its expected answer was drafted from that section's text.
To review them, read each cited section in the document named below, and
check the answer against it. The files are the ones the corpus manifests
describe: download each from its `source_url` in
`../corpus/sp800/ingestion/`, and check its `sha256`.

| Question cites | File | Check |
| --- | --- | --- |
| SP 800-30 Rev. 1 (three spellings) | `nistspecialpublication800-30r1.pdf` | Ch. 3: the four process steps, the first being "prepare". §2.1: the three tiers |
| SP 800-61 Rev. 2 (two spellings) | `NIST.SP.800-61r2.pdf` | §3: the four life-cycle phases. §3.3: the phase after Detection and Analysis |
| SP 800-61r3, and the unrevised `SP 800-61, Section 2.1` | `NIST.SP.800-61r3.pdf` | §2.1: the six CSF 2.0 Functions |
| SP 800-53 Rev. 5, and Rev. 4 | `NIST.SP.800-53r5.pdf`, `NIST.SP.800-53r4.pdf` | §2.2 of each: 20 families, and eighteen |
| SP 800-53 Control AC-2, with no revision | both of the above | AC-2 is Account Management in each |
| SP 800-53A Rev. 5 | `NIST.SP.800-53Ar5.pdf` | §2.4.2: examine, interview, and test |
| SP 800-53B | `NIST.SP.800-53B.pdf` | Chapter Two: three security baselines, plus the privacy baseline |
| SP 800-171 Rev. 2, and r3 | `NIST.SP.800-171r2.pdf`, `NIST.SP.800-171r3.pdf` | Ch. 3: fourteen families. §3: 17 families |
| SP 800-171A Rev. 3 | `NIST.SP.800-171Ar3.pdf` | §2.1: examine, interview, and test |
| SP 800-63B (2017) | `NIST.SP.800-63b.pdf` | §5.1.1.1: 8 characters |
| SP 800-63B-4 (two spellings) | `NIST.SP.800-63b-4.pdf` | §3.1.1.2: 15 characters single-factor, eight with multi-factor |
| SP 800-63-4 | `NIST.SP.800-63-4.pdf` | §1.2: IAL refers to identity proofing |
| SP 800-63Bsup1, and Supplement 1 | `NIST.SP.800-63Bsup1.pdf` | §3: syncable authenticators achieve AAL2 |
| SP 800-60 Volume I, and Vol. II | `nistspecialpublication800-60v1r1.pdf`, `nistspecialpublication800-60v2r1.pdf` | §3.1.1: three impact levels. App. C, §C.2.3.1: budget formulation is Low, Low, Low |
| SP 800-57 Part 1 Rev. 5 | `NIST.SP.800-57pt1r5.pdf` | §5.3: cryptoperiod |
| SP 800-57 Rev. 6 (Initial Public Draft) | `NIST.SP.800-57pt1r6.ipd.pdf` | Note to Reviewers: FIPS 203, 204, and 205 |

Reviewing the questions is separate from validating the worksheet,
`../corpus/sp800/worksheet/sp800-pitfalls.yaml`. That records which document
each citation means, and the person who checks it records their name and
the date in its `validated_by:` and `validated_on:` lines.
