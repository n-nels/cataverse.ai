"""Local secondary-PFO ODE and cutoff forecasting logic."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from threading import Thread
from typing import Sequence

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import solve_ivp
from scipy.optimize import minimize


LOGGER = logging.getLogger(__name__)

PARAMETER_NAMES = (
    "pfo-sec_k_a_s-1",
    "pfo-sec_q_e_au",
    "pfo-sec_k_s_s-1",
    "pfo-sec_k_p_s-1",
    "pfo-sec_q_inf_au",
    "pfo-sec_q0_au",
)


class OdeForecastError(RuntimeError):
    """Raised when the local ODE cannot produce a finite trajectory."""


@dataclass(frozen=True)
class SecondaryPfoParameters:
    """Secondary-PFO parameters in the established ODE order."""

    k_a: float
    q_e: float
    k_s: float
    k_p: float
    q_inf: float
    q_0: float

    @classmethod
    def from_values(cls, values: Sequence[float]) -> "SecondaryPfoParameters":
        """Build parameters from the six-value project contract."""
        if len(values) != 6:
            raise ValueError("Secondary-PFO parameters must contain six values")
        return cls(*(float(value) for value in values))

    def as_array(self) -> NDArray[np.float64]:
        """Return the parameters in the established six-value order."""
        return np.asarray(
            [self.k_a, self.q_e, self.k_s, self.k_p, self.q_inf, self.q_0],
            dtype=float,
        )


@dataclass(frozen=True)
class SecondaryPfoFit:
    """Structured result for a local secondary-PFO fit."""

    parameters: SecondaryPfoParameters | None
    r_squared: float | None
    rmse: float | None
    success: bool
    reason: str | None = None


@dataclass(frozen=True)
class CutoffForecast:
    """Full trajectory and availability masks for one cutoff."""

    cutoff_s: float
    times_s: NDArray[np.float64]
    predicted_area: NDArray[np.float64]
    available_mask: NDArray[np.bool_]
    remaining_mask: NDArray[np.bool_]


@dataclass(frozen=True)
class ForecastResult:
    """Structured forecast result, including fallback provenance."""

    parameters: SecondaryPfoParameters | None
    forecast: CutoffForecast | None
    source: str
    valid: bool
    fallback_reason: str | None = None


def coupled_pfo_odes(
    _time_s: float,
    state: NDArray[np.float64],
    k_a: float,
    q_e: float,
    k_s: float,
    k_p: float,
    q_inf: float,
) -> list[float]:
    """Evaluate the established coupled secondary-PFO equations."""
    q, p = state
    return [k_a * (q_e - q) - k_s * p, k_p * (q - q_inf - p)]


def _validate_parameters(
    parameters: SecondaryPfoParameters,
    *,
    q_guess: float | None = None,
) -> None:
    """Validate the existing fitter's parameter restrictions."""
    values = parameters.as_array()
    if not np.isfinite(values).all():
        raise ValueError("Secondary-PFO parameters must be finite")
    if not 0.0 <= parameters.k_a <= 0.01:
        raise ValueError("k_a is outside [0, 0.01]")
    if not 0.0 <= parameters.k_s <= 0.01:
        raise ValueError("k_s is outside [0, 0.01]")
    if not 0.0 <= parameters.k_p <= parameters.k_a:
        raise ValueError("k_p must be in [0, k_a]")
    if parameters.q_e < 0.0 or parameters.q_inf < 0.0:
        raise ValueError("q_e and q_inf must be non-negative")
    if q_guess is not None:
        upper = max(float(q_guess), 0.0) * 2.0
        if parameters.q_e > upper or parameters.q_inf > upper:
            raise ValueError("q_e and q_inf exceed the fit-dependent upper bound")


def validate_secondary_pfo_parameters(
    parameters: SecondaryPfoParameters,
    *,
    q_guess: float | None = None,
) -> None:
    """Validate one complete finite parameter vector before ODE use."""
    _validate_parameters(parameters, q_guess=q_guess)


