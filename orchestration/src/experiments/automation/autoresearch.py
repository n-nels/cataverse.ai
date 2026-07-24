"""CLI entry point for the autonomous experiment harness.

Usage:

    # smoke test (no git, in-process, small budget) — verifies infrastructure
    python autoresearch.py --manifest manifests/example_lightgbm.yaml --smoke \\
        --max-trials 2 --wall-clock 5

    # real campaign (requires a clean autoresearch/<run-tag> branch)
    python autoresearch.py --manifest manifests/my_campaign.yaml --git

The harness builds the dataset from the cached outputs/ parquet by default.
Pass --data-dir to point at a different cached dataset directory.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure the automation package dir (this file's directory) is importable.
_AUTOMATION_DIR = Path(__file__).resolve().parent
if str(_AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(_AUTOMATION_DIR))

from harness.campaign import run_campaign  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a bounded autonomous hyperparameter campaign."
    )
    parser.add_argument("--manifest", required=True, help="Path to manifest.yaml")
    parser.add_argument(
        "--data-dir", default=None,
        help="Directory with cached X.parquet/y.parquet (default: ./outputs)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--smoke", action="store_true",
                      help="Smoke mode: no git, in-process trials, no branch.")
    mode.add_argument("--git", action="store_true",
                      help="Git mode: require an autoresearch branch, commit/discard per trial.")
    parser.add_argument("--max-trials", type=int, default=None,
                         help="Override (shrink) maximum trial count.")
    parser.add_argument("--wall-clock", type=float, default=None,
                         help="Override (shrink) maximum wall-clock minutes.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not args.smoke and not args.git:
        parser.error("choose --smoke or --git")

    summary = run_campaign(
        manifest_path=args.manifest,
        automation_dir=_AUTOMATION_DIR,
        data_dir=args.data_dir,
        smoke=args.smoke,
        git=args.git,
        max_trials_override=args.max_trials,
        wall_clock_minutes_override=args.wall_clock,
    )

    print("\n=== Campaign complete ===")
    print(f"experiment_id:        {summary.experiment_id}")
    print(f"trials attempted:     {summary.trials_attempted}")
    print(f"successful trials:    {summary.successful_trials}")
    print(f"failed trials:        {summary.failed_trials}")
    print(f"baseline val RMSE:    {summary.baseline_val_rmse}")
    print(f"best val RMSE:        {summary.best_val_rmse}")
    print(f"best test RMSE:       {summary.best_test_rmse}")
    print(f"baseline test RMSE:   {summary.baseline_test_rmse}")
    print(f"recommendation:       {summary.recommendation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())