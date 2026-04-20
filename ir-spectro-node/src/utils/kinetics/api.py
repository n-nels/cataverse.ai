"""User-facing kinetics API with minimal entry points."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

path = Path(__file__).resolve().parents[3]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.utils.kinetics.result_types import BatchFitResult, FitRunResult
from src.utils.kinetics.writer import AREA_SUFFIX, SEARCH_ROOT, WRITER


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
        if r2_values.size > 0:
            summary["median_r2"] = float(np.nanmedian(r2_values))
    if rmse_col and rmse_col in df.columns:
        rmse_values = np.asarray(
            pd.to_numeric(df[rmse_col], errors="coerce"),
            dtype=float,
        )
        if rmse_values.size > 0:
            summary["median_rmse"] = float(np.nanmedian(rmse_values))
    return summary


def fit_file(
    path: str | Path,
    *,
    model: str = "secondary_pfo",
    peak_names: list[str] | None = None,
    mode: str = "full_series",
    min_points: int = 4,
    init: list[float] | None = None,
    use_prior_p0: bool = True,
    output_folder: str | None = "_test",
    save: bool = True,
) -> FitRunResult:
    """Fit one ``*_CarbonylPeakArea.csv`` file.

    Args:
        path: Path to one CarbonylPeakArea CSV.
        model: Kinetic model key. Supported: ``"pfo"``, ``"secondary_pfo"``.
        peak_names: Optional Peak_Name filter. ``None`` fits all available peaks.
        mode: Execution mode selector. ``"full_series"`` runs one fit per peak
            using all time points. ``"rolling"`` runs cumulative fits for each
            unique time using all points up to that time.
        min_points: Minimum points required before fitting a trajectory slice.
        init: Optional initial parameter list (p0) passed to the model fit.
        use_prior_p0: If True, successful secondary-p0 values are carried forward
            between rows (only accepted if r² improves by > 0.01). If False,
            fitting starts fresh from ``init`` (or defaults) for every row.
        output_folder: Output subfolder name when ``save=True``.
        save: If True, write merged legacy-style CSV output.

    Returns:
        FitRunResult containing in-memory fit rows and optional output path.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(file_path)

    if mode not in {"full_series", "rolling"}:
        raise ValueError("mode must be one of: full_series, rolling")
    if model not in {"pfo", "secondary_pfo"}:
        raise ValueError("model must be one of: pfo, secondary_pfo")

    df_input = pd.read_csv(file_path)
    n_rows_input = len(df_input)
    fit_rows = WRITER.prepare_model_fit_rows(
        model,
        df_input,
        min_points=min_points,
        peak_names=peak_names,
        mode=mode,
        p0=init,
        carry_forward_p0=use_prior_p0,
    )

    output_path: Path | None = None
    if save:
        if output_folder is None:
            raise ValueError("output_folder must be set when save=True")
        output_path = WRITER.write_model_fit_params(
            model,
            file_path,
            output_folder_name=output_folder,
            min_points=min_points,
            peak_names=peak_names,
            mode=mode,
            p0=init,
            use_prior_p0=use_prior_p0,
        )

    return FitRunResult(
        path=file_path,
        model=model,
        mode=mode,
        n_rows_input=n_rows_input,
        n_rows_fit=len(fit_rows),
        output_path=output_path,
        metrics_summary=_metrics_summary(fit_rows, model),
        warnings=[],
        fit_params=fit_rows,
    )


