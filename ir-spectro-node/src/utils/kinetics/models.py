"""Kinetic model equations and fitting strategies: PFO and secondary (coupled-ODE) PFO."""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from threading import Thread
from typing import Any, Callable, cast

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import solve_ivp
from scipy.optimize import OptimizeWarning, curve_fit, minimize

from .utils import _KineticUtilities

LOGGER = logging.getLogger(__name__)

PFO_PARAMS = [
    "pfo_k_s-1",
    "pfo_q_e_au",
    "pfo_q0_au",
]


@dataclass
class _ModelRowSpec:
    """Specification for generic row preparation/writing by model."""

    r2_col: str
    rmse_col: str
    param_map: list[tuple[str, str | None]]
    fit_fn: Callable[
        [NDArray[np.float64], NDArray[np.float64], list[float] | None],
        tuple[NDArray[np.float64], NDArray[np.float64], float, float],
    ]


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
                LOGGER.warning("Secondary PFO solve_ivp raised: %s", exc)

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


class KineticModels:
    """Registry and facade for model strategies."""

    def __init__(self, utils: _KineticUtilities) -> None:
        self.utils = utils
        self.ode_helper = _ODESolverHelper()
        self.pfo_model = _PFOModel(utils)
        self.secondary_pfo_model = _SecondaryPFOModel(utils, self.ode_helper)

        self.registry: dict[
            str,
            Callable[
                [NDArray[np.float64], NDArray[np.float64], list[float] | None],
                tuple[NDArray[np.float64], NDArray[np.float64], float, float],
            ],
        ] = {
            "pfo": self.pfo_model.fit_with_errors,
            "secondary_pfo": self.secondary_pfo_model.fit_with_errors,
        }

    def summarize_pfo_fit(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
    ) -> dict[str, Any]:
        return self.pfo_model.summarize(time_s, intensity)
