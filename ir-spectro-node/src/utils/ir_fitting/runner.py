"""Per-file orchestration for offline IR peak refits.

Every run is a full refit: all peaks in ``ir_fitting.fit.peak_list_base`` are
solved jointly against ``raw - baseline``, each existing peak starting from its
saved fit. The fit itself is the package's own copy in ``voigt.py``; nothing
here calls into ``src/analysis``. See ``spec-working.md``.
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

from src.utils.ir_fitting import config as ir_config
from src.utils.ir_fitting.baseline import (
    DEFAULT_WINDOW,
    BaselineVariant,
)
from src.utils.ir_fitting.result_types import FileFitResult, PeakCurve
from src.utils.ir_fitting.voigt import (
    add_params,
    get_shifted_rules,
    manually_skip_files,
    peak_fit,
    select_param_rule,
    voigt_fwhm,
    voigt_model,
)

LOGGER = logging.getLogger(__name__)

ROI_MAX_CM1, ROI_MIN_CM1 = DEFAULT_WINDOW

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

SEED_COLUMNS = {
    "center": "Center",
    "amplitude": "Amplitude",
    "sigma": "Sigma",
    "gamma": "Gamma",
    "y0": "Y0",
}
"""lmfit parameter prefix -> params CSV column the seed is read from."""


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
    the instrument. ``window`` is ``(high, low)`` cm-1 and is used by baseline
    runs only; the refit always uses the ROI.
    """
    high, low = window if window is not None else (ROI_MAX_CM1, ROI_MIN_CM1)
    df = pd.read_csv(subifg_path, header=None)
    roi = df.loc[(df[0] >= low) & (df[0] <= high)]
    if roi.empty:
        raise ValueError(
            f"No subIFG data in {low:.0f}-{high:.0f} cm-1 for {subifg_path}"
        )
    return np.asarray(roi.values, dtype=float)


def resolve_baseline(
    wavenumbers: np.ndarray,
    intensity: np.ndarray,
    file_key: str,
    df_saved_baseline: pd.DataFrame | None,
    mode: str,
    fit_settings: dict,
    warnings: list[str],
    variant: BaselineVariant | None = None,
) -> tuple[np.ndarray, str]:
    """Return ``(baseline, source)`` for one file.

    ``"recompute"`` runs ``variant`` -- ``BaselineVariant()``, the anchored
    two-segment recipe, when ``None``. ``"saved"`` reads the file's column from
    ``*_CarbonylFitBaseline.csv`` and exists for the parity gate and for
    inspecting the old fit; when that column is unusable it falls back to the
    recipe, with a warning.
    """
    if mode not in {"saved", "recompute"}:
        raise ValueError(f"baseline must be 'saved' or 'recompute'; got {mode!r}")

    if mode == "saved":
        saved = _saved_baseline_column(
            file_key, df_saved_baseline, intensity.size, warnings
        )
        if saved is not None:
            return saved, "saved"

    variant = variant if variant is not None else BaselineVariant()
    if tuple(variant.window) != (ROI_MAX_CM1, ROI_MIN_CM1):
        raise ValueError(
            f"variant {variant.label!r} window {variant.window!r} differs from the "
            f"fit ROI {(ROI_MAX_CM1, ROI_MIN_CM1)!r}; the baseline must span the "
            "spectrum it corrects"
        )
    outcome = variant.compute(intensity, fit_settings, wavenumbers)
    if outcome.degenerate:
        message = f"{file_key}: degenerate baseline (no baseline points found)"
        warnings.append(message)
    return np.asarray(outcome.values, dtype=float), "recompute"


def _saved_baseline_column(
    file_key: str,
    df_saved_baseline: pd.DataFrame | None,
    size: int,
    warnings: list[str],
) -> np.ndarray | None:
    """Return a file's saved baseline column, or ``None`` with a warning."""
    if df_saved_baseline is None or file_key not in df_saved_baseline.columns:
        message = f"{file_key}: no saved baseline column; recomputing instead"
    else:
        saved = np.asarray(
            pd.to_numeric(df_saved_baseline[file_key], errors="coerce"), dtype=float
        )
        # Require an exact length match rather than truncating: wavenumbers
        # descend, so a head-slice would pass a size check while sitting out
        # of register with the spectrum.
        if saved.size != size:
            message = (
                f"{file_key}: saved baseline length {saved.size} does not match "
                f"spectrum length {size}; recomputing instead"
            )
        elif np.isnan(saved).all():
            message = f"{file_key}: saved baseline column is all NaN; recomputing"
        else:
            return saved
    LOGGER.warning(message)
    warnings.append(message)
    return None


