"""Command-line entry point for the offline baseline experiment.

Wraps :func:`~src.utils.ir_fitting.api.compare_baselines` behind one argparse
CLI, exposing the inputs that ``spec.md`` section 14 actually *introduced* --
the window, the two anchor sets, the lower-only cut, and the two anchor-guard
thresholds -- so a recipe can be swept without editing source.

Added on the condition ``spec.md`` section 12 named: *"A CLI. Added only if the
workflow needs A/B flags, as ``src/utils/kinetics`` did."* It now does, and
``src/utils/kinetics/classify_cli.py`` is the shape this follows.

**What is deliberately not a flag**, and why (the inventory is in spec.md
section 16):

- ``settings`` -- the ``std_distribution`` parameters. Swept twice and nothing
  recommended (section 14.3 finding 1, section 14.11), so the selected form
  leaves them at their ``config/analysis.yaml`` values. Still reachable
  programmatically through ``BaselineVariant(settings=...)``.
- The baseline *algorithm*. ``create_baseline`` is what the live path runs;
  replacing it below the cut was built, measured and rejected (section 14.12,
  section 14.14 decision 1).
- ``anchor_data_value``'s +/-10 cm-1 local fit width. It decides *where* an
  anchor lands, not *whether* it survives, and section 14 never touched it.
- The reporting windows (``MID_*``, ``UND_*``, ``INT_*``,
  ``REPORTED_BANDS_CM1``). They are measurement, not construction; changing one
  changes what a number means rather than what the baseline is.

Batch *fitting* stays on the edit-constants convention in ``api.py``'s own
``__main__`` block, mirroring kinetics -- where classification got a CLI and
batch fitting did not (see CLAUDE.md).

Usage:
    python scripts\\run_baseline_experiment.py
    python scripts\\run_baseline_experiment.py --with-twin
    python scripts\\run_baseline_experiment.py --anchor-prominence-frac 0.9
    python scripts\\run_baseline_experiment.py --folder nn1120-3_pd_ceo2_004 \\
        --measurements "*-000" --delta-groups delta10 --run-name probe
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

path = Path(__file__).resolve().parents[3]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.utils.ir_fitting.api import (
    DEFAULT_FIGURE_BUDGET,
    baseline_experiment_dir,
    compare_baselines,
    subifg_files,
)
from src.utils.ir_fitting.baseline import (
    ANCHOR_GUARD_CM1,
    ANCHOR_POINTS_CM1,
    ANCHOR_PROMINENCE_FRAC,
    DEFAULT_WINDOW,
    DENSE_UPPER_ANCHOR_POINTS_CM1,
    INT_WINDOW_CM1,
    JUDGED_FILES,
    LOWER_ANCHOR_POINTS_CM1,
    LOWER_SPLIT_POINT_CM1,
    BaselineVariant,
)
from src.utils.ir_fitting.result_types import BaselineComparison

LOGGER = logging.getLogger(__name__)

DEFAULT_RUN_NAME = "lower_anchors_1955"
"""The run name the locked section 14.21/14.22 experiment owns."""

DEFAULT_LABEL = "lower split 1955 + five lower anchors"
"""Label of the selected form, so a no-argument run reproduces section 14.22."""


EPILOG = """\
With no arguments this runs the selected form of spec.md section 14.22 -- the
lower-only cut at 1955 with anchors on both segments -- alone, on the eight
judged files of section 14.2, exactly as api.py's __main__ block used to.

Two things worth knowing before sweeping:

  * `settings` (num_std and friends) is NOT exposed here, and would only reach
    the UPPER curve if it were: _compute_lower_split hands the lower segment
    the unmodified voigt_fit.baseline settings on purpose, and lower_settings
    was removed in section 15.2. Nothing on this CLI changes the algorithm's
    own parameters.

  * The output directory is REUSED. A second run under an unchanged --run-name
    overwrites the first run's figures and CSV. Change --run-name per
    experiment, or pass --dry-run first to see where it would land.
