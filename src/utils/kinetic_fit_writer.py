"""Utilities for fitting kinetics models and writing legacy outputs.

This module is organized into three categories:
1. Models: kinetic model equations and fitting routines
2. Classification: trajectory classification logic
3. Writer/Utilities: dataframe prep, row generation, and CSV writing
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
import sys
import warnings
from threading import Thread
from typing import Any, Callable, cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy.integrate import solve_ivp
from scipy.optimize import OptimizeWarning, curve_fit, minimize

path = Path(__file__).parent.parent.parent
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.analysis.spectral_fitting import get_shifted_monomer_peaks
from src.core import config


LOGGER = logging.getLogger(__name__)
SEARCH_ROOT = Path(config.get_path("data.peak_fit"))
AREA_SUFFIX = config.get_setting("filenames.carbonyl_fit.area_suffix")


# --- Config / constants ---
FLAT_WINDOW_S = 20000.0
MIN_FLAT_START_S = 10000.0
SMOOTHING_WINDOW = 4
EPS_FLAT_DEFAULT = 1e-6
RISE_DELTA_DEFAULT = 1.1e-1
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
class _FitResult:
    """Container for fit results."""

    model_name: str
    params: dict[str, float]
    r_squared: float
    rmse: float
    rss: float
    n_points: int


@dataclass
class _ModelRowSpec:
    """Specification for generic row preparation/writing by model."""

    model_key: str
    r2_col: str
    rmse_col: str
    param_map: list[tuple[str, str | None]]
    fit_fn: Callable[
        [NDArray[np.float64], NDArray[np.float64], list[float] | None],
        tuple[NDArray[np.float64], NDArray[np.float64], float, float],
    ]


@dataclass
class _ModelFitSpec:
    """Model strategy interface bundle for writer and classification."""

    model_key: str
    fit_with_errors: Callable[
        [NDArray[np.float64], NDArray[np.float64], list[float] | None],
        tuple[NDArray[np.float64], NDArray[np.float64], float, float],
    ]
    fit_result_fn: Callable[
        [NDArray[np.float64], NDArray[np.float64], list[float] | None],
        _FitResult | None,
    ]
    summarize_fn: (
        Callable[[NDArray[np.float64], NDArray[np.float64]], dict[str, Any]] | None
    )


class _KineticUtilities:
    """Dataframe and output utilities."""

    @staticmethod
    def calculate_metrics(
        intensity: NDArray[np.float64],
        y_pred: NDArray[np.float64],
    ) -> tuple[float, float, float]:
        residuals = intensity - y_pred
        ss_tot = np.sum((intensity - np.mean(intensity)) ** 2)
        rss = np.sum(residuals**2)
        r_squared = 1 - (rss / ss_tot) if ss_tot > 0 else np.nan
        rmse = np.sqrt(np.mean(residuals**2))
        return r_squared, rmse, rss

    @staticmethod
    def prefix_fit_results(fit_result: dict[str, Any], prefix: str) -> dict[str, Any]:
        return {f"{prefix}{k}": v for k, v in fit_result.items() if k not in {"rmse"}}

    @staticmethod
    def get_peak_names(base_list_key: str, isotope: str | None) -> list[str]:
        config_settings = config.get_analysis_setting("voigt_fit")
        base_list = config_settings.get(base_list_key, [])
        if not base_list:
            return []
        isotope_value = isotope or config_settings.get("isotope_default", "13CO")
        base_isotope = config_settings.get("monomer_peaks_base_isotope", isotope_value)
        shifts = config_settings.get("isotope_shift_cm1", {})
        shift_value = shifts.get(isotope_value, 0) - shifts.get(base_isotope, 0)
        return [f"Peak_{int(peak + shift_value)}" for peak in base_list]

    @staticmethod
    def get_monomer_peak_names(isotope: str | None) -> list[str]:
        config_settings = config.get_analysis_setting("voigt_fit")
        isotope_value = isotope or config_settings.get("isotope_default", "13CO")
        merged_settings = dict(config_settings)
        merged_settings["isotope_default"] = isotope_value
        return [
            f"Peak_{int(peak)}" for peak in get_shifted_monomer_peaks(merged_settings)
        ]

    def build_cluster_sum(
        self, df: pd.DataFrame, isotope: str | None = None
    ) -> pd.DataFrame:
        df = df.copy()
        df["Time (s)"] = pd.to_numeric(df["Time (s)"], errors="coerce")
        df["Cumulative_Peak_Area"] = pd.to_numeric(
            df["Cumulative_Peak_Area"], errors="coerce"
        )
        df = df.dropna(subset=["Time (s)", "Cumulative_Peak_Area"])

        cluster_rows = df[
            df["Peak_Name"].isin(self.get_peak_names("cluster_peaks_base", isotope))
        ]
        if cluster_rows.empty:
            return pd.DataFrame()

        group_cols = ["Time (s)"]
        if "Delta_Group" in cluster_rows.columns:
            group_cols.append("Delta_Group")
        if "File" in cluster_rows.columns:
            group_cols.append("File")
        return (
            cluster_rows.groupby(group_cols)["Cumulative_Peak_Area"].sum().reset_index()
        )

    def build_monomer_sum(
        self, df: pd.DataFrame, isotope: str | None = None
    ) -> pd.DataFrame:
        df = df.copy()
        df["Time (s)"] = pd.to_numeric(df["Time (s)"], errors="coerce")
        df["Cumulative_Peak_Area"] = pd.to_numeric(
            df["Cumulative_Peak_Area"], errors="coerce"
        )
        df = df.dropna(subset=["Time (s)", "Cumulative_Peak_Area"])

        monomer_rows = df[df["Peak_Name"].isin(self.get_monomer_peak_names(isotope))]
        if monomer_rows.empty:
            return pd.DataFrame()

        group_cols = ["Time (s)"]
        if "Delta_Group" in monomer_rows.columns:
            group_cols.append("Delta_Group")
        if "File" in monomer_rows.columns:
            group_cols.append("File")
        return (
            monomer_rows.groupby(group_cols)["Cumulative_Peak_Area"].sum().reset_index()
        )

    def append_sum_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        sum_builders = {
            "monomer_sum": self.build_monomer_sum,
            "cluster_sum": self.build_cluster_sum,
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

    def prepare_peak_area_df(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["Time (s)"] = pd.to_numeric(df["Time (s)"], errors="coerce")
        df["Cumulative_Peak_Area"] = pd.to_numeric(
            df["Cumulative_Peak_Area"], errors="coerce"
        )
        df = df.dropna(subset=["Time (s)", "Cumulative_Peak_Area"])
        return self.append_sum_rows(df)

    @staticmethod
    def write_fit_params_to_legacy(
        legacy_path: str | Path,
        fit_params: pd.DataFrame,
        *,
        join_columns: tuple[str, ...] = ("Peak_Name", "Time (s)"),
        output_folder_name: str = "_test",
        legacy_df: pd.DataFrame | None = None,
    ) -> Path:
        legacy_path = Path(legacy_path)
        df_legacy = pd.read_csv(legacy_path) if legacy_df is None else legacy_df.copy()

        # Remove legacy PFO columns that should not persist in new outputs.
        legacy_pfo_columns = [
            "pfo_ka_s-1",
            "pfo_ka_stderr",
            "pfo_kd_s-1",
            "pfo_kd_stderr",
            "pfo_qe_au",
            "pfo_qe_au_stderr",
            "pfo_qe_stderr",
            "pfo_Keq_au",
            "pfo_Keq_au_stderr",
            "pfo_q0_au_stderr",
        ]
        if legacy_pfo_columns:
            df_legacy = df_legacy.drop(columns=legacy_pfo_columns, errors="ignore")

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

    @staticmethod
    def drop_columns_with_prefixes(
        df: pd.DataFrame,
        prefixes: tuple[str, ...],
    ) -> tuple[pd.DataFrame, list[str]]:
        """Drop columns whose names start with any prefix.

        Returns a tuple of (cleaned_df, dropped_columns).
        """
        if not prefixes:
            return df.copy(), []
        dropped = [
            column
            for column in df.columns
            if any(column.startswith(prefix) for prefix in prefixes)
        ]
        if not dropped:
            return df.copy(), []
        return df.drop(columns=dropped, errors="ignore"), dropped

    @staticmethod
    def write_plain_legacy_output(
        legacy_path: str | Path,
        output_df: pd.DataFrame,
        *,
        output_folder_name: str = "_test",
    ) -> Path:
        """Write a plain legacy CSV (no merge), preserving file name."""
        legacy_path = Path(legacy_path)
        output_dir = (
            legacy_path.parent
            if legacy_path.parent.name == output_folder_name
            else legacy_path.parent / output_folder_name
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / legacy_path.name
        output_df.to_csv(output_path, index=False)
        return output_path


class _ODESolverHelper:
    """Shared ODE solving/interpolation helper for model strategies."""

    @staticmethod
    def linear_interp_with_extrapolation(
        x: NDArray[np.float64],
        y: NDArray[np.float64],
        x_new: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        if x.size == 0:
            return np.full_like(x_new, np.nan, dtype=float)
        if x.size == 1:
            return np.full_like(x_new, float(y[0]), dtype=float)

        y_new = np.interp(x_new, x, y)

        left_mask = x_new < x[0]
        if np.any(left_mask):
            left_slope = (y[1] - y[0]) / (x[1] - x[0]) if x[1] != x[0] else 0.0
            y_new[left_mask] = y[0] + left_slope * (x_new[left_mask] - x[0])

        right_mask = x_new > x[-1]
        if np.any(right_mask):
            right_slope = (y[-1] - y[-2]) / (x[-1] - x[-2]) if x[-1] != x[-2] else 0.0
            y_new[right_mask] = y[-1] + right_slope * (x_new[right_mask] - x[-1])

        return y_new


class _PFOModel:
    """Standard PFO model strategy."""

    def __init__(self, utils: _KineticUtilities) -> None:
        self.utils = utils

    @staticmethod
    def pfo(
        time_s: NDArray[np.float64],
        k: float,
        q_e: float,
        q_0: float,
    ) -> NDArray[np.float64]:
        return q_0 + q_e * (1.0 - np.exp(-k * time_s))

    def fit_with_errors(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        p0: list[float] | None = None,
    ) -> tuple[NDArray[np.float64], NDArray[np.float64], float, float]:
        q_guess = float(np.max(intensity)) if intensity.size else 0.0
        q_floor = max(q_guess, 0.0)
        q_0_fixed = float(intensity[0]) if intensity.size else 0.0

        if p0 is None:
            p0_fit = [1e-4, q_floor]
        elif len(p0) == 2:
            p0_fit = [float(p0[0]), float(p0[1])]
        elif len(p0) == 3:
            p0_fit = [float(p0[0]), float(p0[1])]
            q_0_fixed = float(p0[2])
        elif len(p0) == 5:
            p0_fit = [float(p0[0]), float(p0[2])]
            q_0_fixed = float(p0[4])
        else:
            raise ValueError("pfo p0 must contain 2, 3, or 5 values")

        bounds = (
            [0.0, 0.0],
            [0.01, q_guess * 2],
        )

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
                        lambda t, k, q_e: self.pfo(t, k, q_e, q_0_fixed),
                        time_s,
                        intensity,
                        p0=p0_fit,
                        bounds=bounds,
                        maxfev=500,
                    )
                    y_pred = self.pfo(time_s, popt[0], popt[1], q_0_fixed)
                    r_squared, rmse, _ = self.utils.calculate_metrics(intensity, y_pred)
                    std_errors_fit = np.sqrt(np.diag(pcov))

                    popt_full = np.array([popt[0], popt[1], q_0_fixed], dtype=float)
                    std_errors_full = np.array(
                        [std_errors_fit[0], std_errors_fit[1], np.nan],
                        dtype=float,
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

    def summarize(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
    ) -> dict[str, Any]:
        if len(time_s) < 3:
            result: dict[str, Any] = {"r2": np.nan, "rmse": np.nan}
            for name in PFO_PARAMS:
                result[name] = np.nan
            return result

        popt, _, r_squared, rmse = self.fit_with_errors(time_s, intensity)
        result = {"r2": r_squared, "rmse": rmse}
        for name, value in zip(PFO_PARAMS, popt):
            result[name] = value
        return result

    def fit_result(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        p0: list[float] | None = None,
    ) -> _FitResult | None:
        popt, _, _, _ = self.fit_with_errors(time_s, intensity, p0=p0)
        if not np.all(np.isfinite(popt[[0, 1, 2]])):
            return None
        y_pred = self.pfo(time_s, popt[0], popt[1], popt[2])
        r_squared, rmse, rss = self.utils.calculate_metrics(intensity, y_pred)
        params = {
            "k": float(popt[0]),
            "q_e": float(popt[1]),
            "q_0": float(popt[2]),
        }
        return _FitResult("pfo", params, r_squared, rmse, rss, len(time_s))


class _SecondaryPFOModel:
    """Secondary coupled-ODE PFO model strategy."""

    def __init__(
        self, utils: _KineticUtilities, solver_helper: _ODESolverHelper
    ) -> None:
        self.utils = utils
        self.solver_helper = solver_helper

    @staticmethod
    def coupled_pfo_odes(
        t: float,
        y: list[float],
        k_a: float,
        q_e: float,
        k_s: float,
        k_p: float,
        q_inf: float,
    ) -> list[float]:
        q, p = y
        dq = k_a * (q_e - q) - k_s * p
        dp = k_p * (q - q_inf - p)
        return [dq, dp]

    def states(
        self,
        time_s: NDArray[np.float64],
        k_a: float,
        q_e: float,
        k_s: float,
        k_p: float,
        q_inf: float,
        q_0: float,
        timeout_seconds: float = 5.0,
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]] | None:
        if time_s.size == 0:
            return None

        _, unique_indices = np.unique(time_s, return_index=True)
        time_s_unique = np.sort(time_s[unique_indices])

        result_container: dict[str, Any] = {"sol": None, "error": None}

        def solve_ode() -> None:
            try:
                result_container["sol"] = solve_ivp(
                    self.coupled_pfo_odes,
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
        thread.join(timeout=timeout_seconds)

        if thread.is_alive():
            LOGGER.warning(
                "Secondary PFO solve_ivp timed out after %s seconds", timeout_seconds
            )
            return None

        if result_container["error"] is not None:
            return None

        sol = result_container["sol"]
        if sol is None or not sol.success:
            LOGGER.warning(
                "Secondary PFO solve_ivp failed: %s",
                sol.message if sol is not None else "No solution",
            )
            return None

        q_unique = cast(NDArray[np.float64], sol.y[0])
        p_unique = cast(NDArray[np.float64], sol.y[1])
        q = self.solver_helper.linear_interp_with_extrapolation(
            time_s_unique, q_unique, time_s
        )
        p = self.solver_helper.linear_interp_with_extrapolation(
            time_s_unique, p_unique, time_s
        )
        return q, p

    def fit_with_errors(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        p0: list[float] | None = None,
        timeout_seconds: float = 0.1,
    ) -> tuple[NDArray[np.float64], NDArray[np.float64], float, float]:
        q_0_fixed = float(intensity[0]) if intensity.size else 0.0

        def integrate_secondary(
            params: NDArray[np.float64],
        ) -> tuple[NDArray[np.float64], NDArray[np.float64]] | None:
            k_a, q_e, k_s, k_p_ratio, q_inf = params
            k_p = k_a * k_p_ratio
            return self.states(
                time_s,
                k_a,
                q_e,
                k_s,
                k_p,
                q_inf,
                q_0_fixed,
                timeout_seconds=timeout_seconds,
            )

        def objective(params: NDArray[np.float64]) -> float:
            states = integrate_secondary(params)
            if states is None:
                return np.inf
            q, p = states
            if np.any(~np.isfinite(q)) or np.any(~np.isfinite(p)):
                return np.inf
            residuals = intensity - q
            return float(np.sum(residuals**2))

        q_guess = float(np.max(intensity)) if intensity.size else 0.0

        if p0 is None:
            p0 = [
                3e-4,  # k_a
                q_guess,  # q_e
                5e-5,  # k_s
                0.5,  # k_p_ratio
                0.0,  # q_inf
            ]

        bounds = [
            (0.0, 0.01),
            (0.0, q_guess * 2),
            (0.0, 0.01),
            (0.0, 1.0),
            (0.0, q_guess * 2),
        ]

        # Ensure initial guess is valid for bounded optimizer
        if len(p0) != 5:
            raise ValueError("secondary_pfo p0 must have exactly 5 values")
        p0 = [
            float(np.clip(value, low, high))
            for value, (low, high) in zip(p0, bounds, strict=True)
        ]

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
            states_fit = self.states(
                time_s,
                k_a_fit,
                q_e_fit,
                k_s_fit,
                k_p_fit,
                q_inf_fit,
                q_0_fixed,
                timeout_seconds=timeout_seconds,
            )
            if states_fit is None:
                popt_length = len(p0) + 1
                return (
                    np.full(popt_length, np.nan),
                    np.full(popt_length, np.nan),
                    np.nan,
                    np.nan,
                )
            y_pred, _ = states_fit
            r_squared, rmse, _ = self.utils.calculate_metrics(intensity, y_pred)
            popt_full = np.array(
                [k_a_fit, q_e_fit, k_s_fit, k_p_fit, q_inf_fit, q_0_fixed], dtype=float
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

    def fit_result(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        p0: list[float] | None = None,
    ) -> _FitResult | None:
        popt, _, _, _ = self.fit_with_errors(time_s, intensity, p0=p0)
        if not np.all(np.isfinite(popt)):
            return None
        q_0_fixed = popt[5] if np.isfinite(popt[5]) else float(intensity[0])
        states_fit = self.states(
            time_s, popt[0], popt[1], popt[2], popt[3], popt[4], q_0_fixed
        )
        if states_fit is None:
            return None
        y_pred, _ = states_fit
        r_squared, rmse, rss = self.utils.calculate_metrics(intensity, y_pred)
        params = {
            "k_a": float(popt[0]),
            "q_e": float(popt[1]),
            "k_s": float(popt[2]),
            "k_p": float(popt[3]),
            "q_inf": float(popt[4]),
            "q_0": q_0_fixed,
        }
        return _FitResult("secondary_pfo", params, r_squared, rmse, rss, len(time_s))


class KineticModels:
    """Registry and facade for model strategies."""

    def __init__(self, utils: _KineticUtilities) -> None:
        self.utils = utils
        self.ode_helper = _ODESolverHelper()
        self.pfo_model = _PFOModel(utils)
        self.secondary_pfo_model = _SecondaryPFOModel(utils, self.ode_helper)

        self.registry: dict[str, _ModelFitSpec] = {
            "pfo": _ModelFitSpec(
                model_key="pfo",
                fit_with_errors=self.pfo_model.fit_with_errors,
                fit_result_fn=self.pfo_model.fit_result,
                summarize_fn=self.pfo_model.summarize,
            ),
            "secondary_pfo": _ModelFitSpec(
                model_key="secondary_pfo",
                fit_with_errors=self.secondary_pfo_model.fit_with_errors,
                fit_result_fn=self.secondary_pfo_model.fit_result,
                summarize_fn=None,
            ),
        }

    @staticmethod
    def coupled_pfo_odes(
        t: float,
        y: list[float],
        k_a: float,
        q_e: float,
        k_s: float,
        k_p: float,
        q_inf: float,
    ) -> list[float]:
        return _SecondaryPFOModel.coupled_pfo_odes(t, y, k_a, q_e, k_s, k_p, q_inf)

    def pfo(
        self,
        time_s: NDArray[np.float64],
        k: float,
        q_e: float,
        q_0: float,
    ) -> NDArray[np.float64]:
        return self.pfo_model.pfo(time_s, k, q_e, q_0)

    def pfo_with_secondary_states(
        self,
        time_s: NDArray[np.float64],
        k_a: float,
        q_e: float,
        k_s: float,
        k_p: float,
        q_inf: float,
        q_0: float,
        timeout_seconds: float = 5.0,
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]] | None:
        return self.secondary_pfo_model.states(
            time_s, k_a, q_e, k_s, k_p, q_inf, q_0, timeout_seconds=timeout_seconds
        )

    def fit_pfo_with_errors(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        p0: list[float] | None = None,
    ) -> tuple[NDArray[np.float64], NDArray[np.float64], float, float]:
        return self.pfo_model.fit_with_errors(time_s, intensity, p0=p0)

    def fit_secondary_pfo_with_errors(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        p0: list[float] | None = None,
        timeout_seconds: float = 0.1,
    ) -> tuple[NDArray[np.float64], NDArray[np.float64], float, float]:
        return self.secondary_pfo_model.fit_with_errors(
            time_s,
            intensity,
            p0=p0,
            timeout_seconds=timeout_seconds,
        )

    def summarize_pfo_fit(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
    ) -> dict[str, Any]:
        return self.pfo_model.summarize(time_s, intensity)

    def fit_pfo(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        p0: list[float] | None = None,
    ) -> _FitResult | None:
        return self.pfo_model.fit_result(time_s, intensity, p0=p0)

    def fit_secondary_pfo(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        p0: list[float] | None = None,
    ) -> _FitResult | None:
        return self.secondary_pfo_model.fit_result(time_s, intensity, p0=p0)


class KineticClassification:
    """Trajectory classification helpers."""

    def __init__(self, models: KineticModels, utils: _KineticUtilities) -> None:
        self.models = models
        self.utils = utils

    @staticmethod
    def window_slope(
        time_s: NDArray[np.float64], intensity: NDArray[np.float64]
    ) -> float:
        if len(time_s) < 2:
            return np.nan
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", message="Polyfit may be poorly conditioned"
            )
            slope, _ = np.polyfit(time_s, intensity, 1)
        return float(slope)

    def find_flat_transition(
        self,
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
            slope = self.window_slope(window_time, window_intensity)
            if not np.isfinite(slope):
                continue
            is_flat = abs(slope) <= eps_flat
            if flat_window is not None and not is_flat:
                transition_end = float(time_s[end_idx])
                break
            if is_flat:
                flat_window = (float(start_time), float(time_s[end_idx]), float(slope))
        return flat_window, transition_end

    @staticmethod
    def running_mean(
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
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        eps_flat: float,
        rise_delta: float,
    ) -> tuple[bool, float | None]:
        flat_window, transition_end = self.find_flat_transition(
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

        smooth_result = self.running_mean(time_s, intensity, SMOOTHING_WINDOW)
        smooth_transition: float | None = None
        if smooth_result is not None:
            smooth_time, smooth_intensity = smooth_result
            _, smooth_transition = self.find_flat_transition(
                smooth_time,
                smooth_intensity,
                eps_flat,
                MIN_FLAT_START_S,
                FLAT_WINDOW_S,
            )

        breakpoint_used = (
            smooth_transition if smooth_transition is not None else transition_end
        )
        return True, breakpoint_used

    def classify_trajectory(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        eps_flat: float = EPS_FLAT_DEFAULT,
        rise_delta: float = RISE_DELTA_DEFAULT,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if len(time_s) < 3:
            result["classification"] = "fit_failed"
            return result

        is_disc, breakpoint_s = self.detect_discontinuity(
            time_s, intensity, eps_flat, rise_delta
        )
        if not is_disc or breakpoint_s is None:
            result["classification"] = "continuous"
            return result

        result["classification"] = "discontinuous"
        result["growth_onset_s"] = breakpoint_s
        pre_mask = time_s <= breakpoint_s
        post_mask = time_s > breakpoint_s
        pre_fit = self.models.summarize_pfo_fit(time_s[pre_mask], intensity[pre_mask])
        post_fit = self.models.summarize_pfo_fit(
            time_s[post_mask], intensity[post_mask]
        )
        result.update(self.utils.prefix_fit_results(pre_fit, "pre_"))
        result.update(self.utils.prefix_fit_results(post_fit, "post_"))
        return result


class KineticWriter:
    """Prepare fit rows and write outputs."""

    def __init__(
        self,
        utils: _KineticUtilities,
        models: KineticModels,
        classifier: KineticClassification,
    ) -> None:
        self.utils = utils
        self.models = models
        self.classifier = classifier
        self.model_specs: dict[str, _ModelRowSpec] = {
            "pfo": _ModelRowSpec(
                model_key="pfo",
                r2_col="pfo_r^2",
                rmse_col="pfo_rmse",
                param_map=[
                    ("pfo_k_s-1", "pfo_k_stderr"),
                    ("pfo_q_e_au", "pfo_q_e_stderr"),
                    ("pfo_q0_au", None),
                ],
                fit_fn=self.models.registry["pfo"].fit_with_errors,
            ),
            "secondary_pfo": _ModelRowSpec(
                model_key="secondary_pfo",
                r2_col="pfo-sec_r^2",
                rmse_col="pfo-sec_rmse",
                param_map=[
                    ("pfo-sec_k_a_s-1", "pfo-sec_k_a_stderr"),
                    ("pfo-sec_q_e_au", "pfo-sec_q_e_stderr"),
                    ("pfo-sec_k_s_s-1", "pfo-sec_k_s_stderr"),
                    ("pfo-sec_k_p_s-1", "pfo-sec_k_p_stderr"),
                    ("pfo-sec_q_inf_au", "pfo-sec_q_inf_stderr"),
                    ("pfo-sec_q0_au", None),
                ],
                fit_fn=self.models.registry["secondary_pfo"].fit_with_errors,
            ),
        }

    def _prepare_model_rows_for_file(
        self,
        model_key: str,
        df_legacy: pd.DataFrame,
        *,
        min_points: int,
        peak_names: list[str] | None,
        mode: str,
        p0: list[float] | None,
        carry_forward_p0: bool,
    ) -> pd.DataFrame:
        return self.prepare_model_fit_rows(
            model_key,
            df_legacy,
            min_points=min_points,
            peak_names=peak_names,
            mode=mode,
            p0=p0,
            carry_forward_p0=carry_forward_p0,
        )

    def _select_secondary_p0(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        *,
        threshold_r2: float = 0.96,
        user_p0: list[float] | None = None,
        min_points: int = 4,
    ) -> list[float]:
        """Choose secondary_pfo p0 for the current trajectory slice."""
        if len(time_s) < min_points:
            return user_p0 if user_p0 is not None else [3e-4, 1.0, 5e-5, 0.5, 0.0]

        q_guess = float(np.max(intensity)) if intensity.size else 0.0
        default_p0 = [3e-4, q_guess, 5e-5, 0.5, 0.0]
        current = list(user_p0) if user_p0 is not None else list(default_p0)
        if len(current) != 5:
            current = list(default_p0)

        best_p0 = list(current)
        best_r2 = -np.inf

        fit_fn = self.models.registry["secondary_pfo"].fit_with_errors

        def eval_r2(candidate: list[float]) -> float:
            _, _, r2, _ = fit_fn(time_s, intensity, candidate)
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

    def _select_secondary_p0_for_secondary(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        *,
        model_key: str,
        use_prior_p0: bool,
        previous_p0: list[float] | None,
        previous_r2: float | None,
        user_p0: list[float] | None,
        min_points: int,
    ) -> list[float] | None:
        """Select effective p0 for secondary_pfo, respecting the ``use_prior_p0`` toggle."""
        if model_key != "secondary_pfo":
            return user_p0

        if not use_prior_p0:
            # Start fresh each row: seed from user p0 (or default inside _select_secondary_p0).
            return self._select_secondary_p0(
                time_s,
                intensity,
                threshold_r2=0.96,
                user_p0=user_p0,
                min_points=min_points,
            )

        # use_prior_p0=True: carry forward successful p0 between rows.
        seed_p0 = previous_p0 if previous_r2 is not None else user_p0
        return self._select_secondary_p0(
            time_s,
            intensity,
            threshold_r2=0.96,
            user_p0=seed_p0,
            min_points=min_points,
        )

    @staticmethod
    def _classification_payload(
        group: pd.DataFrame,
        peak_name: str,
        min_points: int,
        classifier: KineticClassification,
    ) -> tuple[float | str, float | str, dict[str, Any]]:
        classification_value: float | str = np.nan
        breakpoint_used_value: float | str = np.nan
        classification: dict[str, Any] = {}

        if peak_name == "cluster_sum" and len(group) >= min_points:
            time_s_all = group["Time (s)"].to_numpy(dtype=float)
            intensity_all = group["Cumulative_Peak_Area"].to_numpy(dtype=float)
            classification = classifier.classify_trajectory(time_s_all, intensity_all)
            for key, value in classification.items():
                if (key.startswith("pre_") or key.startswith("post_")) and isinstance(
                    value, float
                ):
                    classification[key] = float(value)

            classification_raw = classification.get("classification")
            classification_value = (
                str(classification_raw) if classification_raw is not None else np.nan
            )
            breakpoint_raw = classification.get("growth_onset_s")
            breakpoint_used_value = (
                float(breakpoint_raw) if breakpoint_raw is not None else np.nan
            )

        return classification_value, breakpoint_used_value, classification

    def prepare_model_fit_rows(
        self,
        model_key: str,
        df: pd.DataFrame,
        *,
        min_points: int = 4,
        peak_names: list[str] | None = None,
        mode: str = "rolling",
        p0: list[float] | None = None,
        carry_forward_p0: bool = True,
    ) -> pd.DataFrame:
        """Prepare fit-result rows for one DataFrame.

        Parameters
        ----------
        model_key : str
            Which model to fit: ``"pfo"`` or ``"secondary_pfo"``.
        df : pd.DataFrame
            CarbonylPeakArea data with ``Peak_Name``, ``Time (s)``,
            and ``Cumulative_Peak_Area`` columns.
        min_points : int
            Minimum data points required before fitting a peak group.
        peak_names : list[str] | None
            Restrict fitting to these peak names.  None = all peaks.
        mode : str
            ``"rolling"`` — for each time point, fit using all data up
            to and including that time (expanding window).  Produces one
            row per time point per peak.
            ``"full_series"`` — fit once using all data, producing one
            row per peak at the latest time.
        p0 : list[float] | None
            User-supplied initial guess for the optimizer.  None = use
            built-in defaults.
        carry_forward_p0 : bool
            When True (default), the p0 that produced the best r^2 at
            time point N is used as the starting seed for the p0 search
            at time point N+1.  When False, each time point starts from
            ``p0`` (or defaults) independently.  Only affects
            ``secondary_pfo`` in ``"rolling"`` mode.
        """
        spec = self.model_specs.get(model_key)
        if spec is None:
            raise ValueError(f"Unknown model_key: {model_key}")
        if mode not in {"rolling", "full_series"}:
            raise ValueError("mode must be one of: rolling, full_series")

        df = self.utils.prepare_peak_area_df(df)
        if peak_names is not None:
            df = cast(pd.DataFrame, df[df["Peak_Name"].isin(peak_names)].copy())

        records: list[dict[str, float | str]] = []
        for group_key, group_raw in df.groupby("Peak_Name"):
            group = cast(
                pd.DataFrame, group_raw.sort_values("Time (s)").reset_index(drop=True)
            )
            peak_name = str(group_key)

            previous_p0: list[float] | None = None
            previous_r2: float | None = None
            r2_improvement_threshold = 0.01

            classification_value, breakpoint_used_value, classification = (
                self._classification_payload(
                    group, peak_name, min_points, self.classifier
                )
            )

            if len(group) < min_points:
                continue

            if mode == "full_series":
                unique_time = float(group["Time (s)"].max())
                time_s = group["Time (s)"].to_numpy(dtype=float)
                intensity = group["Cumulative_Peak_Area"].to_numpy(dtype=float)
                if len(time_s) < min_points:
                    continue
                current_row = group[group["Time (s)"] == unique_time].iloc[0]
                effective_p0 = self._select_secondary_p0_for_secondary(
                    time_s,
                    intensity,
                    model_key=model_key,
                    use_prior_p0=carry_forward_p0,
                    previous_p0=previous_p0,
                    previous_r2=previous_r2,
                    user_p0=p0,
                    min_points=min_points,
                )
                popt, std_errors, r_squared, rmse = spec.fit_fn(
                    time_s, intensity, effective_p0
                )
                if (
                    model_key == "secondary_pfo"
                    and carry_forward_p0
                    and np.isfinite(r_squared)
                    and (
                        previous_r2 is None
                        or r_squared > previous_r2 + r2_improvement_threshold
                    )
                ):
                    previous_p0 = (
                        list(effective_p0) if effective_p0 is not None else None
                    )
                    previous_r2 = float(r_squared)

                record: dict[str, float | str] = {
                    "Peak_Name": str(current_row["Peak_Name"]),
                    "Time (s)": float(unique_time),
                    spec.r2_col: r_squared,
                    spec.rmse_col: rmse,
                    "classification": classification_value,
                    "growth_onset_s": breakpoint_used_value,
                }

                if (
                    peak_name == "cluster_sum"
                    and classification_value == "discontinuous"
                ):
                    for key, value in classification.items():
                        if key.startswith("pre_") or key.startswith("post_"):
                            record[key] = value

                for idx, (value_key, stderr_key) in enumerate(spec.param_map):
                    value = popt[idx] if idx < len(popt) else np.nan
                    record[value_key] = float(value) if np.isfinite(value) else np.nan
                    if stderr_key is not None:
                        stderr = std_errors[idx] if idx < len(std_errors) else np.nan
                        record[stderr_key] = (
                            float(stderr) if np.isfinite(stderr) else np.nan
                        )

                records.append(record)
            else:
                for unique_time in sorted(group["Time (s)"].unique()):
                    mask = group["Time (s)"] <= unique_time
                    time_s = group.loc[mask, "Time (s)"].to_numpy(dtype=float)
                    intensity = group.loc[mask, "Cumulative_Peak_Area"].to_numpy(
                        dtype=float
                    )
                    if len(time_s) < min_points:
                        continue

                    current_row = group[group["Time (s)"] == unique_time].iloc[0]
                    effective_p0 = self._select_secondary_p0_for_secondary(
                        time_s,
                        intensity,
                        model_key=model_key,
                        use_prior_p0=carry_forward_p0,
                        previous_p0=previous_p0,
                        previous_r2=previous_r2,
                        user_p0=p0,
                        min_points=min_points,
                    )
                    popt, std_errors, r_squared, rmse = spec.fit_fn(
                        time_s, intensity, effective_p0
                    )
                    if (
                        model_key == "secondary_pfo"
                        and carry_forward_p0
                        and np.isfinite(r_squared)
                        and (
                            previous_r2 is None
                            or r_squared > previous_r2 + r2_improvement_threshold
                        )
                    ):
                        previous_p0 = (
                            list(effective_p0) if effective_p0 is not None else None
                        )
                        previous_r2 = float(r_squared)

                    record = {
                        "Peak_Name": str(current_row["Peak_Name"]),
                        "Time (s)": float(unique_time),
                        spec.r2_col: r_squared,
                        spec.rmse_col: rmse,
                        "classification": classification_value,
                        "growth_onset_s": breakpoint_used_value,
                    }

                    if (
                        peak_name == "cluster_sum"
                        and classification_value == "discontinuous"
                    ):
                        for key, value in classification.items():
                            if key.startswith("pre_") or key.startswith("post_"):
                                record[key] = value

                    for idx, (value_key, stderr_key) in enumerate(spec.param_map):
                        value = popt[idx] if idx < len(popt) else np.nan
                        record[value_key] = (
                            float(value) if np.isfinite(value) else np.nan
                        )
                        if stderr_key is not None:
                            stderr = (
                                std_errors[idx] if idx < len(std_errors) else np.nan
                            )
                            record[stderr_key] = (
                                float(stderr) if np.isfinite(stderr) else np.nan
                            )

                    records.append(record)

        return pd.DataFrame(records) if records else pd.DataFrame()

    def prepare_pfo_classification_rows(
        self,
        df: pd.DataFrame,
        *,
        min_points: int = 4,
        peak_names: list[str] | None = None,
    ) -> pd.DataFrame:
        df = self.utils.prepare_peak_area_df(df)
        if peak_names is not None:
            df = cast(pd.DataFrame, df[df["Peak_Name"].isin(peak_names)].copy())

        records: list[dict[str, float | str]] = []
        for group_key, group_raw in df.groupby(["Peak_Name"]):
            group = cast(
                pd.DataFrame, group_raw.sort_values("Time (s)").reset_index(drop=True)
            )
            peak_name = group_key[0] if isinstance(group_key, tuple) else group_key

            classification_value, breakpoint_used_value, classification = (
                self._classification_payload(
                    group,
                    str(peak_name),
                    min_points,
                    self.classifier,
                )
            )

            for idx in range(len(group)):
                current_row = group.iloc[idx]
                record: dict[str, float | str] = {
                    "Peak_Name": str(current_row["Peak_Name"]),
                    "Time (s)": float(current_row["Time (s)"]),
                    "classification": classification_value,
                    "growth_onset_s": breakpoint_used_value,
                }
                if (
                    str(peak_name) == "cluster_sum"
                    and classification_value == "discontinuous"
                ):
                    for key, value in classification.items():
                        if key.startswith("pre_") or key.startswith("post_"):
                            record[key] = value
                records.append(record)

        return pd.DataFrame(records) if records else pd.DataFrame()

    def write_model_fit_params(
        self,
        model_key: str,
        carbonyl_peak_area_path: str | Path,
        *,
        output_folder_name: str = "_test",
        min_points: int = 4,
        peak_names: list[str] | None = None,
        mode: str = "rolling",
        p0: list[float] | None = None,
        use_prior_p0: bool = True,
    ) -> Path:
        """Fit a single kinetics model to one CarbonylPeakArea CSV.

        Reads the CSV, fits the model, merges results back into the
        legacy data, and writes the output to ``output_folder_name``.

        Parameters
        ----------
        model_key : str
            Which model to fit: ``"pfo"`` or ``"secondary_pfo"``.
        carbonyl_peak_area_path : str | Path
            Path to the input ``*_CarbonylPeakArea.csv``.
        output_folder_name : str
            Subdirectory name for output CSVs (e.g. ``"_test"``).
        min_points : int
            Minimum number of time points required before fitting starts.
        peak_names : list[str] | None
            Restrict fitting to these peak names.  None = all peaks.
        mode : str
            ``"rolling"`` fits at every time point with an expanding window.
            ``"full_series"`` fits once using all data.
        p0 : list[float] | None
            User-supplied initial guess for the optimizer.  None = use
            built-in defaults.
        use_prior_p0 : bool
            When True (default), the p0 that produced the best r^2 at
            time point N is used as the starting seed for the p0 search
            at time point N+1.  When False, each time point starts from
            ``p0`` (or defaults) independently.  Only affects
            ``secondary_pfo`` in ``"rolling"`` mode.
        """
        carbonyl_peak_area_path = Path(carbonyl_peak_area_path)
        df_legacy = pd.read_csv(carbonyl_peak_area_path)
        df_legacy = self.utils.prepare_peak_area_df(df_legacy)

        fit_params = self._prepare_model_rows_for_file(
            model_key,
            df_legacy,
            min_points=min_points,
            peak_names=peak_names,
            mode=mode,
            p0=p0,
            carry_forward_p0=use_prior_p0,
        )
        if fit_params.empty:
            if model_key == "pfo":
                raise ValueError("No fit results were produced.")
            if model_key == "secondary_pfo":
                raise ValueError("No secondary PFO fit results were produced.")
            raise ValueError(f"No fit results were produced for model: {model_key}")
        return self.utils.write_fit_params_to_legacy(
            carbonyl_peak_area_path,
            fit_params,
            output_folder_name=output_folder_name,
            legacy_df=df_legacy,
        )

    def write_sum_model_fit_params(
        self,
        carbonyl_peak_area_path: str | Path,
        *,
        monomer_model_key: str = "secondary_pfo",
        cluster_model_key: str = "pfo",
        output_folder_name: str = "_test",
        min_points: int = 4,
        mode: str = "rolling",
        monomer_p0: list[float] | None = None,
        cluster_p0: list[float] | None = None,
        carry_forward_p0: bool = True,
    ) -> Path:
        """Fit monomer and cluster groups with separate model assignments.

        Monomer group uses config-based monomer peaks + ``monomer_sum``,
        fitted with ``monomer_model_key`` (default: ``secondary_pfo``).
        Cluster group uses config-based cluster peaks + ``cluster_sum``,
        fitted with ``cluster_model_key`` (default: ``pfo``).
        Results are merged into one legacy output CSV.

        Parameters
        ----------
        carbonyl_peak_area_path : str | Path
            Path to the input ``*_CarbonylPeakArea.csv``.
        monomer_model_key : str
            Model for monomer peaks (default ``"secondary_pfo"``).
        cluster_model_key : str
            Model for cluster peaks (default ``"pfo"``).
        output_folder_name : str
            Subdirectory name for output CSVs (e.g. ``"_test"``).
        min_points : int
            Minimum number of time points required before fitting starts.
        mode : str
            ``"rolling"`` fits at every time point with an expanding window.
            ``"full_series"`` fits once using all data.
        monomer_p0 : list[float] | None
            Initial guess for monomer model optimizer.  None = defaults.
        cluster_p0 : list[float] | None
            Initial guess for cluster model optimizer.  None = defaults.
        carry_forward_p0 : bool
            When True (default), the p0 that produced the best r^2 at
            time point N is used as the starting seed for the p0 search
            at time point N+1.  When False, each time point starts from
            the user p0 (or defaults) independently.  Only affects
            ``secondary_pfo`` in ``"rolling"`` mode.
        """
        carbonyl_peak_area_path = Path(carbonyl_peak_area_path)
        df_legacy = pd.read_csv(carbonyl_peak_area_path)
        df_legacy = self.utils.prepare_peak_area_df(df_legacy)

        monomer_peak_names = [
            *self.utils.get_monomer_peak_names(isotope=None),
            "monomer_sum",
        ]
        cluster_peak_names = [
            *self.utils.get_peak_names("cluster_peaks_base", isotope=None),
            "cluster_sum",
        ]

        overlap = set(monomer_peak_names) & set(cluster_peak_names)
        if overlap:
            raise ValueError(
                "Monomer/cluster peak sets overlap in config: "
                + ", ".join(sorted(overlap))
            )

        monomer_rows = self._prepare_model_rows_for_file(
            monomer_model_key,
            df_legacy,
            min_points=min_points,
            peak_names=monomer_peak_names,
            mode=mode,
            p0=monomer_p0,
            carry_forward_p0=carry_forward_p0,
        )
        cluster_rows = self._prepare_model_rows_for_file(
            cluster_model_key,
            df_legacy,
            min_points=min_points,
            peak_names=cluster_peak_names,
            mode=mode,
            p0=cluster_p0,
            carry_forward_p0=carry_forward_p0,
        )

        frames = [frame for frame in [monomer_rows, cluster_rows] if not frame.empty]
        if not frames:
            raise ValueError("No fit results were produced for monomer/cluster groups.")

        fit_params = pd.concat(frames, ignore_index=True)
        return self.utils.write_fit_params_to_legacy(
            carbonyl_peak_area_path,
            fit_params,
            output_folder_name=output_folder_name,
            legacy_df=df_legacy,
        )

    def write_pfo_classification(
        self,
        carbonyl_peak_area_path: str | Path,
        *,
        output_folder_name: str = "_test",
        min_points: int = 4,
        peak_names: list[str] | None = None,
    ) -> Path:
        carbonyl_peak_area_path = Path(carbonyl_peak_area_path)
        df_legacy = pd.read_csv(carbonyl_peak_area_path)
        df_legacy = self.utils.prepare_peak_area_df(df_legacy)
        fit_params = self.prepare_pfo_classification_rows(
            df_legacy,
            min_points=min_points,
            peak_names=peak_names,
        )
        if fit_params.empty:
            raise ValueError("No classification results were produced.")
        return self.utils.write_fit_params_to_legacy(
            carbonyl_peak_area_path,
            fit_params,
            output_folder_name=output_folder_name,
            legacy_df=df_legacy,
        )

    def remove_legacy_pfo_columns_file(
        self,
        carbonyl_peak_area_path: str | Path,
        *,
        output_folder_name: str = "_test",
        prefixes: tuple[str, ...] = ("pfo",),
    ) -> Path:
        """Remove prefixed legacy columns from one CarbonylPeakArea CSV.

        Currently a no-op: column removal is handled by the API layer.
        """
        carbonyl_peak_area_path = Path(carbonyl_peak_area_path)
        df = pd.read_csv(carbonyl_peak_area_path)
        return self.utils.write_plain_legacy_output(
            carbonyl_peak_area_path,
            df,
            output_folder_name=output_folder_name,
        )

    def remove_legacy_pfo_columns_folder(
        self,
        dataset_folder: str | Path,
        *,
        output_folder_name: str = "_test",
        prefixes: tuple[str, ...] = ("pfo",),
    ) -> list[Path]:
        """Remove prefixed legacy columns for all matching files in a folder.

        Currently a no-op: column removal is handled by the API layer.
        """
        dataset_path = Path(dataset_folder)
        if not dataset_path.is_absolute():
            dataset_path = SEARCH_ROOT / dataset_folder

        csv_files = [
            path
            for path in sorted(dataset_path.rglob("*_CarbonylPeakArea.csv"))
            if "_test" not in path.parts
            and "arxiv" not in path.parts
            and "CalibrationData" not in path.parts
            and path.name.endswith(str(AREA_SUFFIX))
        ]

        outputs: list[Path] = []
        for csv_file in csv_files:
            try:
                output_path = self.remove_legacy_pfo_columns_file(
                    csv_file,
                    output_folder_name=output_folder_name,
                    prefixes=prefixes,
                )
                outputs.append(output_path)
            except Exception as exc:
                LOGGER.warning("Failed to clean %s: %s", csv_file, exc)
        return outputs

    def process_carbonyl_peak_area_files(
        self,
        csv_files: list[Path],
        *,
        model_key: str = "secondary_pfo",
        output_folder_name: str = "_test",
        min_points: int = 4,
        classification_only: bool = False,
        peak_names: list[str] | None = None,
        mode: str = "rolling",
        p0: list[float] | None = None,
        carry_forward_p0: bool = True,
    ) -> list[Path]:
        """Fit kinetics models to a list of CarbonylPeakArea CSV files.

        Parameters
        ----------
        csv_files : list[Path]
            Paths to ``*_CarbonylPeakArea.csv`` files to process.
        model_key : str
            Which model to fit: ``"pfo"`` or ``"secondary_pfo"``.
        output_folder_name : str
            Subdirectory name for output CSVs (e.g. ``"_test"``).
        min_points : int
            Minimum number of time points required before fitting starts.
        classification_only : bool
            If True, skip fitting and only write trajectory classification.
        peak_names : list[str] | None
            Restrict fitting to these peak names.  None = all peaks.
        mode : str
            ``"rolling"`` fits at every time point with an expanding window.
            ``"full_series"`` fits once using all data.
        p0 : list[float] | None
            User-supplied initial guess for the optimizer.  None = use
            built-in defaults.
        carry_forward_p0 : bool
            When True (default), the p0 that produced the best r^2 at
            time point N is used as the starting seed for the p0 search
            at time point N+1.  When False, each time point starts from
            ``p0`` (or defaults) independently.  Only affects
            ``secondary_pfo`` in ``"rolling"`` mode.
        """
        outputs: list[Path] = []
        for csv_file in csv_files:
            LOGGER.info("Processing %s...", csv_file)
            try:
                if not csv_file.name.endswith(str(AREA_SUFFIX)):
                    LOGGER.warning("Skipping non-area CSV: %s", csv_file)
                    continue

                if "20260404_182647_pd_ceo2_004-012" not in str(csv_file):
                    LOGGER.warning("Skipping known problematic file: %s", csv_file)
                    continue
                
                if classification_only:
                    output_path = self.write_pfo_classification(
                        csv_file,
                        output_folder_name=output_folder_name,
                        min_points=min_points,
                        peak_names=peak_names,
                    )
                else:
                    output_path = self.write_model_fit_params(
                        model_key,
                        csv_file,
                        output_folder_name=output_folder_name,
                        min_points=min_points,
                        peak_names=peak_names,
                        mode=mode,
                        p0=p0,
                        use_prior_p0=carry_forward_p0,
                    )
                outputs.append(output_path)
            except Exception as exc:
                LOGGER.warning("Failed processing %s: %s", csv_file, exc)
        return outputs

    def process_carbonyl_peak_area_folder(
        self,
        dataset_folder: str | Path,
        *,
        model_key: str = "secondary_pfo",
        output_folder_name: str = "_test",
        min_points: int = 4,
        classification_only: bool = False,
        peak_names: list[str] | None = None,
        mode: str = "full_series",
        p0: list[float] | None = None,
        carry_forward_p0: bool = True,
    ) -> list[Path]:
        """Batch-process all CarbonylPeakArea CSVs in a dataset folder.

        Searches ``dataset_folder`` (relative to ``SEARCH_ROOT`` if not
        absolute) for ``*_CarbonylPeakArea.csv`` files and fits kinetics
        models to each one.

        Parameters
        ----------
        dataset_folder : str | Path
            Folder name under ``SEARCH_ROOT``, or an absolute path.
        model_key : str
            Which model to fit: ``"pfo"`` or ``"secondary_pfo"``.
        output_folder_name : str
            Subdirectory name for output CSVs (e.g. ``"_test"``).
        min_points : int
            Minimum number of time points required before fitting starts.
        classification_only : bool
            If True, skip fitting and only write trajectory classification.
        peak_names : list[str] | None
            Restrict fitting to these peak names.  None = all peaks.
        mode : str
            ``"rolling"`` fits at every time point with an expanding window.
            ``"full_series"`` fits once using all data.
        p0 : list[float] | None
            User-supplied initial guess for the optimizer.  None = use
            built-in defaults.
        carry_forward_p0 : bool
            When True (default), the p0 that produced the best r^2 at
            time point N is used as the starting seed for the p0 search
            at time point N+1.  When False, each time point starts from
            ``p0`` (or defaults) independently.  Only affects
            ``secondary_pfo`` in ``"rolling"`` mode.
        """
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

        return self.process_carbonyl_peak_area_files(
            csv_files,
            model_key=model_key,
            output_folder_name=output_folder_name,
            min_points=min_points,
            classification_only=classification_only,
            peak_names=peak_names,
            mode=mode,
            p0=p0,
            carry_forward_p0=carry_forward_p0,
        )


# --- Instances ---
UTILS = _KineticUtilities()
MODELS = KineticModels(UTILS)
CLASSIFIER = KineticClassification(MODELS, UTILS)
WRITER = KineticWriter(UTILS, MODELS, CLASSIFIER)


if __name__ == "__main__":
    WRITER.process_carbonyl_peak_area_folder(
        dataset_folder="nn1120-3_pd_ceo2_004",
        model_key="secondary_pfo",
        classification_only=False,
        peak_names=None,
        mode="rolling",
        carry_forward_p0=False,
    )
