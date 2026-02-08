"""Kinetics fitting helpers for peak area analysis."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any, Callable, cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy.optimize import OptimizeWarning, curve_fit
from scipy.stats import t


@dataclass
class PfoFitResult:
    """Structured PFO fit result for a single time point."""

    peak_name: str
    time_s: float
    original_index: int
    ka_s_1: float
    ka_stderr: float
    kd_s_1: float
    kd_stderr: float
    qe_mol: float
    qe_stderr: float
    r_squared: float
    rmse: float

    def to_dict(self) -> dict[str, Any]:
        """Return a dict with legacy column names."""
        return {
            "Peak_Name": self.peak_name,
            "Time (s)": self.time_s,
            "original_index": self.original_index,
            "ka_s-1": self.ka_s_1,
            "ka_stderr": self.ka_stderr,
            "kd_s-1": self.kd_s_1,
            "kd_stderr": self.kd_stderr,
            "qe_mol": self.qe_mol,
            "qe_stderr": self.qe_stderr,
            "r^2": self.r_squared,
            "rmse": self.rmse,
        }


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


def pfo_decay(time_s: np.ndarray, k_a: float, k_d: float, qe: float) -> np.ndarray:
    """Pseudo-first-order decay model."""
    return (qe * (1 - np.exp(-k_a * time_s))) * np.exp(-k_d * time_s)


def calculate_metrics(
    intensity: np.ndarray,
    y_pred: np.ndarray,
) -> tuple[float, float]:
    """Compute r-squared and RMSE for a fit."""
    residuals = intensity - y_pred
    ss_tot = np.sum((intensity - np.mean(intensity)) ** 2)
    ss_res = np.sum(residuals**2)

    r_squared = 1 - (ss_res / ss_tot)
    rmse = np.sqrt(np.mean(residuals**2))

    return r_squared, rmse


def fit_and_evaluate(
    wavenumbers: NDArray[np.float64],
    intensity: NDArray[np.float64],
    func: Callable[..., NDArray[np.float64]],
    p0: list[float] | None = None,
) -> tuple[NDArray[np.float64], NDArray[np.float64], float, float]:
    """Fit a model and return parameters, errors, and diagnostics."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", OptimizeWarning)
        try:
            with np.errstate(
                divide="ignore", invalid="ignore", over="ignore", under="ignore"
            ):
                popt, pcov = curve_fit(
                    func, wavenumbers, intensity, p0=p0, bounds=(0, np.inf)
                )
                y_pred = func(wavenumbers, *popt)
                r_squared, rmse = calculate_metrics(intensity, y_pred)
                std_errors = np.sqrt(np.diag(pcov))
                return popt, std_errors, r_squared, rmse
        except Exception:
            if p0 is not None:
                popt_length = len(p0)
            else:
                popt_length = len(cast(Any, func).__code__.co_varnames) - 1
            return (
                np.full(popt_length, np.nan),
                np.full(popt_length, np.nan),
                np.nan,
                np.nan,
            )


def pfo_fit(df_cumulative_peak_area: pd.DataFrame) -> pd.DataFrame | None:
    """Fit PFO kinetics for cumulative peak area trajectories."""
    fit_result_frames = []
    df_cumulative_peak_area = df_cumulative_peak_area.sort_values(
        ["Peak_Name", "Time (s)"]
    ).reset_index(drop=True)
    df_cumulative_peak_area["original_index"] = df_cumulative_peak_area.groupby(
        "Peak_Name"
    ).cumcount()

    for peak_name, group in df_cumulative_peak_area.groupby("Peak_Name"):
        fit_results = []
        group = group.reset_index(drop=True)

        if len(group) < 5:
            df_cumulative_peak_area.drop("original_index", axis=1, inplace=True)
            return df_cumulative_peak_area

        for i in range(5, len(group)):
            time_s = np.array(group["Time (s)"].iloc[: i + 1])
            cumulative_peak_area = np.array(group["Cumulative_Peak_Area"].iloc[: i + 1])
            current_row = group.iloc[i]

            (
                popt_pfo_decay,
                std_errors_pfo_decay,
                r_squared_pfo_decay,
                rmse_pfo_decay,
            ) = fit_and_evaluate(
                time_s, cumulative_peak_area, pfo_decay, p0=[1e-4, 1e-6, 0.1]
            )

            ka_pfo_decay, kd_pfo_decay, q_pfo_decay = popt_pfo_decay
            ka_stderr_pfo_decay, kd_stderr_pfo_decay, q_stderr_pfo_decay = (
                std_errors_pfo_decay
            )

            fit_results.append(
                PfoFitResult(
                    peak_name=peak_name,
                    time_s=float(current_row["Time (s)"]),
                    original_index=int(current_row["original_index"]),
                    ka_s_1=ka_pfo_decay,
                    ka_stderr=ka_stderr_pfo_decay,
                    kd_s_1=kd_pfo_decay,
                    kd_stderr=kd_stderr_pfo_decay,
                    qe_mol=q_pfo_decay,
                    qe_stderr=q_stderr_pfo_decay,
                    r_squared=r_squared_pfo_decay,
                    rmse=rmse_pfo_decay,
                )
            )

        if fit_results:
            df = pd.DataFrame([result.to_dict() for result in fit_results])
            fit_result_frames.append(df)

    if fit_result_frames:
        df_pfo_fit_results = pd.concat(fit_result_frames, ignore_index=True)

        df_cpa_pfo = pd.merge(
            df_cumulative_peak_area,
            df_pfo_fit_results,
            on=["Peak_Name", "Time (s)", "original_index"],
            how="left",
        )

        df_cpa_pfo.drop("original_index", axis=1, inplace=True)
        df_cpa_pfo = df_cpa_pfo.sort_values(["Peak_Name", "Delta_Group"]).reset_index(
            drop=True
        )
        return df_cpa_pfo
    return None


def append_pfo_fit_results(
    df_cumulative_peak_area: pd.DataFrame,
) -> pd.DataFrame:
    """Safely append PFO fit results to cumulative peak areas."""
    if df_cumulative_peak_area.empty:
        return df_cumulative_peak_area
    try:
        df_peak_area_output = pfo_fit(df_cumulative_peak_area)
    except Exception as e:
        print(f"An error occurred during pfo_fit: {e}")
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
    std_errors = np.sqrt(np.diag(pcov))
    residuals = calibration_moles - y_pred
    see = np.sqrt(np.mean(residuals**2))
    ss_tot = np.sum(calibration_moles**2)
    ss_res = np.sum(residuals**2)
    r_squared = 1 - (ss_res / ss_tot)
    rmse = np.sqrt(np.mean(residuals**2))

    dof = len(calibration_peak_area) - 2
    confidence_level = 0.975
    t_critical = t.ppf(confidence_level, dof)

    pred_stderr = see * np.sqrt(
        1
        + 1 / len(calibration_peak_area)
        + (calibration_peak_area - np.mean(calibration_peak_area)) ** 2
        / np.sum((calibration_peak_area - np.mean(calibration_peak_area)) ** 2)
    )

    pred_interval = (
        t_critical
        * see
        * np.sqrt(
            1
            + 1 / len(calibration_peak_area)
            + (calibration_peak_area - np.mean(calibration_peak_area)) ** 2
            / np.sum((calibration_peak_area - np.mean(calibration_peak_area)) ** 2)
        )
    )

    y_pred_lower = y_pred - pred_interval
    y_pred_upper = y_pred + pred_interval

    return see, r_squared
