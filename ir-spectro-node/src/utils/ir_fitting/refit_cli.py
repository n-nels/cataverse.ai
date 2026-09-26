"""Command-line entry point for offline refits.

Wraps :func:`~src.utils.ir_fitting.api.fit_files`: selects subIFG files,
refits every peak in ``ir_fitting.fit`` on each, writes the live-schema CSVs
and a run log into an output subfolder, and optionally one figure per file.

Peaks and their rules come from ``config/analysis.yaml`` (``ir_fitting.fit``);
edit them there between runs. The baseline recipe comes from the flags below,
which are the same as the baseline CLI's.

Usage:
    python scripts\\run_refit.py
    python scripts\\run_refit.py --plot --output-folder _test-1
    python scripts\\run_refit.py --folder nn1120-4_pd_ceo2_000 \\
        --measurements "*-021" --delta-groups delta10 --plot
    python scripts\\run_refit.py --folder nn1120-3_pd_ceo2_000 \\
        --measurements "*" --limit 0 --plot --workers 8
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

path = Path(__file__).resolve().parents[3]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.utils.ir_fitting import config as ir_config
from src.utils.ir_fitting.api import (
    DEFAULT_FIGURE_BUDGET,
    fit_files,
    subifg_files,
)
from src.utils.ir_fitting.baseline import DEFAULT_FILES, DEFAULT_FOLDER
from src.utils.ir_fitting.baseline_cli import (
    add_recipe_arguments,
    build_variant,
    describe_variant,
)
from src.utils.ir_fitting.voigt import FIT_METHOD
from src.utils.ir_fitting.writer import peak_fit_dir

LOGGER = logging.getLogger(__name__)

DEFAULT_OUTPUT_FOLDER = "_test"
DEFAULT_PLOT_WINDOWS = ((2250.0, 1750.0),)
"""Full ROI only; pass --plot-window for a zoom."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_refit",
        description=(
            "Refit every peak in ir_fitting.fit (config/analysis.yaml) on chosen "
            "subIFG files. Writes params/baseline/residual CSVs and a log into "
            "an output subfolder; never into the source data."
        ),
    )

    data = parser.add_argument_group(
        "which data to fit",
        f"Both selectors omitted fits the {len(DEFAULT_FILES)} default files, "
        f"which exist only in {DEFAULT_FOLDER}.",
    )
    data.add_argument(
        "--folder",
        default=DEFAULT_FOLDER,
        help="Dataset under utility.subtract_ifg.sub_ifg_output "
        "(default: %(default)s).",
    )
    data.add_argument(
        "--measurements",
        nargs="+",
        default=None,
        help='Measurement base names or globs, e.g. "*-021". Default: all.',
    )
    data.add_argument(
        "--delta-groups",
        nargs="+",
        default=None,
        help='Delta groups or file keys: "delta10", "delta10.0042", '
        '"delta10.00*". Default: all.',
    )
    data.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_FIGURE_BUDGET,
        help="Refuse a selection larger than this many files, counting ones "
        "the skip rules will drop (default: %(default)s). 0 disables the check.",
    )

    fit = parser.add_argument_group("the fit")
    fit.add_argument(
        "--baseline",
        choices=("recompute", "saved"),
        default="recompute",
        help="recompute: run the recipe below. saved: reuse the stored "
        "*_CarbonylFitBaseline.csv, i.e. the old baseline (default: %(default)s).",
    )
    add_recipe_arguments(parser, window=False)

    output = parser.add_argument_group("output")
    output.add_argument(
        "--output-folder",
        default=DEFAULT_OUTPUT_FOLDER,
        help="Subfolder of the dataset's peak-fit folder (default: %(default)s). "
        "Reused -- a second run overwrites its CSVs; logs are timestamped.",
    )
    output.add_argument(
        "--no-save", action="store_true", help="Fit only; write no CSVs or log."
    )
    output.add_argument(
        "--plot",
        action="store_true",
        help="Write one figure per file and window, as each file finishes, into "
        "the individual-fit figure folder under a subfolder named like "
        "--output-folder.",
    )
    output.add_argument(
        "--plot-window",
        nargs=2,
        type=float,
        action="append",
        metavar=("HIGH", "LOW"),
        default=None,
        help="Figure x range; repeat for several "
        f"(default: {' and '.join(f'{h:.0f}-{lo:.0f}' for h, lo in DEFAULT_PLOT_WINDOWS)}).",
    )
    output.add_argument(
        "--dpi", type=int, default=200, help="Figure resolution (default: %(default)s)."
    )
    output.add_argument(
        "--normal-priority",
        action="store_true",
        help="Run at normal process priority. By default the refit drops to "
        "below-normal on Windows so OPUS, the instrument server and the pump "
        "loop on the lab machine are never starved. Workers inherit it.",
    )
    output.add_argument(
        "--workers",
        type=_worker_count,
        default=1,
        help="Fit this many measurements at once, one process each "
        f"(default: %(default)s; max {os.cpu_count()}, the core count). At the "
        "default below-normal priority, extra workers use idle cores only.",
    )
    output.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the files, recipe, peaks and destination, then exit.",
    )
    return parser


