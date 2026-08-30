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
from .data import apply as apply_module
from .data import build, fits, plan, source


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
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    settings = Settings.from_env(args.env)
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

    paths = source.discover(root)
    print(f"Found {len(paths)} experiment file(s) under {root}\n")
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

    with driver_session(settings) as session:
        result = plan.plan(session, intended)
        print(plan.render(result, intended))

    gap = plan.summarise_missing_adsparams(intended)
    if not gap["adsparams_built"]:
        print(f"\nNOTE: {gap['note']}")

    if not args.apply:
        print("\nDry run. Nothing was written. Pass --apply to write.")
        return 0 if result.is_safe_to_apply else 1

    if not result.is_safe_to_apply:
        print("\nRefusing to apply: resolve the errors above first.")
        return 1

    try:
        with driver_session(settings) as session:
            outcome = apply_module.apply(
                session, intended, allow_mass_deletion=args.allow_mass_deletion
            )
    except apply_module.RefusedError as exc:
        print(f"\nRefused: {exc}")
        return 1

    print("\nApplied.")
    print(outcome.summary())
    return 1 if (outcome.sweep and outcome.sweep.aborted) else 0


if __name__ == "__main__":
    raise SystemExit(main())
