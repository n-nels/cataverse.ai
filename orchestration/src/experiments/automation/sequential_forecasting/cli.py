"""Command-line entry points for sequential forecasting preparation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import (
    DEFAULT_ARTIFACT_DIR,
    DEFAULT_DATA_ROOT,
    DEFAULT_EXCLUDE_FOLDERS,
    DEFAULT_MINIMUM_FIT_POINTS,
    DEFAULT_MODEL_PATH,
    DEFAULT_ODE_FIT_MODE,
    DEFAULT_ODE_TIMEOUT_SECONDS,
    RunConfig,
)
from .data.adapter import build_examples_from_artifacts, write_examples_artifact
from .data.validation import run_validation
from .rf.artifacts import build_artifacts
from .rf.validation import validate_rf_boundary


def main() -> None:
    """Run a named preparation command."""
    parser = argparse.ArgumentParser(description="Sequential forecasting preparation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    artifact_parser = subparsers.add_parser("rf-artifacts")
    artifact_parser.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    artifact_parser.add_argument("--exclude-folder", dest="exclude_folders", action="append")
    artifact_parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    artifact_parser.add_argument("--model-path", default=str(DEFAULT_MODEL_PATH))
    artifact_parser.add_argument("--oof-folds", type=int, default=5)
    artifact_parser.add_argument(
        "--minimum-fit-points", type=int, default=DEFAULT_MINIMUM_FIT_POINTS
    )
    artifact_parser.add_argument("--ode-fit-mode", default=DEFAULT_ODE_FIT_MODE)
    artifact_parser.add_argument(
        "--ode-timeout-seconds", type=float, default=DEFAULT_ODE_TIMEOUT_SECONDS
    )
    artifact_parser.add_argument(
        "--ode-initial-guess", nargs=5, type=float, default=None
    )
    artifact_parser.add_argument(
        "--ode-prior-fit-carry-forward", action="store_true"
    )

    validation_parser = subparsers.add_parser("validate-contract")
    validation_parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    validation_parser.add_argument("--output-dir", default=None)

    examples_parser = subparsers.add_parser("build-examples")
    examples_parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    examples_parser.add_argument("--output-dir", default=None)

    boundary_parser = subparsers.add_parser("validate-rf-boundary")
    boundary_parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    boundary_parser.add_argument("--output", default=None)

    args = parser.parse_args()
    if args.command == "rf-artifacts":
        excludes = (
            tuple(args.exclude_folders)
            if args.exclude_folders is not None
            else DEFAULT_EXCLUDE_FOLDERS
        )
        output = build_artifacts(
            RunConfig(
                data_root=args.data_root,
                exclude_folders=excludes,
                artifact_dir=args.artifact_dir,
                model_path=args.model_path,
                oof_folds=args.oof_folds,
                minimum_fit_points=args.minimum_fit_points,
                ode_fit_mode=args.ode_fit_mode,
                ode_timeout_seconds=args.ode_timeout_seconds,
                ode_initial_guess=(
                    tuple(args.ode_initial_guess)
                    if args.ode_initial_guess is not None
                    else None
                ),
                ode_prior_fit_carry_forward=args.ode_prior_fit_carry_forward,
            )
        )
        print(f"RF artifacts written to {output}")
    elif args.command == "validate-contract":
        output = run_validation(args.artifact_dir, output_dir=args.output_dir)
        print(f"Contract validation written to {output}")
    elif args.command == "build-examples":
        examples = build_examples_from_artifacts(args.artifact_dir)
        output_dir = args.output_dir or str(Path(args.artifact_dir) / "examples")
        output = write_examples_artifact(examples, output_dir)
        print(f"Sequential examples written to {output}")
    elif args.command == "validate-rf-boundary":
        report = validate_rf_boundary(args.artifact_dir)
        output = Path(args.output or Path(args.artifact_dir) / "rf_boundary_validation.json")
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"RF boundary validation written to {output}")


if __name__ == "__main__":
    main()
