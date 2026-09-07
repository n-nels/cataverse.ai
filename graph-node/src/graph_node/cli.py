"""Command line entry point.

Dry run by default. Writing to the database requires `--apply`, said out loud,
because the sweep deletes and there is no undo.
"""

from __future__ import annotations

import argparse
import logging
import sys
from contextlib import contextmanager
from pathlib import Path

from neo4j import GraphDatabase

from .common.config import Settings
from .common import ids
from .common import s3 as s3mod
from .common.ownership import DATA, KNOWLEDGE, POINTERS
from .common.rebuild import new_run_id
from .common.tls import use_system_trust_store
from .data import apply as apply_module
from .data import build, fits, plan, pointers, source
from .knowledge import build as kbuild
from .knowledge import source as ksource


@contextmanager
def driver_session(settings: Settings):
    """A session against the configured Aura instance, closed on the way out."""
    driver = GraphDatabase.driver(
        settings.uri, auth=(settings.username, settings.password)
    )
    try:
        with driver.session(database=settings.database) as session:
            yield session
    finally:
        driver.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="graph-node",
        description="Rebuild the cataverse data graph from experiment output.",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        help="Directory to scan for *_expParams.json. Defaults to SOURCE_ROOT.",
    )
    parser.add_argument(
        "--env", type=Path, default=None, help="Path to the .env file to read."
    )
    parser.add_argument(
        "--knowledge-root",
        type=Path,
        default=None,
        help="Directory of knowledge YAML. Defaults to graph-node/knowledge.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write to the database. Without it, nothing is touched.",
    )
    parser.add_argument(
        "--allow-mass-deletion",
        action="store_true",
        help=(
            "Permit the sweep to delete more than 20%% of the data graph. Use "
            "only when the dry run's delete column is what you intend."
        ),
    )
    parser.add_argument(
        "--pointers-only",
        action="store_true",
        help=(
            "Only load the S3 pointer nodes. Reads the bucket listing and the "
            "database, never the share drive, so it runs on a machine with no "
            "X: mounted."
        ),
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def run_pointers(args, settings: Settings) -> int:
    """Load RawFile and SpectrumSeries from the bucket listing.

    Separate from the rebuild because it needs different things: S3 and the
    database, but not the share. Its sweep is scoped to POINTERS, so it can
    never reach an experiment node - which is the whole reason those labels are
    not in DATA.
    """
    if not settings.s3_bucket:
        print("S3_BUCKET is not set; see .env.example.", file=sys.stderr)
        return 2

    print(f"Listing s3://{settings.s3_bucket} ...")
    stored = s3mod.list_objects(s3mod.client(settings.aws_region), settings.s3_bucket)
    print(f"  {len(stored)} object(s)")
    print()

    with driver_session(settings) as session:
        known = {
            record["b"]
            for record in session.run(
                "MATCH (f:Filename) WHERE f.base_name IS NOT NULL "
                "RETURN f.base_name AS b"
            )
        }
    print(f"{len(known)} experiment(s) in the graph to attach files to")
    print()

    intended = pointers.build(stored, known_base_names=known)
    for warning in intended.warnings:
        print(f"  {warning}")
    print()

    # HAS_RAW_FILE starts on a Filename, which this run does not write. The
    # writer has to be told that label to match the node the edge points at.
    filename_labels = {ids.filename_id(base): "Filename" for base in known}

    with driver_session(settings) as session:
        result = plan.plan(session, intended, POINTERS)
        print(plan.render(result, intended, POINTERS))

    if not args.apply:
        print()
        print("Dry run. Nothing was written. Pass --apply to write.")
        return 0 if result.is_safe_to_apply else 1

    if not result.is_safe_to_apply:
        print()
        print("Refusing to apply: resolve the errors above first.")
        return 1

    try:
        with driver_session(settings) as session:
            outcome = apply_module.apply(
                session,
                intended,
                POINTERS,
                run_id=new_run_id(),
                allow_mass_deletion=args.allow_mass_deletion,
                extra_node_labels=filename_labels,
            )
        print()
        print("Applied: pointers")
        print(outcome.summary())
    except apply_module.RefusedError as exc:
        print()
        print(f"Refused: {exc}")
        return 1
    return 1 if outcome.sweep and outcome.sweep.aborted else 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    # Before any connection: on a network that inspects TLS, Python's bundled
    # certificate authorities do not include the one doing the inspecting.
    use_system_trust_store()

    settings = Settings.from_env(args.env)

    if args.pointers_only:
        return run_pointers(args, settings)

    root = args.source_root or settings.source_root

    if not root.exists():
        print(
            f"Source root does not exist: {root}\n"
            "Point --source-root at a directory of *_expParams.json files, or "
            "set SOURCE_ROOT in .env. On a machine without the share drive "
            "mounted, X:\\peakFit will not be there.",
            file=sys.stderr,
        )
        return 2

    found = source.discover(root)
    paths = found.included
    print(f"Found {len(paths)} experiment file(s) under {root}")
    if found.excluded:
        # Reported, not silent: an excluded file is a node the sweep will
        # delete, so it has to be visible before --apply, not after.
        print(f"Excluded {len(found.excluded)}:")
        for path, reason in found.excluded[:10]:
            print(f"    {path.name} - {reason}")
        if len(found.excluded) > 10:
            print(f"    ... and {len(found.excluded) - 10} more")
    print()
    if not paths:
        return 2

    experiments = []
    unreadable: list[str] = []
    for path in paths:
        try:
            experiments.append(source.load(path))
        except source.SourceError as exc:
            unreadable.append(str(exc))

    adsparams = fits.load_all([e.base_name for e in experiments], root)
    print(f"Found fit CSVs for {len(adsparams)} of {len(experiments)} experiment(s)\n")

    intended = build.build(experiments, adsparams=adsparams)
    intended.warnings.extend(f"unreadable: {u}" for u in unreadable)

    knowledge = kbuild.build(ksource.load(args.knowledge_root), intended)

    with driver_session(settings) as session:
        result = plan.plan(session, intended, DATA)
        print(plan.render(result, intended, DATA))
        print()
        knowledge_result = plan.plan(session, knowledge, KNOWLEDGE)
        print(plan.render(knowledge_result, knowledge, KNOWLEDGE))

    safe = result.is_safe_to_apply and knowledge_result.is_safe_to_apply

    if not args.apply:
        print("\nDry run. Nothing was written. Pass --apply to write.")
        return 0 if safe else 1

    if not safe:
        print("\nRefusing to apply: resolve the errors above first.")
        return 1

    # One run id for both halves, and data first: knowledge edges attach to
    # data nodes, so those nodes must exist before the edges reach for them.
    run_id = new_run_id()
    try:
        with driver_session(settings) as session:
            data_outcome = apply_module.apply(
                session,
                intended,
                DATA,
                run_id=run_id,
                allow_mass_deletion=args.allow_mass_deletion,
            )
            print("\nApplied: data")
            print(data_outcome.summary())

            knowledge_outcome = apply_module.apply(
                session,
                knowledge,
                KNOWLEDGE,
                run_id=run_id,
                allow_mass_deletion=args.allow_mass_deletion,
                extra_node_labels={n.id: n.label for n in intended.nodes},
            )
            print("\nApplied: knowledge")
            print(knowledge_outcome.summary())
    except apply_module.RefusedError as exc:
        print(f"\nRefused: {exc}")
        return 1

    aborted = [
        o for o in (data_outcome, knowledge_outcome) if o.sweep and o.sweep.aborted
    ]
    return 1 if aborted else 0


if __name__ == "__main__":
    raise SystemExit(main())
