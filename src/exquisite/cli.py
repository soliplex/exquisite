"""The ``exquisite`` command:  argument parsing and the subcommands."""

import argparse
import datetime
import json
import os
import pathlib
import sys

import yaml

import exquisite
from exquisite import bind as bind_mod
from exquisite import corpus as corpus_mod
from exquisite import manifest as manifest_mod
from exquisite import resolve as resolve_mod
from exquisite import retrieval
from exquisite import rules as rules_mod
from exquisite import search
from exquisite import worksheets


class NotADataRoot(argparse.ArgumentTypeError):
    """A ``--root`` lacking ``questions/`` or ``corpus/``."""

    def __init__(self, root: pathlib.Path, missing: list[str]):
        self.root = root
        self.missing = missing
        wanted = " or ".join(f"{name}/" for name in missing)
        super().__init__(
            f"{root} has no {wanted}; run from a data repository, "
            "or pass --root / set EXQUISITE_ROOT"
        )


def _data_root(path: str) -> pathlib.Path:
    """A directory holding ``questions/`` and ``corpus/``, else `NotADataRoot`.

    The package is installed separately from the data it manages, so there is
    no checkout to default to:  the root is the working directory unless
    ``--root`` or ``EXQUISITE_ROOT`` names another.
    """
    root = pathlib.Path(path).resolve()
    missing = [
        name for name in ("questions", "corpus") if not (root / name).is_dir()
    ]

    if missing:
        raise NotADataRoot(root, missing)

    return root


def _corpora(args: argparse.Namespace) -> list:
    if args.corpus:
        return [corpus_mod.find(args.root, name) for name in args.corpus]

    return corpus_mod.discover(args.root)


def _refresh_worksheets(args: argparse.Namespace) -> int:
    done = worksheets.refresh(
        root=args.root,
        corpora=_corpora(args),
        ingestion=args.ingestion,
        generated=args.date,
        provisional=args.provisional,
        rules=args.rules,
    )

    changed = [item for item in done if item[4]]

    for path, designators, kept, dropped, _ in changed:
        note = f"  {dropped} answer(s) dropped" if dropped else ""
        print(
            f"{designators:4d} designators  {kept:4d} answers kept"
            f"{note}  {path}"
        )

    unchanged = len(done) - len(changed)

    if unchanged:
        print(f"{unchanged} worksheet(s) already current")

    if not done:
        print(
            "no worksheets found; use `add-worksheet` to pair a question set"
        )

    return 0


def _add_worksheet(args: argparse.Namespace) -> int:
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
            rules=args.rules,
        )
    except (FileExistsError, ValueError) as exc:
        print(exc, file=sys.stderr)

        return 1

    print(f"created {path.relative_to(args.root)}")

    return 0


