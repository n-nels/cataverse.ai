"""Kinetics fitting helpers for peak area analysis."""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from typing import Any, Callable, cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy.optimize import OptimizeWarning, curve_fit

from ..core import config
from .spectral_fitting import get_shifted_monomer_peaks

LOGGER = logging.getLogger(__name__)

CLASSIFICATION_SETTINGS = config.get_analysis_setting("kinetics_classification") or {}
FLAT_WINDOW_S = float(CLASSIFICATION_SETTINGS.get("flat_window_s", 15000.0))
MIN_FLAT_START_S = float(CLASSIFICATION_SETTINGS.get("min_flat_start_s", 10000.0))
SMOOTHING_WINDOW = int(CLASSIFICATION_SETTINGS.get("smoothing_window", 4))
EPS_FLAT_DEFAULT = float(CLASSIFICATION_SETTINGS.get("eps_flat", 1e-6))
RISE_DELTA_DEFAULT = float(CLASSIFICATION_SETTINGS.get("rise_delta", 1.1e-1))
PFO_PARAMS = [
    "pfo_ka_s-1",
    "pfo_kd_s-1",
    "pfo_qe_au",
    "pfo_Keq_au",
    "pfo_q0_au",
]


@dataclass
class PfoFitResult:
    """Structured PFO fit result for a single time point."""

    peak_name: str
    time_s: float
    ka_s_1: float
    ka_stderr: float
    kd_s_1: float
    kd_stderr: float
    qe_au: float
    qe_au_stderr: float
    Keq_au: float
    Keq_au_stderr: float
    q0_au: float
    q0_au_stderr: float
    r_squared: float
    rmse: float
    classification: str
    growth_onset_s: float | None

    def to_dict(self) -> dict[str, Any]:
        """Return a dict with legacy column names."""
        return {
            "Peak_Name": self.peak_name,
            "Time (s)": self.time_s,
            "pfo_ka_s-1": self.ka_s_1,
            "pfo_ka_stderr": self.ka_stderr,
            "pfo_kd_s-1": self.kd_s_1,
            "pfo_kd_stderr": self.kd_stderr,
            "pfo_qe_au": self.qe_au,
            "pfo_qe_au_stderr": self.qe_au_stderr,
            "pfo_Keq_au": self.Keq_au,
            "pfo_Keq_au_stderr": self.Keq_au_stderr,
            "pfo_q0_au": self.q0_au,
            "pfo_q0_au_stderr": self.q0_au_stderr,
            "pfo_r^2": self.r_squared,
            "pfo_rmse": self.rmse,
            "classification": self.classification,
            "growth_onset_s": self.growth_onset_s,
        }


@dataclass
class FitResult:
    """Container for fit results."""

    model_name: str
    params: dict[str, float]
    r_squared: float
    rmse: float
    rss: float
    n_points: int


def linfunc(
    x: NDArray[np.float64] | pd.Series,
    a: float,
    b: float,
) -> NDArray[np.float64] | pd.Series:
    """Linear function with intercept."""
    return a * x + b


def linfunc_no_intercept(
    x: NDArray[np.float64] | pd.Series,
    a: float | NDArray[np.float64],
) -> NDArray[np.float64] | pd.Series:
    """Linear function constrained to the origin."""
    return a * x


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


def calculate_metrics(
    intensity: np.ndarray,
    y_pred: np.ndarray,
) -> tuple[float, float, float]:
    """Compute r-squared, RMSE, and RSS for a fit."""
    residuals = intensity - y_pred
    ss_tot = np.sum((intensity - np.mean(intensity)) ** 2)
    ss_res = np.sum(residuals**2)

    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else np.nan
    rmse = np.sqrt(np.mean(residuals**2))
    rss = ss_res

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

    popt, _, r_squared, rmse = fit_and_evaluate(time_s, intensity)

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


def fit_and_evaluate(
    time_s: NDArray[np.float64],
    intensity: NDArray[np.float64],
    p0: list[float] | None = None,
) -> tuple[NDArray[np.float64], NDArray[np.float64], float, float]:
    """Fit PFO model and return parameters, errors, and diagnostics."""
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
                r_squared, rmse, _ = calculate_metrics(intensity, y_pred)
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


def classify_trajectory(
    time_s: NDArray[np.float64],
    intensity: NDArray[np.float64],
    eps_flat: float = EPS_FLAT_DEFAULT,
    rise_delta: float = RISE_DELTA_DEFAULT,
) -> dict[str, Any]:
    """Classify trajectory as continuous or discontinuous."""
    result: dict[str, Any] = {}
    if len(time_s) < 3:
        result["classification"] = np.nan
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


