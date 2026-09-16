"""Configuration access for the offline ``ir_fitting`` EDA package.

Reads the ``ir_fitting`` block of ``config/analysis.yaml`` and applies the same
isotope shift ``src/analysis/spectral_fitting.py`` applies to
``voigt_fit.peak_list_base``, so both lists move together when the isotope
changes.
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

IR_FITTING_KEY = "ir_fitting"
VOIGT_KEY = "voigt_fit"

GROUP_KEYS = {
    "cluster": "extra_cluster_peaks_base",
    "monomer": "extra_monomer_peaks_base",
    "unknown": "extra_unknown_peaks_base",
}


def get_voigt_settings() -> dict:
    """Return the ``voigt_fit`` settings block."""
    return config.get_analysis_setting(VOIGT_KEY)


def get_ir_fitting_settings() -> dict:
    """Return the ``ir_fitting`` settings block, or an empty dict if absent."""
    try:
        settings = config.get_analysis_setting(IR_FITTING_KEY)
    except KeyError:
        return {}
    return settings or {}


def _isotope_shift(voigt_settings: dict) -> int:
    """Return the shift applied to 12CO base wavenumbers, as an int."""
    isotope = voigt_settings.get("isotope_default", "13CO")
    shifts = voigt_settings.get("isotope_shift_cm1", {})
    shift = shifts.get(isotope, 0)
    if shift != int(shift):
        raise ValueError(
            f"isotope_shift_cm1[{isotope!r}] = {shift!r} is not an integer. "
            "Peak_Name is formatted as Peak_<value> and must stay integral "
            "(Peak_1795, never Peak_1795.5)."
        )
    return int(shift)


def _shift_peaks(base_peaks: list, voigt_settings: dict, source: str) -> list[int]:
    """Apply the isotope shift to a list of 12CO base wavenumbers."""
    shift = _isotope_shift(voigt_settings)
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


def get_extra_peaks(voigt_settings: dict | None = None) -> list[int]:
    """Return the isotope-shifted ``ir_fitting`` peak list.

    An absent or empty ``extra_peaks_base`` is a valid no-op, not an error.
    """
    voigt_settings = (
        voigt_settings if voigt_settings is not None else get_voigt_settings()
    )
    base_peaks = get_ir_fitting_settings().get("extra_peaks_base") or []
    return _shift_peaks(list(base_peaks), voigt_settings, "ir_fitting.extra_peaks_base")


def get_extra_group_peaks(
    group: str,
    voigt_settings: dict | None = None,
) -> list[int]:
    """Return the isotope-shifted extra peaks for one group.

    ``group`` is one of ``"cluster"``, ``"monomer"``, ``"unknown"`` -- mirroring
    ``voigt_fit``'s ``*_peaks_base`` keys. Grouping is recorded here for later
    promotion into the live config; it does not affect fitting.
    """
    if group not in GROUP_KEYS:
        raise ValueError(f"group must be one of {sorted(GROUP_KEYS)}; got {group!r}")
    voigt_settings = (
        voigt_settings if voigt_settings is not None else get_voigt_settings()
    )
    base_peaks = get_ir_fitting_settings().get(GROUP_KEYS[group]) or []
    return _shift_peaks(
        list(base_peaks), voigt_settings, f"ir_fitting.{GROUP_KEYS[group]}"
    )


def peak_name(peak: int) -> str:
    """Format a shifted wavenumber as a ``Peak_Name`` string."""
    return f"Peak_{int(peak)}"


def get_extra_peak_names(voigt_settings: dict | None = None) -> list[str]:
    """Return ``Peak_Name`` strings for the ``ir_fitting`` peaks."""
    return [peak_name(peak) for peak in get_extra_peaks(voigt_settings)]


def get_live_peaks(voigt_settings: dict | None = None) -> list[int]:
    """Return the isotope-shifted ``voigt_fit.peak_list_base`` peak list."""
    voigt_settings = (
        voigt_settings if voigt_settings is not None else get_voigt_settings()
    )
    base_peaks = voigt_settings.get("peak_list_base") or []
    return _shift_peaks(list(base_peaks), voigt_settings, "voigt_fit.peak_list_base")


def get_baseline_settings(voigt_settings: dict | None = None) -> dict:
    """Return baseline settings for a recompute.

    Inherits ``voigt_fit.baseline``. An ``ir_fitting.baseline`` override is
    deferred (see ``spec.md`` section 6); if one is present it is merged over
    the inherited values so adding it later needs no code change here.
    """
    voigt_settings = (
        voigt_settings if voigt_settings is not None else get_voigt_settings()
    )
    settings = dict(voigt_settings.get("baseline", {}))
    override = get_ir_fitting_settings().get("baseline")
    if override:
        settings.update(override)
    return settings
