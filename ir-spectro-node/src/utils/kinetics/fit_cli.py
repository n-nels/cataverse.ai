"""Command-line entry point for offline kinetics reprocessing.

``--mode segments`` (default) fits once per (peak, segment) over the whole
trajectory, with segments chosen by the measurement's final nucleation label
(``segments.py``, ``spec-working.md``). It writes
``*_CarbonylKineticParams.csv`` (one row per peak and segment) and
``*_CarbonylKineticFeatures.csv`` (classification, boundaries, spike).

``--mode rolling`` is the live-equivalent path: one fit at every time point,
written into ``*_CarbonylPeakArea.csv``:

- monomer peaks + ``monomer_sum`` get secondary_pfo;
- cluster peaks + ``cluster_sum`` get pfo (``writer.REGIME_MODELS``);
- ``cluster_sum`` gets the causal per-row nucleation ``classification``
  (``classification.classify_nucleation`` under ``latch_sweep``).

Inputs are the area CSVs in ``<dataset>/<input-subfolder>/`` (default
``_reprocess``, the refit output), and ``--build-areas`` first (re)builds them
from the refit params (``areas.py``). Output goes to
``<dataset>/<input-subfolder>/<output-folder>/``. Sums and groups come from the
``ir_fitting.fit`` block of ``config/analysis.yaml``, not from flags.

Runs at below-normal process priority by default: this is the lab machine.

Usage:
    python scripts\\run_kinetics_fit.py --folder nn1120-3_pd_ceo2_004 --build-areas
    python scripts\\run_kinetics_fit.py --folder nn1120-3_pd_ceo2_004 --measurements 20260506_052154_pd_ceo2_004-019
    python scripts\\run_kinetics_fit.py --folder nn1120-3_pd_ceo2_004 --classify-only
    python scripts\\run_kinetics_fit.py --folder nn1120-3_pd_ceo2_004 --mode rolling
"""

from __future__ import annotations

import argparse
import logging
import math
import time
from pathlib import Path

from src.utils.ir_fitting.refit_cli import _lower_priority, _worker_count
from src.utils.kinetics import api
from src.utils.kinetics.result_types import FitRunResult


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Classify and kinetics-fit CarbonylPeakArea CSVs (live-equivalent).",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--path", type=Path, help="Process one *_CarbonylPeakArea.csv.")
    target.add_argument(
        "--folder",
        help="Dataset folder name under data.peak_fit (e.g. nn1120-3_pd_ceo2_004).",
    )
    parser.add_argument(
        "--measurements",
        nargs="+",
        default=None,
        help="With --folder: only these measurement base names.",
    )
    parser.add_argument(
        "--input-subfolder",
        default="_reprocess",
        help="With --folder: read area CSVs from <folder>/<input-subfolder>/ "
        "(default: %(default)s).",
    )
    parser.add_argument(
        "--build-areas",
        action="store_true",
        help="With --folder: (re)build the area CSVs from the params CSVs in "
        "<folder>/<input-subfolder>/ first.",
    )
    parser.add_argument(
        "--output-folder",
        default="_test",
        help="Output subfolder next to the input CSVs (default: %(default)s).",
    )
    parser.add_argument(
        "--mode",
        choices=api.MODES,
        default="segments",
        help="'segments': one fit per peak and segment over the whole trajectory, "
        "written to *_CarbonylKineticParams.csv / *_CarbonylKineticFeatures.csv. "
        "'rolling': live-equivalent fit at every time point, written to "
        "*_CarbonylPeakArea.csv (default: %(default)s).",
    )
    parser.add_argument(
        "--classify-only",
        action="store_true",
        help="No kinetic fits (fast): the classification (rolling) or the "
        "features file (segments) only.",
    )
    parser.add_argument(
        "--peak-names",
        nargs="+",
        default=None,
        help="Only fit these Peak_Name rows, e.g. monomer_sum cluster_sum. "
        "Default: every monomer/cluster group peak and both sums.",
    )
    parser.add_argument(
        "--min-points",
        type=int,
        default=4,
        help="Minimum time points before classifying or fitting: per time point "
        "(rolling) or per segment (segments) (default: %(default)s).",
    )
    parser.add_argument(
        "--use-prior-p0",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Seed each time point's secondary_pfo p0 search from the previous "
        "one. Off by default, as in live.",
    )
    parser.add_argument(
        "--normal-priority",
        action="store_true",
        help="Run at normal process priority (default: below normal).",
    )
    parser.add_argument(
        "--workers",
        type=_worker_count,
        default=1,
        help="With --folder: process this many measurements at once, one process "
        "each (default: %(default)s). At the default below-normal priority, extra "
        "workers use idle cores only. More load means more secondary_pfo ODE "
        "timeouts (0.1 s each), which are reported per file.",
    )
    return parser


def _report(result: FitRunResult, label: str) -> None:
    metrics = " ".join(
        f"{k}={v:.3g}" for k, v in result.metrics_summary.items() if math.isfinite(v)
    )
    notes = " ".join(result.warnings)
    name = result.output_path.name if result.output_path else result.path.name
    rows = f"{result.n_rows_fit} rows" if result.n_rows_fit else "no fits"
    print(f"{label} {name}: {rows} {metrics} {notes}".rstrip(), flush=True)


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    if not args.normal_priority:
        _lower_priority()

    kwargs = {
        "mode": args.mode,
        "output_folder": args.output_folder,
        "fit": not args.classify_only,
        "min_points": args.min_points,
        "carry_forward_p0": args.use_prior_p0,
        "peak_names": args.peak_names,
    }

    if args.path is not None:
        start = time.perf_counter()
        result = api.process_file(args.path, **kwargs)
        _report(result, f"[{time.perf_counter() - start:.0f}s]")
        print(f"Wrote {result.output_path}")
        return

    if args.build_areas:
        reports = api.build_areas(
            args.folder,
            input_subfolder=args.input_subfolder,
            measurements=args.measurements,
        )
        print(
            f"Built {len(reports)} area CSVs; "
            f"{sum(r.n_missing for r in reports)} spectra without a fit"
        )

    start = time.perf_counter()
    done = {"n": 0}

    def on_file(result: FitRunResult) -> None:
        done["n"] += 1
        _report(result, f"[{done['n']} done, {time.perf_counter() - start:.0f}s]")

    batch = api.process_folder(
        args.folder,
        input_subfolder=args.input_subfolder,
        measurements=args.measurements,
        on_file=on_file,
        workers=args.workers,
        **kwargs,
    )
    print(
        f"{batch.n_files_success}/{batch.n_files_found} files processed under "
        f"{batch.dataset_folder}"
    )
    for path_str, error in batch.failures.items():
        print(f"  FAILED {path_str}: {error}")


if __name__ == "__main__":
    main()