def reconstruct_saved_curves(
    df_file_params: pd.DataFrame,
    wavenumbers: np.ndarray,
) -> list[PeakCurve]:
    """Rebuild the saved peaks' Voigt curves from their stored parameters.

    Same reconstruction ``plot_spectrum_fit.py::_build_delta_group_fit``
    performs. Rows with any NaN shape parameter (a skipped fit) contribute
    nothing.
    """
    curves: list[PeakCurve] = []
    required = list(SEED_COLUMNS.values())
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


def saved_seeds(df_file_params: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Map ``Peak_Name`` -> seed values from one file's saved rows.

    Rows with any non-finite shape parameter are dropped, so that peak starts
    from its rule. A duplicated ``Peak_Name`` (corrupt history) keeps the last
    row, the most recently appended.
    """
    seeds: dict[str, dict[str, float]] = {}
    if df_file_params.empty:
        return seeds
    for _, row in df_file_params.iterrows():
        values = {
            name: pd.to_numeric(row.get(column), errors="coerce")
            for name, column in SEED_COLUMNS.items()
        }
        if all(np.isfinite(value) for value in values.values()):
            seeds[str(row["Peak_Name"])] = {k: float(v) for k, v in values.items()}
    return seeds


def _rules_for(
    peaks: list[int],
    fit_settings: dict,
    warnings: list[str],
) -> dict[int, dict]:
    """Return each peak's param rule, warning when one hits the catch-all.

    ``select_param_rule`` returns the ``default: true`` entry when nothing
    matches; that default caps ``sigma`` at 6.37 and ``gamma`` at 2.8, which is
    silent and usually wrong for a peak someone just added.
    """
    all_rules = get_shifted_rules(fit_settings)
    rules: dict[int, dict] = {}
    for peak in peaks:
        rule = select_param_rule(peak, all_rules)
        if rule is None:
            raise ValueError(
                f"Peak_{peak} matches no param rule and there is no default rule"
            )
        if rule.get("default"):
            message = (
                f"Peak_{peak} matched no range_cm1 rule and fell through to the "
                "catch-all default. Add an explicit rule in "
                "ir_fitting.fit.param_rules for this peak."
            )
            LOGGER.warning(message)
            warnings.append(message)
        rules[peak] = rule
    return rules


def _warn_on_pinned_params(
    peak: int,
    fitted: Parameters,
    warnings: list[str],
) -> None:
    """Warn for every fitted parameter sitting on one of its bounds.

    A parameter at its bound means the optimizer wanted to go further and the
    rule stopped it, so the value is an artefact of the bound rather than of the
    data. ``center`` at a bound usually means the seeded wavenumber is wrong;
    two neighbours both pinned toward each other suggest one band, not two.

    Logged at DEBUG because a measurement has dozens of files; ``api.py``
    aggregates the collected messages into one WARNING per run.
    """
    for name in ("center", "amplitude", "sigma", "gamma"):
        param = fitted.get(f"{name}_{peak}")
        if param is None or not param.vary:
            continue
        for edge, bound in (("min", param.min), ("max", param.max)):
            if bound is None or not np.isfinite(bound):
                continue
            if not np.isclose(param.value, float(bound), rtol=1e-4, atol=1e-9):
                continue
            message = f"Peak_{peak}: fitted {name} pinned at its {edge} bound ({bound:g})"
            LOGGER.debug(message)
            warnings.append(message)


def _file_rows(
    df_saved_params: pd.DataFrame,
    file_key: str,
) -> pd.DataFrame:
    """Return one file's saved rows (empty frame if none)."""
    if df_saved_params.empty:
        return df_saved_params
    return df_saved_params.loc[df_saved_params["File"] == file_key]


def fit_subifg_file(
    subifg_path: Path,
    df_saved_params: pd.DataFrame,
    df_saved_baseline: pd.DataFrame | None,
    *,
    fit_settings: dict,
    baseline: str = "recompute",
    variant: BaselineVariant | None = None,
) -> FileFitResult | None:
    """Refit every configured peak for one subIFG file.

    Returns ``None`` when the file is skipped by ``manually_skip_files``, so
    offline coverage matches the live path exactly.

    Each peak starts from its saved ``(File, Peak_Name)`` row when one exists
    with finite values, else from its rule. Bounds always come from the rule
    around the nominal wavenumber, never around the seed, so centers cannot
    walk across repeated refits.
    """
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
        fit_settings,
        warnings,
        variant=variant,
    )
    corrected = intensity - baseline_values

    df_file_params = _file_rows(df_saved_params, file_key)
    seeds = saved_seeds(df_file_params)

    peaks = ir_config.get_peaks(fit_settings)
    rules = _rules_for(peaks, fit_settings, warnings)

    fit_params = Parameters()
    n_clipped = n_nudged = 0
    for peak in peaks:
        clipped, nudged = add_params(
            fit_params, peak, rules[peak], seeds.get(ir_config.peak_name(peak))
        )
        n_clipped += clipped
        n_nudged += nudged
    if n_clipped:
        warnings.append(
            f"{file_key}: {n_clipped} seed value(s) outside their rule bounds, "
            "clipped to the bound"
        )

    result = peak_fit(fit_params, wavenumbers, corrected, peaks)
    if not result.success:
        warnings.append(
            f"{file_key}: fit did not converge ({result.message}); the values "
            "are wherever the optimizer stopped"
        )
    fitted = result.params
    data_integral, time_delta = _carry_file_columns(df_file_params)

    curves: list[PeakCurve] = []
    rows: list[dict] = []
    composite = np.zeros_like(wavenumbers)
    for peak in peaks:
        center = float(fitted[f"center_{peak}"].value)
        amplitude = float(fitted[f"amplitude_{peak}"].value)
        sigma = float(fitted[f"sigma_{peak}"].value)
        gamma = float(fitted[f"gamma_{peak}"].value)
        y0 = float(fitted[f"y0_{peak}"].value)

        curve = voigt_model(wavenumbers, y0, amplitude, center, sigma, gamma)
        composite += curve
        # Wavenumbers run descending, so trapezoid is negative for a positive
        # band; negating matches the live peak_analysis convention.
        area = float(-trapezoid(curve, wavenumbers))
        fwhm = float(voigt_fwhm(sigma, gamma))
        _warn_on_pinned_params(peak, fitted, warnings)

        name = ir_config.peak_name(peak)
        curves.append(
            PeakCurve(
                peak_name=name,
                peak_value=float(peak),
                center=center,
                amplitude=amplitude,
                sigma=sigma,
                gamma=gamma,
                y0=y0,
                fwhm=fwhm,
                peak_area=area,
                curve=curve,
                is_new=name not in seeds,
            )
        )
        rows.append(
            {
                "File": file_key,
                "Delta_Group": delta_group,
                "Peak_Name": name,
                # Nominal shifted wavenumber: the live FSD snapping compares
                # indices against wavenumbers and never matches, so nominal is
                # what live output holds.
                "Peak_Value": float(peak),
                "Data_Integral": data_integral,
                "Time_Delta (s)": time_delta,
                "Peak_Area": area,
                "Center": center,
                "Amplitude": amplitude,
                "Sigma": sigma,
                "Gamma": gamma,
                "Y0": y0,
                "fwhm": fwhm,
            }
        )

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
        rows=rows,
        warnings=warnings,
        baseline_source=baseline_source,
        n_seeded=sum(1 for peak in peaks if ir_config.peak_name(peak) in seeds),
        n_clipped=n_clipped,
        n_nudged=n_nudged,
        nfev=int(result.nfev),
        fit_success=bool(result.success),
    )


def load_subifg_file(
    subifg_path: Path,
    df_saved_params: pd.DataFrame,
    df_saved_baseline: pd.DataFrame | None,
    *,
    fit_settings: dict,
    baseline: str = "saved",
    variant: BaselineVariant | None = None,
) -> FileFitResult | None:
    """Load one file and rebuild its saved fit, fitting nothing.

    For inspection and plotting of the existing fit. Returns ``None`` for files
    ``manually_skip_files`` excludes.
    """
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
        fit_settings,
        warnings,
        variant=variant,
    )
    corrected = intensity - baseline_values

    curves = reconstruct_saved_curves(
        _file_rows(df_saved_params, file_key), wavenumbers
    )
    composite = np.zeros_like(wavenumbers)
    for curve in curves:
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
