"""Corpus management for RAG databases: manifests, worksheets, and evaluation labels."""

import argparse
import datetime
import os
import sys
from pathlib import Path


def _data_root(path: str) -> Path:
    """A directory holding ``questions/`` and ``corpus/``, or an argparse error.

    The package is installed separately from the data it manages, so there is
    no checkout to default to:  the root is the working directory unless
    ``--root`` or ``EXQUISITE_ROOT`` names another.
    """
    root = Path(path).resolve()
    missing = [name for name in ("questions", "corpus") if not (root / name).is_dir()]

    if missing:
        raise argparse.ArgumentTypeError(
            f"{root} has no {' or '.join(name + '/' for name in missing)}; run from "
            "a data repository, or pass --root / set EXQUISITE_ROOT"
        )

    return root


def _corpora(args: argparse.Namespace) -> list:
    from exquisite import corpus as corpus_mod

    if args.corpus:
        return [corpus_mod.find(args.root, name) for name in args.corpus]

    return corpus_mod.discover(args.root)


def _refresh_worksheets(args: argparse.Namespace) -> int:
    from exquisite import worksheets

    done = worksheets.refresh(
        root=args.root,
        corpora=_corpora(args),
        ingestion=args.ingestion,
        generated=args.date,
        provisional=args.provisional,
    )

    changed = [item for item in done if item[4]]

    for path, designators, kept, dropped, _ in changed:
        note = f"  {dropped} answer(s) dropped" if dropped else ""
        print(f"{designators:4d} designators  {kept:4d} answers kept{note}  {path}")

    unchanged = len(done) - len(changed)

    if unchanged:
        print(f"{unchanged} worksheet(s) already current")

    if not done:
        print("no worksheets found; use `add-worksheet` to pair a question set")

    return 0


def _add_worksheet(args: argparse.Namespace) -> int:
    from exquisite import corpus as corpus_mod
    from exquisite import worksheets

    corpus_dir = corpus_mod.find(args.root, args.corpus)
    question_set = corpus_mod.find_question_set(args.root, args.questions)

    try:
        path = worksheets.create(
            root=args.root,
            corpus_dir=corpus_dir,
            question_set=question_set,
            ingestion=args.ingestion,
            generated=args.date,
            provisional=args.provisional,
        )
    except (FileExistsError, ValueError) as exc:
        print(exc, file=sys.stderr)

        return 1

    print(f"created {path.relative_to(args.root)}")

    return 0


def _resolve_references(args: argparse.Namespace) -> int:
    from exquisite import manifest as manifest_mod
    from exquisite import resolve as resolve_mod

    failed = 0

    for corpus_dir in _corpora(args):
        corpus = manifest_mod.load(corpus_dir.ingestion(args.ingestion))

        for path in corpus_dir.worksheets():
            tally = resolve_mod.resolve_file(
                worksheet_path=path,
                root=args.root,
                corpus=corpus,
                generated=args.date,
            )

            if tally.get("skipped"):
                continue

            print(
                f"{tally['exact']:4d} exact  {tally['moved']:4d} moved  "
                f"{len(tally['unresolved']):4d} unresolved  "
                f"{path.relative_to(args.root)}"
            )

            for note in tally["unresolved"]:
                print(f"       {note}", file=sys.stderr)
                failed += 1

    return 1 if failed else 0


def _bind(args: argparse.Namespace) -> int:
    """Bind one question set against one corpus.

    Writes the JSON to stdout unless ``--out`` names a file.  Diagnostics go to
    stderr either way, so redirecting stdout yields a usable dataset and a
    readable report at the same time.
    """
    import json

    from exquisite import bind as bind_mod
    from exquisite import corpus as corpus_mod
    from exquisite import manifest as manifest_mod

    corpus_dir = corpus_mod.find(args.root, args.corpus)
    question_set = corpus_mod.find_question_set(args.root, args.questions)
    corpus = manifest_mod.load(corpus_dir.ingestion(args.ingestion))

    try:
        document, tally = bind_mod.bind_file(
            corpus_dir=corpus_dir,
            question_set=question_set,
            root=args.root,
            corpus=corpus,
        )
    except bind_mod.WorksheetError as exc:
        print(exc, file=sys.stderr)

        return 1

    failed = 0

    for reference in tally["unknown_reference"]:
        print(f"no apply_key for reference {reference!r}", file=sys.stderr)
        failed += 1

    for note in tally["unbound"]:
        print(note, file=sys.stderr)
        failed += 1

    for note in tally["changed"]:
        print(f"CHANGED since validation: {note}", file=sys.stderr)

    text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"

    if args.out:
        args.out.write_text(text)
        print(
            f"{tally['labelled']:4d} labelled  {tally['unresolved']:4d} unresolved  "
            f"{tally['no_reference']:3d} no-reference  -> {args.out}"
        )
    else:
        sys.stdout.write(text)

    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="exquisite", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_provisional(parser_):
        parser_.add_argument(
            "--provisional",
            action="store_true",
            help=(
                "pre-fill unanswered designators from trusted identifier matches, "
                "marked `provisional:` until a person confirms them"
            ),
        )

    def add_common(parser_):
        parser_.add_argument(
            "--root",
            type=_data_root,
            default=os.environ.get("EXQUISITE_ROOT", "."),
            help=(
                "data repository holding questions/ and corpus/ "
                "(default: $EXQUISITE_ROOT, else the working directory)"
            ),
        )
        parser_.add_argument(
            "--ingestion",
            default=None,
            help="which manifest to use, when a corpus has more than one",
        )
        parser_.add_argument(
            "--date",
            default=datetime.date.today().isoformat(),
            help="value recorded as `generated:` (default: today)",
        )

    refresh = sub.add_parser(
        "refresh-worksheets",
        help="rebuild candidates and apply keys, keeping the SME's answers",
    )
    refresh.add_argument(
        "--corpus", action="append", help="corpus name; repeatable, defaults to all"
    )
    add_common(refresh)
    add_provisional(refresh)
    refresh.set_defaults(func=_refresh_worksheets)

    add = sub.add_parser(
        "add-worksheet",
        help="pair a question set with a corpus by creating its worksheet",
    )
    add.add_argument("--corpus", required=True, help="corpus name")
    add.add_argument("--questions", required=True, help="question set stem")
    add_common(add)
    add_provisional(add)
    add.set_defaults(func=_add_worksheet)

    resolve = sub.add_parser(
        "resolve-references",
        help="fill in worksheets whose question set already cites document URIs",
    )
    resolve.add_argument(
        "--corpus", action="append", help="corpus name; repeatable, defaults to all"
    )
    add_common(resolve)
    resolve.set_defaults(func=_resolve_references)

    bind_cmd = sub.add_parser(
        "bind",
        help="write one question set with `relevant_uris` for one ingestion",
    )
    bind_cmd.add_argument("--corpus", required=True, help="corpus name")
    bind_cmd.add_argument("--questions", required=True, help="question set stem")
    bind_cmd.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write here instead of stdout",
    )
    add_common(bind_cmd)
    bind_cmd.set_defaults(func=_bind)

    args = parser.parse_args()

    sys.exit(args.func(args))
