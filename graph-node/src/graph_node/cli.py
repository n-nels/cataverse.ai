"""Command line entry point.

Only the dry run exists today. Applying is deliberately not wired up: the
write path has not been built, and pointing it at the live Aura instance is
Nick's call to make, not a default.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from neo4j import GraphDatabase

from .common.config import Settings
from .data import build, fits, plan, source


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
        "--dry-run",
        action="store_true",
        default=True,
        help="Report what would change without writing. Currently the only mode.",
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

    driver = GraphDatabase.driver(
        settings.uri, auth=(settings.username, settings.password)
    )
    try:
        with driver.session(database=settings.database) as session:
            result = plan.plan(session, intended)
            print(plan.render(result, intended))
    finally:
        driver.close()

    gap = plan.summarise_missing_adsparams(intended)
    if not gap["adsparams_built"]:
        print(f"\nNOTE: {gap['note']}")

    print("\nDry run only - applying is not implemented yet.")
    return 0 if result.is_safe_to_apply else 1


if __name__ == "__main__":
    raise SystemExit(main())
