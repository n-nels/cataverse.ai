"""User-facing API for offline IR peak fitting.

Entry points are importable. Batch **fitting** follows the repo convention of
editing the constants in the ``__main__`` block below; batch **baseline
experiments** have an argparse CLI, because the recipe is what gets swept::

    uv run python scripts\run_baseline_experiment.py --help

That split mirrors ``src/utils/kinetics``, where the classification algorithm
under active iteration got a CLI and batch fitting did not (see CLAUDE.md).
``compare_baselines`` below is what that CLI calls; nothing about it is
CLI-only.

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
from fnmatch import fnmatchcase
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
    JUDGED_FILES,
    JUDGED_FOLDER,
    BaselineVariant,
    band_height,
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
    matches_file_key,
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


DEFAULT_FIGURE_BUDGET = 60
"""How many subIFG files :func:`subifg_files` will return before refusing.

A dataset folder holds ~12k subIFG files, and one delta group spans every
measurement in it -- ``["delta10"]`` on ``nn1120-4_pd_ceo2_000`` is 385 files,
which at four variants and 300 dpi is a 385-figure run nobody asked for. So the
helper stops and says what it found; raise ``limit`` deliberately, or narrow
``measurements``.
"""


def subifg_files(
    folder: str | Path,
    *,
    measurements: Sequence[str] | None = None,
    file_keys: Sequence[str] | None = None,
    limit: int | None = DEFAULT_FIGURE_BUDGET,
) -> list[str]:
    """Pick subIFG filenames out of a dataset folder by measurement and delta group.

    The bridge between how a dataset is named on disk and what
    :func:`compare_baselines` wants. ``compare_baselines`` takes fully qualified
    stems (``20260715_094622_pd_ceo2_000-007_delta10.0042``) and otherwise falls
    back to :data:`~src.utils.ir_fitting.baseline.JUDGED_FILES`, which are
    hardcoded to ``nn1120-4_pd_ceo2_000`` -- so *any other folder* needed the
    stems typed out by hand. This builds them::

        compare_baselines(
            variants,
            folder_name="nn1120-3_pd_ceo2_004",
            files=subifg_files(
                "nn1120-3_pd_ceo2_004",
                measurements=["20260304_145524_pd_ceo2_004-000"],
                file_keys=["delta10"],
            ),
            run_name="my_run",
        )

    Args:
        folder: Dataset name or absolute subIFG directory, as
            :func:`resolve_folder` takes.
        measurements: Measurement base names, e.g.
            ``["20260715_094622_pd_ceo2_000-007"]``. Each entry is an exact
            name or a glob (``["*-007", "*-01?"]``). ``None`` = every
            measurement in the folder, which is what ``limit`` exists for.
        file_keys: Which files within each measurement, in the same vocabulary
            :meth:`MeasurementFitResult.select` uses -- an exact key
            (``"delta10.0042"``), a whole delta group (``"delta10"``), or a glob
            (``"delta10.00*"``). ``None`` = every file, i.e. all ten delta
            groups.
        limit: Refuse to return more than this many files. ``None`` disables
            the check; see :data:`DEFAULT_FIGURE_BUDGET` for why it is on.

    Returns:
        Sorted subIFG filenames (stems, no directory), ready to hand to
        ``compare_baselines(files=...)``.

    Raises:
        ValueError: When nothing matched, or when more than ``limit`` files did.
    """
    folder_path = resolve_folder(folder)
    measurement_patterns = None if measurements is None else list(measurements)
    key_patterns = None if file_keys is None else list(file_keys)
    for name, value in (("measurements", measurements), ("file_keys", file_keys)):
        if isinstance(value, str):
            raise TypeError(
                f"{name} must be a list of patterns, not a string; "
                f"pass [{value!r}] instead."
            )

    selected: list[str] = []
    seen_measurements: set[str] = set()
    seen_keys: set[str] = set()
    for item in sorted(folder_path.iterdir()):
        if not item.is_file() or "_delta" not in item.name:
            continue
        base_name = "_".join(item.name.split("_")[:-1])
        file_key = runner.file_key_for(item)
        delta_group, _ = runner.split_file_key(file_key)
        seen_measurements.add(base_name)
        seen_keys.add(delta_group)
        if measurement_patterns is not None and not any(
            base_name == pattern or fnmatchcase(base_name, pattern)
            for pattern in measurement_patterns
        ):
            continue
        if key_patterns is not None and not any(
            matches_file_key(file_key, delta_group, pattern) for pattern in key_patterns
        ):
            continue
        selected.append(item.name)

    if not selected:
        raise ValueError(
            f"no subIFG files in {folder_path} matched measurements="
            f"{measurement_patterns} file_keys={key_patterns}. "
            f"Available delta groups: {sorted(seen_keys)}. "
            f"{len(seen_measurements)} measurements, first few: "
            f"{sorted(seen_measurements)[:3]}"
        )
    if limit is not None and len(selected) > limit:
        raise ValueError(
            f"{len(selected)} files matched, over the limit of {limit}. That is "
            f"one figure each, per variant. Narrow `measurements` (this folder "
            f"has {len(seen_measurements)}) or `file_keys`, or pass a larger "
            f"`limit` on purpose."
        )
    LOGGER.info(
        "%s: selected %d subIFG files from %d measurements",
        folder_path.name,
        len(selected),
        len({"_".join(name.split("_")[:-1]) for name in selected}),
    )
    return selected


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
    with the same settings and ask for the same anchors, **under the same guard
    thresholds**. That is what makes one of them the other's "same recipe, no
    cut" twin.

    The guard values are part of the key and not an afterthought: two variants
    with identical ``anchors`` but different thresholds can gate *different*
    anchors, so the affine corrections differ and they are not each other's
    twin. Matching them anyway would measure ``upper_max_abs_diff`` against the
    wrong curve and report a PASS -- precisely the silent failure that check
    exists to catch (see :func:`_twin_max_abs_diff`).
    """
    return (
        tuple(sorted(variant.settings.items(), key=lambda kv: kv[0])),
        tuple(variant.window),
        tuple(variant.anchors),
        float(variant.anchor_guard_cm1),
        float(variant.anchor_prominence_frac),
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
            eye-judged files of ``spec.md`` sections 14.2/14.3, which all belong
            to ``nn1120-4_pd_ceo2_000``. **Pass this whenever `folder_name` is
            not that dataset**, or every file will be reported missing; build
            the list with :func:`subifg_files` rather than by hand.
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

    # An explicitly named file keeps its verdict when it happens to be one of
    # the judged eight, so naming them by hand -- or reaching them through
    # `subifg_files` -- produces the same figure titles as `files=None`.
    # Keyed on the bare stem, so only consult it for the dataset the judged
    # files belong to -- another folder's file must not inherit a `bad` tag.
    verdicts = dict(JUDGED_FILES) if folder_name == JUDGED_FOLDER else {}
    selected: list[tuple[str, str]] = (
        list(JUDGED_FILES)
        if files is None
        else [(str(name), verdicts.get(str(name), "")) for name in files]
    )
    if not selected:
        raise ValueError("files must contain at least one subIFG filename")

    source_dir = subifg_dir(folder_name)
    comparison = BaselineComparison(folder_name=folder_name, run_name=run_name)
    voigt_settings = ir_config.get_voigt_settings()
    rows: list[dict] = []
    # Labels already warned about a missing twin: the gap is a property of
    # the variant list, not of any one file, so say it once per run.
    warned_no_twin: set[str] = set()

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
                segment_edges=outcome.segment_edges,
                seam_jump=outcome.seam_jump,
                band_heights={
                    center: band_height(wavenumbers, intensity, values, center)
                    for center in REPORTED_BANDS_CM1
                },
            )
            recipe = _recipe_key(variant)
            if variant.lower_split_cm1 is None:
                unsplit_twins.setdefault(recipe, trace)
            else:
                twin = unsplit_twins.get(recipe)
                cut = variant.lower_split_cm1
                if twin is None and variant.label not in warned_no_twin:
                    warned_no_twin.add(variant.label)
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
                    # What the guard ran with, beside what it did. Without
                    # these, an empty `anchors_gated` cannot be told apart from
                    # a threshold raised until nothing gates (spec.md 14.7
                    # finding 8 calibrated these two once and never swept them).
                    "anchor_guard_cm1": variant.anchor_guard_cm1,
                    "anchor_prominence_frac": variant.anchor_prominence_frac,
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
    # Edit the constants below, then run:
    #     uv run python src\utils\ir_fitting\api.py
    # See CLAUDE.md on the edit-constants convention used across this repo.
    #
    # BASELINE EXPERIMENTS ARE NO LONGER HERE. They moved to an argparse CLI,
    # because the recipe is what gets swept and re-typing a variant list is how
    # a sweep goes wrong:
    #     uv run python scripts\run_baseline_experiment.py --help
    # With no arguments that reproduces the selected form of spec.md 14.22 on
    # the eight judged files -- what this block used to do. Batch FITTING stays
    # here on the edit-constants convention, mirroring src/utils/kinetics,
    # where classification got a CLI and batch fitting did not.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    import matplotlib

    matplotlib.use("Agg")  # no interactive windows from a batch run

    folder_name = "nn1120-3_pd_ceo2_004"
    name = "20260304_145524_pd_ceo2_004-000"

    run = fit_file(subifg_dir(folder_name) / name)
    print(run.summary())
    for output_kind, output_path in run.output_paths.items():
        print(f"  {output_kind}: {output_path}")