def _sorted_unique_times(
    time_s: Sequence[float],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return original times and their sorted unique values."""
    original = np.asarray(time_s, dtype=float)
    if original.size == 0 or not np.isfinite(original).all():
        raise ValueError("time_s must contain at least one finite value")
    return original, np.unique(original)


def solve_secondary_pfo(
    time_s: Sequence[float],
    parameters: SecondaryPfoParameters,
    *,
    timeout_seconds: float = 0.1,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Solve the local secondary-PFO ODE on the supplied time grid.

    The initial state is ``[q_0, 0.0]`` and the solver settings match the
    existing implementation: ``solve_ivp``, ``RK45``, and ``rtol=1e-8``.
    Duplicate input times are solved once and interpolated back.
    """
    _validate_parameters(parameters)
    original_times, unique_times = _sorted_unique_times(time_s)
    if timeout_seconds <= 0.0:
        raise ValueError("timeout_seconds must be positive")
    if len(unique_times) == 1:
        q = np.full(original_times.shape, parameters.q_0, dtype=float)
        p = np.zeros(original_times.shape, dtype=float)
        return q, p

    result: dict[str, object] = {"solution": None, "error": None}

    def solve() -> None:
        try:
            result["solution"] = solve_ivp(
                coupled_pfo_odes,
                t_span=(unique_times[0], unique_times[-1]),
                y0=[parameters.q_0, 0.0],
                args=(
                    parameters.k_a,
                    parameters.q_e,
                    parameters.k_s,
                    parameters.k_p,
                    parameters.q_inf,
                ),
                t_eval=unique_times,
                method="RK45",
                rtol=1e-8,
            )
        except (ValueError, RuntimeError) as error:
            result["error"] = error

    thread = Thread(target=solve, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)
    if thread.is_alive():
        raise OdeForecastError("secondary-PFO ODE solver timed out")
    if result["error"] is not None:
        raise OdeForecastError("secondary-PFO ODE solver failed") from result["error"]

    solution = result["solution"]
    if solution is None or not solution.success:
        message = solution.message if solution is not None else "no solution"
        raise OdeForecastError(f"secondary-PFO ODE solver failed: {message}")

    q_unique = np.asarray(solution.y[0], dtype=float)
    p_unique = np.asarray(solution.y[1], dtype=float)
    q = np.interp(original_times, unique_times, q_unique)
    p = np.interp(original_times, unique_times, p_unique)
    if not np.isfinite(q).all() or not np.isfinite(p).all():
        raise OdeForecastError("secondary-PFO ODE returned non-finite states")
    return q, p


def fit_secondary_pfo(
    time_s: Sequence[float],
    intensity: Sequence[float],
    *,
    min_points: int = 4,
    p0: Sequence[float] | None = None,
    timeout_seconds: float = 0.1,
) -> SecondaryPfoFit:
    """Fit the local secondary-PFO model using the existing fit contract."""
    times = np.asarray(time_s, dtype=float)
    values = np.asarray(intensity, dtype=float)
    if times.size != values.size or times.size == 0:
        raise ValueError("time_s and intensity must have the same non-zero length")
    if not np.isfinite(times).all() or not np.isfinite(values).all():
        raise ValueError("time_s and intensity must be finite")
    if min_points < 1:
        raise ValueError("min_points must be positive")
    if len(np.unique(times)) < min_points:
        return SecondaryPfoFit(None, None, None, False, "fit_not_eligible")

    q_0 = float(values[0])
    q_guess = max(float(np.max(values)), 0.0)
    initial = list(p0) if p0 is not None else [3e-4, q_guess, 5e-5, 0.5, 0.0]
    if len(initial) != 5:
        raise ValueError("p0 must contain five values")
    bounds = [
        (0.0, 0.01),
        (0.0, q_guess * 2.0),
        (0.0, 0.01),
        (0.0, 1.0),
        (0.0, q_guess * 2.0),
    ]
    initial = [
        float(np.clip(value, lower, upper))
        for value, (lower, upper) in zip(initial, bounds, strict=True)
    ]

    def objective(candidate: NDArray[np.float64]) -> float:
        k_a, q_e, k_s, k_p_ratio, q_inf = candidate
        parameters = SecondaryPfoParameters(
            float(k_a),
            float(q_e),
            float(k_s),
            float(k_a * k_p_ratio),
            float(q_inf),
            q_0,
        )
        try:
            q_fit, p_fit = solve_secondary_pfo(
                times, parameters, timeout_seconds=timeout_seconds
            )
        except (OdeForecastError, ValueError):
            return np.inf
        if not np.isfinite(q_fit).all() or not np.isfinite(p_fit).all():
            return np.inf
        return float(np.sum((values - q_fit) ** 2))

    try:
        result = minimize(
            objective,
            x0=np.asarray(initial, dtype=float),
            bounds=bounds,
            method="L-BFGS-B",
        )
    except (ValueError, RuntimeError) as error:
        LOGGER.debug("Secondary-PFO minimization failed: %s", error)
        return SecondaryPfoFit(None, None, None, False, "optimizer_failed")

    if not result.success or not np.isfinite(result.x).all():
        return SecondaryPfoFit(None, None, None, False, "optimizer_failed")

    k_a, q_e, k_s, k_p_ratio, q_inf = result.x
    parameters = SecondaryPfoParameters(
        float(k_a),
        float(q_e),
        float(k_s),
        float(k_a * k_p_ratio),
        float(q_inf),
        q_0,
    )
    try:
        q_fit, _ = solve_secondary_pfo(
            times, parameters, timeout_seconds=timeout_seconds
        )
    except (OdeForecastError, ValueError):
        return SecondaryPfoFit(None, None, None, False, "solver_failed")
    residuals = values - q_fit
    ss_total = float(np.sum((values - np.mean(values)) ** 2))
    ss_residual = float(np.sum(residuals**2))
    r_squared = 1.0 - ss_residual / ss_total if ss_total > 0.0 else np.nan
    rmse = float(np.sqrt(np.mean(residuals**2)))
    return SecondaryPfoFit(parameters, r_squared, rmse, True)


def fit_expanding_prefixes(
    time_s: Sequence[float],
    intensity: Sequence[float],
    *,
    min_points: int = 4,
    initial_guess: Sequence[float] | None = None,
    prior_fit_carry_forward: bool = False,
    timeout_seconds: float = 0.1,
) -> tuple[SecondaryPfoFit, ...]:
    """Fit the secondary-PFO model independently on every expanding prefix."""
    times = np.asarray(time_s, dtype=float)
    values = np.asarray(intensity, dtype=float)
    if times.size != values.size or times.size == 0:
        raise ValueError("time_s and intensity must have the same non-zero length")
    if not np.isfinite(times).all() or not np.isfinite(values).all():
        raise ValueError("time_s and intensity must be finite")

    fits: list[SecondaryPfoFit] = []
    prior_guess = list(initial_guess) if initial_guess is not None else None
    for end in range(1, len(times) + 1):
        fit = fit_secondary_pfo(
            times[:end],
            values[:end],
            min_points=min_points,
            p0=prior_guess,
            timeout_seconds=timeout_seconds,
        )
        fits.append(fit)
        if prior_fit_carry_forward and fit.success and fit.parameters is not None:
            k_a = fit.parameters.k_a
            k_p_ratio = fit.parameters.k_p / k_a if k_a > 0.0 else 0.0
            prior_guess = [
                fit.parameters.k_a,
                fit.parameters.q_e,
                fit.parameters.k_s,
                k_p_ratio,
                fit.parameters.q_inf,
            ]
    return tuple(fits)


def _prediction_candidates(
    candidate: SecondaryPfoParameters | None,
    previous_valid: SecondaryPfoParameters | None,
    rf_prediction: SecondaryPfoParameters | None,
) -> tuple[tuple[str, SecondaryPfoParameters | None], ...]:
    """Return prediction candidates in the required fallback order."""
    return (
        ("sequential", candidate),
        ("previous_valid", previous_valid),
        ("rf", rf_prediction),
    )


def build_cutoff_forecast_with_fallback(
    time_s: Sequence[float],
    observed_area: Sequence[float],
    cutoff_s: float,
    *,
    candidate: SecondaryPfoParameters | None,
    previous_valid: SecondaryPfoParameters | None,
    rf_prediction: SecondaryPfoParameters | None,
    final_time_s: float | None = None,
    timeout_seconds: float = 0.1,
) -> ForecastResult:
    """Forecast with sequential, previous-valid, then RF fallback behavior."""
    failures: list[str] = []
    for source, parameters in _prediction_candidates(
        candidate, previous_valid, rf_prediction
    ):
        if parameters is None:
            failures.append(f"{source}:unavailable")
            continue
        try:
            validate_secondary_pfo_parameters(parameters)
            forecast = build_cutoff_forecast(
                time_s,
                observed_area,
                cutoff_s,
                parameters,
                final_time_s=final_time_s,
                timeout_seconds=timeout_seconds,
            )
        except (OdeForecastError, ValueError) as error:
            failures.append(f"{source}:{error}")
            continue
        fallback_reason = "; ".join(failures) if failures else None
        return ForecastResult(parameters, forecast, source, True, fallback_reason)

    return ForecastResult(
        parameters=None,
        forecast=None,
        source="none",
        valid=False,
        fallback_reason="; ".join(failures),
    )


def build_cutoff_forecast(
    time_s: Sequence[float],
    observed_area: Sequence[float],
    cutoff_s: float,
    parameters: SecondaryPfoParameters,
    *,
    final_time_s: float | None = None,
    timeout_seconds: float = 0.1,
) -> CutoffForecast:
    """Generate a full predicted trajectory and cutoff availability masks.

    ``observed_area`` is used only for shape and finite-value validation. The
    ODE prediction never reads observations after ``cutoff_s``.
    """
    times = np.asarray(time_s, dtype=float)
    observed = np.asarray(observed_area, dtype=float)
    if times.size != observed.size or times.size == 0:
        raise ValueError("time_s and observed_area must have the same non-zero length")
    if not np.isfinite(times).all() or not np.isfinite(observed).all():
        raise ValueError("time_s and observed_area must be finite")
    final_time = float(np.max(times) if final_time_s is None else final_time_s)
    mask = times <= final_time
    if not mask.any():
        raise ValueError("final_time_s is before every supplied observation")
    forecast_times = times[mask]
    if cutoff_s < float(forecast_times[0]) or cutoff_s > final_time:
        raise ValueError("cutoff_s is outside the forecast timeline")
    predicted_area, _ = solve_secondary_pfo(
        forecast_times, parameters, timeout_seconds=timeout_seconds
    )
    available_mask = forecast_times <= cutoff_s
    remaining_mask = forecast_times > cutoff_s
    return CutoffForecast(
        cutoff_s=float(cutoff_s),
        times_s=forecast_times,
        predicted_area=predicted_area,
        available_mask=available_mask,
        remaining_mask=remaining_mask,
    )


def remaining_curve_rmse(
    times_s: Sequence[float],
    observed_area: Sequence[float],
    predicted_area: Sequence[float],
    cutoff_s: float,
) -> float | None:
    """Score only observed points strictly after a cutoff.

    Returns ``None`` when no observed remainder exists at the cutoff.
    """
    times = np.asarray(times_s, dtype=float)
    observed = np.asarray(observed_area, dtype=float)
    predicted = np.asarray(predicted_area, dtype=float)
    if not (times.size == observed.size == predicted.size):
        raise ValueError("curve arrays must have the same length")
    remaining = times > cutoff_s
    if not remaining.any():
        return None
    errors = predicted[remaining] - observed[remaining]
    return float(np.sqrt(np.mean(errors**2)))
