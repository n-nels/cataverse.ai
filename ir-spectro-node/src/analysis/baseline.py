"""Anchored, lower-split baseline for the live spectral fit.

Port of the offline default recipe, ``BaselineVariant()`` in
``src/utils/ir_fitting/baseline.py`` (design and history: that package's
``spec.md`` section 5 and ``context/2026-09-17-baseline-investigation.md``).
The recipe's numbers live in ``voigt_fit.baseline_recipe``; the
``std_distribution`` settings in ``voigt_fit.baseline``.

``compute_baseline`` works in four steps:

1. ``create_baseline`` over the whole ROI.
2. An affine correction, least squares through the residual
   ``data - baseline`` at each anchor the guard lets through.
3. Below the cut, a second ``create_baseline`` on the lower samples, with its
   own affine correction from the lower anchors. Above the cut the curve is
   unchanged.
4. Splice the two.

The guard drops an anchor (or the cut) that has an extremum within
``anchor_guard_cm1`` whose prominence is at least ``anchor_prominence_frac``
of the whole-ROI signal range.
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from scipy.signal import find_peaks

from .spectral_fitting import create_baseline

LOGGER = logging.getLogger(__name__)

DEGENERATE_WARNING = "no baseline points"
"""Substring of the ``pybaselines`` warning that means the fit found nothing."""


@dataclass(frozen=True)
class BaselineRecipe:
    """``voigt_fit.baseline_recipe``. Anchor order and duplicates are kept."""

    anchors_cm1: tuple[float, ...]
    lower_split_cm1: float | None
    lower_anchors_cm1: tuple[float, ...]
    anchor_guard_cm1: float
    anchor_prominence_frac: float

    @classmethod
    def from_settings(cls, voigt_settings: dict) -> BaselineRecipe:
        recipe = voigt_settings.get("baseline_recipe")
        if not recipe:
            raise KeyError("voigt_fit.baseline_recipe is missing in config/analysis.yaml")
        split = recipe.get("lower_split_cm1")
        lower_anchors = tuple(float(a) for a in recipe.get("lower_anchors_cm1", []))
        if lower_anchors and split is None:
            raise ValueError("baseline_recipe has lower_anchors_cm1 but no lower_split_cm1")
        return cls(
            anchors_cm1=tuple(float(a) for a in recipe.get("anchors_cm1", [])),
            lower_split_cm1=None if split is None else float(split),
            lower_anchors_cm1=lower_anchors,
            anchor_guard_cm1=float(recipe["anchor_guard_cm1"]),
            anchor_prominence_frac=float(recipe["anchor_prominence_frac"]),
        )


@dataclass
class BaselineOutcome:
    """The baseline :func:`compute_baseline` produced."""

    values: np.ndarray
    degenerate: bool = False
    """``std_distribution`` found no baseline points on a segment; the curve
    is still returned (the file is still fitted), but is not meaningful."""
    anchors_applied: tuple[float, ...] = ()
    lower_anchors_applied: tuple[float, ...] = ()
    split_applied: float | None = None
    """Wavenumber the baseline was cut at; ``None`` if uncut or the cut was gated."""
    warnings: list[str] = field(default_factory=list)


def compute_baseline(
    wavenumbers: np.ndarray,
    intensity: np.ndarray,
    voigt_settings: dict,
) -> BaselineOutcome:
    """Return the anchored, lower-split baseline of one ROI spectrum."""
    wavenumbers = np.asarray(wavenumbers, dtype=float)
    intensity = np.asarray(intensity, dtype=float)
    recipe = BaselineRecipe.from_settings(voigt_settings)
    settings = voigt_settings.get("baseline", {})

    values, degenerate = _segment_baseline(intensity, settings)
    outcome = BaselineOutcome(values=values, degenerate=degenerate)
    if recipe.anchors_cm1:
        outcome.values, outcome.anchors_applied = apply_anchors(
            wavenumbers,
            intensity,
            values,
            recipe.anchors_cm1,
            guard_cm1=recipe.anchor_guard_cm1,
            prominence_frac=recipe.anchor_prominence_frac,
        )
    if recipe.lower_split_cm1 is not None:
        _apply_lower_split(wavenumbers, intensity, outcome, recipe, settings)
    if outcome.degenerate:
        outcome.warnings.append("degenerate baseline (no baseline points found)")
    return outcome


def _apply_lower_split(
    wavenumbers: np.ndarray,
    intensity: np.ndarray,
    outcome: BaselineOutcome,
    recipe: BaselineRecipe,
    settings: dict,
) -> None:
    """Replace the baseline below the cut with a second, anchored one, in place.

    A cut beside a dominant band is gated, and the unsplit baseline is kept.
    """
    cut = float(recipe.lower_split_cm1)
    if gating_extremum(
        wavenumbers,
        intensity,
        cut,
        guard_cm1=recipe.anchor_guard_cm1,
        prominence_frac=recipe.anchor_prominence_frac,
    ):
        LOGGER.debug("baseline cut at %.0f gated", cut)
        return

    # Split by wavenumber value, never by position: wavenumbers descend.
    upper = wavenumbers >= cut
    lower = ~upper
    if upper.sum() < 2 or lower.sum() < 2:
        raise ValueError(
            f"splitting at {cut:.0f} leaves {int(upper.sum())} / {int(lower.sum())} "
            "samples; each segment needs at least two"
        )

    lower_values, lower_degenerate = _segment_baseline(intensity[lower], settings)
    # The guard and data estimate read the FULL ROI: the prominence threshold
    # is a fraction of the whole ROI range, and the local fit at an anchor on
    # the cut would otherwise be one-sided.
    if recipe.lower_anchors_cm1:
        lower_values, outcome.lower_anchors_applied = apply_anchors(
            wavenumbers[lower],
            intensity[lower],
            lower_values,
            recipe.lower_anchors_cm1,
            guard_wavenumbers=wavenumbers,
            guard_intensity=intensity,
            guard_cm1=recipe.anchor_guard_cm1,
            prominence_frac=recipe.anchor_prominence_frac,
        )

    spliced = np.array(outcome.values, dtype=float, copy=True)
    spliced[lower] = lower_values
    outcome.values = spliced
    outcome.degenerate = outcome.degenerate or lower_degenerate
    outcome.split_applied = cut


def _segment_baseline(
    intensity: np.ndarray, settings: dict
) -> tuple[np.ndarray, bool]:
    """Run ``create_baseline``, flagging the "no baseline points" warning."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _, values = create_baseline(intensity, settings)
    degenerate = any(DEGENERATE_WARNING in str(item.message) for item in caught)
    return np.asarray(values, dtype=float), degenerate