def _resolve_references(args: argparse.Namespace) -> int:
    failed = 0

    for corpus_dir in _corpora(args):
        corpus = manifest_mod.load(corpus_dir.ingestion(args.ingestion))

        for path in corpus_dir.worksheets():
            tally = resolve_mod.resolve_file(
                worksheet_path=path,
                root=args.root,
                corpus=corpus,
                generated=args.date,
                rules=args.rules,
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


def _bind_problems(tally: dict) -> int:
    """Report what binding could not do, on stderr;  how many failed."""
    failed = 0

    for reference in tally["unknown_reference"]:
        print(f"no apply_key for reference {reference!r}", file=sys.stderr)
        failed += 1

    for note in tally["unbound"]:
        print(note, file=sys.stderr)
        failed += 1

    for note in tally["changed"]:
        print(f"CHANGED since validation: {note}", file=sys.stderr)

    return failed


def _bind(args: argparse.Namespace) -> int:
    """Bind one question set against one corpus.

    Writes the JSON to stdout unless ``--out`` names a file.  Diagnostics go to
    stderr either way, so redirecting stdout yields a usable dataset and a
    readable report at the same time.
    """

    corpus_dir = corpus_mod.find(args.root, args.corpus)
    question_set = corpus_mod.find_question_set(args.root, args.questions)
    corpus = manifest_mod.load(corpus_dir.ingestion(args.ingestion))

    try:
        document, tally = bind_mod.bind_file(
            corpus_dir=corpus_dir,
            question_set=question_set,
            root=args.root,
            corpus=corpus,
            rules=args.rules,
        )
    except bind_mod.WorksheetError as exc:
        print(exc, file=sys.stderr)

        return 1

    failed = _bind_problems(tally)

    text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"

    if args.out:
        args.out.write_text(text)
        print(
            f"{tally['labelled']:4d} labelled  "
            f"{tally['unresolved']:4d} unresolved  "
            f"{tally['no_reference']:3d} no-reference  -> {args.out}"
        )
    else:
        sys.stdout.write(text)

    return 1 if failed else 0


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _check_retrieval(args: argparse.Namespace) -> int:
    """Bind one question set, search a database for each question, and check
    that the results hold the documents it was bound to.

    The bound question set is never written:  binding problems are reported
    on stderr, as `bind` reports them, and the questions they leave without
    labels are ineligible.  With ``--out``, the run is saved whatever its
    outcome, so a failing run can still be read, or adopted as a reference;
    an existing file is refused before any work, unless ``--force``.
    """
    if args.out is not None and args.out.exists() and not args.force:
        print(
            f"{args.out} exists;  pass --force to replace it",
            file=sys.stderr,
        )

        return 1

    corpus_dir = corpus_mod.find(args.root, args.corpus)
    question_set = corpus_mod.find_question_set(args.root, args.questions)
    corpus = manifest_mod.load(corpus_dir.ingestion(args.ingestion))

    try:
        document, tally = bind_mod.bind_file(
            corpus_dir=corpus_dir,
            question_set=question_set,
            root=args.root,
            corpus=corpus,
            rules=args.rules,
        )
    except bind_mod.WorksheetError as exc:
        print(exc, file=sys.stderr)

        return 1

    _bind_problems(tally)
    asked = retrieval.questions(document["cases"])
    eligible = [question for question in asked if question.relevant]
    config, displaced = search.for_path(search.load_config(args.config))

    if displaced:
        print(
            f"searching {args.db} instead of the configuration's databases "
            f"({', '.join(displaced)})"
        )

    reference = None
    reference_name = str(args.compare) if args.compare else None

    try:
        settings, database = search.describe(args.db, config, args.top_k)
        run = retrieval.Run(
            question_set=question_set.relative,
            corpus=corpus_dir.name,
            ingestion=corpus.database,
            settings=settings,
            database=database,
            substrate=search.substrate(),
        )

        # Checked before searching, so a bad reference fails before the
        # work does.
        if args.compare:
            reference = retrieval.load(args.compare)

            for warning in retrieval.check_settings(
                run, reference, reference_name
            ):
                print(f"{reference_name}: {warning}", file=sys.stderr)

            retrieval.check_pairing(asked, reference, reference_name)
            change = retrieval.corpus_change(run, reference)

            if change:
                print(change)

        run.started = _now()
        hits = search.search(args.db, config, eligible, args.top_k)
        run.finished = _now()
    except (
        search.NoDatabase,
        search.CannotSearch,
        retrieval.NotAResultsFile,
        retrieval.IncomparableReference,
    ) as exc:
        print(exc, file=sys.stderr)

        return 1

    found = {
        question.key: found
        for question, found in zip(eligible, hits, strict=True)
    }
    run.cases = [
        retrieval.score(question, found.get(question.key, []), corpus)
        for question in asked
    ]
    outcome = retrieval.check(run, reference, args.mrr_tolerance)

    if args.out is not None:
        retrieval.save(run, args.out)
        print(f"results saved to {args.out}")

    if args.verbose:
        for line in retrieval.details(run):
            print(line)

    for line in retrieval.report(outcome, reference_name):
        print(line)

    return 1 if outcome.failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="exquisite", description=exquisite.__doc__
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_provisional(parser_):
        parser_.add_argument(
            "--provisional",
            action="store_true",
            help=(
                "pre-fill unanswered designators from trusted identifier "
                "matches, marked `provisional:` until a person confirms them"
            ),
        )

    def add_common(parser_, *, date=True):
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
            "--rules",
            type=pathlib.Path,
            default=None,
            help=(
                "normalization rules to use "
                "(default: exquisite.yaml at the root, if present)"
            ),
        )
        parser_.add_argument(
            "--ingestion",
            default=None,
            help="which manifest to use, when a corpus has more than one",
        )

        if not date:
            return

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
        "--corpus",
        action="append",
        help="corpus name; repeatable, defaults to all",
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
        help=(
            "fill in worksheets whose question set already cites document URIs"
        ),
    )
    resolve.add_argument(
        "--corpus",
        action="append",
        help="corpus name; repeatable, defaults to all",
    )
    add_common(resolve)
    resolve.set_defaults(func=_resolve_references)

    bind_cmd = sub.add_parser(
        "bind",
        help="write one question set with `relevant_uris` for one ingestion",
    )
    bind_cmd.add_argument("--corpus", required=True, help="corpus name")
    bind_cmd.add_argument(
        "--questions", required=True, help="question set stem"
    )
    bind_cmd.add_argument(
        "--out",
        type=pathlib.Path,
        default=None,
        help="write here instead of stdout",
    )
    add_common(bind_cmd)
    bind_cmd.set_defaults(func=_bind)

    check_cmd = sub.add_parser(
        "check-retrieval",
        help=(
            "search a RAG database for each question, and check that the "
            "results hold the documents it is bound to"
        ),
    )
    check_cmd.add_argument("--corpus", required=True, help="corpus name")
    check_cmd.add_argument(
        "--questions", required=True, help="question set stem"
    )
    check_cmd.add_argument(
        "--db",
        required=True,
        help="the haiku-rag database to search:  a path or a URI",
    )
    check_cmd.add_argument(
        "--config",
        type=pathlib.Path,
        default=None,
        help="haiku-rag YAML configuration (default: haiku-rag's defaults)",
    )
    check_cmd.add_argument(
        "--compare",
        type=pathlib.Path,
        default=None,
        help="results of a prior check-retrieval to compare against",
    )
    check_cmd.add_argument(
        "--top-k",
        type=int,
        default=retrieval.DEFAULT_TOP_K,
        help="results per search (default: %(default)s)",
    )
    check_cmd.add_argument(
        "--mrr-tolerance",
        type=float,
        default=retrieval.DEFAULT_MRR_TOLERANCE,
        help=(
            "how far the mean retrieval_mrr may fall below the reference's "
            "before the report says so (default: %(default)s)"
        ),
    )
    check_cmd.add_argument(
        "--out",
        type=pathlib.Path,
        default=None,
        help="write the results here, to compare a later run against",
    )
    check_cmd.add_argument(
        "--force",
        action="store_true",
        help="replace an existing --out file",
    )
    check_cmd.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="show each question's rank, and what came ahead of it",
    )
    add_common(check_cmd, date=False)
    check_cmd.set_defaults(func=_check_retrieval)

    args = parser.parse_args()

    try:
        args.rules = rules_mod.find(args.root, args.rules)
    except (rules_mod.RulesError, OSError, yaml.YAMLError) as exc:
        parser.error(f"cannot use the rules: {exc}")

    sys.exit(args.func(args))