def classify_file(
    path: str | Path,
    *,
    peak_names: list[str] | None = None,
    min_points: int = 4,
    output_folder: str | None = "_test",
    save: bool = True,
) -> FitRunResult:
    """Run classification-only workflow on one ``*_CarbonylPeakArea.csv`` file.

    Args:
        path: Path to one CarbonylPeakArea CSV.
        peak_names: Optional Peak_Name filter. ``None`` classifies all peaks.
        min_points: Minimum points required for classification logic.
        output_folder: Output subfolder name when ``save=True``.
        save: If True, write merged legacy-style CSV output.

    Returns:
        FitRunResult with classification rows and optional output path.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(file_path)

    df_input = pd.read_csv(file_path)
    n_rows_input = len(df_input)
    fit_rows = WRITER.prepare_pfo_classification_rows(
        df_input,
        min_points=min_points,
        peak_names=peak_names,
    )

    output_path: Path | None = None
    if save:
        if output_folder is None:
            raise ValueError("output_folder must be set when save=True")
        output_path = WRITER.write_pfo_classification(
            file_path,
            output_folder_name=output_folder,
            min_points=min_points,
            peak_names=peak_names,
        )

    return FitRunResult(
        path=file_path,
        model=None,
        mode=None,
        n_rows_input=n_rows_input,
        n_rows_fit=len(fit_rows),
        output_path=output_path,
        metrics_summary={},
        warnings=[],
        fit_params=fit_rows,
    )


def fit_folder(
    dataset_folder: str | Path,
    *,
    model: str = "secondary_pfo",
    peak_names: list[str] | None = None,
    mode: str = "full_series",
    min_points: int = 4,
    init: list[float] | None = None,
    use_prior_p0: bool = True,
    output_folder: str = "_test",
) -> BatchFitResult:
    """Fit all matching CarbonylPeakArea files in one dataset folder.

    Args:
        dataset_folder: Absolute folder path or relative folder under SEARCH_ROOT.
        model: Kinetic model key. Supported: ``"pfo"``, ``"secondary_pfo"``.
        peak_names: Optional Peak_Name filter. ``None`` fits all available peaks.
        mode: Execution mode selector passed through to ``fit_file``.
        min_points: Minimum points required before fitting a trajectory slice.
        init: Optional initial parameter list (p0) passed to the model fit.
        use_prior_p0: If True, successful secondary-p0 values are carried forward
            between rows (only accepted if r² improves by > 0.01). If False,
            fitting starts fresh from ``init`` (or defaults) for every row.
        output_folder: Output subfolder name for merged outputs.

    Returns:
        BatchFitResult summarizing successes, failures, and output files.
    """
    if mode not in {"full_series", "rolling"}:
        raise ValueError("mode must be one of: full_series, rolling")
    if model not in {"pfo", "secondary_pfo"}:
        raise ValueError("model must be one of: pfo, secondary_pfo")

    dataset_path = Path(dataset_folder)
    if not dataset_path.is_absolute():
        dataset_path = SEARCH_ROOT / dataset_path

    csv_files = [
        path
        for path in sorted(dataset_path.rglob("*_CarbonylPeakArea.csv"))
        if "_test" not in path.parts
        and "arxiv" not in path.parts
        and "CalibrationData" not in path.parts
        and path.name.endswith(str(AREA_SUFFIX))
    ]

    outputs: list[Path] = []
    failures: dict[str, str] = {}
    for csv_file in csv_files:
        try:
            _ = fit_file(
                csv_file,
                model=model,
                peak_names=peak_names,
                mode=mode,
                min_points=min_points,
                init=init,
                use_prior_p0=use_prior_p0,
                output_folder=output_folder,
                save=True,
            )
            outputs.append(csv_file.parent / output_folder / csv_file.name)
        except Exception as exc:
            failures[str(csv_file)] = str(exc)

    return BatchFitResult(
        dataset_folder=dataset_path,
        n_files_found=len(csv_files),
        n_files_success=len(outputs),
        n_files_failed=len(failures),
        outputs=outputs,
        failures=failures,
    )


def fit_folder_by_sum_models(
    dataset_folder: str | Path,
    *,
    monomer_model: str = "secondary_pfo",
    cluster_model: str = "pfo",
    mode: str = "full_series",
    min_points: int = 4,
    monomer_init: list[float] | None = None,
    cluster_init: list[float] | None = None,
    carry_forward_p0: bool = True,
    output_folder: str = "_test",
) -> BatchFitResult:
    """Fit monomer and cluster groups with different models in one pass.

    Uses config-based peak lists and writes one merged output file per input:
    - monomer peaks + ``monomer_sum`` -> ``monomer_model``
    - cluster peaks + ``cluster_sum`` -> ``cluster_model``

    The ``use_prior_p0`` option applies to the monomer (secondary) model only:
    - True: successful secondary-p0 values are carried forward between rows
      (only accepted if r² improves by > 0.01).
    - False: fitting starts fresh from ``monomer_init`` (or defaults) for every row.
    """
    if mode not in {"full_series", "rolling"}:
        raise ValueError("mode must be one of: full_series, rolling")
    for model in (monomer_model, cluster_model):
        if model not in {"pfo", "secondary_pfo"}:
            raise ValueError("model must be one of: pfo, secondary_pfo")

    dataset_path = Path(dataset_folder)
    if not dataset_path.is_absolute():
        dataset_path = SEARCH_ROOT / dataset_path

    csv_files = [
        path
        for path in sorted(dataset_path.rglob("*_CarbonylPeakArea.csv"))
        if "_test" not in path.parts
        and "arxiv" not in path.parts
        and "CalibrationData" not in path.parts
        and path.name.endswith(str(AREA_SUFFIX))
    ]

    outputs: list[Path] = []
    failures: dict[str, str] = {}
    for csv_file in csv_files:
        try:
            output_path = WRITER.write_sum_model_fit_params(
                csv_file,
                monomer_model_key=monomer_model,
                cluster_model_key=cluster_model,
                output_folder_name=output_folder,
                min_points=min_points,
                mode=mode,
                monomer_p0=monomer_init,
                cluster_p0=cluster_init,
                carry_forward_p0=carry_forward_p0,
            )
            outputs.append(output_path)
        except Exception as exc:
            failures[str(csv_file)] = str(exc)

    return BatchFitResult(
        dataset_folder=dataset_path,
        n_files_found=len(csv_files),
        n_files_success=len(outputs),
        n_files_failed=len(failures),
        outputs=outputs,
        failures=failures,
    )


def remove_legacy_pfo_columns_file(
    path: str | Path,
    *,
    output_folder: str = "_test",
    prefixes: tuple[str, ...] = ("pfo",),
) -> FitRunResult:
    """Remove legacy columns (default prefix ``"pfo"``) from one CSV.

    Args:
        path: Path to one ``*_CarbonylPeakArea.csv`` file.
        output_folder: Output subfolder name for cleaned CSV.
        prefixes: Column-name prefixes to remove. Default removes any column
            whose name starts with ``"pfo"``.

    Returns:
        FitRunResult with ``fit_params`` containing the cleaned dataframe.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(file_path)

    df_input = pd.read_csv(file_path)
    n_rows_input = len(df_input)
    output_path = WRITER.remove_legacy_pfo_columns_file(
        file_path,
        output_folder_name=output_folder,
        prefixes=prefixes,
    )
    cleaned_df = pd.read_csv(output_path)
    removed_count = len(df_input.columns) - len(cleaned_df.columns)

    return FitRunResult(
        path=file_path,
        model=None,
        mode=None,
        n_rows_input=n_rows_input,
        n_rows_fit=len(cleaned_df),
        output_path=output_path,
        metrics_summary={"columns_removed": float(max(removed_count, 0))},
        warnings=[],
        fit_params=cleaned_df,
    )


