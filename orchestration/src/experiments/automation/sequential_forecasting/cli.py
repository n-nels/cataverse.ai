"""Command-line entry points for sequential forecasting preparation."""

from __future__ import annotations

import argparse

from .config import (
    DEFAULT_ARTIFACT_DIR,
    DEFAULT_DATA_ROOT,
    DEFAULT_EXCLUDE_FOLDERS,
    DEFAULT_MODEL_PATH,
    RunConfig,
)
from .data.validation import run_validation
from .rf.artifacts import build_artifacts


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

    validation_parser = subparsers.add_parser("validate-contract")
    validation_parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    validation_parser.add_argument("--output-dir", default=None)

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
            )
        )
        print(f"RF artifacts written to {output}")
    elif args.command == "validate-contract":
        output = run_validation(args.artifact_dir, output_dir=args.output_dir)
        print(f"Contract validation written to {output}")


if __name__ == "__main__":
    main()
