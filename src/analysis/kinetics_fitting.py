"""Kinetics fitting helpers for peak area analysis."""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from threading import Thread
from typing import Any, Callable, cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy.integrate import solve_ivp
from scipy.optimize import OptimizeWarning, curve_fit, minimize

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
    "pfo_k_s-1",
    "pfo_q_e_au",
    "pfo_q0_au",
]
SECONDARY_PFO_PARAMS = [
    "pfo-sec_k_a_s-1",
    "pfo-sec_q_e_au",
    "pfo-sec_k_s_s-1",
    "pfo-sec_k_p_s-1",
    "pfo-sec_q_inf_au",
    "pfo-sec_q0_au",
]


@dataclass
class PfoFitResult:
    """Structured PFO fit result for a single time point."""

    peak_name: str
    time_s: float
    k_s_1: float
    k_stderr: float
    q_e_au: float
    q_e_stderr: float
    q0_au: float
    r_squared: float
    rmse: float
    classification: str
    growth_onset_s: float | None

    def to_dict(self) -> dict[str, Any]:
        """Return a dict with legacy column names."""
        return {
            "Peak_Name": self.peak_name,
            "Time (s)": self.time_s,
            "pfo_k_s-1": self.k_s_1,
            "pfo_k_stderr": self.k_stderr,
            "pfo_q_e_au": self.q_e_au,
            "pfo_q_e_stderr": self.q_e_stderr,
            "pfo_q0_au": self.q0_au,
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
    k: float,
    q_e: float,
    q_0: float,
) -> NDArray[np.float64]:
    """True pseudo-first-order uptake with fixed offset."""
    return q_0 + q_e * (1.0 - np.exp(-k * time_s))


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
    q_guess = float(np.max(intensity)) if intensity.size else 0.0
    q_0_fixed = float(intensity[0]) if intensity.size else 0.0

    if p0 is None:
        p0_fit = [1e-4, max(q_guess, 0.0)]
    elif len(p0) == 2:
        p0_fit = [float(p0[0]), float(p0[1])]
    elif len(p0) == 3:
        p0_fit = [float(p0[0]), float(p0[1])]
        q_0_fixed = float(p0[2])
    else:
        raise ValueError("pfo p0 must contain 2 or 3 values")

    bounds = ([0.0, 0.0], [0.01, q_guess * 2])

    p0_fit = [
        float(np.clip(value, low, high))
        for value, low, high in zip(p0_fit, bounds[0], bounds[1], strict=True)
    ]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", OptimizeWarning)
        try:
            with np.errstate(
                divide="ignore", invalid="ignore", over="ignore", under="ignore"
            ):
                popt, pcov = curve_fit(
                    lambda t, k, q_e: pfo(t, k, q_e, q_0_fixed),
                    time_s,
                    intensity,
                    p0=p0_fit,
                    bounds=bounds,
                    maxfev=20000,
                )
                y_pred = pfo(time_s, popt[0], popt[1], q_0_fixed)
                r_squared, rmse, _ = calculate_metrics(intensity, y_pred)
                std_errors = np.sqrt(np.diag(pcov))
                popt_full = np.array([popt[0], popt[1], q_0_fixed], dtype=float)
                std_errors_full = np.array(
                    [std_errors[0], std_errors[1], np.nan], dtype=float
                )
                return popt_full, std_errors_full, r_squared, rmse
        except Exception as exc:
            LOGGER.warning("PFO fit failed: %s", exc)

    popt_length = len(PFO_PARAMS)
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


def coupled_pfo_odes(
    t: float,
    y: list[float],
    k_a: float,
    q_e: float,
    k_s: float,
    k_p: float,
    q_inf: float,
) -> list[float]:
    """Coupled ODE system for secondary PFO model."""
    q, p = y
    dq = k_a * (q_e - q) - k_s * p
    dp = k_p * (q - q_inf - p)
    return [dq, dp]


def pfo_with_secondary_states(
    time_s: NDArray[np.float64],
    k_a: float,
    q_e: float,
    k_s: float,
    k_p: float,
    q_inf: float,
    q_0: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64]] | None:
    """Return q(t) and p(t) for secondary PFO model."""
    _, unique_indices = np.unique(time_s, return_index=True)
    time_s_unique = np.sort(time_s[unique_indices])

    result_container: dict[str, Any] = {"sol": None, "error": None}

    def solve_ode() -> None:
        try:
            result_container["sol"] = solve_ivp(
                coupled_pfo_odes,
                t_span=(time_s_unique[0], time_s_unique[-1]),
                y0=[q_0, 0.0],
                args=(k_a, q_e, k_s, k_p, q_inf),
                t_eval=time_s_unique,
                method="RK45",
                rtol=1e-8,
            )
        except Exception as exc:
            result_container["error"] = exc

    thread = Thread(target=solve_ode)
    thread.start()
    thread.join(timeout=0.1)

    if thread.is_alive():
        LOGGER.warning("Secondary PFO solve_ivp timed out")
        return None

    if result_container["error"] is not None:
        return None

    sol = result_container["sol"]
    if sol is None or not sol.success:
        return None

    q_unique = cast(NDArray[np.float64], sol.y[0])
    p_unique = cast(NDArray[np.float64], sol.y[1])

    interp_q = np.interp(time_s, time_s_unique, q_unique)
    interp_p = np.interp(time_s, time_s_unique, p_unique)
    return interp_q, interp_p


