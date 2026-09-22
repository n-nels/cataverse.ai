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
    lower_target_metrics,
    signal_range,
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


def _print_targets_help() -> None:
    """The three stated lower-region targets, and why they are never summed."""
    print(
        "\nthe three stated lower-region targets, all as % of signal range:\n"
        "  mid  baseline(1850) - midpoint of the 1866-1838 trough/peak\n"
        "       target 0 on POST-crossing files; on PRE-crossing ones the\n"
        "       target is the 'pre' column beside it (the baseline sitting\n"
        "       on the flanking trough = 'under the base of those peaks')\n"
        "  und  max(baseline - data) over 1885-1840; target 0 FROM BELOW,\n"
        "       positive means the baseline cuts into the 1850/1870-1880 bands\n"
        "  int  mean(data - baseline) over 1838-1750; target 0\n"
        "Read all three. Each one alone ranks a wrong baseline first.\n"
        "\n"
        "'n' is how many samples `int` averaged and 'rng' is that trace's\n"
        "OWN signal range -- both per trace, because a variant with its own\n"
        "window has its own array and `int` would then be a DIFFERENT\n"
        "STATISTIC under the same name. Compare `int` only where n matches\n"
        "(spec.md 14.16 finding 48).\n"
    )


def print_summary(comparison: BaselineComparison, n_variants: int) -> None:
    """Print what a comparison run produced.

    Lifted unchanged from ``api.py``'s ``__main__`` block when the CLI replaced
    it, so the three-target block, the ``upper_max_abs_diff``
    PASS / FAIL / **NOT CHECKED** verdict and the one-variant warning are the
    same text section 14.22 was read from.
    """
    print(
        "\n'moved_pct_of_range' = how far that baseline sits from the first\n"
        "variant, as a percentage of the file's signal range, over the\n"
        "wavenumbers the two share. For scale, the 2040 cm-1 peak is about\n"
        "20% of signal range. It says the baseline MOVED, not that moving it\n"
        "was an improvement -- judge the figures.\n"
    )
    if n_variants == 1:
        # With one variant it IS the reference, so every column measured
        # against the reference compares it to itself: moved_pct_of_range is 0
        # and the _x_ref ratios are 1 by construction. Neither is a result, and
        # 1.0000 in a column whose whole point is "near 2 means the band
        # stopped being halved" reads like a failure otherwise.
        print(
            "\nONE VARIANT: it is its own reference, so moved_pct_of_range "
            "is 0.0000\nand every '_x_ref' ratio is 1.0000 by construction. "
            "Read the raw\nheight_* columns, the lower-region targets and "
            "the figure; add a second\nvariant to get the comparison "
            "columns back (--with-twin, --compare).\n"
        )
    print(
        "'height_2040' / 'height_1980' are those bands' heights "
        "above the baseline; '_x_ref' is the ratio to the first variant. "
        "The current baseline cuts these two in half, so a variant that "
        "fixes that shows a ratio near 2. This measures two named bands "
        "-- it is NOT a baseline quality score (spec.md 14.3 finding 4)."
    )
    # Keep the raw height_* columns beside the ratios: where a band sits below
    # the current baseline the ratio is NaN, and the raw height is then the
    # only thing carrying the result.
    print(
        comparison.table.drop(
            columns=["settings", "upper_max_abs_diff", "lower_moved_pct"]
        ).to_string(index=False, float_format=lambda v: f"{v:9.4f}")
    )

    # Every row that ASKED for a cut, whether or not the guard allowed it -- a
    # gated file still belongs in these blocks, reported with an empty `split`
    # and its wavenumber in `split_gated`.
    checked = comparison.table[
        (comparison.table["split"] != "") | (comparison.table["split_gated"] != "")
    ]
    if not checked.empty:
        # Printed apart from the table because the table's float format rounds
        # to 4 decimals, which would render 1e-9 as 0.0000 -- and "is it
        # exactly zero" is the whole question here (spec.md 14.9).
        print(
            "\nupper_max_abs_diff -- max |lower-split - anchored| ABOVE the cut.\n"
            "Must be exactly 0.0: above the cut the lower-only split IS the\n"
            "anchored baseline by construction. Anything else, or nan (no\n"
            "unsplit twin in this run), means the check did not pass.\n"
        )
        for _, row in checked.iterrows():
            print(f"  {row['upper_max_abs_diff']:.3e}  {row['file']}")
        print(
            "\nlower_moved_pct -- max |lower-split - anchored| BELOW the cut, "
            "as %\nof signal range. This is what the cut actually did; the "
            "band-height\ncolumns cannot show it, because 2040 and 1980 are "
            "both above the cut.\n"
        )
        for _, row in checked.iterrows():
            print(f"  {row['lower_moved_pct']:8.3f}  {row['file']}")
        # nan is an UNPERFORMED check, not a failed one: it means no variant
        # with this one's settings, window, anchors and guards ran without a
        # cut, so there was nothing to compare against. Showing the selected
        # form alone is exactly that case, and calling it FAIL would be a lie.
        worst = checked["upper_max_abs_diff"].max()
        if np.isnan(worst):
            print(
                "\n  NOT CHECKED -- no unsplit twin in this run. Add the "
                "matching\n  no-cut variant (same settings, window, anchors "
                "and guards): --with-twin\n  builds exactly that one."
            )
        else:
            print(f"\n  worst: {worst:.3e} -- " + ("PASS" if worst == 0.0 else "FAIL"))

        # 1955 is in BOTH anchor sets, so both sides are pulled toward the same
        # data value there and the seam should be small. Pulled, not pinned:
        # with five lower anchors the correction is least-squares and no anchor
        # is hit exactly, so the two-anchor identity that predicted the seam
        # from the upper residual no longer holds (spec.md 14.19). The
        # band-height columns cannot score this -- 2040 and 1980 sit above the
        # cut and are guaranteed equal to `anchored`.
        print(
            "\nseam_pct_of_range -- the jump across the cut, as % of signal\n"
            "range. nan where the guard refused the cut: there is then no\n"
            "seam, because there is no second segment.\n"
        )
        for label in checked["variant"].unique():
            print(f"  {label}")
            for _, row in checked[checked["variant"] == label].iterrows():
                print(
                    f"    seam {row['seam_pct_of_range']:8.3f}  "
                    f"lower_moved {row['lower_moved_pct']:7.3f}  "
                    f"lo@{row['lower_anchors'] or '-':<26} "
                    f"gated {row['lower_anchors_gated'] or '-':<12} "
                    f"{row['file']}"
                )

    # The three targets the user stated for the lower region (spec.md 14.12),
    # rebuilt as real columns in 14.14 because 14.12 and 14.13 each re-derived
    # them in a scratchpad probe that was not kept.
    #
    # They are printed together and never summed: `irsqr` was the best of 44
    # methods on `int` alone while sitting 9% of range below where it belongs
    # (14.12 finding 33). Which `mid` target applies is a REGIME judgement -- 0
    # on post-crossing files, `pre` on pre-crossing ones -- so both are shown
    # and neither is subtracted.
    _print_targets_help()
    for item in comparison.files:
        print(f"  {item.subifg_path.name}  [{item.verdict}]")
        for trace in item.traces:
            metrics = lower_target_metrics(trace.wavenumbers, trace.raw, trace.baseline)
            int_n = int(
                np.count_nonzero(
                    (trace.wavenumbers <= INT_WINDOW_CM1[0])
                    & (trace.wavenumbers >= INT_WINDOW_CM1[1])
                )
            )
            print(
                f"      mid {metrics['mid']:+7.2f} (pre "
                f"{metrics['mid_pre_target']:+6.2f})  "
                f"und {metrics['und']:+7.2f}  "
                f"int {metrics['int']:+7.2f} (n {int_n:>3})  "
                f"rng {signal_range(trace.raw):.5f}   {trace.label}"
            )


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

    print(f"\nOutput -> {baseline_experiment_dir(args.folder, args.run_name)}")
    print_summary(comparison, len(variants))


if __name__ == "__main__":
    main()
