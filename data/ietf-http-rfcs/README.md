# IETF HTTP RFC example corpus

A small data repository of the HTTP specifications from 1996 to 2022, built to
exercise what makes RFCs hard to label. An RFC is never revised in place:
every new edition gets a new number, and editions split and merge. So the
tooling cannot tell from an identifier that one document replaced another.
See [#4](https://github.com/soliplex/exquisite/issues/4).

Run `exquisite` against it with `--root`:

```bash
uv run exquisite refresh-worksheets --root data/ietf-http-rfcs --ingestion http-2022
uv run exquisite bind --root data/ietf-http-rfcs --corpus http \
    --questions http-pitfalls --ingestion http-2022
```

`tests/unit/test_data_ietf_http_rfcs.py` pins what `exquisite` makes of it.

## Contents

```text
exquisite.yaml                        normalization rules: STD aliases, drafts
questions/http-pitfalls.json          24 questions, each citing a pitfall
corpus/http/
  ingestion/http-2015.{csv,yaml}      the specifications current in 2015
  ingestion/http-2022.{csv,yaml}      the specifications current in 2022
  worksheet/http-pitfalls.yaml        which documents each citation means
```

## The documents

Fourteen documents, as published on `rfc-editor.org` (and, for the draft,
`ietf.org`), downloaded on 2026-10-02. Every document is the official TXT,
the one format the RFC Editor publishes for all of them. The documents
themselves are not committed: each manifest records the official URL as
`source_url`, and the `sha256` of the downloaded file.

| Document | `http-2015` | `http-2022` | Status |
| --- | :-: | :-: | --- |
| RFC 1945, HTTP/1.0 | ✓ | ✓ | Informational; never obsoleted |
| RFC 2068, HTTP/1.1 | ✓ | | obsoleted by RFC 2616 |
| RFC 2616, HTTP/1.1 | ✓ | | obsoleted by RFC 7230–7235 |
| RFC 2818, HTTP Over TLS | ✓ | | obsoleted by RFC 9110, which absorbed it |
| RFC 7230, Message Syntax and Routing | ✓ | | obsoleted by RFC 9110 and RFC 9112, which split it |
| RFC 7231, Semantics and Content | ✓ | | obsoleted by RFC 9110 |
| RFC 7234, Caching | ✓ | | obsoleted by RFC 9111 |
| RFC 7540, HTTP/2 | ✓ | | obsoleted by RFC 9113 |
| RFC 9110, HTTP Semantics (STD 97) | | ✓ | Internet Standard |
| RFC 9111, HTTP Caching (STD 98) | | ✓ | Internet Standard |
| RFC 9112, HTTP/1.1 (STD 99) | | ✓ | Internet Standard |
| RFC 9113, HTTP/2 | | ✓ | Proposed Standard |
| RFC 9114, HTTP/3 | | ✓ | Proposed Standard |
| draft-ietf-httpbis-semantics-19 | | ✓ | the final draft of RFC 9110 |

**The ingestions are synthetic.** No RAG database has ingested this corpus
yet, so the URIs (`file:///data/ietf-http-rfcs/…`) are shaped like an
ingester's, and the sidecars record no substrate. The hashes and source URLs
are real. Every identifier is recorded as `override`, mapped by hand.

## The pitfalls

Each question's citation is spelled to provoke one of these. Every answer
was checked against the cited section of the document.

| Pitfall | Citations |
| --- | --- |
| One RFC, several spellings | `RFC 9110`, `RFC9110` |
| An STD alias for an RFC | `STD 97`, `STD 98`, `STD 99` |
| A superseded RFC, its answer unchanged | `RFC 7231` on safe methods and 404, as in RFC 9110 |
| Editions whose answers differ | `RFC 2068` and `RFC 2616` define 404 as "has not found anything matching the Request-URI", RFC 9110 as "did not find a current representation" |
| One RFC split across successors | `RFC 2616` on caching (now RFC 9111) and on persistent connections (now RFC 9112); `RFC 7230` (now RFC 9110 and RFC 9112) |
| An RFC absorbed into a broader one | `RFC 2818` on port 443, now in RFC 9110 |
| The same content, renumbered | `RFC 7540, Section 3.5` became `RFC 9113, Section 3.4` |
| A new protocol, with no predecessor | `RFC 9114` |
| Unchanged throughout | `RFC 1945` |
| A draft, versioned and not | `draft-ietf-httpbis-semantics-19`, and `draft-ietf-httpbis-semantics` with no revision |

No citation uses `§` as a location marker, or names the location before the
document (`Section 8.3 of RFC 9110`). `exquisite` does not yet reduce either
to a correct designator (#4); questions in those forms belong with the fix.

## What binding shows

The worksheet records the document each citation actually means, so neither
ingestion binds every question:

- `http-2022` labels 14 of 24. It cannot label the citations of RFCs since
  obsoleted.
- `http-2015` labels 11 of 24. It cannot label the citations of RFCs not
  yet published, their STD aliases, or the draft.

Unlike a NIST revision, nothing in an RFC's identifier says what succeeded
it: no rule relates RFC 7231 to RFC 9110. The worksheet's notes name each
successor. Making that lineage available to the tooling is the open
question in #4, and the case for the ingestion diff proposed in
[discussion #20](https://github.com/soliplex/exquisite/discussions/20).

## The worksheet

The answers were drafted by an agent from the documents' text, and have not
been reviewed by a person:  `validated_by:` is deliberately blank.
