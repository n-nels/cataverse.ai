"""Command-line entry point for the offline kinetics model-fitting workflow.

Wraps ``api.fit_file``/``api.fit_folder`` behind one argparse CLI: pick a
kinetic model (``pfo`` or ``secondary_pfo``) and which peaks to fit it against
(e.g. ``monomer_sum``, ``cluster_sum``, or any individual ``Peak_Name``), plus
the fit's other parameters (mode, min-points, initial guess, output folder).

This is deliberately separate from ``classify_cli.py`` (classification): classifying a
trajectory's shape and fitting its kinetic parameters are different jobs, and
mixing their outputs made a prior reprocessing attempt hard to reason about.

Usage:
    python scripts\\run_kinetics_fit.py --folder nn1120-3_pd_ceo2_004 --model pfo --peak-names cluster_sum
    python scripts\\run_kinetics_fit.py --path <file>.csv --model secondary_pfo --peak-names monomer_sum --mode rolling
    python scripts\\run_kinetics_fit.py --path <file>.csv --model pfo --peak-names monomer_sum --no-use-prior-p0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

path = Path(__file__).resolve().parents[3]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.utils.kinetics import api

MODEL_CHOICES = ("pfo", "secondary_pfo")
MODE_CHOICES = ("full_series", "rolling")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch-fit a kinetic model against CarbonylPeakArea CSVs.",
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--path", type=Path, help="Fit one *_CarbonylPeakArea.csv file.")
    target.add_argument(
        "--folder",
        type=Path,
        help="Fit every matching file under a dataset folder "
        "(absolute, or relative to SEARCH_ROOT).",
    )
    parser.add_argument(
        "--model",
        choices=MODEL_CHOICES,
        default="secondary_pfo",
        help="Kinetic model to fit (default: %(default)s).",
    )
    parser.add_argument(
        "--peak-names",
        nargs="+",
        default=None,
        help="Which Peak_Name rows to fit, e.g. 'monomer_sum' or 'cluster_sum' "
        "or one or more explicit 'Peak_<value>' names. Default: all peaks.",
    )
    parser.add_argument(
        "--mode",
        choices=MODE_CHOICES,
        default="rolling",
        help="'rolling' fits at every time point with an expanding window "
        "(default) -- matches how the live server pipeline fits over the "
        "life of a run. 'full_series' fits once using all data, writing the "
        "result only to the row at the final time point.",
    )
    parser.add_argument("--min-points", type=int, default=4)
    parser.add_argument(
        "--init",
        nargs="+",
        type=float,
        default=None,
        help="Initial parameter guess (p0) passed to the optimizer. "
        "Default: built-in defaults.",
    )
    parser.add_argument(
        "--use-prior-p0",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Carry forward the previous row's successful p0 as the next "
        "row's starting seed (secondary_pfo + rolling mode only). "
        "Use --no-use-prior-p0 to start fresh from --init/defaults every row.",
    )
    parser.add_argument(
        "--output-folder",
        default="_test",
        help="Output subfolder name for fitted CSVs (default: %(default)s).",
    )
    parser.add_argument(
        "--monomer-sum-peaks",
        nargs="+",
        default=None,
        help="Override which Peak_Name rows are summed into 'monomer_sum', "
        "e.g. Peak_2113 Peak_2103 Peak_2093. Default: use the config-defined "
        "definition (or the input CSV's existing monomer_sum row).",
    )
    parser.add_argument(
        "--cluster-sum-peaks",
        nargs="+",
        default=None,
        help="Same override as --monomer-sum-peaks, for 'cluster_sum'.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.path is None and args.folder is None:
        parser.error("one of --path or --folder is required")

    if args.path is not None:
        result = api.fit_file(
            args.path,
            model=args.model,
            peak_names=args.peak_names,
            mode=args.mode,
            min_points=args.min_points,
            init=args.init,
            use_prior_p0=args.use_prior_p0,
            output_folder=args.output_folder,
            monomer_sum_peaks=args.monomer_sum_peaks,
            cluster_sum_peaks=args.cluster_sum_peaks,
        )
        print(f"Wrote {result.output_path} ({result.n_rows_fit} rows)")
        for key, value in result.metrics_summary.items():
            print(f"  {key}: {value:.4g}")
        return

    batch_result = api.fit_folder(
        args.folder,
        model=args.model,
        peak_names=args.peak_names,
        mode=args.mode,
        min_points=args.min_points,
        init=args.init,
        use_prior_p0=args.use_prior_p0,
        output_folder=args.output_folder,
        monomer_sum_peaks=args.monomer_sum_peaks,
        cluster_sum_peaks=args.cluster_sum_peaks,
    )
    print(
        f"{batch_result.n_files_success}/{batch_result.n_files_found} files "
        f"fit under {batch_result.dataset_folder}"
    )
    for path_str, error in batch_result.failures.items():
        print(f"  FAILED {path_str}: {error}")


if __name__ == "__main__":
    main()
