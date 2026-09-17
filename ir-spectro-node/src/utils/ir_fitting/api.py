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
    JUDGED_FILES,
    SPLIT_POINT_CM1,  # noqa: F401 -- for the commented-out split variant in __main__
    BaselineVariant,
    band_height,
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
                split_applied=outcome.split_applied,
                split_gated=outcome.split_gated,
                segment_edges=outcome.segment_edges,
                seam_jump=outcome.seam_jump,
                band_heights={
                    center: band_height(wavenumbers, intensity, values, center)
                    for center in REPORTED_BANDS_CM1
                },
            )
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
                    # The seam discontinuity as a percentage of this file's
                    # signal range, so it reads on the same scale as
                    # moved_pct_of_range and the band heights.
                    "seam_pct_of_range": (
                        float("nan")
                        if outcome.split_applied is None
                        else 100 * outcome.seam_jump / variant_range
                    ),
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
        # ------------------------------------------------------------------
        folder_name = "nn1120-4_pd_ceo2_000"
        run_name = "anchored_3"  # change per experiment so runs do not overwrite

        variants = [
            ("current", {}),
            # Anchored: same settings, same full ROI, baseline pinned to the
            # data at ANCHOR_POINTS_CM1 where the guard allows it. This is the
            # recommended form (spec.md 14.7).
            ("anchored", {}, DEFAULT_WINDOW, ANCHOR_POINTS_CM1),
            # Splitting the array at the crossing was tried and is worse than
            # the anchors alone (spec.md 14.8); split_cm1 stays available:
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
            comparison.table.drop(columns=["settings"]).to_string(
                index=False, float_format=lambda v: f"{v:9.4f}"
            )
        )

    else:
        folder_name = "nn1120-3_pd_ceo2_004"
        name = "20260304_145524_pd_ceo2_004-000"

        run = fit_file(subifg_dir(folder_name) / name)
        print(run.summary())
        for output_kind, output_path in run.output_paths.items():
            print(f"  {output_kind}: {output_path}")
