"""Voigt profile spectral fitting helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast, Optional

import numpy as np
import pandas as pd
import pybaselines

from lmfit import Minimizer, Model, Parameters
from lmfit.minimizer import MinimizerResult
from scipy.integrate import trapezoid
from scipy.signal import find_peaks
from scipy.special import voigt_profile


@dataclass
class PeakFitRecord:
    """Per-peak fit output record."""

    file: str
    delta_group: str
    peak_name: str
    peak_value: float
    data_integral: float
    time_delta_s: float
    peak_area: float
    center: float | None = None
    amplitude: float | None = None
    sigma: float | None = None
    gamma: float | None = None
    y0: float | None = None
    fwhm: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a dict with legacy column names."""
        data = {
            "File": self.file,
            "Delta_Group": self.delta_group,
            "Peak_Name": self.peak_name,
            "Peak_Value": self.peak_value,
            "Data_Integral": self.data_integral,
            "Time_Delta (s)": self.time_delta_s,
            "Peak_Area": self.peak_area,
        }
        if self.center is not None:
            data.update(
                {
                    "Center": self.center,
                    "Amplitude": self.amplitude,
                    "Sigma": self.sigma,
                    "Gamma": self.gamma,
                    "Y0": self.y0,
                    "fwhm": self.fwhm,
                }
            )
        return data


@dataclass
class PeakAnalysisResult:
    """Structured result for spectral peak analysis."""

    composite_fit: np.ndarray
    residual: np.ndarray
    peak_fit_records: list[PeakFitRecord]
    skipped: bool


def get_peak_list(config_settings: dict) -> list[float]:
    """Return the isotope-shifted peak list."""
    base_list = config_settings.get("peak_list_base", [])
    if not base_list:
        return [
            2196,
            2176,
            2156,
            2146,
            2136,
            2125,
            2113,
            2103,
            2093,
            2073,
            2062,
            2050,
            2040,
            2030,
            2015,
            2000,
            1988,
            1975,
        ]

    isotope = config_settings.get("isotope_default", "13CO")
    shifts = config_settings.get("isotope_shift_cm1", {})
    shift_value = shifts.get(isotope, 0)
    return [peak + shift_value for peak in base_list]


def get_shifted_rules(config_settings: dict) -> list[dict]:
    """Return isotope-shifted parameter rules."""
    isotope = config_settings.get("isotope_default", "13CO")
    rule_isotope = config_settings.get("param_rules_base_isotope", isotope)
    shifts = config_settings.get("isotope_shift_cm1", {})
    shift_value = shifts.get(isotope, 0) - shifts.get(rule_isotope, 0)
    if shift_value == 0:
        return config_settings.get("param_rules", [])

    shifted_rules = []
    for rule in config_settings.get("param_rules", []):
        rule_copy = dict(rule)
        range_cm1 = rule.get("range_cm1")
        if range_cm1 and len(range_cm1) == 2:
            rule_copy["range_cm1"] = [
                range_cm1[0] + shift_value,
                range_cm1[1] + shift_value,
            ]
        shifted_rules.append(rule_copy)
    return shifted_rules


def get_shifted_monomer_peaks(config_settings: dict) -> list[float]:
    """Return isotope-shifted monomer peak list."""
    isotope = config_settings.get("isotope_default", "13CO")
    monomer_isotope = config_settings.get("monomer_peaks_base_isotope", isotope)
    shifts = config_settings.get("isotope_shift_cm1", {})
    shift_value = shifts.get(isotope, 0) - shifts.get(monomer_isotope, 0)
    monomer_peaks = config_settings.get("monomer_peaks_base")
    if not monomer_peaks:
        return [2093, 2103, 2113, 2125]
    return [peak + shift_value for peak in monomer_peaks]


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


def combined_voigt(
    x: np.ndarray,
    fit_params: Parameters,
    peak_list_core: list[float],
) -> np.ndarray:
    """Combine Voigt models for all peaks."""
    combined_profile = np.zeros_like(x)
    for peak in peak_list_core:
        center = fit_params[f"center_{peak}"].value
        amplitude = fit_params[f"amplitude_{peak}"].value
        sigma = fit_params[f"sigma_{peak}"].value
        gamma = fit_params[f"gamma_{peak}"].value
        y0 = fit_params[f"y0_{peak}"].value
        combined_profile += Model(voigt_model).eval(
            x=x, y0=y0, center=center, amplitude=amplitude, sigma=sigma, gamma=gamma
        )
    return combined_profile


