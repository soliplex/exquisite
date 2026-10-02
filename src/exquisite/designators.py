"""Turning a question's prose citation into a document designator.

A question set records its source as human prose -- ``ISO/IEC 27001:2022
Sec 6.1.2`` -- naming a document *and* a location inside it.  Only the
document part is wanted, so the location is stripped off; what remains is the
"designator".

Designators are then grouped by a "collapsed key", which folds the spelling
variance these sets are full of: ``Vol 3`` for ``V3``, a supplement however it
is spelled for ``SUPP``, and all punctuation and spacing.  The volume and
supplement spellings follow the conventions the ingestion-time identifier
inference writes into `document_identifier`, so a designator and an identifier
for the same publication collapse to the same key.

Equivalences particular to one publisher's scheme -- a series renamed over
time, a prefix some citations carry and others omit -- are not built in.

None of this runs when a worksheet is *applied*.  A worksheet carries every
verbatim ``metadata.reference`` string in its ``apply_keys`` block, so applying
is exact string lookup.  That is deliberate: if the applier had to re-derive
designators it would have to reproduce this module exactly, and any drift
would silently leave cases unlabelled rather than raising.
"""

import re

#: Dash characters these question sets mix freely, all meaning "-".
_DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-"})

#: Words that begin the *location* half of a citation.  Everything from the
#: first one onward is discarded.
_LOCATION = re.compile(
    r"[,;]|\b(?:chap|chapter|para|paragraph|pg|pgs|page|pages|table|figure|fig"
    r"|attach\w*|attch|att|sec|section|note)\b",
    re.I,
)


def designator(reference: str) -> str:
    """The document-naming part of a ``reference``.

    A reference that is already a URI names a file outright -- the author
    picked it -- so the designator is that file's name.  Running such a
    reference through the prose machinery instead yields a punctuation-stripped
    path like ``filedownloadsdocidpdf``, which groups nothing usefully
    and asks an SME to re-decide something already decided.
    """
    if "://" in reference:
        import os
        import urllib.parse

        head = reference.split("#attachment=", 1)
        name = os.path.basename(
            urllib.parse.unquote(head[-1] if len(head) > 1 else head[0])
        )

        return name or reference

    text = reference.translate(_DASHES)
    text = re.sub(r"^\s*Ref:?\s*", "", text, flags=re.I)
    match = _LOCATION.search(text)
    head = text[: match.start()] if match else text

    return re.sub(r"\s+", " ", head.strip(" ,.-"))


def _normalized(text: str) -> str:
    """Lower-cased, with the known equivalences applied but spacing intact."""
    out = text.casefold().replace("_", " ")  # "_" is a separator here
    out = re.sub(r"\bvol(?:ume)?\.?\s*", "v", out)  # "Vol 3" -> "v3"
    # "Supplement", "Suppl", "Sup" -> "supp", as `identify` writes it.
    out = re.sub(r"\b(?:sup|supp|suppl|supplement)\b", "supp", out)

    return out


def collapsed_key(text: str) -> str:
    """The key that groups spelling variants of one document together."""
    return re.sub(r"[^a-z0-9]", "", _normalized(text))


def extension(key: str, text: str) -> str | None:
    """What ``text`` adds after ``key``, when it extends it at a real boundary.

    ``key`` is a collapsed key;  ``text`` is compared in its normalized,
    uncollapsed form, because collapsing erases the boundary that decides the
    question.  ``nistsp8005`` is a prefix of ``nistsp80053``, yet SP 800-53
    is not part of an SP 800-5;  ``iec61508`` is a prefix of ``iec615083``,
    and IEC 61508-3 *is* part of IEC 61508.  The difference is the ``-``
    that collapsing removed.

    So the key's characters are consumed from ``text``, and what follows must
    begin at a separator, or where a digit meets a letter (``800-53``
    then ``A``).  A digit run or a word that simply continues is not an
    extension.  Returns the remainder, collapsed, or None.
    """
    normalized = _normalized(text)
    position = 0
    consumed = 0

    while consumed < len(key) and position < len(normalized):
        char = normalized[position]
        position += 1

        if not char.isalnum():
            continue

        if char != key[consumed]:
            return None

        consumed += 1

    if consumed < len(key):
        return None

    rest = normalized[position:]
    collapsed_rest = re.sub(r"[^a-z0-9]", "", rest)

    if not collapsed_rest:
        return None

    starts_at_separator = not rest[0].isalnum()
    last, following = key[-1], rest[0]
    changes_kind = (
        following.isalnum() and last.isdigit() != following.isdigit()
    )

    return collapsed_rest if starts_at_separator or changes_kind else None


def series(name: str) -> str:
    """The publication series a designator or filename belongs to.

    Read off the *first token* rather than the collapsed form:  collapsing
    ``nist-incident-handling`` first yields the series
    ``nistincidenthandling``, which would hide that document from a search of
    its own series -- and in a corpus whose only copy of ``NIST SP 800-61`` is
    named ``nist-incident-handling.pdf``, that is the only file the designator
    can resolve to.
    """
    tokens = re.split(r"[^a-z0-9]+", _normalized(name))
    match = re.match(r"([a-z]+)", tokens[0] if tokens else "")
    found = match.group(1) if match else ""

    return found


def numbers(text: str) -> list[str]:
    """The digit runs in ``text``, in order."""
    return re.findall(r"\d+", text)
