"""Command-line entry points for sequential forecasting preparation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .baselines import run_baselines
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
from .evaluation import run_evaluation
from .inference import run_inference
from .sequential_model import DEFAULT_RIDGE_ALPHAS, train_initial_model
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

    baseline_parser = subparsers.add_parser("evaluate-baselines")
    baseline_parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    baseline_parser.add_argument("--output-dir", default=None)
    baseline_parser.add_argument("--ode-timeout-seconds", type=float, default=None)

    model_parser = subparsers.add_parser("train-sequential-model")
    model_parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    model_parser.add_argument("--output-dir", default=None)
    model_parser.add_argument("--ridge-alpha", dest="ridge_alphas", action="append", type=float)
    model_parser.add_argument("--ode-timeout-seconds", type=float, default=None)

    inference_parser = subparsers.add_parser("run-inference")
    inference_parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    inference_parser.add_argument("--model-dir", default=None)
    inference_parser.add_argument("--output-dir", default=None)
    inference_parser.add_argument("--ode-timeout-seconds", type=float, default=None)

    evaluation_parser = subparsers.add_parser("evaluate-sequential")
    evaluation_parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    evaluation_parser.add_argument("--baseline-dir", default=None)
    evaluation_parser.add_argument("--inference-dir", default=None)
    evaluation_parser.add_argument("--output-dir", default=None)
    evaluation_parser.add_argument(
        "--assignment", choices=("train", "validation", "test"), default="test"
    )

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
    elif args.command == "evaluate-baselines":
        output = run_baselines(
            args.artifact_dir,
            output_dir=args.output_dir,
            timeout_seconds=args.ode_timeout_seconds,
        )
        print(f"Baseline artifacts written to {output}")
    elif args.command == "train-sequential-model":
        output = train_initial_model(
            args.artifact_dir,
            output_dir=args.output_dir,
            ridge_alphas=(
                tuple(args.ridge_alphas)
                if args.ridge_alphas is not None
                else DEFAULT_RIDGE_ALPHAS
            ),
            timeout_seconds=args.ode_timeout_seconds,
        )
        print(f"Sequential model artifacts written to {output}")
    elif args.command == "run-inference":
        output = run_inference(
            args.artifact_dir,
            model_dir=args.model_dir,
            output_dir=args.output_dir,
            timeout_seconds=args.ode_timeout_seconds,
        )
        print(f"Inference artifacts written to {output}")
    elif args.command == "evaluate-sequential":
        output = run_evaluation(
            args.artifact_dir,
            baseline_dir=args.baseline_dir,
            inference_dir=args.inference_dir,
            output_dir=args.output_dir,
            assignment=args.assignment,
        )
        print(f"Evaluation artifacts written to {output}")


if __name__ == "__main__":
    main()
