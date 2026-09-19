"""User-facing API for offline IR peak fitting.

No CLI: entry points are importable, and batch work follows the repo convention
of editing the constants in the ``__main__`` block below.

    from src.utils.ir_fitting import fit_file, fit_folder

The unit of ``fit_file`` is one *measurement* -- a base name such as
``20260304_145524_pd_ceo2_004-000`` -- not one subIFG file. It iterates every
delta group and index sharing that base name, matching the granularity of the
params CSV, and writes one merged CSV.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

path = Path(__file__).resolve().parents[3]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.core import config
from src.utils.ir_fitting import config as ir_config
from src.utils.ir_fitting import runner, writer
from src.utils.ir_fitting.baseline import (
    ANCHOR_POINTS_CM1,
    DEFAULT_WINDOW,
    INT_SHARED_WINDOW_CM1,
    INT_WINDOW_CM1,
    JUDGED_FILES,
    LOWER_ANCHOR_POINTS_CM1,  # noqa: F401  (used by the commented-out variants in __main__)
    LOWER_ANCHOR_POINTS_FIVE_CM1,
    LOWER_CONTINUATION_LAM,  # noqa: F401  (used by the commented-out variants in __main__)
    LOWER_CONTINUATION_SETTINGS,  # noqa: F401  (used by the commented-out variants in __main__)
    LOWER_FLOOR_POINT_CM1,  # noqa: F401  (used by the commented-out variants in __main__)
    LOWER_METHOD_CANDIDATE,  # noqa: F401  (used by the commented-out variants in __main__)
    LOWER_MID_PROBE_CM1,
    LOWER_SPLIT_POINT_CM1,
    SPLIT_POINT_CM1,  # noqa: F401 -- for the commented-out split variant in __main__
    BaselineVariant,
    anchor_data_value,
    band_height,
    gating_extremum,
    int_shared,
    lower_target_metrics,
    overlap_shift,
    signal_range,
)
from src.utils.ir_fitting.result_types import (
    BaselineComparison,
    BaselineTrace,
    BatchFitResult,
    FileBaselineComparison,
    MeasurementFitResult,
)
from src.utils.ir_fitting.runner import ExistingPeakRowsError, fit_subifg_file

LOGGER = logging.getLogger(__name__)

REPORTED_BANDS_CM1: tuple[float, ...] = (2040.0, 1980.0)
"""Bands whose height is reported per variant by :func:`compare_baselines`.