def _worker_count(text: str) -> int:
    """argparse type for --workers: 1 up to the core count."""
    count = int(text)
    cores = os.cpu_count() or 1
    if not 1 <= count <= cores:
        raise argparse.ArgumentTypeError(f"must be 1 to {cores} (the core count)")
    return count


@dataclass
class _FigureWriter:
    """Per-file ``on_file`` callback: write that file's figures as it finishes.

    A module-level class rather than a closure so it pickles into --workers
    processes.
    """

    windows: list[tuple[float, float]]
    dpi: int
    output_dir: Path

    def __call__(self, measurement, file_result) -> None:
        # Imported here: src.visualizations depends on this package.
        from src.visualizations.plot_individual_fit import plot_file_fit

        for window in self.windows:
            output_path = plot_file_fit(
                file_result,
                folder_name=measurement.folder_name,
                file_name=measurement.file_name,
                xlim=window,
                dpi=self.dpi,
                output_dir=self.output_dir,
            )
            if output_path is not None:
                LOGGER.info("figure -> %s", output_path.name)


def _lower_priority() -> None:
    """Drop this process to below-normal priority on Windows (no-op elsewhere)."""
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    below_normal = 0x4000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # Declared, not left to ctypes' default int: the process handle is
    # pointer-sized and an undeclared call truncates it, so the call fails.
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.SetPriorityClass.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.SetPriorityClass.restype = wintypes.BOOL
    if not kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), below_normal):
        LOGGER.warning("could not lower process priority")


def _figure_dir(folder: str, output_folder: str) -> Path:
    # Imported here: src.visualizations depends on this package.
    from src.visualizations.plot_individual_fit import figure_dir

    return figure_dir(folder) / output_folder


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    import matplotlib

    matplotlib.use("Agg")  # no interactive windows from a batch run

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        variant = build_variant(args)
    except ValueError as exc:  # a bad recipe, reported as a usage error
        parser.error(str(exc))

    if args.measurements is None and args.delta_groups is None:
        files = list(DEFAULT_FILES)
        if args.folder != DEFAULT_FOLDER:
            parser.error(
                f"the default files exist only in {DEFAULT_FOLDER}; pass "
                "--measurements and/or --delta-groups for another folder"
            )
    else:
        try:
            files = subifg_files(
                args.folder,
                measurements=args.measurements,
                file_keys=args.delta_groups,
                limit=args.limit or None,
            )
        except (ValueError, NotADirectoryError) as exc:
            parser.error(str(exc))

    peaks = ir_config.get_peaks()
    print(f"Files -> {len(files)} selected:")
    for stem in files:
        print(f"    {stem}")
    if args.baseline == "recompute":
        print(f"Baseline -> {describe_variant(variant)}")
    else:
        print("Baseline -> saved *_CarbonylFitBaseline.csv (recipe flags ignored)")
    print(f"Peaks -> {len(peaks)} from ir_fitting.fit: {' '.join(map(str, peaks))}")
    print(f"Optimizer -> {FIT_METHOD}")
    print(f"Workers -> {args.workers}")
    if not args.no_save:
        print(f"Writing to -> {peak_fit_dir(args.folder) / args.output_folder}")
    if args.plot:
        print(f"Figures -> {_figure_dir(args.folder, args.output_folder)}")

    if args.dry_run:
        print("\n--dry-run: nothing fitted, nothing written.")
        return

    if not args.normal_priority:
        _lower_priority()

    # Figures are written as each file finishes, not after the batch, so a
    # long run can be watched and a crash keeps every figure drawn so far.
    on_file = None
    if args.plot:
        windows = (
            [tuple(w) for w in args.plot_window]
            if args.plot_window
            else list(DEFAULT_PLOT_WINDOWS)
        )
        figure_dir = _figure_dir(args.folder, args.output_folder)
        on_file = _FigureWriter(windows=windows, dpi=args.dpi, output_dir=figure_dir)

    started = time.time()
    batch = fit_files(
        args.folder,
        files,
        baseline=args.baseline,
        variant=variant,
        output_folder=args.output_folder,
        save=not args.no_save,
        on_file=on_file,
        workers=args.workers,
    )

    if args.plot:
        # Counted on disk: with --workers the figures are written in other
        # processes. The folder is reused, so count only this run's.
        n_figures = sum(
            1 for item in figure_dir.glob("*.png") if item.stat().st_mtime >= started
        )
        print(f"\n{n_figures} figures in {figure_dir}")

    print(f"\n{batch.summary()}")
    not_converged = [
        f"{m.file_name} {f.file_key}"
        for m in batch.measurements
        for f in m.files
        if f.rows and not f.fit_success
    ]
    if not_converged:
        print(f"{len(not_converged)} fit(s) did not converge:")
        for item in not_converged:
            print(f"    {item}")
    if batch.log_path is not None:
        print(f"Log -> {batch.log_path}")


if __name__ == "__main__":
    main()
