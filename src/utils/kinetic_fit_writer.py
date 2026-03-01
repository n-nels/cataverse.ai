"""Utilities for writing new kinetic fit parameters to legacy outputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
import warnings
import sys
from typing import Any, cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy.optimize import OptimizeWarning, curve_fit

path = Path(__file__).parent.parent.parent
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.analysis.spectral_fitting import get_shifted_monomer_peaks
from src.core import config


LOGGER = logging.getLogger(__name__)
SEARCH_ROOT = Path(config.get_path("data.peak_fit"))
AREA_SUFFIX = config.get_setting("filenames.carbonyl_fit.area_suffix")

# --- Config / constants ---
FLAT_WINDOW_S = 15000.0
MIN_FLAT_START_S = 10000.0
SMOOTHING_WINDOW = 5
EPS_FLAT_DEFAULT = 1e-6
RISE_DELTA_DEFAULT = 1.1e-1
PFO_PARAMS = [
    "pfo_ka_s-1",
    "pfo_kd_s-1",
    "pfo_qe_au",
    "pfo_Keq_au",
    "pfo_q0_au",
]


@dataclass
class FitResult:
    """Container for fit results."""

    model_name: str
    params: dict[str, float]
    r_squared: float
    rmse: float
    rss: float
    n_points: int


# --- Summation helpers ---
def _append_sum_rows(df: pd.DataFrame) -> pd.DataFrame:
    sum_builders = {
        "monomer_sum": build_monomer_sum,
        "cluster_sum": build_cluster_sum,
    }
    template_columns = list(df.columns)
    sum_frames: list[pd.DataFrame] = []

    for sum_name, builder in sum_builders.items():
        if "Peak_Name" in df.columns and (df["Peak_Name"] == sum_name).any():
            continue
        sum_df = cast(pd.DataFrame, builder(df))
        if not isinstance(sum_df, pd.DataFrame):
            LOGGER.warning("Unexpected sum output for %s", sum_name)
            continue
        if sum_df.empty:
            continue
        sum_df = sum_df.copy()
        sum_df["Peak_Name"] = sum_name
        for column in template_columns:
            if column not in sum_df:
                sum_df[column] = np.nan
        sum_df = sum_df[template_columns]
        sum_frames.append(cast(pd.DataFrame, sum_df))

    if not sum_frames:
        return df
    frames: list[pd.DataFrame] = [df]
    frames.extend(sum_frames)
    return pd.concat(frames, ignore_index=True)


def _drop_bi_columns(df: pd.DataFrame) -> pd.DataFrame:
    bi_columns = [column for column in df.columns if column.startswith("bi_")]
    if not bi_columns:
        return df
    return df.drop(columns=bi_columns, errors="ignore")


def _get_peak_names(base_list_key: str, isotope: str | None) -> list[str]:
    config_settings = config.get_analysis_setting("voigt_fit")
    base_list = config_settings.get(base_list_key, [])
    if not base_list:
        return []
    isotope_value = isotope or config_settings.get("isotope_default", "13CO")
    base_isotope = config_settings.get("monomer_peaks_base_isotope", isotope_value)
    shifts = config_settings.get("isotope_shift_cm1", {})
    shift_value = shifts.get(isotope_value, 0) - shifts.get(base_isotope, 0)
    return [f"Peak_{int(peak + shift_value)}" for peak in base_list]


def _get_monomer_peak_names(isotope: str | None) -> list[str]:
    config_settings = config.get_analysis_setting("voigt_fit")
    isotope_value = isotope or config_settings.get("isotope_default", "13CO")
    merged_settings = dict(config_settings)
    merged_settings["isotope_default"] = isotope_value
    return [f"Peak_{int(peak)}" for peak in get_shifted_monomer_peaks(merged_settings)]


def build_cluster_sum(df: pd.DataFrame, isotope: str | None = None) -> pd.DataFrame:
    """Build cluster_sum from dataframe."""
    df = df.copy()
    df["Time (s)"] = pd.to_numeric(df["Time (s)"], errors="coerce")
    df["Cumulative_Peak_Area"] = pd.to_numeric(
        df["Cumulative_Peak_Area"], errors="coerce"
    )
    df = df.dropna(subset=["Time (s)", "Cumulative_Peak_Area"])

    cluster_rows = df[
        df["Peak_Name"].isin(_get_peak_names("cluster_peaks_base", isotope))
    ]
    if cluster_rows.empty:
        return pd.DataFrame()

    group_cols = ["Time (s)"]
    if "Delta_Group" in cluster_rows.columns:
        group_cols.append("Delta_Group")
    if "File" in cluster_rows.columns:
        group_cols.append("File")

    return cluster_rows.groupby(group_cols)["Cumulative_Peak_Area"].sum().reset_index()


def build_monomer_sum(df: pd.DataFrame, isotope: str | None = None) -> pd.DataFrame:
    df = df.copy()
    df["Time (s)"] = pd.to_numeric(df["Time (s)"], errors="coerce")
    df["Cumulative_Peak_Area"] = pd.to_numeric(
        df["Cumulative_Peak_Area"], errors="coerce"
    )
    df = df.dropna(subset=["Time (s)", "Cumulative_Peak_Area"])

    monomer_rows = df[df["Peak_Name"].isin(_get_monomer_peak_names(isotope))]
    if monomer_rows.empty:
        return pd.DataFrame()

    group_cols = ["Time (s)"]
    if "Delta_Group" in monomer_rows.columns:
        group_cols.append("Delta_Group")
    if "File" in monomer_rows.columns:
        group_cols.append("File")

    return monomer_rows.groupby(group_cols)["Cumulative_Peak_Area"].sum().reset_index()


# --- Fit + metrics helpers ---
def _prepare_peak_area_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Time (s)"] = pd.to_numeric(df["Time (s)"], errors="coerce")
    df["Cumulative_Peak_Area"] = pd.to_numeric(
        df["Cumulative_Peak_Area"], errors="coerce"
    )
    df = df.dropna(subset=["Time (s)", "Cumulative_Peak_Area"])
    return _append_sum_rows(df)


def _calculate_metrics(
    intensity: NDArray[np.float64],
    y_pred: NDArray[np.float64],
) -> tuple[float, float, float]:
    residuals = intensity - y_pred
    ss_tot = np.sum((intensity - np.mean(intensity)) ** 2)
    rss = np.sum(residuals**2)
    r_squared = 1 - (rss / ss_tot) if ss_tot > 0 else np.nan
    rmse = np.sqrt(np.mean(residuals**2))
    return r_squared, rmse, rss


def summarize_pfo_fit(
    time_s: NDArray[np.float64],
    intensity: NDArray[np.float64],
) -> dict[str, Any]:
    if len(time_s) < 3:
        result: dict[str, Any] = {
            "r2": np.nan,
            "rmse": np.nan,
        }
        for name in PFO_PARAMS:
            result[name] = np.nan
        return result

    popt, _, r_squared, rmse = _fit_pfo_with_errors(time_s, intensity)

    result: dict[str, Any] = {
        "r2": r_squared,
        "rmse": rmse,
    }
    for name, value in zip(PFO_PARAMS, popt):
        result[name] = value
    return result


def _prefix_fit_results(fit_result: dict[str, Any], prefix: str) -> dict[str, Any]:
    return {f"{prefix}{k}": v for k, v in fit_result.items() if k not in {"rmse"}}


def _window_slope(time_s: NDArray[np.float64], intensity: NDArray[np.float64]) -> float:
    if len(time_s) < 2:
        return np.nan
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Polyfit may be poorly conditioned")
        slope, _ = np.polyfit(time_s, intensity, 1)
    return float(slope)


def _find_flat_transition(
    time_s: NDArray[np.float64],
    intensity: NDArray[np.float64],
    eps_flat: float,
    min_start_s: float,
    window_s: float,
) -> tuple[tuple[float, float, float] | None, float | None]:
    flat_window: tuple[float, float, float] | None = None
    transition_end: float | None = None
    for start_idx, start_time in enumerate(time_s):
        if start_time < min_start_s:
            continue
        end_time = start_time + window_s
        end_idx = np.searchsorted(time_s, end_time, side="right") - 1
        if end_idx <= start_idx + 1:
            continue
        window_time = time_s[start_idx : end_idx + 1]
        window_intensity = intensity[start_idx : end_idx + 1]
        slope = _window_slope(window_time, window_intensity)
        if not np.isfinite(slope):
            continue
        is_flat = abs(slope) <= eps_flat
        if flat_window is not None and not is_flat:
            transition_end = float(time_s[end_idx])
            break
        if is_flat:
            flat_window = (float(start_time), float(time_s[end_idx]), float(slope))
    return flat_window, transition_end


def _running_mean(
    time_s: NDArray[np.float64],
    intensity: NDArray[np.float64],
    window: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64]] | None:
    if len(time_s) < window:
        return None
    kernel = np.ones(window) / float(window)
    smoothed = np.convolve(intensity, kernel, mode="valid")
    smoothed_time = time_s[window - 1 :]
    return smoothed_time, smoothed


def detect_discontinuity(
    time_s: NDArray[np.float64],
    intensity: NDArray[np.float64],
    eps_flat: float,
    rise_delta: float,
) -> tuple[bool, float | None]:
    flat_window, transition_end = _find_flat_transition(
        time_s, intensity, eps_flat, MIN_FLAT_START_S, FLAT_WINDOW_S
    )
    if flat_window is None or transition_end is None:
        return False, None

    flat_start, flat_end, _ = flat_window
    start_idx = np.searchsorted(time_s, flat_start, side="left")
    end_idx = np.searchsorted(time_s, flat_end, side="right")
    baseline = float(np.mean(intensity[start_idx:end_idx]))
    last_count = max(int(round(len(time_s) * 0.05)), 1)
    tail_mean = float(np.mean(intensity[-last_count:]))
    if tail_mean < baseline + rise_delta:
        return False, None

    smooth_result = _running_mean(time_s, intensity, SMOOTHING_WINDOW)
    smooth_transition: float | None = None
    if smooth_result is not None:
        smooth_time, smooth_intensity = smooth_result
        _, smooth_transition = _find_flat_transition(
            smooth_time, smooth_intensity, eps_flat, MIN_FLAT_START_S, FLAT_WINDOW_S
        )

    breakpoint_used = (
        smooth_transition if smooth_transition is not None else transition_end
    )
    return True, breakpoint_used


def pfo(
    time_s: NDArray[np.float64],
    k_a: float,
    k_d: float,
    q_e: float,
    K_eq: float,
    q_0: float,
) -> NDArray[np.float64]:
    """PFO uptake with exponential decay toward equilibrium offset."""
    adsorption = q_e * (1.0 - np.exp(-k_a * time_s)) * np.exp(-k_d * time_s)
    equilibrium = K_eq * (1.0 - np.exp(-k_d * time_s))
    return q_0 + adsorption + equilibrium


def _fit_pfo_with_errors(
    time_s: NDArray[np.float64],
    intensity: NDArray[np.float64],
    p0: list[float] | None = None,
) -> tuple[NDArray[np.float64], NDArray[np.float64], float, float]:
    if p0 is None:
        q_guess = float(np.max(intensity)) if intensity.size else 0.0
        q_floor = max(q_guess, 0.0)
        q0_guess = float(intensity[0]) if intensity.size else 0.0
        p0 = [1e-4, 1e-6, q_floor, q_floor * 0.5, q0_guess]
    bounds = ([0.0, 0.0, 0.0, 0.0, -np.inf], [np.inf, np.inf, np.inf, np.inf, np.inf])

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", OptimizeWarning)
        try:
            with np.errstate(
                divide="ignore", invalid="ignore", over="ignore", under="ignore"
            ):
                popt, pcov = curve_fit(
                    pfo,
                    time_s,
                    intensity,
                    p0=p0,
                    bounds=bounds,
                    maxfev=20000,
                )
                y_pred = pfo(time_s, *popt)
                r_squared, rmse, _ = _calculate_metrics(intensity, y_pred)
                std_errors = np.sqrt(np.diag(pcov))
                return popt, std_errors, r_squared, rmse
        except Exception as exc:
            LOGGER.warning("PFO fit failed: %s", exc)

    popt_length = len(p0)
    return (
        np.full(popt_length, np.nan),
        np.full(popt_length, np.nan),
        np.nan,
        np.nan,
    )


def fit_pfo(
    time_s: NDArray[np.float64],
    intensity: NDArray[np.float64],
    p0: list[float] | None = None,
) -> FitResult | None:
    """Fit PFO kinetics model to data."""
    popt, _, r_squared, rmse = _fit_pfo_with_errors(time_s, intensity, p0=p0)
    if not np.all(np.isfinite(popt)):
        return None
    y_pred = pfo(time_s, *popt)
    r_squared, rmse, rss = _calculate_metrics(intensity, y_pred)
    params = {
        "k_a": float(popt[0]),
        "k_d": float(popt[1]),
        "q_e": float(popt[2]),
        "K_eq": float(popt[3]),
        "q_0": float(popt[4]),
    }
    return FitResult(
        model_name="pfo",
        params=params,
        r_squared=r_squared,
        rmse=rmse,
        rss=rss,
        n_points=len(time_s),
    )


def classify_trajectory(
    time_s: NDArray[np.float64],
    intensity: NDArray[np.float64],
    eps_flat: float = EPS_FLAT_DEFAULT,
    rise_delta: float = RISE_DELTA_DEFAULT,
) -> dict[str, Any]:
    """Classify trajectory as continuous or discontinuous."""
    result: dict[str, Any] = {}
    if len(time_s) < 3:
        result["classification"] = "fit_failed"
        return result

    is_disc, breakpoint_s = detect_discontinuity(
        time_s, intensity, eps_flat, rise_delta
    )
    if not is_disc or breakpoint_s is None:
        result["classification"] = "continuous"
        return result

    result["classification"] = "discontinuous"
    result["growth_onset_s"] = breakpoint_s
    pre_mask = time_s <= breakpoint_s
    post_mask = time_s > breakpoint_s
    pre_fit = summarize_pfo_fit(time_s[pre_mask], intensity[pre_mask])
    post_fit = summarize_pfo_fit(time_s[post_mask], intensity[post_mask])
    result.update(_prefix_fit_results(pre_fit, "pre_"))
    result.update(_prefix_fit_results(post_fit, "post_"))

    return result


# --- Row preparation (operations) ---
def _prepare_pfo_fit_rows(
    df: pd.DataFrame,
    *,
    min_points: int = 4,
) -> pd.DataFrame:
    df = _prepare_peak_area_df(df)

    records: list[dict[str, float | str]] = []
    sum_names = ["cluster_sum"]

    for group_key, group in df.groupby("Peak_Name"):
        group = group.sort_values("Time (s)").reset_index(drop=True)
        peak_name = group_key

        # Compute classification once per Peak_Name for sum peaks
        classification_value: float | str = np.nan
        breakpoint_used_value: float | str = np.nan
        classification: dict[str, Any] = {}
        if peak_name in sum_names and len(group) >= min_points:
            time_s_all = group["Time (s)"].to_numpy(dtype=float)
            intensity_all = group["Cumulative_Peak_Area"].to_numpy(dtype=float)
            classification = classify_trajectory(time_s_all, intensity_all)
            for key, value in classification.items():
                if key.startswith("pre_") or key.startswith("post_"):
                    if isinstance(value, float):
                        classification[key] = float(value)
            classification_raw = classification.get("classification")
            classification_value = (
                str(classification_raw) if classification_raw is not None else np.nan
            )
            breakpoint_raw = classification.get("growth_onset_s")
            breakpoint_used_value = (
                float(breakpoint_raw) if breakpoint_raw is not None else np.nan
            )

        if len(group) < min_points:
            continue

        unique_times = sorted(group["Time (s)"].unique())
        for unique_time in unique_times:
            mask = group["Time (s)"] <= unique_time
            time_s = group.loc[mask, "Time (s)"].to_numpy(dtype=float)
            intensity = group.loc[mask, "Cumulative_Peak_Area"].to_numpy(dtype=float)

            if len(time_s) < min_points:
                continue

            current_row = group[group["Time (s)"] == unique_time].iloc[0]
            popt, std_errors, r_squared, rmse = _fit_pfo_with_errors(time_s, intensity)

            record: dict[str, float | str] = {
                "Peak_Name": str(current_row["Peak_Name"]),
                "Time (s)": float(unique_time),
                "pfo_r^2": r_squared,
                "pfo_rmse": rmse,
                "classification": classification_value,
                "growth_onset_s": breakpoint_used_value,
            }
            if peak_name in sum_names and classification_value == "discontinuous":
                for key, value in classification.items():
                    if key.startswith("pre_") or key.startswith("post_"):
                        record[key] = value

            param_map = [
                ("pfo_ka_s-1", "pfo_ka_stderr"),
                ("pfo_kd_s-1", "pfo_kd_stderr"),
                ("pfo_qe_au", "pfo_qe_au_stderr"),
                ("pfo_Keq_au", "pfo_Keq_au_stderr"),
                ("pfo_q0_au", "pfo_q0_au_stderr"),
            ]
            for (value_key, stderr_key), value, stderr in zip(
                param_map, popt, std_errors, strict=True
            ):
                record[value_key] = float(value) if np.isfinite(value) else np.nan
                record[stderr_key] = float(stderr) if np.isfinite(stderr) else np.nan

            records.append(record)

    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def _prepare_pfo_classification_rows(
    df: pd.DataFrame,
    *,
    min_points: int = 4,
) -> pd.DataFrame:
    df = _prepare_peak_area_df(df)

    # Group only by Peak_Name (no Delta_Group) to aggregate across all groups
    group_cols = ["Peak_Name"]

    records: list[dict[str, float | str]] = []
    sum_names = ["cluster_sum"]

    for group_key, group in df.groupby(group_cols):
        group = group.sort_values("Time (s)").reset_index(drop=True)
        peak_name = group_key[0] if isinstance(group_key, tuple) else group_key

        classification_value: float | str = np.nan
        breakpoint_used_value: float | str = np.nan
        classification: dict[str, Any] = {}
        if peak_name in sum_names and len(group) >= min_points:
            time_s_all = group["Time (s)"].to_numpy(dtype=float)
            intensity_all = group["Cumulative_Peak_Area"].to_numpy(dtype=float)
            classification = classify_trajectory(time_s_all, intensity_all)
            for key, value in classification.items():
                if key.startswith("pre_") or key.startswith("post_"):
                    if isinstance(value, float):
                        classification[key] = float(value)
            classification_raw = classification.get("classification")
            classification_value = (
                str(classification_raw) if classification_raw is not None else np.nan
            )
            breakpoint_raw = classification.get("growth_onset_s")
            breakpoint_used_value = (
                float(breakpoint_raw) if breakpoint_raw is not None else np.nan
            )

        for idx in range(len(group)):
            current_row = group.iloc[idx]
            record: dict[str, float | str] = {
                "Peak_Name": str(current_row["Peak_Name"]),
                "Time (s)": float(current_row["Time (s)"]),
                "classification": classification_value,
                "growth_onset_s": breakpoint_used_value,
            }
            if peak_name in sum_names and classification_value == "discontinuous":
                for key, value in classification.items():
                    if key.startswith("pre_") or key.startswith("post_"):
                        record[key] = value
            records.append(record)

    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


# --- Writers / public API ---
def write_fit_params_to_legacy(
    legacy_path: str | Path,
    fit_params: pd.DataFrame,
    *,
    join_columns: tuple[str, ...] = ("Peak_Name", "Time (s)"),
    output_folder_name: str = "_test",
    legacy_df: pd.DataFrame | None = None,
) -> Path:
    """Write fit parameters onto a legacy CSV in a safe output folder.

    Args:
        legacy_path: Path to the existing legacy CSV file.
        fit_params: DataFrame containing fitted parameters to merge in.
        join_columns: Column names used to align the legacy rows and fit params.
        output_folder_name: Output subfolder name to avoid overwriting data.

    Returns:
        Path to the newly written CSV file.
    """
    legacy_path = Path(legacy_path)
    df_legacy = pd.read_csv(legacy_path) if legacy_df is None else legacy_df.copy()

    # Remove old _mol columns if they exist
    old_mol_columns = [
        col
        for col in df_legacy.columns
        if any(suffix in col for suffix in ["pfo_qe_mol", "pfo_qeq_mol", "pfo_q0_mol"])
    ]
    drop_columns = old_mol_columns + ["pfo_qe_stderr", "breakpoint_s"]
    if drop_columns:
        df_legacy = df_legacy.drop(columns=drop_columns, errors="ignore")

    join_columns_present = tuple(
        col
        for col in join_columns
        if col in df_legacy.columns and col in fit_params.columns
    )
    if not join_columns_present:
        raise ValueError(
            "No shared join columns found between legacy data and fit parameters."
        )

    df_merged = pd.merge(
        df_legacy,
        fit_params,
        on=list(join_columns_present),
        how="left",
        suffixes=("", "_new"),
    )

    for column in df_merged.columns:
        if not column.endswith("_new"):
            continue
        base_column = column.removesuffix("_new")
        if base_column in df_merged.columns:
            df_merged[base_column] = df_merged[column]
        else:
            df_merged.rename(columns={column: base_column}, inplace=True)
        df_merged.drop(columns=[column], inplace=True)

    output_dir = (
        legacy_path.parent
        if legacy_path.parent.name == output_folder_name
        else legacy_path.parent / output_folder_name
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / legacy_path.name
    df_merged.to_csv(output_path, index=False)
    return output_path


def write_pfo_fit_params(
    carbonyl_peak_area_path: str | Path,
    *,
    output_folder_name: str = "_test",
    min_points: int = 4,
) -> Path:
    """Fit PFO kinetics per Peak_Name and write params to _test output."""
    carbonyl_peak_area_path = Path(carbonyl_peak_area_path)
    df_legacy = pd.read_csv(carbonyl_peak_area_path)
    df_legacy = _drop_bi_columns(df_legacy)
    df_legacy = _prepare_peak_area_df(df_legacy)
    pfo_params = _prepare_pfo_fit_rows(df_legacy, min_points=min_points)
    if pfo_params.empty:
        raise ValueError("No fit results were produced.")
    return write_fit_params_to_legacy(
        carbonyl_peak_area_path,
        pfo_params,
        output_folder_name=output_folder_name,
        legacy_df=df_legacy,
    )


def write_pfo_classification(
    carbonyl_peak_area_path: str | Path,
    *,
    output_folder_name: str = "_test",
    min_points: int = 4,
) -> Path:
    """Write classification values without per-row fitting."""
    carbonyl_peak_area_path = Path(carbonyl_peak_area_path)
    df_legacy = pd.read_csv(carbonyl_peak_area_path)
    df_legacy = _drop_bi_columns(df_legacy)
    df_legacy = _prepare_peak_area_df(df_legacy)
    fit_params = _prepare_pfo_classification_rows(df_legacy, min_points=min_points)
    if fit_params.empty:
        raise ValueError("No classification results were produced.")
    return write_fit_params_to_legacy(
        carbonyl_peak_area_path,
        fit_params,
        output_folder_name=output_folder_name,
        legacy_df=df_legacy,
    )


def process_carbonyl_peak_area_files(
    csv_files: list[Path],
    *,
    output_folder_name: str = "_test",
    min_points: int = 4,
    classification_only: bool = False,
) -> list[Path]:
    """Process multiple CarbonylPeakArea CSVs into _test outputs."""
    outputs: list[Path] = []
    for csv_file in csv_files:
        LOGGER.info("Processing %s...", csv_file)
        try:
            if not csv_file.name.endswith(str(AREA_SUFFIX)):
                LOGGER.warning("Skipping non-area CSV: %s", csv_file)
                continue
            if classification_only:
                output_path = write_pfo_classification(
                    csv_file,
                    output_folder_name=output_folder_name,
                    min_points=min_points,
                )
            else:
                output_path = write_pfo_fit_params(
                    csv_file,
                    output_folder_name=output_folder_name,
                    min_points=min_points,
                )
            outputs.append(output_path)
        except Exception as exc:
            LOGGER.warning("Failed processing %s: %s", csv_file, exc)
    return outputs


def process_carbonyl_peak_area_folder(
    dataset_folder: str | Path,
    *,
    output_folder_name: str = "_test",
    min_points: int = 4,
    classification_only: bool = False,
) -> list[Path]:
    """Process CarbonylPeakArea CSVs within a dataset folder."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    dataset_path = Path(dataset_folder)
    if not dataset_path.is_absolute():
        dataset_path = SEARCH_ROOT / dataset_path

    if not SEARCH_ROOT.exists():
        LOGGER.error("Search root not found: %s", SEARCH_ROOT)
        return []
    if not dataset_path.exists():
        LOGGER.error("Dataset folder not found: %s", dataset_path)
        return []

    csv_files = [
        path
        for path in sorted(dataset_path.rglob("*_CarbonylPeakArea.csv"))
        if "_test" not in path.parts
        and "arxiv" not in path.parts
        and "CalibrationData" not in path.parts
    ]

    if not csv_files:
        LOGGER.error("No matching CSV files found in %s", dataset_path)
        return []

    return process_carbonyl_peak_area_files(
        csv_files,
        output_folder_name=output_folder_name,
        min_points=min_points,
        classification_only=classification_only,
    )


if __name__ == "__main__":
    # Example usage
    process_carbonyl_peak_area_folder(
        dataset_folder="nn1120-3_pd_ceo2_003",
        classification_only=True,
    )

    # file = Path(
    #     r"C:\Data\peakFit\nn1120-3_pd_ceo2_003\20260220_165102_pd_ceo2_003-118_CarbonylPeakArea.csv"
    # )
    # process_carbonyl_peak_area_files([file], output_folder_name="_test", min_points=6)