These are the two the current baseline cuts in half, so "did this band stop
being halved" is the question a variant is judged on. It is a measurement of
two named bands, not a baseline quality score -- see ``baseline.band_height``
and spec.md section 14.3 finding 4.
"""


def subifg_dir(folder_name: str) -> Path:
    """Return the subIFG source folder for a dataset."""
    return Path(config.get_path("utility.subtract_ifg.sub_ifg_output", folder_name))


def resolve_folder(folder: str | Path) -> Path:
    """Resolve a dataset folder argument to a subIFG directory.

    ``folder`` may be a dataset name (resolved under
    ``utility.subtract_ifg.sub_ifg_output``) or an absolute path.
    """
    folder_path = Path(folder)
    if not folder_path.is_absolute():
        folder_path = subifg_dir(str(folder))
    if not folder_path.is_dir():
        raise NotADirectoryError(folder_path)
    return folder_path


def measurement_names(folder: str | Path) -> list[str]:
    """Return every measurement base name in a subIFG dataset folder.

    A subIFG file is named ``<base name>_delta<N>.<index>``, so stripping the
    trailing ``_delta...`` chunk and deduplicating gives one entry per
    measurement.

    Shared by :func:`fit_folder` and the plotting entry points, so folder
    discovery is defined once.
    """
    folder_path = resolve_folder(folder)
    return sorted(
        {
            "_".join(item.name.split("_")[:-1])
            for item in folder_path.iterdir()
            if item.is_file() and "_delta" in item.name
        }
        - {""}
    )


def _resolve_measurement(measurement: str | Path) -> tuple[str, str, Path]:
    """Resolve a measurement argument to ``(folder_name, file_name, folder)``."""
    measurement_path = Path(measurement)
    if measurement_path.parent.name:
        return (
            measurement_path.parent.name,
            measurement_path.name,
            measurement_path.parent,
        )
    raise ValueError(
        "measurement must include its dataset folder, e.g. "
        r"C:\Data\OpusConvert_subIFG_lgRfl\<dataset>\<base name>"
    )


def fit_file(
    measurement: str | Path,
    *,
    append_only: bool = True,
    baseline: str = "saved",
    on_existing: str = "skip",
    output_folder: str = "_test",
    save: bool = True,
    baseline_settings: dict | None = None,
) -> MeasurementFitResult:
    """Fit the ``ir_fitting`` peaks for one measurement.

    Args:
        measurement: Path to a measurement base name inside a subIFG dataset
            folder, e.g.
            ``C:\\Data\\OpusConvert_subIFG_lgRfl\\nn1120-3_pd_ceo2_004\\20260304_145524_pd_ceo2_004-000``.
            Every ``<base name>_delta*.*`` file under it is processed.
        append_only: ``True`` reuses the saved fit parameters for the existing
            peaks and fits only the ``ir_fitting`` peaks against what those do
            not explain. ``False`` discards them and refits every peak jointly
            from the subIFG -- the only correct way to backfill a peak that
            overlaps the existing cluster.
        baseline: ``"saved"`` reads the stored baseline column; ``"recompute"``
            re-runs ``create_baseline``. With no ``ir_fitting.baseline``
            override the two are identical (see spec.md section 6).
        on_existing: What to do when a peak already has a row for a file --
            ``"skip"`` (default, logged), ``"overwrite"``, or ``"error"``.
        output_folder: Output subfolder name. Never writes into the source folder.
        save: If False, compute only and return the in-memory result.

    An empty ``ir_fitting.extra_peaks_base`` is not an error -- the run loads and
    reconstructs the saved fit and adds no rows. With ``save=True`` that rewrites
    an unchanged params CSV into the output folder, which is harmless; the
    baseline and residual CSVs are still produced. To inspect without writing
    anything, use :func:`load_measurement`.

    Returns:
        MeasurementFitResult with per-file curves, merged rows and output paths.
    """
    if on_existing not in {"skip", "overwrite", "error"}:
        raise ValueError(
            f"on_existing must be 'skip', 'overwrite' or 'error'; got {on_existing!r}"
        )
    if baseline not in {"saved", "recompute"}:
        raise ValueError(f"baseline must be 'saved' or 'recompute'; got {baseline!r}")
    if not append_only and on_existing != "skip":
        LOGGER.warning(
            "on_existing=%r is ignored when append_only=False: a full refit "
            "produces a row for every peak, so every refitted row replaces its "
            "saved counterpart.",
            on_existing,
        )

    folder_name, file_name, source_dir = _resolve_measurement(measurement)
    voigt_settings = ir_config.get_voigt_settings()
    extra_peaks = ir_config.get_extra_peaks(voigt_settings)

    if not extra_peaks and append_only:
        # Not an error: loading and reconstructing the saved fit is useful on its
        # own, and is how the baseline and fit plots work before any peak has
        # been seeded.
        LOGGER.warning(
            "ir_fitting.extra_peaks_base is empty -- no peaks will be fitted. "
            "Seed it in config/analysis.yaml (12CO base wavenumbers, integers) "
            "to add peaks; loading and plotting work without it."
        )

    result, df_existing = _run_measurement(
        folder_name,
        file_name,
        source_dir,
        voigt_settings=voigt_settings,
        extra_peaks=extra_peaks,
        append_only=append_only,
        baseline=baseline,
        on_existing=on_existing,
        baseline_settings=baseline_settings,
    )

    result.merged_params = writer.merge_params(
        df_existing, result.files, on_existing=on_existing, append_only=append_only
    )
    if save:
        result.output_paths = writer.write_measurement(
            result, output_folder=output_folder
        )
    _log_warning_summary(result)
    LOGGER.info("%s", result.summary())
    return result


def _run_measurement(
    folder_name: str,
    file_name: str,
    source_dir: Path,
    *,
    voigt_settings: dict,
    extra_peaks: list[int],
    append_only: bool,
    baseline: str,
    on_existing: str,
    baseline_settings: dict | None = None,
) -> tuple[MeasurementFitResult, pd.DataFrame]:
    """Process every subIFG file of a measurement.

    Shared by ``fit_file`` and ``load_measurement`` -- the two differ only in
    whether ``extra_peaks`` is non-empty and whether the caller writes output.
    Returns the result and the existing params table the caller needs to merge.
    """
    result = MeasurementFitResult(folder_name=folder_name, file_name=file_name)
    df_existing = writer.load_measurement_params(folder_name, file_name)
    df_saved_baseline = writer.load_saved_baseline(folder_name, file_name)

    subifg_files = sorted(source_dir.glob(f"{file_name}_delta*.*"))
    if not subifg_files:
        raise FileNotFoundError(
            f"No subIFG files matching {file_name}_delta*.* in {source_dir}"
        )

    for subifg_path in subifg_files:
        try:
            file_result = fit_subifg_file(
                subifg_path,
                df_existing,
                df_saved_baseline,
                voigt_settings=voigt_settings,
                extra_peaks=extra_peaks,
                append_only=append_only,
                baseline=baseline,
                on_existing=on_existing,
                baseline_settings=baseline_settings,
            )
        except ExistingPeakRowsError:
            raise  # on_existing="error" is meant to stop the run
        except Exception as exc:  # one bad file must not abort the measurement
            message = f"{subifg_path.name}: {exc}"
            LOGGER.error(message)
            result.warnings.append(message)
            continue
        if file_result is None:
            continue
        result.files.append(file_result)
        result.warnings.extend(file_result.warnings)

    return result, df_existing


def load_measurement(
    measurement: str | Path,
    *,
    baseline: str = "saved",
    baseline_settings: dict | None = None,
) -> MeasurementFitResult:
    """Load one measurement without fitting anything.

    Reads every subIFG file of the measurement, resolves its baseline, and
    reconstructs the saved peaks' Voigt curves from
    ``*_CarbonylPeakFitParams.csv`` -- producing the same ``FileFitResult``
    bundle ``fit_file`` returns, minus any newly fitted peak.

    This is the entry point for inspection: it fits nothing, writes nothing, and
    does **not** depend on ``ir_fitting.extra_peaks_base``, so the baseline and
    fit plots work before any peak has been seeded. That ordering matters -- the
    baselines are what should inform which peaks to seed.

    Args:
        measurement: Path to a measurement base name inside a subIFG dataset
            folder, as for :func:`fit_file`.
        baseline: ``"saved"`` reads the stored baseline column; ``"recompute"``
            re-runs ``create_baseline``.

    Returns:
        MeasurementFitResult with per-file raw/baseline/corrected/composite/
        residual arrays and reconstructed curves. ``n_fitted`` is always 0.
    """
    if baseline not in {"saved", "recompute"}:
        raise ValueError(f"baseline must be 'saved' or 'recompute'; got {baseline!r}")

    folder_name, file_name, source_dir = _resolve_measurement(measurement)
    result, _ = _run_measurement(
        folder_name,
        file_name,
        source_dir,
        voigt_settings=ir_config.get_voigt_settings(),
        extra_peaks=[],
        append_only=True,
        baseline=baseline,
        on_existing="skip",
        baseline_settings=baseline_settings,
    )
    LOGGER.info(
        "%s: loaded %d files, fitted nothing", result.file_name, len(result.files)
    )
    return result


def _recipe_key(variant: BaselineVariant) -> tuple:
    """Everything about a variant except which cut, if any, it makes.

    Two variants share a key when they hand ``create_baseline`` the same array
    with the same settings and ask for the same anchors. That is what makes one
    of them the other's "same recipe, no cut" twin.
    """
    return (
        tuple(sorted(variant.settings.items(), key=lambda kv: kv[0])),
        tuple(variant.window),
        tuple(variant.anchors),
    )


def _twin_max_abs_diff(
    trace: BaselineTrace,
    twin: BaselineTrace | None,
    cut: float,
    side: str,
) -> float:
    """Largest ``|trace - twin|`` on one side of ``cut``.

    Two questions, one measurement, and they are asymmetric on purpose:

    - ``"upper"`` is a **check**. The lower-only split of spec.md section 14.9
      keeps the full-ROI anchored baseline at and above the cut, so this is
      **0.0 exactly** or the implementation is wrong -- not "small", not
      "within tolerance". A float tolerance would hide precisely the bug the
      check exists to catch, which is a truncated array reaching
      ``create_baseline`` and moving the upper baseline a little.
    - ``"lower"`` is the **result**. Below the cut is the only region the
      variant touches, so this is how much it did.

    Returns ``nan`` when no twin was run: an unperformed check, which must not
    read as a passed one.
    """
    if twin is None:
        return float("nan")
    if twin.wavenumbers.shape != trace.wavenumbers.shape or not np.array_equal(
        twin.wavenumbers, trace.wavenumbers
    ):
        return float("nan")
    mask = trace.wavenumbers >= cut if side == "upper" else trace.wavenumbers < cut
    if not mask.any():
        return float("nan")
    return float(np.abs(trace.baseline[mask] - twin.baseline[mask]).max())


def compare_baselines(
    variants: Sequence[BaselineVariant | tuple],
    *,
    folder_name: str = "nn1120-4_pd_ceo2_000",
    files: Sequence[str] | None = None,
    run_name: str = "sweep",
    plot: bool = True,
    save: bool = True,
    dpi: int = 300,
) -> BaselineComparison:
    """Compute several baseline variants on the same files and compare them.

    The entry point for baseline experimentation. Fits nothing, touches no
    params CSV, and writes only into the figures tree -- so it is safe to run
    repeatedly while deciding what a good baseline looks like.

    Every variant is measured against the **first** one, so put the baseline
    you are comparing to at the front (normally ``("current", {})``).

    Args:
        variants: :class:`BaselineVariant` objects, or
            ``(label, settings[, window])`` tuples. ``settings`` overrides any
            of ``num_std``, ``half_window``, ``interp_half_window``,
            ``fill_half_window``, ``smooth_half_window``; anything omitted
            keeps its ``config/analysis.yaml`` value. ``window`` is
            ``(high, low)`` cm-1 and defaults to the 2250-1750 ROI.
        folder_name: Dataset the files belong to.
        files: subIFG filenames, e.g.
            ``["20260715_094622_pd_ceo2_000-007_delta10.0042"]``. ``None`` uses
            :data:`~src.utils.ir_fitting.baseline.JUDGED_FILES` -- the eight
            eye-judged files of ``spec.md`` sections 14.2/14.3.
        run_name: Subfolder under the dataset's baseline-experiment directory.
            Use a different name per experiment so runs do not overwrite.
        plot: Render one figure per file.
        save: Write figures and the comparison CSV.
        dpi: Figure resolution.

    Returns:
        :class:`BaselineComparison` -- per-file traces, a tidy table, and the
        paths written. The table reports how far each baseline *moved*; it does
        not score quality, because no reliable score exists here (spec.md
        section 14.3 finding 4). Judge the figures.
    """
    resolved = [BaselineVariant.coerce(item) for item in variants]
    if not resolved:
        raise ValueError("variants must contain at least one entry")

    labels = [variant.label for variant in resolved]
    if len(set(labels)) != len(labels):
        raise ValueError(f"variant labels must be unique; got {labels}")

    selected: list[tuple[str, str]] = (
        list(JUDGED_FILES) if files is None else [(str(name), "") for name in files]
    )
    if not selected:
        raise ValueError("files must contain at least one subIFG filename")

    source_dir = subifg_dir(folder_name)
    comparison = BaselineComparison(folder_name=folder_name, run_name=run_name)
    voigt_settings = ir_config.get_voigt_settings()
    rows: list[dict] = []

    for file_stem, verdict in selected:
        subifg_path = source_dir / file_stem
        if not subifg_path.exists():
            message = f"missing {subifg_path}"
            LOGGER.error(message)
            comparison.warnings.append(message)
            continue

        file_key = runner.file_key_for(subifg_path)
        delta_group, _ = runner.split_file_key(file_key)
        item = FileBaselineComparison(
            file_key=file_key,
            delta_group=delta_group,
            subifg_path=subifg_path,
            verdict=verdict,
        )

        reference: BaselineTrace | None = None
        reference_range = float("nan")
        # Traces for variants that make no cut, keyed by recipe. A lower-only
        # split (spec.md 14.9) claims to leave everything above the cut
        # untouched; its twin here is what that claim is measured against.
        unsplit_twins: dict[tuple, BaselineTrace] = {}
        for variant in resolved:
            try:
                arr = runner.load_subifg_roi(subifg_path, window=variant.window)
            except Exception as exc:  # a bad window must not abort the run
                message = f"{file_stem} / {variant.label}: {exc}"
                LOGGER.error(message)
                comparison.warnings.append(message)
                continue
            wavenumbers, intensity = arr[:, 0], arr[:, 1]
            outcome = variant.compute(intensity, voigt_settings, wavenumbers)
            values, degenerate = outcome.values, outcome.degenerate

            trace = BaselineTrace(
                label=variant.label,
                settings=dict(variant.settings),
                window=tuple(variant.window),
                wavenumbers=wavenumbers,
                raw=intensity,
                baseline=values,
                degenerate=degenerate,
                anchors_applied=outcome.anchors_applied,
                anchors_gated=outcome.anchors_gated,
                lower_anchors_applied=outcome.lower_anchors_applied,
                lower_anchors_gated=outcome.lower_anchors_gated,
                split_applied=outcome.split_applied,
                split_gated=outcome.split_gated,
                split_form=outcome.split_form,
                segment_edges=outcome.segment_edges,
                seam_jump=outcome.seam_jump,
                seam_excess_jump=outcome.seam_excess_jump,
                lower_continuation_lam_applied=outcome.lower_continuation_lam_applied,
                lower_continuation_points=outcome.lower_continuation_points,
                lower_floor_applied=outcome.lower_floor_applied,
                floor_edges=outcome.floor_edges,
                floor_seam_jump=outcome.floor_seam_jump,
                band_heights={
                    center: band_height(wavenumbers, intensity, values, center)
                    for center in REPORTED_BANDS_CM1
                },
            )
            recipe = _recipe_key(variant)
            if variant.split_cm1 is None and variant.lower_split_cm1 is None:
                unsplit_twins.setdefault(recipe, trace)
            elif variant.lower_split_cm1 is not None:
                twin = unsplit_twins.get(recipe)
                cut = variant.lower_split_cm1
                if twin is None:
                    # A nan here is an unperformed check, and a programmatic
                    # caller never sees the __main__ block's summary -- so say
                    # so, for the reason BaselineOutcome gives about a silently
                    # un-anchored baseline looking like an anchored no-op.
                    LOGGER.warning(
                        "variant %r cuts at %.0f but no variant with the same "
                        "settings, window and anchors and no cut was run; "
                        "upper_max_abs_diff and lower_moved_pct are nan. Add the "
                        "unsplit twin (e.g. the 'anchored' variant) to check that "
                        "the region above the cut did not move (spec.md 14.9).",
                        variant.label,
                        cut,
                    )
                trace.upper_max_abs_diff = _twin_max_abs_diff(trace, twin, cut, "upper")
                lower_shift = _twin_max_abs_diff(trace, twin, cut, "lower")
                trace.lower_moved_pct = 100 * lower_shift / signal_range(intensity)

            variant_range = signal_range(intensity)
            if reference is None:
                reference = trace
                reference_range = variant_range
            else:
                shift, region = overlap_shift(
                    reference.wavenumbers,
                    reference.baseline,
                    wavenumbers,
                    values,
                )
                trace.moved_pct_of_range = 100 * shift / reference_range
                trace.compared_over = region

            item.traces.append(trace)
            band_columns: dict[str, float] = {}
            for center in REPORTED_BANDS_CM1:
                height = trace.band_heights.get(center, float("nan"))
                band_columns[f"height_{center:.0f}"] = height
                reference_height = (
                    reference.band_heights.get(center, float("nan"))
                    if reference is not None
                    else float("nan")
                )
                # A ratio is only meaningful when the reference height is
                # positive. Where the band sits *below* the current baseline the
                # reference is negative and "x N" would read as an improvement
                # while meaning nothing; the raw height column carries it instead.
                band_columns[f"height_{center:.0f}_x_ref"] = (
                    height / reference_height
                    if reference_height and reference_height > 0
                    else float("nan")
                )
            rows.append(
                {
                    "file": file_stem,
                    "verdict": verdict,
                    "variant": variant.label,
                    "window": f"{variant.window[0]:.0f}-{variant.window[1]:.0f}",
                    "anchors": "/".join(f"{a:.0f}" for a in outcome.anchors_applied),
                    "anchors_gated": "/".join(
                        f"{a:.0f}" for a, _, _ in outcome.anchors_gated
                    ),
                    # The lower segment's own correction, reported separately
                    # from the full-ROI one: two lines on two arrays (spec.md
                    # 14.10). Blank on every variant that makes no lower cut.
                    "lower_anchors": "/".join(
                        f"{a:.0f}" for a in outcome.lower_anchors_applied
                    ),
                    "lower_anchors_gated": "/".join(
                        f"{a:.0f}" for a, _, _ in outcome.lower_anchors_gated
                    ),
                    # Which algorithm actually ran below the cut (spec.md
                    # 14.12). Blank means std_distribution -- including on a
                    # variant that asked for a method but had its cut gated, so
                    # this says what ran rather than what was requested.
                    "lower_method": outcome.lower_method_applied,
                    # The continuation of spec.md 14.14 and the one parameter
                    # it has. Blank on every other form -- including a variant
                    # that asked for one but had its cut gated, which is why
                    # this reads the outcome and not the variant.
                    "lower_cont_lam": (
                        ""
                        if outcome.lower_continuation_lam_applied is None
                        else f"{outcome.lower_continuation_lam_applied:g}"
                    ),
                    # How many classified samples the continuation was fitted
                    # to (14.14 finding 42). -1 = no continuation; 0 = the
                    # straight extrapolation of the anchored slope.
                    "lower_cont_pts": outcome.lower_continuation_points,
                    # `int` restricted to the samples EVERY variant covers, so
                    # a window-truncated form can be ranked against a full-ROI
                    # one (spec.md 14.16). Scaled by the REFERENCE range, not
                    # this trace's, for the reason int_shared's docstring gives.
                    "int_shared": int_shared(
                        wavenumbers, intensity, values, reference_range
                    ),
                    # Where the lower segment stopped (spec.md 14.13). Blank
                    # means it ran to the ROI floor, which is every variant
                    # through 14.12.
                    "lower_floor": (
                        ""
                        if outcome.lower_floor_applied is None
                        else f"{outcome.lower_floor_applied:.0f}"
                    ),
                    "split": (
                        ""
                        if outcome.split_applied is None
                        else f"{outcome.split_applied:.0f}"
                    ),
                    "split_gated": (
                        ""
                        if outcome.split_gated is None
                        else f"{outcome.split_gated[0]:.0f}"
                    ),
                    "split_form": outcome.split_form,
                    # Must be exactly 0.0 for a lower-only split: above the cut
                    # it is the unsplit anchored baseline by construction
                    # (spec.md 14.9). Blank where there is nothing to check.
                    "upper_max_abs_diff": trace.upper_max_abs_diff,
                    # How far the cut moved the baseline below itself, against
                    # the same anchored twin -- the variant's entire effect,
                    # since height_2040/height_1980 sit above the cut and cannot
                    # move (spec.md 14.9).
                    "lower_moved_pct": trace.lower_moved_pct,
                    # The seam discontinuity as a percentage of this file's
                    # signal range, so it reads on the same scale as
                    # moved_pct_of_range and the band heights.
                    "seam_pct_of_range": (
                        float("nan")
                        if outcome.split_applied is None
                        else 100 * outcome.seam_jump / variant_range
                    ),
                    # The seam with the ordinary grid step taken out, so the
                    # continuation (continuous by construction) and the spliced
                    # forms can be read in the same column. This is the
                    # discontinuity; seam_pct_of_range above is not, quite.
                    "seam_excess_pct_of_range": (
                        float("nan")
                        if outcome.split_applied is None
                        else 100 * outcome.seam_excess_jump / variant_range
                    ),
                    # The floor's own seam, on the same scale. Not summed with
                    # the cut's: below the floor the curve is the anchored
                    # baseline, so this measures how far the two forms disagree
                    # there, which is a different question from the cut's.
                    "floor_seam_pct_of_range": (
                        float("nan")
                        if outcome.lower_floor_applied is None
                        else 100 * outcome.floor_seam_jump / variant_range
                    ),
                    # The user's three stated targets for the region below the
                    # cut (spec.md 14.12). Reported together and never summed:
                    # each one alone ranks a wrong baseline first (finding 33).
                    # `mid` targets 0 on post-crossing files; on pre-crossing
                    # ones the target is `mid_pre_target` in the same column's
                    # units. `und` targets 0 from below, `int` targets 0.
                    **lower_target_metrics(wavenumbers, intensity, values),
                    **band_columns,
                    "moved_pct_of_range": trace.moved_pct_of_range,
                    "compared_over": (
                        ""
                        if trace.compared_over is None
                        else f"{trace.compared_over[0]:.0f}-{trace.compared_over[1]:.0f}"
                    ),
                    "degenerate": degenerate,
                    "settings": str(dict(variant.settings)),
                }
            )

        if item.traces:
            comparison.files.append(item)

    comparison.table = pd.DataFrame(rows)

    if plot and comparison.files:
        # Imported here: src.visualizations depends on this package, so a
        # module-level import would be circular.
        from src.visualizations.plot_baseline import plot_baseline_comparison

        for item in comparison.files:
            figure_path = plot_baseline_comparison(
                item,
                folder_name=folder_name,
                run_name=run_name,
                save=save,
                dpi=dpi,
            )
            if figure_path is not None:
                comparison.figure_paths.append(figure_path)

    if save and not comparison.table.empty:
        output_dir = baseline_experiment_dir(folder_name, run_name)
        comparison.table_path = output_dir / "baseline_comparison.csv"
        comparison.table.to_csv(comparison.table_path, index=False)

    for message in comparison.warnings:
        LOGGER.warning("%s", message)
    LOGGER.info("%s", comparison.summary())
    return comparison


def baseline_experiment_dir(folder_name: str, run_name: str) -> Path:
    """Return (and create) the output directory for a baseline experiment.

    Under the figures tree, not ``data.peak_fit``: this is an experiment log to
    look at, not pipeline data, and nothing downstream reads it. That also
    keeps it clear of ``writer.resolve_output_dir``, whose job is protecting the
    params CSV from being overwritten in place -- a hazard figures do not have.
    """
    if not isinstance(run_name, str) or not run_name.strip():
        raise ValueError(f"run_name must be a non-empty name; got {run_name!r}")
    name = run_name.strip()
    if Path(name).is_absolute() or ".." in Path(name).parts:
        raise ValueError(f"run_name must be a relative subfolder name; got {name!r}")

    output_dir = (
        Path(
            config.get_path(
                "data.figures",
                folder_name,
                config.get_path("data.baseline_experiments"),
            )
        )
        / name
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _log_warning_summary(result: MeasurementFitResult) -> None:
    """Log one aggregated WARNING per distinct issue instead of one per file.

    A measurement holds dozens of subIFG files, so a per-file warning for a
    pinned parameter produces the same line over and over. The individual
    messages stay on ``result.warnings`` for inspection.
    """
    counts: dict[str, int] = {}
    for message in result.warnings:
        counts[message] = counts.get(message, 0) + 1
    n_files = max(len(result.files), 1)
    for message, count in sorted(counts.items(), key=lambda item: -item[1]):
        LOGGER.warning("[%d/%d files] %s", count, n_files, message)


def fit_folder(
    folder: str | Path,
    *,
    append_only: bool = True,
    baseline: str = "saved",
    on_existing: str = "skip",
    output_folder: str = "_test",
    save: bool = True,
    baseline_settings: dict | None = None,
) -> BatchFitResult:
    """Fit every measurement in a subIFG dataset folder.

    ``folder`` may be a dataset name (resolved under
    ``utility.subtract_ifg.sub_ifg_output``) or an absolute path.
    """
    folder_path = resolve_folder(folder)
    batch = BatchFitResult(folder_name=folder_path.name)
    for base_name in measurement_names(folder_path):
        try:
            batch.measurements.append(
                fit_file(
                    folder_path / base_name,
                    append_only=append_only,
                    baseline=baseline,
                    on_existing=on_existing,
                    output_folder=output_folder,
                    save=save,
                    baseline_settings=baseline_settings,
                )
            )
        except Exception as exc:
            LOGGER.error("%s: %s", base_name, exc)
    LOGGER.info("%s", batch.summary())
    return batch


if __name__ == "__main__":
    # Edit the constants under the mode you want, then run:
    #     uv run python src\utils\ir_fitting\api.py
    # See CLAUDE.md on the edit-constants convention used across this repo.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    import matplotlib

    matplotlib.use("Agg")  # no interactive windows from a batch run

    MODE = "baseline"  # "baseline" = compare baselines; "fit" = run the peak fit

    if MODE == "baseline":
        # ------------------------------------------------------------------
        # Baseline experiment. Fits nothing, writes only figures + one CSV.
        #
        # Each variant is ("label", {settings}) or ("label", {settings},
        # (high, low)) to also change the window. The FIRST variant is what
        # every other one is measured against.
        #
        # Settings you can change (anything omitted keeps its
        # config/analysis.yaml value; a misspelled name raises):
        #     num_std, half_window, interp_half_window,
        #     fill_half_window, smooth_half_window
        #
        # Window is (high, low) in cm-1 and changes which slice of the
        # spectrum the algorithm sees -- which changes the baseline
        # everywhere, not just at the edges (spec.md section 14.3 finding 2).
        #
        # A 4th tuple element is the anchor list: wavenumbers the baseline is
        # forced to pass through, applied after create_baseline as an affine
        # correction. ANCHOR_POINTS_CM1 is the calibrated (2006, 1955) pair.
        # An anchor with a dominant band within +/-25 cm-1 is dropped by the
        # guard and reported in the anchors_gated column (spec.md 14.7).
        #
        # A 5th element is the split wavenumber: the ROI is cut there and each
        # side gets its own baseline -- upper with this variant's settings and
        # anchors, lower with the current baseline's settings and none. The
        # same guard gates the cut, independently of the anchors (spec.md 14.8).
        #
        # A 6th element is the LOWER-ONLY split wavenumber, and it excludes the
        # 5th. Same cut point, different operation: create_baseline runs once on
        # the full window, the anchors are fitted to that full-ROI result, and
        # only below the cut is a second baseline substituted. Above the cut the
        # result is bit-for-bit the unsplit anchored baseline, which the
        # upper_max_abs_diff column checks (spec.md 14.9).
        #
        # Past the 5th slot, use the KEYWORD form -- BaselineVariant(label=...,
        # lower_split_cm1=...) -- as the lower-split variants below do. The
        # positional tuple exists to keep ("label", {}) short; at eight slots
        # with two Nones in the middle it no longer does. Both are accepted.
        #
        # lower_anchors are anchors for the second baseline lower_split_cm1
        # creates, and require it. Their own affine correction runs on its own
        # array, so it cannot reach above the cut. The five-anchor experiment
        # below uses (1955, 1790, 1800, 1810, 1820) over the lower segment
        # 1955-1750; it is a least-squares correction, not an exact fit at each
        # point. Reported in lower_anchors / lower_anchors_gated, separately
        # from the full-ROI anchors.
        #
        # lower_settings are std_distribution overrides for the lower segment
        # ONLY -- the place to try different params, since that segment is ~106
        # samples against the ROI's ~259 and the sample-count knobs
        # (half_window and friends) are ~2.4x larger relative to it than where
        # they were tuned. None = the current baseline's own parameters, which
        # is what every measurement in 14.8-14.10 used.
        # ------------------------------------------------------------------
        #
        # lower_method replaces the lower segment's ALGORITHM rather than its
        # parameters -- any pybaselines.Baseline method (spec.md 14.12). It is
        # the knob 14.3 finding 1 and 14.11 could not turn: both swept
        # std_distribution's parameters, never the algorithm. Mutually exclusive
        # with lower_settings, whose keys belong to std_distribution.
        # ------------------------------------------------------------------
        folder_name = "nn1120-4_pd_ceo2_000"
        run_name = "lower_anchors_1955"

        variants = [
            ("current", {}),
            # Anchored: same settings, same full ROI, baseline pinned to the
            # data at ANCHOR_POINTS_CM1 where the guard allows it. This is the
            # recommended form (spec.md 14.7).
            #
            # Keep this second so it remains the ORANGE trace in the figures.
            ("anchored", {}, DEFAULT_WINDOW, ANCHOR_POINTS_CM1),
            # Lower-only split: retain the anchored full-ROI baseline at and
            # above 1955, then recompute only the lower 1955-1750 segment.
            BaselineVariant(
                label="lower split 1955",
                anchors=ANCHOR_POINTS_CM1,
                lower_split_cm1=LOWER_SPLIT_POINT_CM1,
            ),
            # Historical §14.19 form: the lower segment is still 1955-1750,
            # but its own baseline gets five anchors. Change the cut with
            # lower_split_cm1 and change these lower anchors independently.
            BaselineVariant(
                label="lower split 1955 + five lower anchors",
                anchors=(*ANCHOR_POINTS_CM1, 2011,2010,2009,2008,2007,2006,2005,2004,2003,2002,2001,2000),
                lower_split_cm1=LOWER_SPLIT_POINT_CM1,
                lower_anchors=LOWER_ANCHOR_POINTS_FIVE_CM1,
            ),
            # ---- previous lower-split experiments ----
            # Colours: raw is black, then variants take tab10 in list order --
            # `current` is blue and the established three-anchor `anchored`
            # curve is ORANGE. The active comparison above keeps that ordering;
            # the lower-only forms follow it.
            #
            # The two-endpoint lower anchors of 14.10.1, the pspline_arpls of
            # 14.12, the 1800 floor of 14.13 and the continuation of 14.15 are
            # still built and measured in spec.md; they are out of these
            # figures, not out of the package.
            #
            # ---- a different ALGORITHM below the cut (spec.md 14.12) ----
            # No anchors below 1955: the correction is gone and the curve is
            # whatever the algorithm produces. These historical lower-split
            # variants remain commented out because this run is intentionally
            # the lower-split five-anchor comparison.
            # BaselineVariant(
            #     label="lower pspline_arpls",
            #     anchors=ANCHOR_POINTS_CM1,
            #     lower_split_cm1=LOWER_SPLIT_POINT_CM1,
            #     lower_method=LOWER_METHOD_CANDIDATE,
            # ),
            # ---- the same method, tied off at 1800 (spec.md 14.13) ----
            # The lower segment stops above the ROI floor, so the algorithm no
            # longer sees the array edge 14.12's figures faulted on
            # ...-012_delta10.0052. Below 1800 the anchored baseline stands --
            # the second interface that made this the form the user removed.
            # BaselineVariant(
            #     label="lower pspline_arpls floor 1800",
            #     anchors=ANCHOR_POINTS_CM1,
            #     lower_split_cm1=LOWER_SPLIT_POINT_CM1,
            #     lower_method=LOWER_METHOD_CANDIDATE,
            #     lower_floor_cm1=LOWER_FLOOR_POINT_CM1,
            # ),
            # The two other methods that clear all three stated targets once the
            # floor is in (spec.md 14.13 finding 38). mixture_model has the
            # smallest cut seam of the three; cwt_br has the worst.
            # BaselineVariant(
            #     label="lower mixture_model floor 1800",
            #     anchors=ANCHOR_POINTS_CM1,
            #     lower_split_cm1=LOWER_SPLIT_POINT_CM1,
            #     lower_method="mixture_model",
            #     lower_floor_cm1=LOWER_FLOOR_POINT_CM1,
            # ),
            # Other methods measured in 14.12; loess is the seam's best showing,
            # irsqr the case for why a near-zero low-window residual is not on
            # its own a good baseline (it is a strict lower envelope and misses
            # the 1850 midpoint by 8.9% of range).
            # BaselineVariant(
            #     label="lower loess",
            #     anchors=ANCHOR_POINTS_CM1,
            #     lower_split_cm1=LOWER_SPLIT_POINT_CM1,
            #     lower_method="loess",
            # ),
            # BaselineVariant(
            #     label="lower pspline_arpls lam1e2",
            #     anchors=ANCHOR_POINTS_CM1,
            #     lower_split_cm1=LOWER_SPLIT_POINT_CM1,
            #     lower_method="pspline_arpls",
            #     lower_method_kwargs={"lam": 1e2},
            # ),
            # ---- std_distribution settings, swept under the anchor (14.11) ----
            # `settings` on an anchored variant reaches the FULL-ROI/upper
            # baseline, and through it the anchor residuals and the seam.
            # num_std and half_window only move it together; the other three
            # keys are inert (14.11 finding 27). Nothing is recommended: this
            # halves the seam and makes the 2040 recovery slightly worse
            # (finding 29), and the 60-file breadth check ranks hw15 above
            # hw20 where the judged six rank them the other way (finding 30).
            # ("anchored ns2.5 hw20", {"num_std": 2.5, "half_window": 20},
            #  DEFAULT_WINDOW, ANCHOR_POINTS_CM1),
            # ("anchored ns2.5 hw15", {"num_std": 2.5, "half_window": 15},
            #  DEFAULT_WINDOW, ANCHOR_POINTS_CM1),
            # Same settings carried onto the split form -- this is what the
            # seam of 14.11 finding 28 was measured on. Its unsplit twin above
            # is not optional, for the reason `anchored` is not.
            # BaselineVariant(
            #     label="lo anchors ns2.5 hw20",
            #     settings={"num_std": 2.5, "half_window": 20},
            #     anchors=ANCHOR_POINTS_CM1,
            #     lower_split_cm1=LOWER_SPLIT_POINT_CM1,
            #     lower_anchors=LOWER_ANCHOR_POINTS_CM1,
            # ),
            # Different params for the LOWER segment only -- add variants here.
            # Nothing is recommended; these are the knobs, and the reason they
            # might want changing is the segment's length (see above). 14.11
            # finding 26 measured this arm: it cannot move the seam at all, by
            # construction, and below 1955 there is no proxy -- so it is a
            # figures-only comparison.
            # BaselineVariant(
            #     label="lower split 1955 + anchors + half_window 4",
            #     anchors=ANCHOR_POINTS_CM1,
            #     lower_split_cm1=LOWER_SPLIT_POINT_CM1,
            #     lower_anchors=LOWER_ANCHOR_POINTS_CM1,
            #     lower_settings={"half_window": 4},
            # ),
            # Truncating both sides was tried and is worse than the anchors
            # alone (spec.md 14.8); split_cm1 stays available:
            # ("split 1955", {}, DEFAULT_WINDOW, ANCHOR_POINTS_CM1, SPLIT_POINT_CM1),
            # ("num_std 1.4", {"num_std": 1.4}),
            # ("half_window 20", {"half_window": 20}),
            # # Window change: same settings, top edge at 2200 instead of 2250.
            # ("window 2200", {}, (2225.0, 1775.0)),
        ]

        # files=None uses JUDGED_FILES: 8 files -- 6 judged wrong, plus 2
        # judged good (both from measurement ...-022, so the good gate is n=1
        # measurement, not n=2 independent ones).
        # Pass subIFG filenames to look at others, e.g.
        #     files=["20260715_094622_pd_ceo2_000-007_delta10.0082"]
        comparison = compare_baselines(
            variants,
            folder_name=folder_name,
            files=None,
            run_name=run_name,
        )

        print(f"\nOutput -> {baseline_experiment_dir(folder_name, run_name)}")
        print(
            "\n'moved_pct_of_range' = how far that baseline sits from the first\n"
            "variant, as a percentage of the file's signal range, over the\n"
            "wavenumbers the two share. For scale, the 2040 cm-1 peak is about\n"
            "20% of signal range. It says the baseline MOVED, not that moving it\n"
            "was an improvement -- judge the figures.\n"
        )
        print(
            "'height_2040' / 'height_1980' are those bands' heights "
            "above the baseline; '_x_ref' is the ratio to the first variant. "
            "The current baseline cuts these two in half, so a variant that "
            "fixes that shows a ratio near 2. This measures two named bands "
            "-- it is NOT a baseline quality score (spec.md 14.3 finding 4)."
        )
        # Keep the raw height_* columns beside the ratios: where a band sits
        # below the current baseline the ratio is NaN, and the raw height is
        # then the only thing carrying the result.
        print(
            comparison.table.drop(
                columns=["settings", "upper_max_abs_diff", "lower_moved_pct"]
            ).to_string(index=False, float_format=lambda v: f"{v:9.4f}")
        )

        # Printed apart from the table because the table's float format rounds
        # to 4 decimals, which would render 1e-9 as 0.0000 -- and "is it
        # exactly zero" is the whole question here (spec.md 14.9).
        checked = comparison.table[comparison.table["split_form"] == "lower_only"]
        if not checked.empty:
            print(
                "\nupper_max_abs_diff -- max |lower-split - anchored| ABOVE the cut.\n"
                "Must be exactly 0.0: above the cut the lower-only split IS the\n"
                "anchored baseline by construction. Anything else, or nan (no\n"
                "'anchored' twin in this run), means the check did not pass.\n"
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
            worst = checked["upper_max_abs_diff"].max()
            print(f"\n  worst: {worst:.3e} -- " + ("PASS" if worst == 0.0 else "FAIL"))

            # The seam is the metric for spec.md 14.10: 1955 is in BOTH anchor
            # sets, so both sides are pulled toward the same data value there,
            # and 14.9's only cost over 14.7 was a seam of 0% -> up to 5.6% of
            # range. The band-height columns cannot score this -- 2040 and 1980
            # sit above the cut and are guaranteed equal to `anchored`.
            print(
                "\nseam_pct_of_range -- the jump across the cut, as % of signal\n"
                "range. This is the column 14.10 is judged on: anchoring the\n"
                "lower segment at 1955 pulls it toward the same data value the\n"
                "full-ROI correction was pulled toward, so the seam should\n"
                "shrink. Pulled, not pinned -- with five anchors the correction\n"
                "is least-squares and no anchor is hit exactly.\n"
            )
            for label in checked["variant"].unique():
                print(f"  {label}")
                for _, row in checked[checked["variant"] == label].iterrows():
                    print(
                        f"    seam {row['seam_pct_of_range']:8.3f}  "
                        f"lower_moved {row['lower_moved_pct']:7.3f}  "
                        f"lo@{row['lower_anchors'] or '-':<16} "
                        f"gated {row['lower_anchors_gated'] or '-':<12} "
                        f"{row['file']}"
                    )

        # The three targets the user stated for the lower region
        # (spec.md 14.12), rebuilt as real columns in 14.14 because 14.12 and
        # 14.13 each re-derived them in a scratchpad probe that was not kept.
        #
        # They are printed together and never summed: `irsqr` was the best of 44
        # methods on `int` alone while sitting 9% of range below where it
        # belongs (14.12 finding 33). Which `mid` target applies is a REGIME
        # judgement -- 0 on post-crossing files, `pre` on pre-crossing ones --
        # so both are shown and neither is subtracted.
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
            f"  int_sh  the same statistic over "
            f"{INT_SHARED_WINDOW_CM1[0]:.0f}-{INT_SHARED_WINDOW_CM1[1]:.0f}\n"
            "       ONLY -- the samples every variant covers -- and scaled by\n"
            "       the REFERENCE range. This is the column that ranks a\n"
            "       window-truncated form against a full-ROI one; plain `int`\n"
            "       cannot, and spec.md 14.16 got that wrong before measuring.\n"
            "\n"
            "'n' is how many samples plain `int` averaged and 'rng' is that\n"
            "trace's OWN signal range -- both per trace, because a truncated\n"
            "variant has its own array. A variant windowed to 1790 keeps only\n"
            "1838-1790 of the `int` window, so its `int` is a DIFFERENT\n"
            "STATISTIC under the same name: compare plain `int` only where n\n"
            "matches, and read int_sh otherwise (spec.md 14.16 finding 48).\n"
        )
        for item in comparison.files:
            print(f"  {item.subifg_path.name}  [{item.verdict}]")
            reference_range = signal_range(item.traces[0].raw)
            for trace in item.traces:
                metrics = lower_target_metrics(
                    trace.wavenumbers, trace.raw, trace.baseline
                )
                int_n = int(
                    np.count_nonzero(
                        (trace.wavenumbers <= INT_WINDOW_CM1[0])
                        & (trace.wavenumbers >= INT_WINDOW_CM1[1])
                    )
                )
                shared = int_shared(
                    trace.wavenumbers, trace.raw, trace.baseline, reference_range
                )
                print(
                    f"      mid {metrics['mid']:+7.2f} (pre "
                    f"{metrics['mid_pre_target']:+6.2f})  "
                    f"und {metrics['und']:+7.2f}  "
                    f"int {metrics['int']:+7.2f} (n {int_n:>3})  "
                    f"int_sh {shared:+7.2f}  "
                    f"rng {signal_range(trace.raw):.5f}   {trace.label}"
                )

        # The claim 14.14 is built on, and the only column that can check it:
        # a continuation does not MEET the anchored curve at the cut, it STARTS
        # from it, so the discontinuity should be zero rather than small. The
        # raw seam cannot show that -- adjacent samples of a continuous curve
        # still differ by ~slope x the 1.9 cm-1 grid step.
        continuations = comparison.table[
            comparison.table["lower_method"] == "continuation"
        ]
        if not continuations.empty:
            print(
                "\nseam_excess -- the seam with the ordinary grid step taken "
                "out, as % of\nsignal range. For a spliced form it is the seam; "
                "for the continuation it\nis the part that is a genuine "
                "discontinuity, and it should be ~0.\n'pts' is how many "
                "classified samples the continuation was fitted to\n(14.14 "
                "finding 42): 3 on ...-021 is the whole diagnosis, and 0 means "
                "the\ncurve is the straight extrapolation of the anchored "
                "slope and nothing more.\n"
            )
            for label in checked["variant"].unique():
                print(f"  {label}")
                for _, row in checked[checked["variant"] == label].iterrows():
                    pts = int(row["lower_cont_pts"])
                    print(
                        f"    seam {row['seam_pct_of_range']:8.3f}  "
                        f"excess {row['seam_excess_pct_of_range']:8.3f}  "
                        f"pts {'-' if pts < 0 else pts:>4}  "
                        f"{row['file']}"
                    )

        # What the three-anchor comparison gives up: the lower region is only
        # extrapolated from its 1955 residual. The seven-anchor variant adds
        # four lower constraints, including 1800; this probe keeps that
        # comparison visible for every trace.
        #
        # The guard's verdict is printed beside it because it is the standing
        # limit it documents: 1800 sits ~5 cm-1 from the 1795 band and the
        # guard passes it anyway, since ANCHOR_PROMINENCE_FRAC is scaled to the
        # FULL ROI range while the low bands are 2-9% of it. '-' = not gated.
        print(
            f"\nmid-segment probe at {LOWER_MID_PROBE_CM1:.0f} -- "
            "data(1800) - baseline(1800), as % of\nsignal range. It is "
            "extrapolated under the three-anchor set and constrained by the "
            "seven-anchor variant. 'guard' is its prominence if gated.\n"
        )
        for item in comparison.files:
            cells = []
            for trace in item.traces:
                asc = np.argsort(trace.wavenumbers)
                value = anchor_data_value(
                    trace.wavenumbers, trace.raw, LOWER_MID_PROBE_CM1
                )
                fitted = float(
                    np.interp(
                        LOWER_MID_PROBE_CM1,
                        trace.wavenumbers[asc],
                        trace.baseline[asc],
                    )
                )
                miss = 100 * (value - fitted) / signal_range(trace.raw)
                cells.append(f"{trace.label}: {miss:+6.2f}")
            hit = gating_extremum(
                item.traces[0].wavenumbers, item.traces[0].raw, LOWER_MID_PROBE_CM1
            )
            guard = "-" if hit is None else f"{hit[1]:.2f}@{hit[0]:.0f}"
            print(f"  {item.subifg_path.name}   guard {guard}")
            for cell in cells:
                print(f"      {cell}")

        # With exactly two lower anchors, the seam is predictable from the
        # upper residual at 1955. The active five-anchor form does not have that
        # identity: its lower correction is a least-squares pull, so this is
        # reported only as an upper-side reference, not as a pass/fail check.
        print(
            "\nseam reference -- predicted from the anchored residual at 1955;\n"
            "the five-anchor lower correction is not expected to equal it.\n"
            "Both as % of signal range; 'gap' is actual minus reference.\n"
        )
        for item in comparison.files:
            anchored = next((t for t in item.traces if t.label == "anchored"), None)
            lower_anchored = next(
                (
                    t
                    for t in item.traces
                    if t.lower_anchors_applied and t.split_applied is not None
                ),
                None,
            )
            if anchored is None or lower_anchored is None:
                continue
            asc = np.argsort(anchored.wavenumbers)
            residual = anchor_data_value(
                anchored.wavenumbers, anchored.raw, LOWER_SPLIT_POINT_CM1
            ) - float(
                np.interp(
                    LOWER_SPLIT_POINT_CM1,
                    anchored.wavenumbers[asc],
                    anchored.baseline[asc],
                )
            )
            rng = signal_range(anchored.raw)
            predicted = -100 * residual / rng
            actual = 100 * lower_anchored.seam_jump / rng
            print(
                f"  predicted {predicted:+7.3f}  actual {actual:+7.3f}  "
                f"gap {actual - predicted:+7.3f}  {item.subifg_path.name}"
            )

    else:
        folder_name = "nn1120-3_pd_ceo2_004"
        name = "20260304_145524_pd_ceo2_004-000"

        run = fit_file(subifg_dir(folder_name) / name)
        print(run.summary())
        for output_kind, output_path in run.output_paths.items():
            print(f"  {output_kind}: {output_path}")
