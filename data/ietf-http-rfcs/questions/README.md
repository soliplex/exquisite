# Reviewing `http-pitfalls`

Each question in `http-pitfalls.json` cites a section of one RFC or draft,
and its expected answer was drafted from that section's text. To review
them, read each cited section in the document named below, and check the
answer against it. The files are the ones the corpus manifests describe:
download each from its `source_url` in `../corpus/http/ingestion/`, and
check its `sha256`.

| Question cites | File | Check |
| --- | --- | --- |
| RFC 9110, and RFC9110 | `rfc9110.txt` | §9.2.1: the safe methods. §15.5.5: 404. §4.2.2: https defaults to port 443 |
| STD 97 | `rfc9110.txt` | §9.2.2: the idempotent methods |
| RFC 2818 | `rfc2818.txt` | §2.3: the default port is 443 |
| RFC 7231 | `rfc7231.txt` | §4.2.1: the safe methods. §6.5.4: 404 |
| RFC 2616 | `rfc2616.txt` | §10.4.5: 404. §14.9: Cache-Control. §8.1.2: persistent connections are the default |
| RFC 2068 | `rfc2068.txt` | §10.4.5: 404 |
| RFC 7234 | `rfc7234.txt` | §5.2: Cache-Control |
| RFC 9111, and STD 98 | `rfc9111.txt` | §5.2: Cache-Control |
| RFC 7230 | `rfc7230.txt` | §6.3: persistence |
| RFC 9112, and STD 99 | `rfc9112.txt` | §9.3: persistence |
| RFC 7540 | `rfc7540.txt` | §3.5: the connection preface |
| RFC 9113 | `rfc9113.txt` | §3.4: the connection preface. §3.1: "h2" |
| RFC 9114 | `rfc9114.txt` | §3.1: the ALPN token "h3" |
| RFC 1945 | `rfc1945.txt` | §8: GET, HEAD, and POST |
| draft-ietf-httpbis-semantics-19, and the unversioned name | `draft-ietf-httpbis-semantics-19.txt` | §9.2.1: the safe methods. §9.2.2: the idempotent methods |

Reviewing the questions is separate from validating the worksheet,
`../corpus/http/worksheet/http-pitfalls.yaml`. That records which document
each citation means, and the person who checks it records their name and
the date in its `validated_by:` and `validated_on:` lines.