def _append_sum_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Append monomer_sum and cluster_sum rows to dataframe."""
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


def pfo_fit(df_cumulative_peak_area: pd.DataFrame) -> pd.DataFrame | None:
    """Fit PFO kinetics for cumulative peak area trajectories."""
    df = df_cumulative_peak_area.copy()
    df["Time (s)"] = pd.to_numeric(df["Time (s)"], errors="coerce")
    df["Cumulative_Peak_Area"] = pd.to_numeric(
        df["Cumulative_Peak_Area"], errors="coerce"
    )
    df = df.dropna(subset=["Time (s)", "Cumulative_Peak_Area"])
    df = _append_sum_rows(df)

    records: list[dict[str, float | str]] = []
    sum_names = ["cluster_sum"]

    for group_key, group in df.groupby("Peak_Name"):
        group = group.sort_values("Time (s)").reset_index(drop=True)
        peak_name = group_key[0] if isinstance(group_key, tuple) else group_key

        classification_value: float | str = np.nan
        breakpoint_used_value: float | str = np.nan
        classification: dict[str, Any] = {}
        if peak_name in sum_names and len(group) >= 4:
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

        if len(group) < 4:
            continue

        unique_times = sorted(group["Time (s)"].unique())
        for unique_time in unique_times:
            mask = group["Time (s)"] <= unique_time
            time_s = group.loc[mask, "Time (s)"].to_numpy(dtype=float)
            intensity = group.loc[mask, "Cumulative_Peak_Area"].to_numpy(dtype=float)

            if len(time_s) < 4:
                continue

            current_row = group[group["Time (s)"] == unique_time].iloc[0]
            popt, std_errors, r_squared, rmse = fit_and_evaluate(time_s, intensity)

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

            param_keys = [
                ("pfo_ka_s-1", "pfo_ka_stderr"),
                ("pfo_kd_s-1", "pfo_kd_stderr"),
                ("pfo_qe_au", "pfo_qe_au_stderr"),
                ("pfo_Keq_au", "pfo_Keq_au_stderr"),
                ("pfo_q0_au", "pfo_q0_au_stderr"),
            ]
            for (value_key, stderr_key), value, stderr in zip(
                param_keys, popt, std_errors, strict=True
            ):
                record[value_key] = float(value) if np.isfinite(value) else np.nan
                record[stderr_key] = float(stderr) if np.isfinite(stderr) else np.nan

            records.append(record)

    if not records:
        return None

    df_fit_results = pd.DataFrame(records)

    df_merged = pd.merge(
        df_cumulative_peak_area,
        df_fit_results,
        on=["Peak_Name", "Time (s)"],
        how="left",
    )

    return df_merged


def append_pfo_fit_results(
    df_cumulative_peak_area: pd.DataFrame,
) -> pd.DataFrame:
    """Safely append PFO fit results to cumulative peak areas."""
    if df_cumulative_peak_area.empty:
        return df_cumulative_peak_area
    pfo_columns = {
        "pfo_ka_s-1",
        "pfo_ka_stderr",
        "pfo_kd_s-1",
        "pfo_kd_stderr",
        "pfo_qe_au",
        "pfo_qe_au_stderr",
        "pfo_Keq_au",
        "pfo_Keq_au_stderr",
        "pfo_q0_au",
        "pfo_q0_au_stderr",
        "pfo_r^2",
        "pfo_rmse",
        "classification",
        "growth_onset_s",
    }
    if pfo_columns.intersection(df_cumulative_peak_area.columns):
        return df_cumulative_peak_area
    try:
        df_peak_area_output = pfo_fit(df_cumulative_peak_area)
    except Exception as exc:
        LOGGER.warning("An error occurred during pfo_fit: %s", exc)
        return df_cumulative_peak_area
    return (
        df_cumulative_peak_area if df_peak_area_output is None else df_peak_area_output
    )


def calibration_statistics(
    calibration_peak_area: NDArray[np.float64] | pd.Series,
    calibration_moles: NDArray[np.float64] | pd.Series,
    peak_area_mole_carbonyl_slope: float | NDArray[np.float64],
    pcov: NDArray[np.float64],
) -> tuple[float | None, float]:
    """Compute calibration standard error of estimate and r-squared."""
    if calibration_peak_area is None or len(calibration_peak_area) < 2:
        return None, np.nan
    y_pred = linfunc_no_intercept(
        calibration_peak_area,
        cast(float | NDArray[np.float64], peak_area_mole_carbonyl_slope),
    )
    residuals = calibration_moles - y_pred
    see = np.sqrt(np.mean(residuals**2))
    ss_tot = np.sum(calibration_moles**2)
    ss_res = np.sum(residuals**2)
    r_squared = 1 - (ss_res / ss_tot)

    return see, r_squared


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
