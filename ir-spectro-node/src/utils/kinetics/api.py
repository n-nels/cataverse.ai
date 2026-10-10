"""User-facing kinetics API.

- ``build_areas``: refit params -> ``*_CarbonylPeakArea.csv`` (``areas.py``).
- ``process_file`` / ``process_folder``: causal classification plus the
  live-equivalent rolling kinetic fits (``writer.py``, ``mode="rolling"``),
  or one fit per segment (``segments.py``, ``mode="segments"``).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.utils.kinetics.areas import AreaBuildReport, build_folder_areas
from src.utils.kinetics.result_types import BatchFitResult, FitRunResult
from src.utils.kinetics.segments import SEGMENT_WRITER
from src.utils.kinetics.utils import select_measurements
from src.utils.kinetics.writer import AREA_SUFFIX, SEARCH_ROOT, WRITER

LOGGER = logging.getLogger(__name__)
MODELS_LOGGER = "src.utils.kinetics.models"
MODES = ("rolling", "segments")


class _TimeoutCounter(logging.Handler):
    """Count secondary_pfo ODE timeouts (0.1 s wall clock each) during one file.

    A timeout makes that solve's objective infinite, so results depend on
    machine load; the count makes that visible per file.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.count = 0

    def emit(self, record: logging.LogRecord) -> None:
        if "timed out" in record.getMessage():
            self.count += 1


def _discover_area_csvs(
    dataset_path: Path, input_subfolder: str | None = None
) -> list[Path]:
    """Find ``*_CarbonylPeakArea.csv`` files for a dataset folder.

    With ``input_subfolder`` (e.g. ``"_reprocess"``): exactly the files in
    ``<dataset>/<input_subfolder>/``, non-recursive. Without it: the live files
    under the dataset folder, excluding output/reference subfolders (``_test*``,
    ``_reprocess*``) and ``arxiv``, ``CalibrationData``.
    """
    if input_subfolder:
        return sorted((dataset_path / input_subfolder).glob(f"*{AREA_SUFFIX}"))
    excluded = {"arxiv", "CalibrationData"}
    excluded_prefixes = ("_test", "_reprocess")
    return [
        path
        for path in sorted(dataset_path.rglob(f"*{AREA_SUFFIX}"))
        if not any(
            part in excluded or part.startswith(excluded_prefixes)
            for part in path.relative_to(dataset_path).parts[:-1]
        )
    ]


def _dataset_path(dataset_folder: str | Path) -> Path:
    dataset_path = Path(dataset_folder)
    return dataset_path if dataset_path.is_absolute() else SEARCH_ROOT / dataset_path


def build_areas(
    dataset_folder: str,
    *,
    input_subfolder: str = "_reprocess",
    measurements: list[str] | None = None,
) -> list[AreaBuildReport]:
    """Build ``*_CarbonylPeakArea.csv`` from the params CSVs in ``<dataset>/<input_subfolder>``.

    See ``areas.py``: time from the per-spectrum timeline, sums from the
    ``ir_fitting.fit`` groups.
    """
    return build_folder_areas(
        dataset_folder, input_subfolder=input_subfolder, measurements=measurements
    )