def signal_range(y: np.ndarray) -> float:
    """``max(y) - min(y)``, or ``nan`` for a flat array."""
    span = float(np.nanmax(y) - np.nanmin(y))
    return span if span > 0 else float("nan")


def gating_extremum(
    wavenumbers: np.ndarray,
    intensity: np.ndarray,
    anchor: float,
    guard_cm1: float,
    prominence_frac: float,
) -> tuple[float, float] | None:
    """Return the dominant extremum within ``guard_cm1`` of ``anchor``, if any.

    Prominence is measured against the whole ROI signal range, not the local
    excursion: these spectra are oscillatory, so a locally scaled prominence
    would gate every anchor.
    """
    span = signal_range(intensity)
    if not np.isfinite(span) or span <= 0:
        return None

    best: tuple[float, float] | None = None
    for sign in (1, -1):
        indices, properties = find_peaks(sign * intensity, prominence=0.0)
        for index, prominence in zip(indices, properties["prominences"]):
            if abs(wavenumbers[index] - anchor) > guard_cm1:
                continue
            fraction = float(prominence) / span
            if fraction >= prominence_frac and (best is None or fraction > best[1]):
                best = (float(wavenumbers[index]), fraction)
    return best


def anchor_data_value(
    wavenumbers: np.ndarray,
    intensity: np.ndarray,
    anchor: float,
    half_width: float = 10.0,
) -> float:
    """Estimate the data's value at ``anchor`` by a local straight-line fit."""
    near = np.abs(wavenumbers - anchor) <= half_width
    if near.sum() < 2:
        return float(intensity[int(np.argmin(np.abs(wavenumbers - anchor)))])
    slope, intercept = np.polyfit(wavenumbers[near], intensity[near], 1)
    return float(slope * anchor + intercept)


def apply_anchors(
    wavenumbers: np.ndarray,
    intensity: np.ndarray,
    baseline: np.ndarray,
    anchors: Sequence[float],
    *,
    guard_wavenumbers: np.ndarray | None = None,
    guard_intensity: np.ndarray | None = None,
    guard_cm1: float,
    prominence_frac: float,
) -> tuple[np.ndarray, tuple[float, ...]]:
    """Add an affine correction fitted at every anchor the guard lets through.

    Three or more surviving anchors give a least-squares line, two the exact
    line through both, one a constant shift, none no change.
    ``guard_wavenumbers`` / ``guard_intensity`` are what the guard and data
    estimate read when they differ from the arrays being corrected (the full
    ROI, for the lower segment).
    """
    ascending = np.argsort(wavenumbers)
    grid_w = wavenumbers[ascending]
    grid_b = baseline[ascending]
    guard_w = wavenumbers if guard_wavenumbers is None else np.asarray(guard_wavenumbers, dtype=float)
    guard_y = intensity if guard_intensity is None else np.asarray(guard_intensity, dtype=float)
    # One grid step of tolerance keeps an anchor sitting exactly on a segment
    # edge -- 1955 under a cut at 1955.
    tolerance = float(np.median(np.diff(grid_w))) if grid_w.size > 1 else 0.0

    applied: list[float] = []
    residuals: list[tuple[float, float]] = []
    for anchor in anchors:
        if not grid_w[0] - tolerance <= anchor <= grid_w[-1] + tolerance:
            continue
        if gating_extremum(
            guard_w, guard_y, anchor, guard_cm1=guard_cm1, prominence_frac=prominence_frac
        ):
            continue
        value = anchor_data_value(guard_w, guard_y, anchor)
        residuals.append((float(anchor), value - float(np.interp(anchor, grid_w, grid_b))))
        applied.append(float(anchor))

    if not residuals:
        correction = np.zeros_like(baseline)
    elif len(residuals) == 1:
        correction = np.full_like(baseline, residuals[0][1])
    else:
        anchor_w = np.array([item[0] for item in residuals], dtype=float)
        anchor_d = np.array([item[1] for item in residuals], dtype=float)
        slope, intercept = np.polyfit(anchor_w, anchor_d, 1)
        correction = slope * wavenumbers + intercept

    return baseline + correction, tuple(applied)
