"""Kinetic models, peak-group sums and the nucleation label for live analysis.

Models (pfo, secondary_pfo, exp_decay) match the offline package
``src/utils/kinetics/models.py``; the segment fits that use them are in
``segments.py`` and the nucleation detector in ``classification.py``
(docs/spec-live-migration.md). A model change has to land on both sides.
"""

from __future__ import annotations

import logging
import warnings
from threading import Thread
from typing import Any, cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy.integrate import solve_ivp
from scipy.optimize import OptimizeWarning, curve_fit, minimize

from ..core import config
from .spectral_fitting import get_shifted_monomer_peaks

LOGGER = logging.getLogger(__name__)

CLASSIFICATION_COLUMNS = ["classification", "growth_onset_s", "latch_time_s"]
"""Written on ``cluster_sum`` rows of ``*_CarbonylPeakArea.csv``."""
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
                    # Offline's value (src/utils/kinetics/models.py): the
                    # reprocessed kinetics were fitted with it.
                    maxfev=500,
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


EXP_DECAY_PARAMS = ["exp_k_s-1", "exp_y_inf_au", "exp_y_b_au"]


def exp_decay(
    tau_s: NDArray[np.float64], k: float, y_inf: float, y_b: float
) -> NDArray[np.float64]:
    """Exponential relaxation to ``y_inf`` from ``y_b`` at ``tau_s = 0``."""
    return y_inf + (y_b - y_inf) * np.exp(-k * tau_s)


def fit_exp_decay_with_errors(
    time_s: NDArray[np.float64],
    intensity: NDArray[np.float64],
    p0: list[float] | None = None,
) -> tuple[NDArray[np.float64], NDArray[np.float64], float, float]:
    """Fit ``exp_decay`` on the segment's own clock (``tau = t - t[0]``).

    Copy of ``src/utils/kinetics/models.py::_ExpDecayModel``. ``y_b`` is fixed:
    ``p0[2]`` when given (the segments path passes the smoothed value there),
    else the first observed value. Only ``k`` and ``y_inf`` are fitted; a NaN
    ``p0[0]``/``p0[1]`` takes the default guess.
    """
    nan_result = (
        np.full(len(EXP_DECAY_PARAMS), np.nan),
        np.full(len(EXP_DECAY_PARAMS), np.nan),
        np.nan,
        np.nan,
    )
    if intensity.size < 3:
        return nan_result
    tau_s = time_s - time_s[0]
    y_b = float(intensity[0])
    if p0 is not None and len(p0) > 2 and np.isfinite(p0[2]):
        y_b = float(p0[2])
    span = float(np.ptp(intensity)) or 1.0
    bounds = (
        [0.0, float(np.min(intensity)) - span],
        [0.01, float(np.max(intensity)) + span],
    )
    duration = float(tau_s[-1]) or 1.0
    guess = [3.0 / duration, float(intensity[-1])]
    if p0 is not None:
        guess = [
            float(value) if np.isfinite(value) else default
            for value, default in zip(p0[:2], guess, strict=True)
        ]
    p0_fit = [
        float(np.clip(value, low, high))
        for value, low, high in zip(guess, bounds[0], bounds[1], strict=True)
    ]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", OptimizeWarning)
        try:
            with np.errstate(
                divide="ignore", invalid="ignore", over="ignore", under="ignore"
            ):
                popt, pcov = curve_fit(
                    lambda t, k, y_inf: exp_decay(t, k, y_inf, y_b),
                    tau_s,
                    intensity,
                    p0=p0_fit,
                    bounds=bounds,
                    maxfev=2000,
                )
                y_pred = exp_decay(tau_s, popt[0], popt[1], y_b)
                r_squared, rmse, _ = calculate_metrics(intensity, y_pred)
                std_errors = np.sqrt(np.diag(pcov))
                return (
                    np.array([popt[0], popt[1], y_b], dtype=float),
                    np.array([std_errors[0], std_errors[1], np.nan], dtype=float),
                    r_squared,
                    rmse,
                )
        except Exception as exc:
            LOGGER.warning("exp_decay fit failed: %s", exc)
    return nan_result


def classify_area_rows(
    df_cumulative_peak_area: pd.DataFrame,
    by_time: dict[float, dict[str, Any]],
) -> pd.DataFrame:
    """Left-join the causal nucleation label onto the ``cluster_sum`` rows.

    ``by_time`` is ``classification.classify_by_time`` of the same frame.
    The area rows are returned unchanged and in order; every
    :data:`CLASSIFICATION_COLUMNS` column is present, NaN on other rows.
    """
    df = df_cumulative_peak_area.copy()
    df["Time (s)"] = pd.to_numeric(df["Time (s)"], errors="coerce")
    labels = pd.DataFrame(
        [
            {"Peak_Name": "cluster_sum", "Time (s)": t, **payload}
            for t, payload in by_time.items()
        ],
        columns=["Peak_Name", "Time (s)", *CLASSIFICATION_COLUMNS],
    )
    df = df.drop(columns=[c for c in CLASSIFICATION_COLUMNS if c in df.columns])
    return df.merge(labels, on=["Peak_Name", "Time (s)"], how="left")


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
