"""Command-line entry point for scoring a classifier against ``ground_truth.json``.

Runs the validation harness (``validation.py``): the causal prefix sweep with
the 3-consecutive-fire latch (``classification.latch_sweep``), the same sweep
that writes the per-row ``classification`` column. ``--classifier`` picks among
the detector variants in ``classification.py`` (see docs/spec_nuc-clf.md).

Writing classified CSVs is done by the fit CLI:
``scripts\\run_kinetics_fit.py --folder <dataset> --classify-only``.

Usage:
    python scripts\\run_kinetics_classification.py --validate
    python scripts\\run_kinetics_classification.py --validate --input-subfolder _reprocess
    python scripts\\run_kinetics_classification.py --validate --folders nn1120-4_pd_ceo2_000
"""

from __future__ import annotations

import argparse

from src.utils.kinetics import validation
from src.utils.kinetics.writer import CLASSIFIERS

CLASSIFIER_CHOICES = CLASSIFIERS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Score a cluster_sum classifier against ground_truth.json.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run the ground-truth validation (the only mode; kept for "
        "compatibility).",
    )
    parser.add_argument(
        "--input-subfolder",
        default=None,
        help="Read each ground-truth file from <folder>/<input-subfolder>/ "
        "(e.g. _reprocess) instead of the live dataset folder.",
    )
    parser.add_argument(
        "--folders",
        nargs="+",
        default=None,
        help="Only score ground-truth entries in these dataset folders.",
    )
    parser.add_argument(
        "--classifier",
        choices=sorted(CLASSIFIER_CHOICES),
        default="combined",
        help="Which detector to score (default: %(default)s).",
    )
    for removed in ("--path", "--folder"):
        parser.add_argument(removed, help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.path is not None or args.folder is not None:
        parser.error(
            "--path/--folder moved to the fit CLI: "
            r"scripts\run_kinetics_fit.py --folder <dataset> --classify-only"
        )
    report = validation.run_validation(
        classify_fn=CLASSIFIER_CHOICES[args.classifier],
        input_subfolder=args.input_subfolder,
        folders=args.folders,
    )
    report.print_summary()


if __name__ == "__main__":
    main()