def process_file(
    path: str | Path,
    *,
    mode: str = "rolling",
    output_folder: str = "_reprocess",
    fit: bool = True,
    min_points: int = 4,
    carry_forward_p0: bool = False,
    peak_names: list[str] | None = None,
) -> FitRunResult:
    """Classify and fit one area CSV into ``output_folder``.

    ``mode="rolling"``: live-equivalent. Monomer peaks + ``monomer_sum`` get
    secondary_pfo, cluster peaks + ``cluster_sum`` get pfo
    (``writer.REGIME_MODELS``), fitted at every time point, and
    ``cluster_sum`` gets the causal per-row nucleation ``classification``
    (``classification.classify_nucleation``) and, once latched,
    ``growth_onset_s`` (the growth onset) and ``latch_time_s`` (the latch
    time). Writes ``*_CarbonylPeakArea.csv``.

    ``mode="segments"``: one fit per (peak, segment) over the whole
    trajectory (``segments.py``). Writes ``*_CarbonylKineticParams.csv`` and
    ``*_CarbonylKineticFeatures.csv``; ``carry_forward_p0`` does not apply.

    ``fit=False`` writes the classification (rolling) or the features
    (segments) only. The result's ``warnings`` report ODE timeouts, if any.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}; got {mode!r}")
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(file_path)
    counter = _TimeoutCounter()
    models_logger = logging.getLogger(MODELS_LOGGER)
    models_logger.addHandler(counter)
    try:
        if mode == "segments":
            params_path, features_path, rows = SEGMENT_WRITER.write_measurement(
                file_path,
                output_folder_name=output_folder,
                fit=fit,
                min_points=min_points,
                peak_names=peak_names,
            )
            output_path = params_path or features_path
        else:
            output_path, rows = WRITER.write_measurement(
                file_path,
                output_folder_name=output_folder,
                fit=fit,
                min_points=min_points,
                carry_forward_p0=carry_forward_p0,
                peak_names=peak_names,
            )
    finally:
        models_logger.removeHandler(counter)
    summary: dict[str, float] = {}
    if mode == "segments":
        for model in ("secondary_pfo", "pfo", "exp_decay"):
            r2 = pd.to_numeric(rows.loc[rows["model"] == model, "r^2"], errors="coerce")
            if r2.notna().any():
                summary[f"{model}_median_r2"] = float(r2.median())
    else:
        for model in ("secondary_pfo", "pfo"):
            for key, value in _metrics_summary(rows, model).items():
                summary[f"{model}_{key}"] = value
    return FitRunResult(
        path=file_path,
        model=None,
        mode=mode,
        n_rows_input=int(rows["Peak_Name"].nunique()) if not rows.empty else 0,
        n_rows_fit=len(rows),
        output_path=output_path,
        metrics_summary=summary,
        warnings=[f"{counter.count} ODE timeouts"] if counter.count else [],
        fit_params=rows,
    )


def _process_file_in_worker(path: Path, kwargs: dict[str, Any]) -> FitRunResult:
    """``process_file`` in a worker process; rows are on disk, so not returned."""
    return replace(process_file(path, **kwargs), fit_params=pd.DataFrame())


def _init_worker() -> None:
    """Quiet a worker: its per-solve timeout warnings are counted, not printed."""
    logging.getLogger().setLevel(logging.ERROR)


def process_folder(
    dataset_folder: str | Path,
    *,
    input_subfolder: str | None = "_reprocess",
    measurements: list[str] | None = None,
    on_file: Callable[[FitRunResult], None] | None = None,
    workers: int = 1,
    **kwargs: Any,
) -> BatchFitResult:
    """``process_file`` over every area CSV of one dataset folder.

    ``measurements`` restricts to these measurement base names, exact or glob
    (``["*-043"]``); a ``ValueError`` if none match. ``on_file`` is
    called after each file (progress reporting). ``workers`` > 1 processes that
    many files at once, one process each, as the ``ir_fitting`` refit does.
    Workers inherit this process's priority class.
    """
    dataset_path = _dataset_path(dataset_folder)
    csv_files = _discover_area_csvs(dataset_path, input_subfolder)
    if measurements is not None:
        by_name = {p.name.removesuffix(str(AREA_SUFFIX)): p for p in csv_files}
        wanted = select_measurements(list(by_name), measurements, dataset_path)
        csv_files = [by_name[name] for name in wanted]
    outputs: list[Path] = []
    failures: dict[str, str] = {}

    def record(result: FitRunResult) -> None:
        if result.output_path is not None:
            outputs.append(result.output_path)
        if on_file is not None:
            on_file(result)

    n_workers = max(1, min(workers, os.cpu_count() or 1, len(csv_files)))
    if n_workers == 1:
        for csv_file in csv_files:
            try:
                result = process_file(csv_file, **kwargs)
            except Exception as exc:  # noqa: BLE001 - record and keep going
                failures[str(csv_file)] = str(exc)
                continue
            record(result)
    else:
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor, as_completed

        # One fit per worker: stop BLAS in each from also spreading over every
        # core. Must be in the environment before the workers import numpy.
        for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
            os.environ.setdefault(var, "1")
        LOGGER.info("parallel: %d workers over %d files", n_workers, len(csv_files))
        with ProcessPoolExecutor(
            max_workers=n_workers,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=_init_worker,
        ) as pool:
            futures = {
                pool.submit(_process_file_in_worker, csv_file, kwargs): csv_file
                for csv_file in csv_files
            }
            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001 - one file must not stop the batch
                    failures[str(futures[future])] = str(exc)
                    continue
                record(result)
    return BatchFitResult(
        dataset_folder=dataset_path,
        n_files_found=len(csv_files),
        n_files_success=len(outputs),
        n_files_failed=len(failures),
        outputs=outputs,
        failures=failures,
    )


def _metrics_summary(df: pd.DataFrame, model: str | None) -> dict[str, float]:
    if df.empty:
        return {}

    if model == "pfo":
        r2_col, rmse_col = "pfo_r^2", "pfo_rmse"
    elif model == "secondary_pfo":
        r2_col, rmse_col = "pfo-sec_r^2", "pfo-sec_rmse"
    else:
        r2_col, rmse_col = None, None

    summary: dict[str, float] = {}
    if r2_col and r2_col in df.columns:
        r2_values = np.asarray(
            pd.to_numeric(df[r2_col], errors="coerce"),
            dtype=float,
        )
        if np.isfinite(r2_values).any():
            summary["median_r2"] = float(np.nanmedian(r2_values))
    if rmse_col and rmse_col in df.columns:
        rmse_values = np.asarray(
            pd.to_numeric(df[rmse_col], errors="coerce"),
            dtype=float,
        )
        if np.isfinite(rmse_values).any():
            summary["median_rmse"] = float(np.nanmedian(rmse_values))
    return summary
