"""Per-file orchestration for offline IR peak fitting.

Wraps ``src/analysis/spectral_fitting.py`` rather than re-implementing it, so
there is one Voigt model and one set of param rules in the repo. See
``spec.md`` section 3 for why this differs from ``src/utils/kinetics``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from lmfit import Parameters
from scipy.integrate import trapezoid

path = Path(__file__).resolve().parents[3]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.analysis.spectral_fitting import (
    add_params,
    create_baseline,
    get_shifted_rules,
    manually_skip_files,
    peak_fit,
    select_param_rule,
    voigt_model,
)
from src.utils.ir_fitting import config as ir_config
from src.utils.ir_fitting.result_types import FileFitResult, PeakCurve

LOGGER = logging.getLogger(__name__)


class ExistingPeakRowsError(ValueError):
    """Raised under ``on_existing="error"`` when a peak already has rows.

    A distinct type so the per-file error guard in ``api.fit_file`` can let it
    propagate instead of logging it and carrying on -- which would silently turn
    the strictest mode into the most permissive one.
    """


ROI_MIN_CM1 = 1750
ROI_MAX_CM1 = 2250

WAVENUMBER_COLUMN = "Wavenumber (cm-1)"

PARAM_COLUMNS = [
    "File",
    "Delta_Group",
    "Peak_Name",
    "Peak_Value",
    "Data_Integral",
    "Time_Delta (s)",
    "Peak_Area",
    "Center",
    "Amplitude",
    "Sigma",
    "Gamma",
    "Y0",
    "fwhm",
]


def file_key_for(subifg_path: Path) -> str:
    """Return the ``File`` column value for a subIFG path (``delta5.0007``)."""
    return subifg_path.name.split("_")[-1]


def split_file_key(file_key: str) -> tuple[str, str]:
    """Split ``delta5.0007`` into ``("delta5", "0007")``."""
    delta_group, _, file_index = file_key.partition(".")
    return delta_group, file_index


def load_subifg_roi(
    subifg_path: Path,
    window: tuple[float, float] | None = None,
) -> np.ndarray:
    """Load a subIFG file clipped to a wavenumber window.

    Defaults to the analysis ROI, mirroring ``src/analysis/io.py::import_data``
    -- same 1750-2250 window, same descending wavenumber order as written by
    the instrument.

    ``window`` is ``(high, low)`` cm-1 and exists for baseline
    experimentation: ``create_baseline`` receives only ``y``, so the window
    *is* the array the algorithm sees. The fit path does not pass it, and
    changing the ROI that peaks are fitted over is a separate decision -- this
    is only the seam that would make it possible.
    """
    high, low = window if window is not None else (ROI_MAX_CM1, ROI_MIN_CM1)
    df = pd.read_csv(subifg_path, header=None)
    roi = df.loc[(df[0] >= low) & (df[0] <= high)]
    if roi.empty:
        raise ValueError(
            f"No subIFG data in {low:.0f}-{high:.0f} cm-1 for {subifg_path}"
        )
    return np.asarray(roi.values, dtype=float)


def voigt_fwhm(sigma: float, gamma: float) -> float:
    """Voigt pseudo-FWHM, identical to ``spectral_fitting.peak_analysis``."""
    fwhm_gaussian = 2 * sigma * np.sqrt(2 * np.log(2))
    fwhm_lorentz = 2 * gamma
    return (0.5346 * fwhm_lorentz) + np.sqrt(
        (0.2166 * fwhm_lorentz**2) + fwhm_gaussian**2
    )


def resolve_baseline(
    wavenumbers: np.ndarray,
    intensity: np.ndarray,
    file_key: str,
    df_saved_baseline: pd.DataFrame | None,
    mode: str,
    voigt_settings: dict,
    warnings: list[str],
    baseline_settings: dict | None = None,
) -> tuple[np.ndarray, str]:
    """Return ``(baseline, source)`` for one file.

    ``"saved"`` reads the file's column from ``*_CarbonylFitBaseline.csv``, which
    guarantees the new peak areas sit on exactly the same baseline as the
    existing peaks. ``"recompute"`` re-runs ``create_baseline``; with no
    ``ir_fitting.baseline`` override and no ``baseline_settings`` that reproduces
    the saved values exactly, because
    ``pybaselines.classification.std_distribution`` takes no peak list and so
    cannot know that extra peaks were declared (see spec.md section 6).

    ``baseline_settings`` overrides the resolved settings for this call only --
    the sweep hook of section 14.6 step 1. It forces ``"recompute"``, since
    reading a stored column would ignore it.
    """
    if mode not in {"saved", "recompute"}:
        raise ValueError(f"baseline must be 'saved' or 'recompute'; got {mode!r}")

    if mode == "saved" and not baseline_settings:
        if df_saved_baseline is None or file_key not in df_saved_baseline.columns:
            message = (
                f"{file_key}: no saved baseline column available; recomputing instead"
            )
            LOGGER.warning(message)
            warnings.append(message)
        else:
            saved = np.asarray(
                pd.to_numeric(df_saved_baseline[file_key], errors="coerce"),
                dtype=float,
            )
            # Wavenumbers DESCEND, so index 0 is the high-wavenumber end and a
            # narrower top edge drops samples from the FRONT. Align on the tail,
            # and require an exact length match rather than truncating: a
            # head-slice would pass the size check while sitting 26 samples out
            # of register, silently comparing 2250-1800 against 2200-1750.
            if saved.size != intensity.size:
                message = (
                    f"{file_key}: saved baseline length {saved.size} does not "
                    f"match spectrum length {intensity.size} -- the saved column "
                    "was written over a different wavenumber window; recomputing "
                    "instead"
                )
                LOGGER.warning(message)
                warnings.append(message)
            elif np.isnan(saved).all():
                message = f"{file_key}: saved baseline column is all NaN; recomputing"
                LOGGER.warning(message)
                warnings.append(message)
            else:
                return saved, "saved"

    _, baseline = create_baseline(
        intensity,
        ir_config.get_baseline_settings(voigt_settings, override=baseline_settings),
    )
    return np.asarray(baseline, dtype=float), "recompute"


def reconstruct_live_curves(
    df_file_params: pd.DataFrame,
    wavenumbers: np.ndarray,
) -> list[PeakCurve]:
    """Rebuild the saved peaks' Voigt curves from their stored parameters.

    Same reconstruction ``plot_spectrum_fit.py::_build_delta_group_fit``
    performs. Rows with any NaN shape parameter (a skipped fit) contribute
    nothing.
    """
    curves: list[PeakCurve] = []
    required = ["Y0", "Amplitude", "Center", "Sigma", "Gamma"]
    usable = df_file_params.dropna(subset=required)
    for _, row in usable.iterrows():
        curve = voigt_model(
            wavenumbers,
            float(row["Y0"]),
            float(row["Amplitude"]),
            float(row["Center"]),
            float(row["Sigma"]),
            float(row["Gamma"]),
        )
        curves.append(
            PeakCurve(
                peak_name=str(row["Peak_Name"]),
                peak_value=float(row["Peak_Value"]),
                center=float(row["Center"]),
                amplitude=float(row["Amplitude"]),
                sigma=float(row["Sigma"]),
                gamma=float(row["Gamma"]),
                y0=float(row["Y0"]),
                fwhm=float(row.get("fwhm", np.nan)),
                peak_area=float(row.get("Peak_Area", np.nan)),
                curve=curve,
                is_new=False,
            )
        )
    return curves


def _warn_on_default_rule(
    peaks: list[int],
    voigt_settings: dict,
    warnings: list[str],
) -> None:
    """Warn when a peak falls through to the catch-all param rule.

    ``select_param_rule`` returns the ``range_cm1: [0, 0]`` / ``default: true``
    entry when nothing matches, and that default caps ``sigma`` at 6.37 and
    ``gamma`` at 2.8 -- far too narrow for the broad low-wavenumber bands, and
    silent. Replacing the catch-all is deferred (spec.md section 12); surfacing
    when it fires is not.
    """
    rules = get_shifted_rules(voigt_settings)
    for peak in peaks:
        rule = select_param_rule(peak, rules)
        if rule is None or not rule.get("default"):
            continue
        sigma_max = rule.get("sigma", {}).get("max")
        gamma_max = rule.get("gamma", {}).get("max")
        message = (
            f"Peak_{peak} matched no range_cm1 rule and fell through to the "
            f"catch-all default (sigma.max={sigma_max}, gamma.max={gamma_max}). "
            "Add an explicit rule in voigt_fit.param_rules for this peak."
        )
        LOGGER.warning(message)
        warnings.append(message)


def _warn_on_pinned_params(
    peak: int,
    fitted: Parameters,
    voigt_settings: dict,
    warnings: list[str],
) -> None:
    """Warn for every fitted parameter sitting on one of its bounds.

    A parameter at its bound means the optimizer wanted to go further and the
    rule stopped it, so the value is an artefact of the bound rather than of the
    data. Two cases matter especially:

    - ``sigma`` at its maximum means the band is wider than the rule allows and
      its tails may reach the existing peak cluster, which is the condition
      under which append-only fitting stops being safe (spec.md section 5).
    - ``center`` at a bound means the peak wants to sit outside the window the
      rule allows, i.e. the seeded wavenumber is probably wrong.

    Logged at DEBUG because a measurement has dozens of files; ``api.py``
    aggregates the collected messages into one WARNING per run.
    """
    rule = select_param_rule(peak, get_shifted_rules(voigt_settings))
    if rule is None:
        return

    for name in ("center", "amplitude", "sigma", "gamma"):
        param = fitted.get(f"{name}_{peak}")
        if param is None or not param.vary:
            continue
        for edge, bound in (("min", param.min), ("max", param.max)):
            if bound is None or not np.isfinite(bound):
                continue
            if not np.isclose(param.value, float(bound), rtol=1e-4, atol=1e-9):
                continue
            detail = ""
            if name == "sigma" and edge == "max":
                detail = (
                    f" (Gaussian FWHM ~{voigt_fwhm(param.value, 0.0):.0f} cm-1; "
                    "band may not be isolated -- consider append_only=False)"
                )
            elif name == "center":
                detail = " (seeded wavenumber may be wrong for this band)"
            message = (
                f"Peak_{peak}: fitted {name} pinned at its {edge} bound "
                f"({bound:g}){detail}"
            )
            LOGGER.debug(message)
            warnings.append(message)


def fit_subifg_file(
    subifg_path: Path,
    df_measurement_params: pd.DataFrame,
    df_saved_baseline: pd.DataFrame | None,
    *,
    voigt_settings: dict,
    extra_peaks: list[int],
    append_only: bool = True,
    baseline: str = "saved",
    on_existing: str = "skip",
    baseline_settings: dict | None = None,
) -> FileFitResult | None:
    """Fit the ``ir_fitting`` peaks for one subIFG file.

    Returns ``None`` when the file is skipped by ``manually_skip_files``, so
    offline coverage matches the live path exactly.

    ``baseline_settings`` overrides the baseline settings for this call only
    (see :func:`resolve_baseline`).
    """
    if on_existing not in {"skip", "overwrite", "error"}:
        raise ValueError(
            f"on_existing must be 'skip', 'overwrite' or 'error'; got {on_existing!r}"
        )

    file_key = file_key_for(subifg_path)
    delta_group, file_index = split_file_key(file_key)
    if manually_skip_files(delta_group, file_index):
        return None

    warnings: list[str] = []
    arr_roi = load_subifg_roi(subifg_path)
    wavenumbers = arr_roi[:, 0]
    intensity = arr_roi[:, 1]

    baseline_values, baseline_source = resolve_baseline(
        wavenumbers,
        intensity,
        file_key,
        df_saved_baseline,
        baseline,
        voigt_settings,
        warnings,
        baseline_settings=baseline_settings,
    )
    corrected = intensity - baseline_values

    df_file_params = (
        df_measurement_params.loc[df_measurement_params["File"] == file_key]
        if not df_measurement_params.empty
        else df_measurement_params
    )

    peaks_to_fit: list[int] = []
    skipped_peaks: list[str] = []

    if append_only:
        # Decide which of the ir_fitting peaks this run fits, and which saved
        # rows to keep. on_existing is a question about appending, so it is
        # evaluated only here -- a full refit produces a row for every peak and
        # has nothing to append onto.
        existing_names = set(df_file_params.get("Peak_Name", pd.Series(dtype=str)))
        for peak in extra_peaks:
            name = ir_config.peak_name(peak)
            if name not in existing_names:
                peaks_to_fit.append(peak)
                continue
            if on_existing == "error":
                raise ExistingPeakRowsError(
                    f"{file_key}: {name} already has a row in the params CSV. "
                    "Pass on_existing='overwrite' to replace it, or 'skip' to "
                    "keep it."
                )
            if on_existing == "overwrite":
                peaks_to_fit.append(peak)
                continue
            LOGGER.info("%s: %s already fitted; skipping", file_key, name)
            skipped_peaks.append(name)

        # Reconstruct the saved peaks and subtract them, so the optimizer sees
        # only what the existing model does not already explain. Fitting the new
        # peaks against the raw corrected spectrum would let the unmodelled
        # carbonyl cluster distort them.
        refitted = {ir_config.peak_name(peak) for peak in peaks_to_fit}
        keep = df_file_params
        if refitted and not keep.empty:
            keep = keep.loc[~keep["Peak_Name"].isin(refitted)]
        live_curves = reconstruct_live_curves(keep, wavenumbers)
    else:
        # Full refit: every peak is solved jointly against the corrected
        # spectrum, so nothing is reconstructed and nothing is skipped.
        live_curves = []
        peaks_to_fit = sorted(
            set(ir_config.get_live_peaks(voigt_settings)) | set(extra_peaks),
            reverse=True,
        )

    live_composite = np.zeros_like(wavenumbers)
    for curve in live_curves:
        live_composite += curve.curve

    target = corrected - live_composite

    new_curves: list[PeakCurve] = []
    new_rows: list[dict] = []
    if peaks_to_fit:
        _warn_on_default_rule(peaks_to_fit, voigt_settings, warnings)

        # All peaks this run fits go into one Parameters set and are solved
        # jointly: 1795 and 1775 are 20 cm-1 apart with sigma.max 26, so they
        # overlap each other and cannot be fitted independently.
        fit_params = Parameters()
        for peak in peaks_to_fit:
            add_params(fit_params, peak, peak, file_index, None, voigt_settings)

        result = peak_fit(fit_params, wavenumbers, target, peaks_to_fit)
        fitted = result.params

        data_integral, time_delta = _carry_file_columns(df_file_params)

        for peak in peaks_to_fit:
            center = fitted[f"center_{peak}"].value
            amplitude = fitted[f"amplitude_{peak}"].value
            sigma = fitted[f"sigma_{peak}"].value
            gamma = fitted[f"gamma_{peak}"].value
            y0 = fitted[f"y0_{peak}"].value

            curve = voigt_model(wavenumbers, y0, amplitude, center, sigma, gamma)
            # Wavenumbers run descending, so trapezoid is negative for a
            # positive band; negating matches peak_analysis's convention.
            area = float(-trapezoid(curve, wavenumbers))
            fwhm = voigt_fwhm(sigma, gamma)

            _warn_on_pinned_params(peak, fitted, voigt_settings, warnings)

            name = ir_config.peak_name(peak)
            new_curves.append(
                PeakCurve(
                    peak_name=name,
                    peak_value=float(peak),
                    center=float(center),
                    amplitude=float(amplitude),
                    sigma=float(sigma),
                    gamma=float(gamma),
                    y0=float(y0),
                    fwhm=float(fwhm),
                    peak_area=area,
                    curve=curve,
                    is_new=True,
                )
            )
            new_rows.append(
                {
                    "File": file_key,
                    "Delta_Group": delta_group,
                    "Peak_Name": name,
                    # Peak_Value is the nominal shifted wavenumber. The live
                    # path's FSD snapping (resolve_peak_lists) compares array
                    # indices against wavenumbers and so has matched nothing
                    # since nn1120-3_pd_ceo2_001; nominal reproduces current
                    # live output exactly.
                    "Peak_Value": float(peak),
                    "Data_Integral": data_integral,
                    "Time_Delta (s)": time_delta,
                    "Peak_Area": area,
                    "Center": float(center),
                    "Amplitude": float(amplitude),
                    "Sigma": float(sigma),
                    "Gamma": float(gamma),
                    "Y0": float(y0),
                    "fwhm": float(fwhm),
                }
            )

    curves = live_curves + new_curves
    composite = live_composite.copy()
    for curve in new_curves:
        composite += curve.curve

    return FileFitResult(
        file_key=file_key,
        delta_group=delta_group,
        subifg_path=subifg_path,
        wavenumbers=wavenumbers,
        raw=intensity,
        baseline=baseline_values,
        corrected=corrected,
        composite=composite,
        residual=composite - corrected,
        curves=curves,
        new_rows=new_rows,
        skipped_peaks=skipped_peaks,
        warnings=warnings,
        baseline_source=baseline_source,
    )


def _carry_file_columns(df_file_params: pd.DataFrame) -> tuple[float, float]:
    """Return ``(Data_Integral, Time_Delta (s))`` carried from existing rows.

    Both are per-file constants in the live output -- one unique value across
    every peak row of a file -- so copying is exact and avoids re-deriving the
    subIFG-log/exp-params chain.
    """
    if df_file_params.empty:
        return float("nan"), float("nan")
    integral = pd.to_numeric(df_file_params["Data_Integral"], errors="coerce").dropna()
    delta = pd.to_numeric(df_file_params["Time_Delta (s)"], errors="coerce").dropna()
    return (
        float(integral.iloc[0]) if not integral.empty else float("nan"),
        float(delta.iloc[0]) if not delta.empty else float("nan"),
    )