def remove_legacy_pfo_columns_folder(
    dataset_folder: str | Path,
    *,
    output_folder: str = "_test",
    prefixes: tuple[str, ...] = ("pfo",),
) -> BatchFitResult:
    """Remove legacy columns (default prefix ``"pfo"``) in a folder.

    Args:
        dataset_folder: Absolute path or relative folder under ``SEARCH_ROOT``.
        output_folder: Output subfolder name for cleaned CSVs.
        prefixes: Column-name prefixes to remove. Default removes any column
            whose name starts with ``"pfo"``.

    Returns:
        BatchFitResult for all matching ``*_CarbonylPeakArea.csv`` files.
    """
    dataset_path = Path(dataset_folder)
    if not dataset_path.is_absolute():
        dataset_path = SEARCH_ROOT / dataset_path

    csv_files = [
        path
        for path in sorted(dataset_path.rglob("*_CarbonylPeakArea.csv"))
        if "_test" not in path.parts
        and "arxiv" not in path.parts
        and "CalibrationData" not in path.parts
        and path.name.endswith(str(AREA_SUFFIX))
    ]

    outputs: list[Path] = []
    failures: dict[str, str] = {}
    for csv_file in csv_files:
        try:
            output_path = WRITER.remove_legacy_pfo_columns_file(
                csv_file,
                output_folder_name=output_folder,
                prefixes=prefixes,
            )
            outputs.append(output_path)
        except Exception as exc:
            failures[str(csv_file)] = str(exc)

    return BatchFitResult(
        dataset_folder=dataset_path,
        n_files_found=len(csv_files),
        n_files_success=len(outputs),
        n_files_failed=len(failures),
        outputs=outputs,
        failures=failures,
    )


if __name__ == "__main__":
    
    fit_folder_by_sum_models(
        dataset_folder=SEARCH_ROOT / "nn1120-3_pd_ceo2_004",
        monomer_model="secondary_pfo",
        cluster_model="pfo",
        mode="rolling",
        min_points=4,
        monomer_init=None,
        cluster_init=None,
        carry_forward_p0=False,
        output_folder="_test",
    )
