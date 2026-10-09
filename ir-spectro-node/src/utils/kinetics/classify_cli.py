"""Command-line entry point for nucleation classification of area CSVs.

Two modes:

- **reprocess** (``--folder`` / ``--path``): write each area CSV, unchanged,
  with the causal per-row ``classification`` and, once latched,
  ``growth_onset_s`` (the growth onset, ``classification.growth_onset``)
  and ``latch_time_s`` (the latch time) on the ``cluster_sum`` rows. No kinetic
  fits; for those use ``scripts\\run_kinetics_fit.py``. Inputs are
  ``<dataset>/<input-subfolder>/`` (default ``_reprocess``), output goes to
  ``<dataset>/<input-subfolder>/<output-folder>/``.
- **validate** (``--validate``): score the detector against
  ``ground_truth.json`` (``validation.py``), e.g. after retuning it.
  ``--validate-spikes`` scores the cluster_sum spike detector
  (``segments.detect_spike``) against the entries' optional ``spike`` labels.

The detector is ``classification.classify_nucleation`` (Peak_1988 rise +
monomer_sum + amplitude gates) under the 3-consecutive-fire latch. Its
parameters are the ``kinetics_reprocess_classification`` block of
config/analysis.yaml.

Usage:
    python scripts\\run_kinetics_classification.py --folder nn1120-3_pd_ceo2_004
    python scripts\\run_kinetics_classification.py --folder "*"
    python scripts\\run_kinetics_classification.py --folder nn1120-3_pd_ceo2_004 --measurements 20260506_052154_pd_ceo2_004-019
    python scripts\\run_kinetics_classification.py --validate --input-subfolder _reprocess
    python scripts\\run_kinetics_classification.py --validate-spikes
"""

from __future__ import annotations

import argparse
import logging
import math
from pathlib import Path

import pandas as pd

from src.utils.ir_fitting.refit_cli import _lower_priority
from src.utils.kinetics import api, validation
from src.utils.kinetics.result_types import FitRunResult
from src.utils.kinetics.writer import SEARCH_ROOT

DEFAULT_OUTPUT_FOLDER = "_test_classification"
"""Not ``_test``: that is where ``run_kinetics_fit.py`` writes fitted CSVs."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write the nucleation classification into CarbonylPeakArea "
        "CSVs, or score it against ground_truth.json.",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--path", type=Path, help="Classify one *_CarbonylPeakArea.csv."
    )
    target.add_argument(
        "--folder",
        nargs="+",
        help="Classify dataset folders under data.peak_fit: names or globs, "
        'e.g. nn1120-3_pd_ceo2_004, "nn1120-3_*", "*". A glob only matches '
        "folders that have <input-subfolder>/.",
    )
    target.add_argument(
        "--validate",
        action="store_true",
        help="Score the detector against ground_truth.json instead.",
    )
    target.add_argument(
        "--validate-spikes",
        action="store_true",
        help="Score the cluster_sum spike detector (segments.detect_spike) against "
        "the 'spike' labels in ground_truth.json; unlabeled entries are skipped. "
        "Reads <folder>/_reprocess/ unless --input-subfolder is given.",
    )
    parser.add_argument(
        "--measurements",
        nargs="+",
        default=None,
        help="With --folder: only these measurement base names, exact or glob "
        '(e.g. "*-043").',
    )
    parser.add_argument(
        "--input-subfolder",
        default=None,
        help="Read area CSVs from <folder>/<input-subfolder>/ (default: _reprocess "
        "with --folder; the live dataset folder with --validate).",
    )
    parser.add_argument(
        "--output-folder",
        default=DEFAULT_OUTPUT_FOLDER,
        help="Output subfolder next to the input CSVs (default: %(default)s).",
    )
    parser.add_argument(
        "--folders",
        nargs="+",
        default=None,
        help="With --validate: only score ground-truth entries in these folders.",
    )
    parser.add_argument("--min-points", type=int, default=4)
    parser.add_argument(
        "--normal-priority",
        action="store_true",
        help="Run at normal process priority (default: below normal).",
    )
    return parser


def _resolve_folders(patterns: list[str], input_subfolder: str) -> list[str]:
    """Dataset folder names under ``data.peak_fit`` matching ``patterns``.

    A plain name is taken as given (``process_folder`` reports it if empty);
    a glob keeps only folders that have ``input_subfolder``, so ``"*"`` skips
    e.g. ``_test``. Raises ``ValueError`` for a glob that matches nothing.
    """
    names: list[str] = []
    for pattern in patterns:
        if not any(ch in pattern for ch in "*?["):
            matches = [pattern]
        else:
            matches = sorted(
                path.name
                for path in SEARCH_ROOT.glob(pattern)
                if (path / input_subfolder).is_dir()
            )
            if not matches:
                raise ValueError(
                    f"--folder {pattern!r} matches no folder under {SEARCH_ROOT} "
                    f"with a {input_subfolder} subfolder"
                )
        names += [name for name in matches if name not in names]
    return names


def _hours(rows: pd.DataFrame, column: str) -> float | None:
    """First written ``column`` value (seconds) in hours; None if absent or never latched."""
    if rows.empty or column not in rows.columns:
        return None
    values = pd.to_numeric(rows[column], errors="coerce").dropna()
    return float(values.iloc[0]) / 3600.0 if not values.empty else None


def _report(result: FitRunResult) -> None:
    latch = _hours(result.fit_params, "latch_time_s")
    if latch is None or not math.isfinite(latch):
        verdict = "continuous"
    else:
        onset = _hours(result.fit_params, "growth_onset_s")
        onset_text = (
            f"{onset:.2f} h" if onset is not None and math.isfinite(onset) else "n/a"
        )
        verdict = f"discontinuous, onset at {onset_text}, latched at {latch:.2f} h"
    print(f"{result.path.name}: {verdict}", flush=True)


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    if args.validate:
        report = validation.run_validation(
            input_subfolder=args.input_subfolder,
            folders=args.folders,
        )
        report.print_summary()
        return

    if args.validate_spikes:
        validation.print_spike_summary(
            validation.run_spike_validation(
                input_subfolder=args.input_subfolder or "_reprocess",
                folders=args.folders,
            )
        )
        return

    if not args.normal_priority:
        _lower_priority()
    kwargs = {
        "output_folder": args.output_folder,
        "fit": False,
        "min_points": args.min_points,
    }

    if args.path is not None:
        result = api.process_file(args.path, **kwargs)
        _report(result)
        print(f"Wrote {result.output_path}")
        return

    input_subfolder = args.input_subfolder or "_reprocess"
    try:
        folders = _resolve_folders(args.folder, input_subfolder)
    except ValueError as exc:
        parser.error(str(exc))

    for folder in folders:
        if len(folders) > 1:
            print(f"\n== {folder}", flush=True)
        try:
            batch = api.process_folder(
                folder,
                input_subfolder=input_subfolder,
                measurements=args.measurements,
                on_file=_report,
                **kwargs,
            )
        except ValueError as exc:
            if len(folders) == 1:
                parser.error(str(exc))
            print(f"  skipped: {exc}")
            continue
        output_dir = batch.outputs[0].parent if batch.outputs else batch.dataset_folder
        print(
            f"{batch.n_files_success}/{batch.n_files_found} files written to "
            f"{output_dir}"
        )
        for path_str, error in batch.failures.items():
            print(f"  FAILED {path_str}: {error}")


if __name__ == "__main__":
    main()
