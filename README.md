# Corpus management for RAG databases

Ref: [Exquisite Corpse](https://en.wikipedia.org/wiki/Exquisite_corpse)

## Normalization rules

Question sets cite documents in prose (`ISO 9001 Sec 4.2`), and the same
publication is spelled many ways. `exquisite` reduces each citation to a
*designator* (`ISO 9001`) and groups designators by a *collapsed key*
(`iso9001`), so spelling variants of one document land together.

The built-in rules cover only conventions that hold across publishers:

- dashes of every kind read as `-`;
- `Vol 3` / `Volume 3` read as `v3`;
- `Supplement` / `Suppl` / `Sup` read as `supp`;
- the location half of a citation begins at a comma, semicolon, or a word
  such as `Sec`, `Chapter`, `Para`, `Page`, `Table` or `Figure`;
- an empty reference, or `[To Be Filled Out]`, is no reference at all.

A corpus following a publisher's own scheme adds its own rules in an
`exquisite.yaml` at the root of the data repository, beside `questions/`
and `corpus/`. Pass `--rules PATH` to use another file. With no file, only
the built-ins apply.

```yaml
designators:
  # Regex -> replacement, applied in order to the lower-cased designator,
  # before the built-in folding.  Here:  "Std. 12" and "12" are one key.
  rewrite:
    - {pattern: '^\s*std\.?\s+', replace: ''}
    - {pattern: '\baddendum\b', replace: 'supplement'}
  # A series renamed over time:  the canonical name, then its aliases.
  # Filenames beginning with an alias are searched as the canonical series.
  series:
    handbook: [manual, guide]
  # Extra words that begin the location half of a citation.
  location_words: [clause, annex]
references:
  # Extra values that stand where a reference belongs but are none,
  # compared exactly (after trimming whitespace), like the built-in one.
  placeholders: ["TBD", "n/a", "N/A"]
# Extra kinds of extension.  Each pattern is matched against what a
# document's identifier adds beyond a cited key ("ISO 9001 Amd 1" adds
# "amd1" to "ISO 9001"), and is tried before the built-in "supplement",
# "volume" and "sub-publication".
relations:
  - {pattern: '^amd\d', label: amendment}
  - {pattern: '^errata', label: errata}
attachments:
  # A note on each attachment whose parent filename matches.
  parent_notes:
    - {pattern: '^bulletin-', note: 'parent is a bulletin'}
```

Every section and key is optional. Caller rules extend the built-ins and
never replace them. Patterns are case-insensitive and are compiled when the
file is loaded; placeholders and location words are plain text, not
patterns. An unknown key, a value of the wrong shape, or a pattern
that does not compile stops the command, and the error names the key that
holds it.

Rules change how designators group, so each worksheet records a digest of
the rules it was generated under, with the generation of the built-in rules
and whether a rules file contributed:

```yaml
rules: a6597c4a4571   # normalization v1, built-ins only
```

The digest covers the built-ins as well as `exquisite.yaml`, so it changes
when a new release of `exquisite` changes the built-in rules, not only when
the file does. Each generation of the built-ins is described in
`exquisite.rules.NORMALIZATION_CHANGES`, so `v1` can be looked up. A refresh under different rules regenerates the worksheet,
and the changed digest shows why. If the worksheet had already been
validated, the digest it was validated under is kept beside the new one, as
`validated_against_rules:`, so the regrouping is flagged for re-validation
rather than inherited silently. Binding is unaffected: a worksheet's `apply_keys` map
each verbatim citation to its designator, so binding is exact string lookup
whatever the rules.
