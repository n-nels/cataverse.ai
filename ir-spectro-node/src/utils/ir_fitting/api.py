"""User-facing API for offline IR peak refits and baseline runs.

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
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from fnmatch import fnmatchcase
from pathlib import Path

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
    FileFitResult,
    MeasurementFitResult,
    matches_file_key,
)
from src.utils.ir_fitting.runner import fit_subifg_file, load_subifg_file
from src.utils.ir_fitting.voigt import FIT_METHOD, SEED_NUDGE_FRAC

PACKAGE_LOGGER = "src.utils.ir_fitting"
# Named explicitly, not __name__: run as a script this module is "__main__",
# and its lines would miss the package-level file handler.
LOGGER = logging.getLogger(f"{PACKAGE_LOGGER}.api")
LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

FileCallback = Callable[[MeasurementFitResult, FileFitResult], None]
"""Called with (measurement so far, file just processed) after each file."""

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


ISO_X_MARKER = "isoX"
"""Isotope-exchange subIFGs carry this in their name. The live server routes
them to the iso_xchg integration, never to the carbonyl fit (see
``src/instrument/dispatch.py``), so folder discovery here skips them."""


def _is_fit_subifg(item: Path) -> bool:
    """True for a subIFG file the carbonyl refit applies to."""
    return item.is_file() and "_delta" in item.name and ISO_X_MARKER not in item.name


def measurement_names(folder: str | Path) -> list[str]:
    """Return every measurement base name in a subIFG dataset folder.

    A subIFG file is named ``<base name>_delta<N>.<index>``, so stripping the
    trailing ``_delta...`` chunk and deduplicating gives one entry per
    measurement. ``isoX`` files are skipped.

    Shared by :func:`fit_folder` and the plotting entry points, so folder
    discovery is defined once.
    """
    folder_path = resolve_folder(folder)
    return sorted(
        {
            "_".join(item.name.split("_")[:-1])
            for item in folder_path.iterdir()
            if _is_fit_subifg(item)
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
        ``isoX`` files are never returned.

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
    n_iso_x = 0
    for item in sorted(folder_path.iterdir()):
        if not _is_fit_subifg(item):
            n_iso_x += item.is_file() and ISO_X_MARKER in item.name
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
        "%s: selected %d subIFG files from %d measurements (skipped %d %s files)",
        folder_path.name,
        len(selected),
        len({"_".join(name.split("_")[:-1]) for name in selected}),
        n_iso_x,
        ISO_X_MARKER,
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
    baseline: str = "recompute",
    variant: BaselineVariant | None = None,
    output_folder: str = "_test",
    save: bool = True,
    log_file: bool = True,
    file_keys: Sequence[str] | None = None,
    on_file: FileCallback | None = None,
) -> MeasurementFitResult:
    """Refit every configured peak for one measurement.

    Every peak in ``ir_fitting.fit.peak_list_base`` is solved jointly per
    subIFG file, each starting from its saved fit where one exists. The output
    params CSV holds only this run's rows: a file that fails, or that
    ``manually_skip_files`` excludes, has none.

    Args:
        measurement: Path to a measurement base name inside a subIFG dataset
            folder, e.g.
            ``C:\\Data\\OpusConvert_subIFG_lgRfl\\nn1120-3_pd_ceo2_004\\20260304_145524_pd_ceo2_004-000``.
            Every ``<base name>_delta*.*`` file under it is processed.
        baseline: ``"recompute"`` (default) runs ``variant``; ``"saved"`` reads
            the stored ``*_CarbonylFitBaseline.csv`` column, for the parity gate.
        variant: Baseline recipe for ``"recompute"``. ``None`` is
            ``BaselineVariant()``, the same
            recipe the baseline CLI runs by default.
        output_folder: Output subfolder name, e.g. ``"_test"`` (reused, so a
            rerun overwrites it) or ``"_test-1"`` to keep a run. Never writes
            into the source folder.
        save: If False, compute only and return the in-memory result.
        log_file: With ``save``, also write ``refit_<timestamp>.log`` into the
            output folder. :func:`fit_folder` turns this off and writes one log
            for the whole batch instead.
        file_keys: Fit only these files: exact keys (``"delta10.0042"``), whole
            delta groups (``"delta10"``) or globs. ``None`` fits every file.
            The params CSV then holds only the selected files' rows.
        on_file: Called after each file is fitted, before the next one starts,
            e.g. to write its figure while the run is still going. An exception
            it raises is logged and does not stop the fit.

    Returns:
        MeasurementFitResult with per-file curves, rows and output paths.
    """
    if baseline not in {"saved", "recompute"}:
        raise ValueError(f"baseline must be 'saved' or 'recompute'; got {baseline!r}")

    folder_name, file_name, source_dir = _resolve_measurement(measurement)
    with _run_log(folder_name, output_folder, enabled=save and log_file) as log_path:
        if log_path is not None:
            _log_run_header(folder_name, [file_name], baseline, variant, output_folder)
        result = _run_measurement(
            fit_subifg_file,
            folder_name,
            file_name,
            source_dir,
            baseline=baseline,
            variant=variant,
            file_keys=file_keys,
            on_file=on_file,
        )

        result.params = writer.params_frame(result.files)
        if save:
            result.output_paths = writer.write_measurement(
                result, output_folder=output_folder
            )
            if log_path is not None:
                result.output_paths["log"] = log_path
        _log_warning_summary(result)
        LOGGER.info("%s", result.summary())
    return result


def _run_measurement(
    per_file,
    folder_name: str,
    file_name: str,
    source_dir: Path,
    *,
    baseline: str,
    variant: BaselineVariant | None,
    file_keys: Sequence[str] | None = None,
    on_file: FileCallback | None = None,
) -> MeasurementFitResult:
    """Apply ``per_file`` (fit or load) to the subIFG files of a measurement.

    ``file_keys`` narrows the files and ``on_file`` is called per file, both as
    :func:`fit_file` describes.

    The saved params table is read for seeds and for the carried
    ``Data_Integral`` / ``Time_Delta (s)`` columns only; none of its rows reach
    the output.
    """
    result = MeasurementFitResult(folder_name=folder_name, file_name=file_name)
    df_saved_params = writer.load_measurement_params(folder_name, file_name)
    df_saved_baseline = writer.load_saved_baseline(folder_name, file_name)
    fit_settings = ir_config.get_fit_settings()

    subifg_paths = sorted(source_dir.glob(f"{file_name}_delta*.*"))
    if not subifg_paths:
        raise FileNotFoundError(
            f"No subIFG files matching {file_name}_delta*.* in {source_dir}"
        )
    if file_keys is not None:
        patterns = list(file_keys)
        subifg_paths = [
            item
            for item in subifg_paths
            if any(
                matches_file_key(
                    runner.file_key_for(item),
                    runner.split_file_key(runner.file_key_for(item))[0],
                    pattern,
                )
                for pattern in patterns
            )
        ]
        if not subifg_paths:
            raise ValueError(f"{file_name}: no subIFG files matched file_keys={patterns}")

    LOGGER.info("%s: %d subIFG files", file_name, len(subifg_paths))
    for subifg_path in subifg_paths:
        started = time.perf_counter()
        try:
            file_result = per_file(
                subifg_path,
                df_saved_params,
                df_saved_baseline,
                fit_settings=fit_settings,
                baseline=baseline,
                variant=variant,
            )
        except Exception as exc:  # one bad file must not abort the measurement
            message = f"{subifg_path.name}: {exc}"
            # Traceback goes to the log file; the file gets no output rows.
            LOGGER.exception("%s -- no rows written for this file", message)
            result.warnings.append(message)
            continue
        if file_result is None:
            continue
        result.files.append(file_result)
        result.warnings.extend(file_result.warnings)
        if file_result.rows:
            LOGGER.info(
                "%s %s: %s nfev=%d seeded=%d nudged=%d clipped=%d %.1fs",
                file_name,
                file_result.file_key,
                "ok" if file_result.fit_success else "NOT CONVERGED",
                file_result.nfev,
                file_result.n_seeded,
                file_result.n_nudged,
                file_result.n_clipped,
                time.perf_counter() - started,
            )
        if on_file is not None:
            try:
                on_file(result, file_result)
            except Exception:  # a failed callback must not abort the fit
                LOGGER.exception("%s: on_file callback failed", subifg_path.name)

    return result


def load_measurement(
    measurement: str | Path,
    *,
    baseline: str = "saved",
    variant: BaselineVariant | None = None,
) -> MeasurementFitResult:
    """Load one measurement and rebuild its saved fit, without fitting.

    Reads every subIFG file of the measurement, resolves its baseline, and
    reconstructs the saved peaks' Voigt curves from
    ``*_CarbonylPeakFitParams.csv``. Fits nothing and writes nothing.

    Args:
        measurement: As for :func:`fit_file`.
        baseline: ``"saved"`` (default) reads the stored baseline column;
            ``"recompute"`` runs ``variant``.
        variant: As for :func:`fit_file`.

    Returns:
        MeasurementFitResult with per-file raw/baseline/corrected/composite/
        residual arrays and reconstructed curves. ``n_fitted`` is always 0.
    """
    if baseline not in {"saved", "recompute"}:
        raise ValueError(f"baseline must be 'saved' or 'recompute'; got {baseline!r}")

    folder_name, file_name, source_dir = _resolve_measurement(measurement)
    result = _run_measurement(
        load_subifg_file,
        folder_name,
        file_name,
        source_dir,
        baseline=baseline,
        variant=variant,
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
    fit_settings = ir_config.get_fit_settings()

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
        outcome = variant.compute(intensity, fit_settings, wavenumbers)

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


@contextmanager
def _run_log(
    folder_name: str,
    output_folder: str,
    *,
    enabled: bool = True,
) -> Iterator[Path | None]:
    """Copy this package's log lines to ``refit_<timestamp>.log`` for the run.

    The file sits in the run's output folder beside the CSVs, and is
    timestamped so a rerun into the same folder keeps earlier logs. The package
    logger is raised to INFO for the duration so the file is complete; those
    INFO lines also reach any console handler. The level is restored afterwards.
    """
    if not enabled:
        yield None
        return
    output_dir = writer.resolve_output_dir(
        writer.peak_fit_dir(folder_name), output_folder
    )
    log_path = output_dir / f"refit_{datetime.now().astimezone():%Y%m%d_%H%M%S}.log"
    package_logger = logging.getLogger(PACKAGE_LOGGER)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    previous_level = package_logger.level
    if package_logger.getEffectiveLevel() > logging.INFO:
        package_logger.setLevel(logging.INFO)
    package_logger.addHandler(handler)
    try:
        yield log_path
    except Exception:
        LOGGER.exception("run aborted")
        raise
    finally:
        package_logger.removeHandler(handler)
        package_logger.setLevel(previous_level)
        handler.close()


def _log_run_header(
    folder_name: str,
    measurements: list[str],
    baseline: str,
    variant: BaselineVariant | None,
    output_folder: str,
) -> None:
    """Record what this run was, so a log read the next morning stands alone."""
    fit_settings = ir_config.get_fit_settings()
    peaks = ir_config.get_peaks(fit_settings)
    recipe = variant if variant is not None else BaselineVariant()
    LOGGER.info(
        "refit start: dataset %s, %d measurement(s)", folder_name, len(measurements)
    )
    LOGGER.info("output folder: %s", output_folder)
    if baseline == "recompute":
        LOGGER.info("baseline: recompute %s", recipe)
    else:
        LOGGER.info("baseline: saved *_CarbonylFitBaseline.csv")
    LOGGER.info("optimizer: %s, seed nudge %.2g of range", FIT_METHOD, SEED_NUDGE_FRAC)
    LOGGER.info("peaks (%d): %s", len(peaks), " ".join(str(peak) for peak in peaks))


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
    baseline: str = "recompute",
    variant: BaselineVariant | None = None,
    output_folder: str = "_test",
    save: bool = True,
    measurements: Sequence[str] | None = None,
    file_keys: Sequence[str] | None = None,
) -> BatchFitResult:
    """Refit the measurements of a subIFG dataset folder.

    ``folder`` may be a dataset name (resolved under
    ``utility.subtract_ifg.sub_ifg_output``) or an absolute path. With
    ``save``, one ``refit_<timestamp>.log`` covering the whole batch is written
    into the output folder -- the record to read after an overnight run.

    ``measurements`` (exact names or globs, e.g. ``["*-021"]``) and
    ``file_keys`` (as :func:`fit_file`) narrow the run; ``None`` means all.
    """
    folder_path = resolve_folder(folder)
    batch = BatchFitResult(folder_name=folder_path.name)
    names = measurement_names(folder_path)
    if measurements is not None:
        if isinstance(measurements, str):
            raise TypeError("measurements must be a list of patterns, not a string")
        names = [
            name
            for name in names
            if any(name == pattern or fnmatchcase(name, pattern) for pattern in measurements)
        ]
        if not names:
            raise ValueError(f"no measurements in {folder_path} matched {measurements}")
    with _run_log(folder_path.name, output_folder, enabled=save) as log_path:
        batch.log_path = log_path
        if save:
            _log_run_header(folder_path.name, names, baseline, variant, output_folder)
        for index, base_name in enumerate(names, start=1):
            LOGGER.info("measurement %d/%d: %s", index, len(names), base_name)
            try:
                batch.measurements.append(
                    fit_file(
                        folder_path / base_name,
                        baseline=baseline,
                        variant=variant,
                        output_folder=output_folder,
                        save=save,
                        log_file=False,
                        file_keys=file_keys,
                    )
                )
            except Exception:  # one bad measurement must not stop the batch
                LOGGER.exception("%s: measurement failed", base_name)
        LOGGER.info("%s", batch.summary())
    return batch



def fit_files(
    folder: str | Path,
    files: Sequence[str],
    *,
    baseline: str = "recompute",
    variant: BaselineVariant | None = None,
    output_folder: str = "_test",
    save: bool = True,
    on_file: FileCallback | None = None,
) -> BatchFitResult:
    """Refit an explicit list of subIFG files from one dataset folder.

    ``files`` are subIFG filenames (``<base name>_delta<N>.<index>``), as
    :func:`subifg_files` returns them. They are grouped by measurement, and each
    measurement's params CSV holds only its listed files' rows. One
    ``refit_<timestamp>.log`` covers the whole call. ``on_file`` is passed to
    :func:`fit_file`. This is the entry point for the refit CLI.
    """
    folder_path = resolve_folder(folder)
    by_measurement: dict[str, list[str]] = {}
    for filename in files:
        item = Path(str(filename))
        base_name = "_".join(item.name.split("_")[:-1])
        if not base_name or "_delta" not in item.name:
            raise ValueError(f"not a subIFG filename: {filename!r}")
        by_measurement.setdefault(base_name, []).append(runner.file_key_for(item))

    batch = BatchFitResult(folder_name=folder_path.name)
    names = sorted(by_measurement)
    with _run_log(folder_path.name, output_folder, enabled=save) as log_path:
        batch.log_path = log_path
        if save:
            _log_run_header(folder_path.name, names, baseline, variant, output_folder)
            LOGGER.info("files (%d): %s", len(files), " ".join(sorted(map(str, files))))
        for index, base_name in enumerate(names, start=1):
            LOGGER.info("measurement %d/%d: %s", index, len(names), base_name)
            try:
                batch.measurements.append(
                    fit_file(
                        folder_path / base_name,
                        baseline=baseline,
                        variant=variant,
                        output_folder=output_folder,
                        save=save,
                        log_file=False,
                        file_keys=by_measurement[base_name],
                        on_file=on_file,
                    )
                )
            except Exception:  # one bad measurement must not stop the batch
                LOGGER.exception("%s: measurement failed", base_name)
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
    name = "20260304_145524_pd_ceo2_004-000"  # None = every measurement
    output_folder = "_test"  # reused each run; e.g. "_test-1" to keep one

    if name is None:
        batch = fit_folder(folder_name, output_folder=output_folder)
        print(batch.summary())
    else:
        run = fit_file(subifg_dir(folder_name) / name, output_folder=output_folder)
        print(run.summary())
        for output_kind, output_path in run.output_paths.items():
            print(f"  {output_kind}: {output_path}")
