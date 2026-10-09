"""Voigt model, parameter rules and least-squares fit for offline refits.

Copied from ``src/analysis/spectral_fitting.py`` so this package can change its
baseline, peak list and rules without touching the live server. The copy is
deliberate divergence, guarded by the parity gate in ``spec.md`` section
7: with ``method="leastsq"`` and the same start, it reproduces the live fit
exactly. The default optimizer differs from live; see :data:`FIT_METHOD`.

Nothing here imports ``src.analysis``.
"""

from __future__ import annotations

import logging

import numpy as np
import pybaselines
from lmfit import Minimizer, Parameters
from lmfit.minimizer import MinimizerResult
from scipy.signal import find_peaks
from scipy.special import voigt_profile

LOGGER = logging.getLogger(__name__)

PARAM_NAMES = ("center", "amplitude", "sigma", "gamma", "y0")
"""lmfit parameter prefixes, in ``Parameters`` insertion order per peak."""

SEED_NUDGE_FRAC = 0.01
"""How far inside a bound a seed is moved: this fraction of a two-sided
parameter's range, or of its rule ``value`` when one side is open."""


def voigt_model(
    x: np.ndarray,
    y0: float,
    amplitude: float,
    center: float,
    sigma: float,
    gamma: float,
) -> np.ndarray:
    """Voigt line shape with a constant offset."""
    return y0 + (amplitude * voigt_profile(x - center, sigma, gamma))


def voigt_fwhm(sigma: float, gamma: float) -> float:
    """Voigt pseudo-FWHM, identical to ``spectral_fitting.peak_analysis``."""
    fwhm_gaussian = 2 * sigma * np.sqrt(2 * np.log(2))
    fwhm_lorentz = 2 * gamma
    return (0.5346 * fwhm_lorentz) + np.sqrt(
        (0.2166 * fwhm_lorentz**2) + fwhm_gaussian**2
    )


def combined_voigt(
    x: np.ndarray,
    fit_params: Parameters,
    peaks: list[int],
) -> np.ndarray:
    """Sum the Voigt curves of every peak.

    Calls :func:`voigt_model` directly; the live version wraps it in
    ``lmfit.Model(...).eval`` per peak per iteration, which is the same
    arithmetic at a much higher cost.
    """
    combined = np.zeros_like(x)
    for peak in peaks:
        combined += voigt_model(
            x,
            fit_params[f"y0_{peak}"].value,
            fit_params[f"amplitude_{peak}"].value,
            fit_params[f"center_{peak}"].value,
            fit_params[f"sigma_{peak}"].value,
            fit_params[f"gamma_{peak}"].value,
        )
    return combined


def objective(
    fit_params: Parameters,
    wavenumbers: np.ndarray,
    target: np.ndarray,
    peaks: list[int],
) -> np.ndarray:
    """Residual ``model - target``, matching the live sign convention."""
    return combined_voigt(wavenumbers, fit_params, peaks) - target


FIT_METHOD = "least_squares"
"""lmfit method. Live uses ``"leastsq"`` (Levenberg-Marquardt), which has no
native bounds: lmfit maps each bounded parameter through a sine transform whose
slope is zero at the bound, and it hit its 2000*(n+1) evaluation cap on most
new-baseline refits. ``"least_squares"`` (scipy trust-region-reflective)
enforces bounds directly. Pass ``method="leastsq"`` to reproduce live."""


def peak_fit(
    fit_params: Parameters,
    wavenumbers: np.ndarray,
    target: np.ndarray,
    peaks: list[int],
    method: str = FIT_METHOD,
) -> MinimizerResult:
    """Least-squares Voigt fit."""
    minimizer = Minimizer(
        lambda current: objective(current, wavenumbers, target, peaks),
        fit_params,
    )
    return minimizer.minimize(method=method)