def fit_secondary_pfo_with_errors(
    time_s: NDArray[np.float64],
    intensity: NDArray[np.float64],
    p0: list[float] | None = None,
) -> tuple[NDArray[np.float64], NDArray[np.float64], float, float]:
    """Fit secondary PFO model and return parameters, errors, and diagnostics."""
    q_0_fixed = float(intensity[0]) if intensity.size else 0.0
    q_guess = float(np.max(intensity)) if intensity.size else 0.0

    if p0 is None:
        p0 = [3e-4, q_guess, 5e-5, 0.5, 0.0]
    if len(p0) != 5:
        raise ValueError("secondary_pfo p0 must have exactly 5 values")

    bounds = [
        (0.0, 0.01),
        (0.0, q_guess * 2),
        (0.0, 0.01),
        (0.0, 1.0),
        (0.0, q_guess * 2),
    ]

    p0 = [
        float(np.clip(value, low, high))
        for value, (low, high) in zip(p0, bounds, strict=True)
    ]

    def objective(params: NDArray[np.float64]) -> float:
        k_a, q_e, k_s, k_p_ratio, q_inf = params
        k_p = k_a * k_p_ratio
        states = pfo_with_secondary_states(time_s, k_a, q_e, k_s, k_p, q_inf, q_0_fixed)
        if states is None:
            return np.inf
        q_fit, p_fit = states
        if np.any(~np.isfinite(q_fit)) or np.any(~np.isfinite(p_fit)):
            return np.inf
        residuals = intensity - q_fit
        return float(np.sum(residuals**2))

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", OptimizeWarning)
        try:
            result = minimize(
                objective,
                x0=np.array(p0, dtype=float),
                bounds=bounds,
                method="L-BFGS-B",
            )
        except Exception as exc:
            LOGGER.debug("Secondary PFO minimization failed: %s", exc)
            result = None

    if result is not None and result.success:
        k_a_fit, q_e_fit, k_s_fit, k_p_ratio, q_inf_fit = result.x
        k_p_fit = k_a_fit * k_p_ratio
        states = pfo_with_secondary_states(
            time_s, k_a_fit, q_e_fit, k_s_fit, k_p_fit, q_inf_fit, q_0_fixed
        )
        if states is None:
            popt_length = len(p0) + 1
            return (
                np.full(popt_length, np.nan),
                np.full(popt_length, np.nan),
                np.nan,
                np.nan,
            )
        q_fit, _ = states
        r_squared, rmse, _ = calculate_metrics(intensity, q_fit)
        popt_full = np.array(
            [k_a_fit, q_e_fit, k_s_fit, k_p_fit, q_inf_fit, q_0_fixed],
            dtype=float,
        )
        std_errors_full = np.full_like(popt_full, np.nan, dtype=float)
        return popt_full, std_errors_full, r_squared, rmse

    popt_length = len(p0) + 1
    return (
        np.full(popt_length, np.nan),
        np.full(popt_length, np.nan),
        np.nan,
        np.nan,
    )


def _prepare_pfo_fit_rows(
    df: pd.DataFrame,
    *,
    peak_names: list[str] | None = None,
    min_points: int = 4,
    latest_only: bool = True,
) -> pd.DataFrame:
    records: list[dict[str, float | str]] = []
    sum_names = ["cluster_sum"]

    if peak_names is not None:
        df = df.loc[df["Peak_Name"].isin(peak_names)].copy()

    for group_key, group in df.groupby("Peak_Name"):
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

        if len(group) < min_points:
            continue

        unique_times = sorted(group["Time (s)"].unique())
        fit_times = [unique_times[-1]] if latest_only else unique_times

        for t in fit_times:
            # Use all data up to time t for fitting
            mask = group["Time (s)"] <= t
            time_s = group.loc[mask, "Time (s)"].to_numpy(dtype=float)
            intensity = group.loc[mask, "Cumulative_Peak_Area"].to_numpy(dtype=float)

            if len(time_s) < min_points:
                continue

            current_row = group[group["Time (s)"] == t].iloc[0]
            popt, std_errors, r_squared, rmse = fit_and_evaluate(time_s, intensity)

            record: dict[str, float | str] = {
                "Peak_Name": str(current_row["Peak_Name"]),
                "Time (s)": float(t),
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
                ("pfo_k_s-1", "pfo_k_stderr"),
                ("pfo_q_e_au", "pfo_q_e_stderr"),
                ("pfo_q0_au", None),
            ]
            for (value_key, stderr_key), value, stderr in zip(
                param_keys, popt, std_errors, strict=True
            ):
                record[value_key] = float(value) if np.isfinite(value) else np.nan
                if stderr_key is not None:
                    record[stderr_key] = (
                        float(stderr) if np.isfinite(stderr) else np.nan
                    )

            records.append(record)

    return pd.DataFrame(records) if records else pd.DataFrame()


