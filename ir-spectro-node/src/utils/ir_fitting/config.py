"""Configuration access for the offline ``ir_fitting`` package.

Reads ``ir_fitting.fit`` in ``config/analysis.yaml``: a copy of ``voigt_fit``'s
keys (peak lists, groups, isotope shift, baseline settings, param rules) that
this package owns. The live ``voigt_fit`` block is never read here, so offline
refits and live output cannot leak into each other.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

path = Path(__file__).resolve().parents[3]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.core import config

LOGGER = logging.getLogger(__name__)

FIT_KEY = "ir_fitting.fit"

GROUP_KEYS = {
    "cluster": "cluster_peaks_base",
    "monomer": "monomer_peaks_base",
    "unknown": "unknown_peaks_base",
}


def get_fit_settings() -> dict:
    """Return the ``ir_fitting.fit`` settings block."""
    settings = config.get_analysis_setting(FIT_KEY)
    if not settings:
        raise KeyError(f"{FIT_KEY} is missing or empty in config/analysis.yaml")
    return settings


def _isotope_shift(fit_settings: dict) -> int:
    """Return the shift applied to 12CO base wavenumbers, as an int."""
    isotope = fit_settings.get("isotope_default", "13CO")
    shifts = fit_settings.get("isotope_shift_cm1", {})
    shift = shifts.get(isotope, 0)
    if shift != int(shift):
        raise ValueError(
            f"isotope_shift_cm1[{isotope!r}] = {shift!r} is not an integer. "
            "Peak_Name is formatted as Peak_<value> and must stay integral "
            "(Peak_1795, never Peak_1795.5)."
        )
    return int(shift)


def _shift_peaks(base_peaks: list, fit_settings: dict, source: str) -> list[int]:
    """Apply the isotope shift to a list of 12CO base wavenumbers."""
    shift = _isotope_shift(fit_settings)
    shifted: list[int] = []
    for peak in base_peaks:
        if peak != int(peak):
            raise ValueError(
                f"{source} contains {peak!r}, which is not an integer. "
                "Peak_Name must match the historic strings exactly "
                "(Peak_1795, not Peak_1795.0)."
            )
        shifted.append(int(peak) + shift)
    return shifted


def get_peaks(fit_settings: dict | None = None) -> list[int]:
    """Return the isotope-shifted peak list, highest wavenumber first."""
    fit_settings = fit_settings if fit_settings is not None else get_fit_settings()
    base_peaks = fit_settings.get("peak_list_base") or []
    if not base_peaks:
        raise ValueError(f"{FIT_KEY}.peak_list_base is empty")
    peaks = _shift_peaks(list(base_peaks), fit_settings, f"{FIT_KEY}.peak_list_base")
    if len(set(peaks)) != len(peaks):
        raise ValueError(f"{FIT_KEY}.peak_list_base has duplicate peaks")
    return sorted(peaks, reverse=True)


def get_group_peaks(group: str, fit_settings: dict | None = None) -> list[int]:
    """Return the isotope-shifted peaks of one group.

    ``group`` is one of ``"cluster"``, ``"monomer"``, ``"unknown"``. Groups do
    not affect fitting; they are recorded for kinetics and for promotion.
    """
    if group not in GROUP_KEYS:
        raise ValueError(f"group must be one of {sorted(GROUP_KEYS)}; got {group!r}")
    fit_settings = fit_settings if fit_settings is not None else get_fit_settings()
    base_peaks = fit_settings.get(GROUP_KEYS[group]) or []
    return _shift_peaks(
        list(base_peaks), fit_settings, f"{FIT_KEY}.{GROUP_KEYS[group]}"
    )


def peak_name(peak: int) -> str:
    """Format a shifted wavenumber as a ``Peak_Name`` string."""
    return f"Peak_{int(peak)}"


BASELINE_KEYS = frozenset(
    {
        "half_window",
        "interp_half_window",
        "fill_half_window",
        "num_std",
        "smooth_half_window",
        "weights",
    }
)
"""The settings ``create_baseline`` forwards to ``std_distribution``.

Used to reject a typo'd override key. ``create_baseline`` reads its settings
with ``.get(...)`` and silently falls back to a default, so ``num_stds: 1.4``
would run the *unmodified* baseline and look like "this parameter does
nothing" -- the most misleading possible outcome for a sweep.
"""


def get_baseline_settings(
    fit_settings: dict | None = None,
    override: dict | None = None,
) -> dict:
    """Return ``std_distribution`` settings for one baseline segment.

    ``ir_fitting.fit.baseline``, then ``override`` (a
    :class:`~src.utils.ir_fitting.baseline.BaselineVariant`'s ``settings``).
    """
    fit_settings = fit_settings if fit_settings is not None else get_fit_settings()
    settings = dict(fit_settings.get("baseline", {}))
    if override:
        unknown = set(override) - BASELINE_KEYS
        if unknown:
            raise ValueError(
                f"unknown baseline setting(s) {sorted(unknown)}; "
                f"expected any of {sorted(BASELINE_KEYS)}. "
                "create_baseline would ignore these silently."
            )
        settings.update(override)
    return settings