def create_baseline(
    y: np.ndarray,
    baseline_settings: dict,
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(corrected, baseline)`` from ``std_distribution``."""
    baseline_result: tuple[np.ndarray, ...] | None = (
        pybaselines.classification.std_distribution(
            y,
            half_window=baseline_settings.get("half_window", 10),
            interp_half_window=baseline_settings.get("interp_half_window", 5),
            fill_half_window=baseline_settings.get("fill_half_window", 6),
            num_std=baseline_settings.get("num_std", 1.1),
            smooth_half_window=baseline_settings.get("smooth_half_window"),
            weights=baseline_settings.get("weights"),
        )
    )
    if baseline_result is None:
        raise ValueError("Baseline calculation failed.")
    baseline = baseline_result[0]
    return y - baseline, baseline


def get_shifted_rules(fit_settings: dict) -> list[dict]:
    """Return parameter rules shifted from their base isotope to the active one."""
    isotope = fit_settings.get("isotope_default", "13CO")
    rule_isotope = fit_settings.get("param_rules_base_isotope", isotope)
    shifts = fit_settings.get("isotope_shift_cm1", {})
    shift_value = shifts.get(isotope, 0) - shifts.get(rule_isotope, 0)
    if shift_value == 0:
        return fit_settings.get("param_rules", [])

    shifted_rules = []
    for rule in fit_settings.get("param_rules", []):
        rule_copy = dict(rule)
        range_cm1 = rule.get("range_cm1")
        if range_cm1 and len(range_cm1) == 2:
            rule_copy["range_cm1"] = [
                range_cm1[0] + shift_value,
                range_cm1[1] + shift_value,
            ]
        shifted_rules.append(rule_copy)
    return shifted_rules


def select_param_rule(peak: float, parameter_rules: list[dict]) -> dict | None:
    """Return the rule whose ``range_cm1`` holds ``peak``, else the default rule."""
    default_rule = None
    for rule in parameter_rules:
        if rule.get("default"):
            default_rule = rule
            continue

        range_cm1 = rule.get("range_cm1")
        if not range_cm1 or len(range_cm1) != 2:
            continue

        lower, upper = range_cm1
        upper_inclusive = rule.get("upper_inclusive", False)
        if peak >= lower and (peak <= upper if upper_inclusive else peak < upper):
            return rule

    return default_rule


def has_peaks(corrected: np.ndarray, subifg_settings: dict) -> bool:
    """Live's skip detector: True if ``corrected`` has any positive or negative peak.

    Copy of the check in ``spectral_fitting.peak_analysis``: ``find_peaks`` on
    the baseline-corrected ROI and on its negative, with ``prominence`` and a
    height of ``height_multiplier`` times the mean absolute signal. When it
    finds nothing the spectrum is not fitted and every peak gets area 0, so
    fitted noise cannot build up a false cumulative area over a long run.
    """
    prominence = subifg_settings.get("prominence", 0.0003)
    height = subifg_settings.get("height_multiplier", 3) * np.mean(np.abs(corrected))
    peaks_pos, _ = find_peaks(corrected, prominence=prominence, height=height)
    peaks_neg, _ = find_peaks(-corrected, prominence=prominence, height=height)
    return len(peaks_pos) > 0 or len(peaks_neg) > 0


def find_fsd_peaks(
    arr_fsd_roi: np.ndarray,
    baseline_settings: dict,
    fsd_settings: dict,
) -> np.ndarray:
    """Wavenumbers of the peaks in an FSD spectrum.

    Copy of ``spectral_fitting.find_fsd_peaks`` with one fix: live returns the
    ``find_peaks`` *indices*, which its callers then compare to wavenumbers,
    so live snapping never matches. This returns wavenumbers.
    """
    x = arr_fsd_roi[:, 0]
    _, fsd_baseline = create_baseline(arr_fsd_roi[:, 1], baseline_settings)
    peaks, _ = find_peaks(
        arr_fsd_roi[:, 1] - fsd_baseline,
        prominence=fsd_settings.get("prominence", 0.0001),
        height=fsd_settings.get("height", 0.003),
    )
    return x[peaks]


FSD_SNAP_TOLERANCE_CM1 = 5.0
"""Live ``resolve_peak_lists`` tolerance."""


def snap_peaks(peaks: list[int], fsd_wavenumbers: np.ndarray) -> list[float]:
    """Center each peak on an FSD peak within :data:`FSD_SNAP_TOLERANCE_CM1`.

    Same loop as live ``resolve_peak_lists``: the *last* unused FSD peak in
    tolerance wins (not the closest), and an FSD peak is used at most once.
    Peaks with no FSD peak in range keep their nominal wavenumber.
    """
    used: set[float] = set()
    snapped: list[float] = []
    for peak in peaks:
        closest = float(peak)
        for found in fsd_wavenumbers:
            if (
                np.isclose(float(found), float(peak), atol=FSD_SNAP_TOLERANCE_CM1)
                and float(found) not in used
            ):
                closest = float(found)
        snapped.append(closest)
        used.add(closest)
    return snapped


def add_params(
    fit_params: Parameters,
    peak: int,
    rule: dict,
    seed: dict[str, float] | None = None,
    center_cm1: float | None = None,
) -> tuple[int, int]:
    """Add one peak's lmfit parameters; return ``(n_clipped, n_nudged)`` seeds.

    Bounds and ``vary`` flags come from ``rule``, with the center window around
    the **nominal** ``peak``. The live ``add_params`` also takes ``temp_peak``
    for rule ``special_cases``; no rule uses them and there is no FSD here, so
    that branch is dropped.

    ``seed`` maps ``center/amplitude/sigma/gamma/y0`` to starting values, the
    saved fit's result. Missing names fall back to the rule's ``value``.

    ``center_cm1`` (FSD snapping, opt-in) moves the center's start and window
    from ``peak`` to that wavenumber. Parameter names and the rule still
    follow ``peak``.

    - A seed outside its bounds is clipped to the bound and counted
      (``n_clipped``), rather than left to lmfit's silent clamp.
    - A seed on (or within :data:`SEED_NUDGE_FRAC` of) a bound is moved that
      far inside it and counted (``n_nudged``). lmfit maps bounded parameters
      through a transform whose derivative is zero at the bound, so a seed
      sitting exactly on one has a zero Jacobian column. The saved fits pin
      about half their parameters, and seeding them as-is stopped ``leastsq``
      after one iteration with nothing moved.
    """
    seed = seed or {}
    clips = 0
    nudges = 0

    def start(name: str, default: float, low: float, high: float) -> float:
        nonlocal clips, nudges
        value = seed.get(name)
        if value is None or not np.isfinite(value):
            return default
        clipped = float(np.clip(value, low, high))
        if clipped != value:
            clips += 1
        if np.isfinite(low) and np.isfinite(high):
            step = SEED_NUDGE_FRAC * (high - low)
        else:
            step = SEED_NUDGE_FRAC * (abs(default) or 1e-4)
        if np.isfinite(low) and clipped - low < step:
            nudges += 1
            return low + step
        if np.isfinite(high) and high - clipped < step:
            nudges += 1
            return high - step
        return clipped

    center = float(peak) if center_cm1 is None else float(center_cm1)
    center_rule = rule.get("center", {})
    center_min = center + center_rule.get("min_offset", -1)
    center_max = center + center_rule.get("max_offset", 1)
    fit_params.add(
        f"center_{peak}",
        value=start("center", center, center_min, center_max),
        min=center_min,
        max=center_max,
    )

    amplitude_rule = rule.get("amplitude", {})
    amplitude_min = amplitude_rule.get("min", -np.inf)
    fit_params.add(
        f"amplitude_{peak}",
        value=start(
            "amplitude", amplitude_rule.get("value", 0.01), amplitude_min, np.inf
        ),
        min=amplitude_min,
    )

    sigma_rule = rule.get("sigma", {})
    sigma_min = sigma_rule.get("min", 2.55)
    sigma_max = sigma_rule.get("max", 6.37)
    fit_params.add(
        f"sigma_{peak}",
        value=start("sigma", sigma_rule.get("value", 5), sigma_min, sigma_max),
        min=sigma_min,
        max=sigma_max,
    )

    gamma_rule = rule.get("gamma", {})
    gamma_min = gamma_rule.get("min", 0)
    gamma_max = gamma_rule.get("max", np.inf)
    fit_params.add(
        f"gamma_{peak}",
        value=start("gamma", gamma_rule.get("value", 2), gamma_min, gamma_max),
        min=gamma_min,
        max=gamma_max,
    )

    y0_rule = rule.get("y0", {})
    y0_min = y0_rule.get("min", 0)
    y0_vary = y0_rule.get("vary", False)
    y0_default = y0_rule.get("value", 0)
    fit_params.add(
        f"y0_{peak}",
        # A fixed parameter takes the rule's value, never a seed: seeding it
        # would silently turn a rule edit into a no-op on refit.
        value=start("y0", y0_default, y0_min, np.inf) if y0_vary else y0_default,
        min=y0_min,
        vary=y0_vary,
    )

    return clips, nudges


def manually_skip_files(delta_file: str, file_index: str) -> bool:
    """Return True for manually skipped low-S/N files (from empirical observation)."""
    return ((delta_file == "delta1") and (int(file_index) > 2)) or delta_file in {
        "delta2",
        "delta3",
        "delta4",
    }