def _prepare_secondary_fit_rows(
    df: pd.DataFrame,
    *,
    peak_names: list[str] | None = None,
    min_points: int = 4,
    p0: list[float] | None = None,
    latest_only: bool = True,
) -> pd.DataFrame:
    records: list[dict[str, float | str]] = []
    if peak_names is not None:
        df = df.loc[df["Peak_Name"].isin(peak_names)].copy()

    for group_key, group in df.groupby("Peak_Name"):
        group = group.sort_values("Time (s)").reset_index(drop=True)
        if len(group) < min_points:
            continue

        unique_times = sorted(group["Time (s)"].unique())
        fit_times = [unique_times[-1]] if latest_only else unique_times

        for t in fit_times:
            # Use all data up to time t for fitting
            mask = group["Time (s)"] <= t
            time_s = group.loc[mask, "Time (s)"].to_numpy(dtype=float)
            intensity = group.loc[mask, "Cumulative_Peak_Area"].to_numpy(dtype=float)

            if len(time_s) < min_points:
                continue

            current_row = group[group["Time (s)"] == t].iloc[0]
            effective_p0 = _select_secondary_p0(
                time_s,
                intensity,
                threshold_r2=0.96,
                user_p0=p0,
                min_points=min_points,
            )
            popt, std_errors, r_squared, rmse = fit_secondary_pfo_with_errors(
                time_s,
                intensity,
                effective_p0,
            )

            record: dict[str, float | str] = {
                "Peak_Name": str(current_row["Peak_Name"]),
                "Time (s)": float(t),
                "pfo-sec_r^2": r_squared,
                "pfo-sec_rmse": rmse,
            }

            param_keys = [
                ("pfo-sec_k_a_s-1", "pfo-sec_k_a_stderr"),
                ("pfo-sec_q_e_au", "pfo-sec_q_e_stderr"),
                ("pfo-sec_k_s_s-1", "pfo-sec_k_s_stderr"),
                ("pfo-sec_k_p_s-1", "pfo-sec_k_p_stderr"),
                ("pfo-sec_q_inf_au", "pfo-sec_q_inf_stderr"),
                ("pfo-sec_q0_au", None),
            ]
            for (value_key, stderr_key), value, stderr in zip(
                param_keys, popt, std_errors, strict=True
            ):
                record[value_key] = float(value) if np.isfinite(value) else np.nan
                if stderr_key is not None:
                    record[stderr_key] = (
                        float(stderr) if np.isfinite(stderr) else np.nan
                    )

            records.append(record)

    return pd.DataFrame(records) if records else pd.DataFrame()


