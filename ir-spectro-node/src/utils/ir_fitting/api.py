"""User-facing API for offline IR peak fitting and baseline runs.

Batch **fitting** follows the repo convention of editing the constants in the
``__main__`` block below. Batch **baseline** runs have an argparse CLI::

    uv run python scripts\run_baseline_experiment.py --help

``run_baseline`` below is what that CLI calls.

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

import pandas as pd

path = Path(__file__).resolve().parents[3]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.core import config
from src.utils.ir_fitting import config as ir_config
from src.utils.ir_fitting import runner, writer
from src.utils.ir_fitting.baseline import (
    DEFAULT_FILES,
    DEFAULT_FOLDER,
    BaselineVariant,
)
from src.utils.ir_fitting.result_types import (
    BaselineRun,
    BatchFitResult,
    FileBaseline,
    MeasurementFitResult,
    matches_file_key,
)
from src.utils.ir_fitting.runner import ExistingPeakRowsError, fit_subifg_file

LOGGER = logging.getLogger(__name__)

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
"""How many subIFG files :func:`subifg_files` returns before refusing.

A dataset folder holds ~12k subIFG files and one delta group spans every
measurement in it, so an unnarrowed selection is hundreds of figures.
"""


def subifg_files(
    folder: str | Path,
    *,
    measurements: Sequence[str] | None = None,
    file_keys: Sequence[str] | None = None,
    limit: int | None = DEFAULT_FIGURE_BUDGET,
) -> list[str]:
    """Pick subIFG filenames out of a dataset folder by measurement and delta group.

    Args:
        folder: Dataset name or absolute subIFG directory, as
            :func:`resolve_folder` takes.
        measurements: Measurement base names, exact or glob (``["*-007"]``).
            ``None`` = every measurement in the folder.
        file_keys: An exact key (``"delta10.0042"``), a whole delta group
            (``"delta10"``), or a glob (``"delta10.00*"``). ``None`` = every file.
        limit: Refuse to return more than this many files. ``None`` disables
            the check.

    Returns:
        Sorted subIFG filenames, ready for ``run_baseline(files=...)``.

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


def run_baseline(
    variant: BaselineVariant,
    *,
    folder_name: str = DEFAULT_FOLDER,
    files: Sequence[str] | None = None,
    run_name: str = "default",
    plot: bool = True,
    save: bool = True,
    dpi: int = 300,
) -> BaselineRun:
    """Compute one baseline recipe on each file and plot it.

    Fits nothing and touches no params CSV; figures are written under the
    dataset's baseline-experiment directory.

    Args:
        variant: The recipe to run.
        folder_name: Dataset the files belong to.
        files: subIFG filenames. ``None`` uses
            :data:`~src.utils.ir_fitting.baseline.DEFAULT_FILES`, which belong
            to ``nn1120-4_pd_ceo2_000`` -- pass this for any other dataset,
            built with :func:`subifg_files`.
        run_name: Output subfolder. Reused -- a second run overwrites it.
        plot: Render one figure per file.
        save: Write figures.
        dpi: Figure resolution.
    """
    selected = list(DEFAULT_FILES) if files is None else [str(name) for name in files]
    if not selected:
        raise ValueError("files must contain at least one subIFG filename")

    source_dir = subifg_dir(folder_name)
    run = BaselineRun(folder_name=folder_name, run_name=run_name, label=variant.label)
    voigt_settings = ir_config.get_voigt_settings()

    for file_stem in selected:
        subifg_path = source_dir / file_stem
        if not subifg_path.exists():
            run.warnings.append(f"missing {subifg_path}")
            continue
        try:
            arr = runner.load_subifg_roi(subifg_path, window=variant.window)
        except Exception as exc:  # one bad file must not abort the run
            run.warnings.append(f"{file_stem}: {exc}")
            continue
        wavenumbers, intensity = arr[:, 0], arr[:, 1]
        outcome = variant.compute(intensity, voigt_settings, wavenumbers)

        file_key = runner.file_key_for(subifg_path)
        delta_group, _ = runner.split_file_key(file_key)
        run.files.append(
            FileBaseline(
                file_key=file_key,
                delta_group=delta_group,
                subifg_path=subifg_path,
                wavenumbers=wavenumbers,
                raw=intensity,
                baseline=outcome.values,
                degenerate=outcome.degenerate,
                anchors_applied=outcome.anchors_applied,
                lower_anchors_applied=outcome.lower_anchors_applied,
                split_applied=outcome.split_applied,
            )
        )

    if plot and run.files:
        # Imported here: src.visualizations depends on this package, so a
        # module-level import would be circular.
        from src.visualizations.plot_baseline import plot_baseline_run_file

        for item in run.files:
            figure_path = plot_baseline_run_file(
                item,
                label=variant.label,
                folder_name=folder_name,
                run_name=run_name,
                save=save,
                dpi=dpi,
            )
            if figure_path is not None:
                run.figure_paths.append(figure_path)

    for message in run.warnings:
        LOGGER.warning("%s", message)
    LOGGER.info("%s", run.summary())
    return run


def baseline_experiment_dir(folder_name: str, run_name: str) -> Path:
    """Return (and create) the output directory for a baseline run.

    Under the figures tree, not ``data.peak_fit``: nothing downstream reads it.
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
    # Baseline runs have their own CLI:
    #     uv run python scripts\run_baseline_experiment.py --help
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    import matplotlib

    matplotlib.use("Agg")  # no interactive windows from a batch run

    folder_name = "nn1120-3_pd_ceo2_004"
    name = "20260304_145524_pd_ceo2_004-000"

    run = fit_file(subifg_dir(folder_name) / name)
    print(run.summary())
    for output_kind, output_path in run.output_paths.items():
        print(f"  {output_kind}: {output_path}")