def objective(
    fit_params: Parameters,
    wavenumbers: np.ndarray,
    y_baseline: np.ndarray,
    peak_list_core: list[float],
) -> np.ndarray:
    """Objective function for fitting."""
    return combined_voigt(wavenumbers, fit_params, peak_list_core) - y_baseline


def peak_fit(
    fit_params: Parameters,
    wavenumbers: np.ndarray,
    y_baseline: np.ndarray,
    peak_list_core: list[float],
) -> MinimizerResult:
    """Perform a least-squares Voigt fit."""
    minimizer = Minimizer(
        lambda current_params: objective(
            current_params, wavenumbers, y_baseline, peak_list_core
        ),
        fit_params,
    )
    return minimizer.minimize()


def find_fsd_peaks(
    arr_fsd_roi: np.ndarray,
    baseline_settings: dict,
    fsd_peak_settings: dict,
) -> np.ndarray:
    """Find peaks in the FSD region."""
    x = arr_fsd_roi[:, 0]
    fsd_signal = arr_fsd_roi[:, 1].T

    fsd_result: Optional[tuple[np.ndarray, ...]] = (
        pybaselines.classification.std_distribution(
            fsd_signal,
            half_window=baseline_settings.get("half_window", 10),
            interp_half_window=baseline_settings.get("interp_half_window", 5),
            fill_half_window=baseline_settings.get("fill_half_window", 6),
            num_std=baseline_settings.get("num_std", 1.1),
            smooth_half_window=baseline_settings.get("smooth_half_window"),
            weights=baseline_settings.get("weights"),
        )
    )
    if fsd_result is None:
        raise ValueError("FSD baseline calculation failed.")
    fsd_baseline = fsd_result[0]
    fsd_baseline_corrected = fsd_signal - fsd_baseline

    peaks, properties = find_peaks(
        fsd_baseline_corrected,
        prominence=fsd_peak_settings.get("prominence", 0.0001),
        height=fsd_peak_settings.get("height", 0.003),
    )
    peak_wavenumbers = x[peaks]

    return peaks