"""


def print_summary(comparison: BaselineComparison, n_variants: int) -> None:
    """Print a compact per-file summary; the full table is the CSV.

    One row per file x variant, then the ``upper_max_abs_diff`` verdict and the
    gated files. The ``_x_ref`` ratios and ``moved`` are shown only with two or
    more variants -- with one, the variant is its own reference and they are
    1 and 0 by construction. ``n`` is kept beside ``int`` because a variant
    with its own window averages a different sample set (spec.md 14.16
    finding 48).
    """
    table = comparison.table
    if table.empty:
        print("\nNo rows.")
        return

    # Rows are appended file-major, variant-minor, in the same order as the
    # traces, so the two line up one-to-one.
    int_n = [
        int(
            np.count_nonzero(
                (trace.wavenumbers <= INT_WINDOW_CM1[0])
                & (trace.wavenumbers >= INT_WINDOW_CM1[1])
            )
        )
        for item in comparison.files
        for trace in item.traces
    ]
    gated = [
        "/".join(
            f"{kind} {value}"
            for kind, value in (
                ("anchor", row["anchors_gated"]),
                ("cut", row["split_gated"]),
            )
            if value
        )
        or "-"
        for _, row in table.iterrows()
    ]
    compact = pd.DataFrame(
        {
            "file": table["file"],
            "variant": table["variant"],
            "gated": gated,
            "seam": table["seam_pct_of_range"],
            "mid": table["mid"],
            "pre": table["mid_pre_target"],
            "und": table["und"],
            "int": table["int"],
            "n": int_n,
            "h2040": table["height_2040"],
            "h1980": table["height_1980"],
        }
    )
    if n_variants > 1:
        compact["h2040_x_ref"] = table["height_2040_x_ref"]
        compact["h1980_x_ref"] = table["height_1980_x_ref"]
        compact["moved"] = table["moved_pct_of_range"]
    print()
    print(compact.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    # Every row that ASKED for a cut, whether or not the guard allowed it.
    # Exact zero is the test, so the worst value is printed in .3e -- the
    # table's rounding would render 1e-9 as 0.0000 (spec.md 14.9). nan is an
    # unperformed check, not a failed one.
    checked = table[(table["split"] != "") | (table["split_gated"] != "")]
    if not checked.empty:
        worst = checked["upper_max_abs_diff"].max()
        if np.isnan(worst):
            print("\nupper check: NOT CHECKED -- add --with-twin")
        else:
            verdict = "PASS" if worst == 0.0 else "FAIL"
            print(f"\nupper check: {verdict} (worst {worst:.3e})")

    gated_files = compact.loc[compact["gated"] != "-", "file"].unique()
    if len(gated_files):
        print("gated: " + ", ".join(gated_files))

    if comparison.table_path is not None:
        print(f"CSV -> {comparison.table_path}")
    else:
        print("CSV -> not saved")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_baseline_experiment",
        description=(
            "Run one baseline recipe over chosen subIFG files and write figures "
            "plus baseline_comparison.csv. Fits nothing, touches no params CSV, "
            "writes only into the figures tree."
        ),
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    data = parser.add_argument_group(
        "which data to look at",
        "Both selectors omitted falls back to the eight judged files of "
        "spec.md 14.2, which exist ONLY in nn1120-4_pd_ceo2_000.",
    )
    data.add_argument(
        "--folder",
        default="nn1120-4_pd_ceo2_000",
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
        help="Refuse a selection larger than this -- one figure each, per "
        "variant (default: %(default)s). 0 disables the check.",
    )
    data.add_argument(
        "--run-name",
        default=DEFAULT_RUN_NAME,
        help="Output subfolder under the dataset's baseline_experiments "
        "directory (default: %(default)s). REUSED -- change it per experiment.",
    )

    recipe = parser.add_argument_group(
        "the recipe",
        "Defaults are the selected form of spec.md 14.22; omitting all of "
        "these reproduces it exactly.",
    )
    recipe.add_argument(
        "--label",
        default=DEFAULT_LABEL,
        help="Name shown in the legend and the CSV (default: %(default)r).",
    )
    recipe.add_argument(
        "--window",
        nargs=2,
        type=float,
        metavar=("HIGH", "LOW"),
        default=list(DEFAULT_WINDOW),
        help="Wavenumber extent handed to the algorithm, high then low "
        "(default: %(default)s). This changes the baseline EVERYWHERE, not "
        "just at the edges (14.3 finding 2); every truncation tried was "
        "rejected.",
    )
    recipe.add_argument(
        "--anchors",
        nargs="+",
        type=float,
        metavar="CM1",
        default=list(DENSE_UPPER_ANCHOR_POINTS_CM1),
        help="Wavenumbers the full-ROI baseline is pulled through, as an "
        "affine correction after create_baseline (14.7). ORDER AND DUPLICATES "
        "ARE KEPT: the default set contains 2006 twice on purpose, giving that "
        "wavenumber double weight in the least-squares line (14.21, 15.1). "
        "Default: the 15-point dense upper set.",
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
        default=LOWER_SPLIT_POINT_CM1,
        help="Cut below which a second baseline replaces the first; at and "
        "above it the anchored full-ROI curve stands bit-for-bit (14.9). "
        "Default: %(default)s.",
    )
    recipe.add_argument(
        "--no-lower-split",
        action="store_true",
        help="One baseline over the whole window -- the 14.7 anchored form.",
    )
    recipe.add_argument(
        "--lower-anchors",
        nargs="+",
        type=float,
        metavar="CM1",
        default=list(LOWER_ANCHOR_POINTS_CM1),
        help="The lower segment's own affine correction, on its own array "
        "(14.10, 14.19). Requires a cut. Default: the five-point set.",
    )
    recipe.add_argument(
        "--no-lower-anchors",
        action="store_true",
        help="Leave the lower segment unanchored, as 14.9 measured it.",
    )

    guard = parser.add_argument_group(
        "the anchor guard",
        "One test, three gate sites -- each full-ROI anchor, each lower "
        "anchor, and the cut -- so these two configure all of them together "
        "(14.22). Introduced in 14.7 and calibrated once; never swept.",
    )
    guard.add_argument(
        "--anchor-guard-cm1",
        type=float,
        default=ANCHOR_GUARD_CM1,
        metavar="CM1",
        help="Half-width of the window an anchor is rejected for containing a "
        "dominant extremum (default: %(default)s).",
    )
    guard.add_argument(
        "--anchor-prominence-frac",
        type=float,
        default=ANCHOR_PROMINENCE_FRAC,
        metavar="FRAC",
        help="Prominence, as a fraction of the file's WHOLE ROI signal range, "
        "that makes an extremum dominant (default: %(default)s). Raising it "
        "gates less. At 1955 the guard file scores 0.75-0.82 and every file "
        "the anchor helps scores <= 0.24 (14.7 finding 8). It does NOT protect "
        "an anchor below ~1900 at any value (14.10 finding 16).",
    )

    compare = parser.add_argument_group(
        "comparison traces",
        "Every variant is measured against the FIRST in the list.",
    )
    compare.add_argument(
        "--with-twin",
        action="store_true",
        help="Add an uncut variant carrying THIS run's own window, anchors and "
        "guards, placed immediately before the candidate. That is what "
        "upper_max_abs_diff needs to be a real check: without it the summary "
        "prints NOT CHECKED, because `anchored` uses the three-point set and "
        "is not a twin of the dense one (14.22).",
    )
    compare.add_argument(
        "--compare",
        action="store_true",
        help="Prepend the 14.21 comparison traces -- `current`, `anchored` "
        "(three-point set) and the unanchored cut -- in the order that "
        "restores their established colours. This does NOT by itself check the "
        "candidate's upper_max_abs_diff; --with-twin does.",
    )

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
        help="Print the resolved variants, the selected files and the "
        "destination, then exit without computing.",
    )
    return parser


def build_variants(args: argparse.Namespace) -> list[BaselineVariant]:
    """Turn parsed arguments into the variant list, candidate last.

    Ordering is not cosmetic. ``compare_baselines`` fills its twin table as it
    iterates, so an unsplit twin only counts when it comes **before** the
    variant it is a twin of; and the first entry is the reference every
    ``moved_pct_of_range`` is measured against. So the twin goes immediately
    before the candidate -- which puts it first when it is the only other
    trace, and leaves ``current`` as the reference under ``--compare``, where
    the established colours of 14.21 depend on that order.
    """
    window = (float(args.window[0]), float(args.window[1]))
    # list(), never set(): the dense upper set carries 2006 twice on purpose
    # and deduplicating it would change the least-squares correction (14.21).
    anchors = () if args.no_anchors else tuple(args.anchors)
    lower_split = None if args.no_lower_split else float(args.lower_split)
    lower_anchors = (
        ()
        if args.no_lower_anchors or lower_split is None
        else tuple(args.lower_anchors)
    )
    guards = {
        "anchor_guard_cm1": args.anchor_guard_cm1,
        "anchor_prominence_frac": args.anchor_prominence_frac,
    }

    if args.no_lower_split and not args.no_lower_anchors:
        # BaselineVariant would raise on lower_anchors without a cut. The
        # default list is not something the caller typed, so dropping it is
        # right -- but silence is how a knob comes to look like it did nothing.
        LOGGER.info(
            "--no-lower-split: the default lower anchors are dropped, there "
            "being no lower segment to correct."
        )

    variants: list[BaselineVariant] = []
    if args.compare:
        variants.append(BaselineVariant(label="current", window=window, **guards))
        variants.append(
            BaselineVariant(
                label="anchored",
                window=window,
                anchors=ANCHOR_POINTS_CM1,
                **guards,
            )
        )
        if lower_split is not None:
            # A twin of `anchored`, so this one's upper_max_abs_diff is a real
            # check even when --with-twin is absent.
            variants.append(
                BaselineVariant(
                    label=f"lower split {lower_split:.0f}",
                    window=window,
                    anchors=ANCHOR_POINTS_CM1,
                    lower_split_cm1=lower_split,
                    **guards,
                )
            )

    if args.with_twin:
        if lower_split is None:
            LOGGER.warning(
                "--with-twin has nothing to check: this variant makes no cut, "
                "so it IS its own unsplit form. Ignoring it."
            )
        else:
            variants.append(
                BaselineVariant(
                    label=f"{args.label} [uncut twin]",
                    window=window,
                    anchors=anchors,
                    **guards,
                )
            )

    variants.append(
        BaselineVariant(
            label=args.label,
            window=window,
            anchors=anchors,
            lower_split_cm1=lower_split,
            lower_anchors=lower_anchors,
            **guards,
        )
    )
    return variants


def describe_variant(variant: BaselineVariant) -> str:
    """One line per variant for the pre-run print."""
    parts = [f"window {variant.window[0]:.0f}-{variant.window[1]:.0f}"]
    parts.append(
        "anchors "
        + (
            "-"
            if not variant.anchors
            else "/".join(f"{a:.0f}" for a in variant.anchors)
        )
    )
    if variant.lower_split_cm1 is None:
        parts.append("no cut")
    else:
        parts.append(f"cut {variant.lower_split_cm1:.0f}")
        parts.append(
            "lower anchors "
            + (
                "-"
                if not variant.lower_anchors
                else "/".join(f"{a:.0f}" for a in variant.lower_anchors)
            )
        )
    parts.append(
        f"guard +/-{variant.anchor_guard_cm1:.0f} @ {variant.anchor_prominence_frac:g}"
    )
    return f"{variant.label}\n        " + "\n        ".join(parts)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    import matplotlib

    matplotlib.use("Agg")  # no interactive windows from a batch run

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        variants = build_variants(args)
    except ValueError as exc:  # a bad recipe, reported as a usage error
        parser.error(str(exc))

    # MEASUREMENTS/DELTA_GROUPS -> explicit subIFG stems; both None ->
    # files=None -> JUDGED_FILES: 8 files from nn1120-4_pd_ceo2_000 -- 6 judged
    # wrong plus the 2 guard files of ...-022, which are the cases the anchor
    # rule must detect and skip, not baselines certified correct.
    if args.measurements is None and args.delta_groups is None:
        files = None
        print(f"Files -> the {len(JUDGED_FILES)} judged files (spec.md 14.2)")
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

    print(f"Variants -> {len(variants)}, measured against the first:")
    for index, variant in enumerate(variants):
        print(f"    [{index}] {describe_variant(variant)}")

    # Printed before the run, not after: this directory is reused, so seeing
    # the destination is the only warning that a run is about to land on top of
    # an earlier one's figures.
    print(f"Writing to -> {baseline_experiment_dir(args.folder, args.run_name)}")

    if args.dry_run:
        print("\n--dry-run: nothing computed, nothing written.")
        return

    comparison = compare_baselines(
        variants,
        folder_name=args.folder,
        files=files,
        run_name=args.run_name,
        plot=not args.no_plot,
        save=not args.no_save,
        dpi=args.dpi,
    )

    print_summary(comparison, len(variants))


if __name__ == "__main__":
    main()