def append_fit_results(
    df_cumulative_peak_area: pd.DataFrame,
    df_prior_kinetics: pd.DataFrame | None = None,
    *,
    latest_only: bool = True,
) -> pd.DataFrame:
    """Append kinetics fit results to cumulative peak areas.

    Parameters
    ----------
    df_cumulative_peak_area : pd.DataFrame
        Fresh cumulative peak areas (no kinetics columns).
    df_prior_kinetics : pd.DataFrame | None
        Previously saved CarbonylPeakArea data containing kinetics
        columns from earlier runs.  When *latest_only* is True,
        kinetics rows are carried forward and only the latest time
        point is re-fitted.
    latest_only : bool
        If True (default, real-time mode), only the latest time point
        per peak group is fitted; prior kinetics results are carried
        forward.  If False (batch mode), every time point is fitted
        and *df_prior_kinetics* is ignored.
    """
    if df_cumulative_peak_area.empty:
        return df_cumulative_peak_area

    df = df_cumulative_peak_area.copy()
    df["Time (s)"] = pd.to_numeric(df["Time (s)"], errors="coerce")
    df["Cumulative_Peak_Area"] = pd.to_numeric(
        df["Cumulative_Peak_Area"], errors="coerce"
    )
    df = df.dropna(subset=["Time (s)", "Cumulative_Peak_Area"])
    df = _append_sum_rows(df)

    monomer_peak_names = [*_get_monomer_peak_names(isotope=None), "monomer_sum"]
    cluster_peak_names = [
        *_get_peak_names("cluster_peaks_base", isotope=None),
        "cluster_sum",
    ]

    overlap = set(monomer_peak_names) & set(cluster_peak_names)
    if overlap:
        raise ValueError(
            "Monomer/cluster peak sets overlap in config: " + ", ".join(sorted(overlap))
        )

    try:
        monomer_rows = _prepare_secondary_fit_rows(
            df, peak_names=monomer_peak_names, latest_only=latest_only
        )
        cluster_rows = _prepare_pfo_fit_rows(
            df, peak_names=cluster_peak_names, latest_only=latest_only
        )
    except Exception as exc:
        LOGGER.warning("An error occurred during kinetics fitting: %s", exc)
        return df_cumulative_peak_area

    frames = [frame for frame in [monomer_rows, cluster_rows] if not frame.empty]
    if not frames:
        return df_cumulative_peak_area

    df_new_fit = pd.concat(frames, ignore_index=True)

    # Merge prior kinetics rows with new fit rows
    if df_prior_kinetics is not None and not df_prior_kinetics.empty:
        # Extract kinetics-only columns from prior results
        kinetics_cols = [
            c
            for c in df_prior_kinetics.columns
            if c not in df_cumulative_peak_area.columns
        ]
        if kinetics_cols:
            merge_cols = ["Peak_Name", "Time (s)"]
            df_prior_fit = df_prior_kinetics[merge_cols + kinetics_cols].copy()
            # Prior CSV can have duplicate (Peak_Name, Time) keys
            # when multiple Delta_Groups share the same cumulative
            # time.  Collapse them so the final merge stays 1-to-1.
            df_prior_fit = df_prior_fit.drop_duplicates(subset=merge_cols, keep="last")
            # Remove rows that will be replaced by new fit results
            new_keys = df_new_fit[merge_cols]
            df_prior_fit = df_prior_fit.merge(
                new_keys, on=merge_cols, how="left", indicator=True
            )
            df_prior_fit = df_prior_fit[df_prior_fit["_merge"] == "left_only"].drop(
                columns=["_merge"]
            )
            df_new_fit = pd.concat([df_prior_fit, df_new_fit], ignore_index=True)

    # Ensure unique keys on right side to prevent many-to-many join
    df_new_fit = df_new_fit.drop_duplicates(
        subset=["Peak_Name", "Time (s)"], keep="last"
    )
    df_merged = pd.merge(
        df_cumulative_peak_area,
        df_new_fit,
        on=["Peak_Name", "Time (s)"],
        how="left",
    )
    return df_merged


def _select_secondary_p0(
    time_s: NDArray[np.float64],
    intensity: NDArray[np.float64],
    *,
    threshold_r2: float = 0.96,
    user_p0: list[float] | None = None,
    min_points: int = 4,
) -> list[float]:
    """Select secondary p0 for the current trajectory slice."""
    if len(time_s) < min_points:
        return user_p0 if user_p0 is not None else [3e-4, 1.0, 5e-5, 0.5, 0.0]

    q_guess = float(np.max(intensity)) if intensity.size else 0.0
    default_p0 = [3e-4, q_guess, 5e-5, 0.5, 0.0]
    current = list(user_p0) if user_p0 is not None else list(default_p0)
    if len(current) != 5:
        current = list(default_p0)

    best_p0 = list(current)
    best_r2 = -np.inf

    def eval_r2(candidate: list[float]) -> float:
        _, _, r2, _ = fit_secondary_pfo_with_errors(time_s, intensity, candidate)
        return float(r2) if np.isfinite(r2) else -np.inf

    baseline_r2 = eval_r2(best_p0)
    if baseline_r2 > best_r2:
        best_r2 = baseline_r2
    if best_r2 >= threshold_r2:
        return best_p0

    search_steps: list[tuple[int, list[float]]] = [
        (0, [3e-5, 6e-4]),  # k_a
        (1, [q_guess / 2.0]),  # q_e
        (2, [9e-5, 1e-5]),  # k_s
        (3, [0.1, 1.0]),  # k_p_ratio
        (4, [0.5]),  # q_inf
    ]

    for param_idx, trial_values in search_steps:
        local_best_p0 = list(best_p0)
        local_best_r2 = best_r2

        for trial in trial_values:
            candidate = list(best_p0)
            candidate[param_idx] = float(trial)
            r2 = eval_r2(candidate)
            if r2 > local_best_r2:
                local_best_r2 = r2
                local_best_p0 = candidate

        best_p0 = local_best_p0
        best_r2 = local_best_r2
        if best_r2 >= threshold_r2:
            return best_p0

    return best_p0


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