def create_baseline(
    y: np.ndarray,
    baseline_settings: dict,
) -> tuple[np.ndarray, np.ndarray]:
    """Create and subtract a baseline from the signal."""
    # create baseline and subtract
    baseline_result: Optional[tuple[np.ndarray, ...]] = (
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
    baseline_std_distribution = baseline_result[0]
    baseline_corrected = y - baseline_std_distribution
    return baseline_corrected, baseline_std_distribution


def select_param_rule(peak: float, parameter_rules: list[dict]) -> dict | None:
    """Select the parameter rule matching the peak."""
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


def resolve_center_offsets(
    rule: dict,
    peak: float,
    iterator: str,
    peak_tmp: float | None,
) -> tuple[float, float]:
    """Resolve center bounds for a peak."""
    center_rule = rule.get("center", {})
    min_offset = center_rule.get("min_offset", -1)
    max_offset = center_rule.get("max_offset", 1)
    for case in rule.get("special_cases", []):
        condition = case.get("condition")
        if condition == "peak_tmp is not None":
            if peak_tmp is not None:
                center_rule = case.get("center", {})
                min_offset = center_rule.get("min_offset", min_offset)
                max_offset = center_rule.get("max_offset", max_offset)
                break

    return min_offset, max_offset


def add_params(
    fit_params: Parameters,
    peak: float,
    peak_name: float,
    file_index: str,
    temp_peak: float | None,
    voigt_settings: dict,
) -> None:
    """Add lmfit parameter entries for a peak."""
    parameter_rules = get_shifted_rules(voigt_settings)
    param_rule = select_param_rule(peak, parameter_rules)
    if param_rule is None:
        return None

    min_offset, max_offset = resolve_center_offsets(
        param_rule, peak, file_index, temp_peak
    )
    center_value = param_rule.get("center", {})
    fit_params.add(
        f"center_{peak_name}",
        value=peak,
        min=peak + min_offset,
        max=peak + max_offset,
    )

    amplitude_rule = param_rule.get("amplitude", {})
    amplitude_value = amplitude_rule.get("value", 0.01)
    if "min" in amplitude_rule:
        fit_params.add(
            f"amplitude_{peak_name}",
            value=amplitude_value,
            min=amplitude_rule["min"],
        )
    else:
        fit_params.add(f"amplitude_{peak_name}", value=amplitude_value)

    sigma_rule = param_rule.get("sigma", {})
    fit_params.add(
        f"sigma_{peak_name}",
        value=sigma_rule.get("value", 5),
        min=sigma_rule.get("min", 2.55),
        max=sigma_rule.get("max", 6.37),
    )

    gamma_rule = param_rule.get("gamma", {})
    if "max" in gamma_rule:
        fit_params.add(
            f"gamma_{peak_name}",
            value=gamma_rule.get("value", 2),
            min=gamma_rule.get("min", 0),
            max=gamma_rule.get("max", 2.8),
        )
    else:
        fit_params.add(
            f"gamma_{peak_name}",
            value=gamma_rule.get("value", 2),
            min=gamma_rule.get("min", 0),
        )

    y0_rule = param_rule.get("y0", {})
    fit_params.add(
        f"y0_{peak_name}",
        value=y0_rule.get("value", 0),
        min=y0_rule.get("min", 0),
        vary=y0_rule.get("vary", False),
    )

    return None


def manually_skip_files(delta_file: str, file_index: str) -> bool:
    """Return True for manually skipped low-S/N files (from empirical observation)."""
    if ((delta_file == "delta1") and (int(file_index) > 2)) or delta_file in {
        "delta2",
        "delta3",
        "delta4",
    }:
        return True
    return False


def resolve_time_delta(
    file_path: str,
    subifg_log: pd.DataFrame,
    exp_params: pd.DataFrame,
) -> float:
    """Resolve time delta between sample and background."""
    sample_name = file_path.split("\\")[-1]

    indices = cast(
        pd.Index,
        subifg_log["sample_name"].index[subifg_log["sample_name"] == sample_name],
    )
    sample_name_indices = cast(list[int], list(indices))
    if not sample_name_indices:
        print(f"Missing subifg log entry for {file_path}")
        return 0

    try:
        sample = cast(pd.Series, subifg_log["sample"]).iloc[sample_name_indices[0]]
        background = cast(pd.Series, subifg_log["background"]).iloc[
            sample_name_indices[0]
        ]

        matching_rows = [
            cast(pd.Index, exp_params[exp_params["file_directory"] == path].index)[0]
            for path in [sample, background]
        ]

        start_time = cast(pd.Timestamp, exp_params["datetime"].iloc[matching_rows[0]])
        end_time = cast(pd.Timestamp, exp_params["datetime"].iloc[matching_rows[1]])
        time_delta = (start_time - end_time).total_seconds()
        return float(time_delta)
    except Exception as e:
        print(f"Error resolving time delta for {file_path}: {e}")
        return 0


def resolve_peak_lists(
    peak_list_core: list[float],
    fsd_peak_indices: np.ndarray,
) -> list[float]:
    """Resolve final peak list based on detected FSD peaks."""
    used_peaks = set()
    peak_list = []
    for predefined_peak in peak_list_core:
        closest_peak = predefined_peak
        for found_peak in fsd_peak_indices:
            if (
                np.isclose(float(found_peak), float(predefined_peak), atol=5.0)
                and found_peak not in used_peaks
            ):
                closest_peak = found_peak
        peak_list.append(closest_peak)
        used_peaks.add(closest_peak)
    return peak_list


def resolve_temp_peak(fsd_peak_indices: np.ndarray) -> float | None:
    """Resolve temporary peak used for special cases."""
    for peak in fsd_peak_indices:
        if np.isclose(peak, 2169.5, atol=0.5):
            return peak
    return None


def peak_analysis(
    file_path: str,
    wavenumbers: np.ndarray,
    arr_subifg_roi: np.ndarray,
    baseline_corrected: np.ndarray,
    peak_list_core: list[float],
    peak_list: list[float],
    delta_file: str,
    fit_params: Parameters,
    voigt_settings: dict,
    time_delta: float,
) -> PeakAnalysisResult:
    """Analyze peaks and return structured fit results.

    Returns a dictionary containing:
    - composite_fit: np.ndarray of the fitted model
    - residual: np.ndarray of fit residuals
    - peak_fit_records: list[dict] of per-peak fit parameters
    - skipped: bool indicating if fitting was skipped
    """
    composite_fit = np.zeros_like(wavenumbers)
    residual = np.zeros_like(wavenumbers)
    peak_fit_records: list[PeakFitRecord] = []

    delta_group = file_path.split("_")[-1].split(".")[0]

    # skip fitting if criteria not met
    avg_y = np.mean(abs(baseline_corrected))

    subifg_peak_settings = voigt_settings.get("find_peaks", {}).get("subifg", {})
    subifg_prominence = subifg_peak_settings.get("prominence", 0.0003)
    subifg_height_multiplier = subifg_peak_settings.get("height_multiplier", 3)

    peaks_pos, properties = find_peaks(
        baseline_corrected,
        prominence=subifg_prominence,
        height=subifg_height_multiplier * avg_y,
    )
    peak_wavenumbers_pos = arr_subifg_roi[:, 0][peaks_pos]

    peaks_neg, properties = find_peaks(
        -baseline_corrected,
        prominence=subifg_prominence,
        height=subifg_height_multiplier * avg_y,
    )
    peak_wavenumbers_neg = arr_subifg_roi[:, 0][peaks_neg]

    if len(peaks_pos) == 0 and len(peaks_neg) == 0:
        print("skipped: ", file_path)

        wavenumbers_pos = wavenumbers[baseline_corrected >= 0]
        baseline_corrected_pos = baseline_corrected[baseline_corrected >= 0]
        wavenumbers_neg = wavenumbers[baseline_corrected < 0]
        baseline_corrected_neg = baseline_corrected[baseline_corrected < 0]

        integral_pos = -np.trapezoid(baseline_corrected_pos, wavenumbers_pos)
        integral_neg = -np.trapezoid(baseline_corrected_neg, wavenumbers_neg)
        subifg_integral = integral_pos + integral_neg

        for i, peak in enumerate(peak_list_core):
            peak_fit_records.append(
                PeakFitRecord(
                    file=file_path.split("_")[-1],
                    delta_group=delta_group,
                    peak_name=f"Peak_{peak}",
                    peak_value=peak_list[i],
                    data_integral=subifg_integral,
                    time_delta_s=time_delta,
                    peak_area=0,
                )
            )

        return PeakAnalysisResult(
            composite_fit=composite_fit,
            residual=residual,
            peak_fit_records=peak_fit_records,
            skipped=True,
        )

    # fit peaks
    fit_result_bundle = peak_fit(
        fit_params, wavenumbers, baseline_corrected, peak_list_core
    )
    fitted_params = cast(Parameters, getattr(fit_result_bundle, "params"))
    residual = cast(np.ndarray, getattr(fit_result_bundle, "residual"))

    for i, peak in enumerate(peak_list_core):
        center = fitted_params[f"center_{peak}"].value
        amplitude = fitted_params[f"amplitude_{peak}"].value
        sigma = fitted_params[f"sigma_{peak}"].value
        gamma = fitted_params[f"gamma_{peak}"].value
        y0 = fitted_params[f"y0_{peak}"].value

        y_fit = Model(voigt_model).eval(
            x=wavenumbers,
            y0=y0,
            center=center,
            amplitude=amplitude,
            sigma=sigma,
            gamma=gamma,
        )

        peak_area = -trapezoid(y_fit, wavenumbers)

        wavenumbers_pos = wavenumbers[baseline_corrected >= 0]
        baseline_corrected_pos = baseline_corrected[baseline_corrected >= 0]
        wavenumbers_neg = wavenumbers[baseline_corrected < 0]
        baseline_corrected_neg = baseline_corrected[baseline_corrected < 0]

        integral_pos = -np.trapezoid(baseline_corrected_pos, wavenumbers_pos)
        integral_neg = -np.trapezoid(baseline_corrected_neg, wavenumbers_neg)
        subifg_integral = integral_pos + integral_neg

        fwhm_gaussian = 2 * sigma * np.sqrt(2 * np.log(2))
        fwhm_lorentz = 2 * gamma
        fwhm_voigt = (0.5346 * fwhm_lorentz) + np.sqrt(
            (0.2166 * fwhm_lorentz**2) + fwhm_gaussian**2
        )

        peak_fit_records.append(
            PeakFitRecord(
                file=file_path.split("_")[-1],
                delta_group=delta_group,
                peak_name=f"Peak_{peak}",
                peak_value=peak_list[i],
                data_integral=subifg_integral,
                center=center,
                amplitude=amplitude,
                sigma=sigma,
                gamma=gamma,
                y0=y0,
                fwhm=fwhm_voigt,
                time_delta_s=time_delta,
                peak_area=peak_area,
            )
        )
        composite_fit += y_fit

    return PeakAnalysisResult(
        composite_fit=composite_fit,
        residual=residual,
        peak_fit_records=peak_fit_records,
        skipped=False,
    )
