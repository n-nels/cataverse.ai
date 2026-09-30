"""Command-line entry point for offline baseline runs.

Wraps :func:`~src.utils.ir_fitting.api.run_baseline`: builds one
:class:`BaselineVariant` from the flags, runs it on the selected subIFG files
and writes one figure per file.

Usage:
    python scripts\\run_baseline_experiment.py
    python scripts\\run_baseline_experiment.py --anchors 2240 2006 1955 --run-name probe
    python scripts\\run_baseline_experiment.py --folder nn1120-3_pd_ceo2_004 \\
        --measurements "*-000" --delta-groups delta10 --run-name probe
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

path = Path(__file__).resolve().parents[3]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.utils.ir_fitting.api import (
    DEFAULT_FIGURE_BUDGET,
    baseline_experiment_dir,
    run_baseline,
    subifg_files,
)
from src.utils.ir_fitting.baseline import (
    DEFAULT_FILES,
    DEFAULT_FOLDER,
    DEFAULT_LABEL,
    DEFAULT_WINDOW,
    BaselineVariant,
)

LOGGER = logging.getLogger(__name__)

DEFAULT_RUN_NAME = "default"


def add_recipe_arguments(
    parser: argparse.ArgumentParser,
    *,
    window: bool = True,
) -> None:
    """Add the baseline-recipe and anchor-guard flags.

    Shared with the refit CLI so both take the same recipe flags, with
    defaults from ``BaselineVariant()``. ``window=False`` omits ``--window``:
    the refit's baseline must span the fixed fit ROI.
    """
    default = BaselineVariant()
    recipe = parser.add_argument_group("the recipe")
    recipe.add_argument(
        "--label",
        default=DEFAULT_LABEL,
        help="Name shown in the figure legend (default: %(default)r).",
    )
    if window:
        recipe.add_argument(
            "--window",
            nargs=2,
            type=float,
            metavar=("HIGH", "LOW"),
            default=list(default.window),
            help="Wavenumber extent handed to the algorithm, high then low "
            "(default: %(default)s).",
        )
    recipe.add_argument(
        "--anchors",
        nargs="+",
        type=float,
        metavar="CM1",
        default=list(default.anchors),
        help="Wavenumbers the full-ROI baseline is pulled toward. Order and "
        "duplicates are kept: repeating a wavenumber multiplies its weight in "
        "the least-squares correction (default: %(default)s).",
    )
    recipe.add_argument(
        "--no-anchors",
        action="store_true",
        help="Run unanchored -- the plain create_baseline curve.",
    )
    recipe.add_argument(
        "--lower-split",
        type=float,
        metavar="CM1",
        default=default.lower_split_cm1,
        help="Cut below which a second baseline replaces the first "
        "(default: %(default)s).",
    )
    recipe.add_argument(
        "--no-lower-split",
        action="store_true",
        help="One baseline over the whole window.",
    )
    recipe.add_argument(
        "--lower-anchors",
        nargs="+",
        type=float,
        metavar="CM1",
        default=list(default.lower_anchors),
        help="The lower segment's own anchors. Requires a cut "
        "(default: %(default)s).",
    )
    recipe.add_argument(
        "--no-lower-anchors",
        action="store_true",
        help="Leave the lower segment unanchored.",
    )

    guard = parser.add_argument_group(
        "the anchor guard",
        "Applied to each anchor, each lower anchor and the cut.",
    )
    guard.add_argument(
        "--anchor-guard-cm1",
        type=float,
        default=default.anchor_guard_cm1,
        metavar="CM1",
        help="Half-width of the window an anchor is rejected for containing a "
        "dominant extremum (default: %(default)s).",
    )
    guard.add_argument(
        "--anchor-prominence-frac",
        type=float,
        default=default.anchor_prominence_frac,
        metavar="FRAC",
        help="Prominence, as a fraction of the file's whole ROI signal range, "
        "that makes an extremum dominant. Raising it gates less "
        "(default: %(default)s).",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_baseline_experiment",
        description=(
            "Run one baseline recipe over chosen subIFG files and write one "
            "figure per file. Fits nothing and touches no params CSV."
        ),
    )

    data = parser.add_argument_group(
        "which data to look at",
        f"Both selectors omitted runs the {len(DEFAULT_FILES)} default files, "
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
        help='Measurement base names or globs, e.g. "*-007". Default: all.',
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
        help="Refuse a selection larger than this (default: %(default)s). "
        "0 disables the check.",
    )
    data.add_argument(
        "--run-name",
        default=DEFAULT_RUN_NAME,
        help="Output subfolder under the dataset's baseline_experiments "
        "directory (default: %(default)s). Reused -- a second run overwrites it.",
    )

    add_recipe_arguments(parser)

    output = parser.add_argument_group("output")
    output.add_argument(
        "--no-plot", action="store_true", help="Skip rendering figures."
    )
    output.add_argument(
        "--no-save", action="store_true", help="Compute only; write nothing."
    )
    output.add_argument(
        "--dpi", type=int, default=300, help="Figure resolution (default: %(default)s)."
    )
    output.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the recipe, the selected files and the destination, then "
        "exit without computing.",
    )
    return parser


def build_variant(args: argparse.Namespace) -> BaselineVariant:
    """Turn parsed arguments into the recipe to run."""
    lower_split = None if args.no_lower_split else float(args.lower_split)
    if args.no_lower_split and not args.no_lower_anchors:
        LOGGER.info("--no-lower-split: the lower anchors are dropped.")
    return BaselineVariant(
        label=args.label,
        window=(
            (float(args.window[0]), float(args.window[1]))
            if getattr(args, "window", None)
            else DEFAULT_WINDOW
        ),
        # tuple(), never set(): repeated anchors are weights.
        anchors=() if args.no_anchors else tuple(args.anchors),
        lower_split_cm1=lower_split,
        lower_anchors=(
            ()
            if args.no_lower_anchors or lower_split is None
            else tuple(args.lower_anchors)
        ),
        anchor_guard_cm1=args.anchor_guard_cm1,
        anchor_prominence_frac=args.anchor_prominence_frac,
    )


def _cm1_list(values: tuple[float, ...]) -> str:
    return " ".join(f"{value:.0f}" for value in values) if values else "-"


def describe_variant(variant: BaselineVariant) -> str:
    """The recipe, one setting per line, for the pre-run print."""
    lines = [
        f"window {variant.window[0]:.0f}-{variant.window[1]:.0f}",
        f"anchors {_cm1_list(variant.anchors)}",
    ]
    if variant.lower_split_cm1 is None:
        lines.append("no cut")
    else:
        lines.append(f"cut {variant.lower_split_cm1:.0f}")
        lines.append(f"lower anchors {_cm1_list(variant.lower_anchors)}")
    lines.append(
        f"guard +/-{variant.anchor_guard_cm1:.0f} @ {variant.anchor_prominence_frac:g}"
    )
    return f"{variant.label}\n    " + "\n    ".join(lines)


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
        files = None
        print(f"Files -> the {len(DEFAULT_FILES)} default files in {DEFAULT_FOLDER}")
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
        print(f"Files -> {len(files)} selected:")
        for stem in files:
            print(f"    {stem}")

    print(f"Recipe -> {describe_variant(variant)}")
    # Printed before the run: the directory is reused, so this is the only
    # warning that a run is about to overwrite an earlier one's figures.
    print(f"Writing to -> {baseline_experiment_dir(args.folder, args.run_name)}")

    if args.dry_run:
        print("\n--dry-run: nothing computed, nothing written.")
        return

    run = run_baseline(
        variant,
        folder_name=args.folder,
        files=files,
        run_name=args.run_name,
        plot=not args.no_plot,
        save=not args.no_save,
        dpi=args.dpi,
    )
    print(f"\n{run.summary()}")


if __name__ == "__main__":
    main()
