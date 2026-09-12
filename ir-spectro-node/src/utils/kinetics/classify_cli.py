"""Command-line entry point for the offline kinetics classification workflow.

Wraps ``classify_file``/``classify_folder`` and the ground-truth validation
harness (``validation.py``) behind one argparse CLI, with a ``--classifier``
flag to pick among the detector variants in ``classification.py`` -- including
the in-progress nucleation-classifier candidates being scored against
``ground_truth.json`` per ``docs/spec.md``.

Batch *fitting* (``fit_file``/``fit_folder``/``fit_folder_by_sum_models``) is
deliberately not covered here -- it stays on the edit-constants-and-rerun
convention via ``api.py``'s own ``__main__`` block (see CLAUDE.md).

Usage:
    python scripts\\run_kinetics_classification.py --folder nn1120-3_pd_ceo2_004
    python scripts\\run_kinetics_classification.py --path <file>.csv --classifier drawdown
    python scripts\\run_kinetics_classification.py --validate --classifier combined
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

path = Path(__file__).resolve().parents[3]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.utils.kinetics import api, validation
from src.utils.kinetics.writer import CLASSIFIER

CLASSIFIER_CHOICES: dict[str, Callable[..., dict[str, Any]]] = {
    "default": CLASSIFIER.classify_trajectory,
    "sustained_rise": CLASSIFIER.classify_trajectory_sustained_rise,
    "drawdown": CLASSIFIER.classify_trajectory_drawdown,
    "combined": CLASSIFIER.classify_trajectory_combined,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch-run trajectory classification over CarbonylPeakArea CSVs.",
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument(
        "--path", type=Path, help="Classify one *_CarbonylPeakArea.csv file."
    )
    target.add_argument(
        "--folder",
        type=Path,
        help="Classify every matching file under a dataset folder "
        "(absolute, or relative to SEARCH_ROOT).",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Ignore --path/--folder; score the chosen --classifier against "
        "ground_truth.json instead and print the summary.",
    )
    parser.add_argument(
        "--classifier",
        choices=sorted(CLASSIFIER_CHOICES),
        default="combined",
        help="Which classification algorithm to run (default: %(default)s). "
        "'combined' is the current best-performing detector per docs/spec.md "
        "(285/288); 'default' is the original baseline (264/288).",
    )
    parser.add_argument(
        "--peak-names",
        nargs="+",
        default=None,
        help="Restrict to these Peak_Name values (default: all).",
    )
    parser.add_argument("--min-points", type=int, default=4)
    parser.add_argument(
        "--output-folder",
        default="_test",
        help="Output subfolder name for classified CSVs (default: %(default)s).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    classify_fn = CLASSIFIER_CHOICES[args.classifier]

    if args.validate:
        report = validation.run_validation(classify_fn=classify_fn)
        report.print_summary()
        return

    if args.path is None and args.folder is None:
        parser.error("one of --path, --folder, or --validate is required")

    if args.path is not None:
        result = api.classify_file(
            args.path,
            peak_names=args.peak_names,
            min_points=args.min_points,
            output_folder=args.output_folder,
            classify_fn=classify_fn,
        )
        print(f"Wrote {result.output_path} ({result.n_rows_fit} rows)")
        return

    batch_result = api.classify_folder(
        args.folder,
        peak_names=args.peak_names,
        min_points=args.min_points,
        output_folder=args.output_folder,
        classify_fn=classify_fn,
    )
    print(
        f"{batch_result.n_files_success}/{batch_result.n_files_found} files "
        f"classified under {batch_result.dataset_folder}"
    )
    for path_str, error in batch_result.failures.items():
        print(f"  FAILED {path_str}: {error}")


if __name__ == "__main__":
    main()
