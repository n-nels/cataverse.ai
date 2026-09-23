"""Anchored, lower-split baseline for offline reprocessing.

:class:`BaselineVariant` is one baseline recipe: ``create_baseline`` over a
wavenumber window, an affine correction fitted at anchor points, and an
optional second baseline below a cut with its own anchors. The design record
is ``spec.md`` section 9; its history is in ``context/``.
"""

from __future__ import annotations

import logging
import sys
import warnings
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks

path = Path(__file__).resolve().parents[3]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.analysis.spectral_fitting import create_baseline
from src.utils.ir_fitting import config as ir_config

LOGGER = logging.getLogger(__name__)

Window = tuple[float, float]

DEFAULT_WINDOW: Window = (2250.0, 1750.0)
"""``(high, low)`` cm-1, matching ``io.py::import_data``'s ROI."""

DEGENERATE_WARNING = "no baseline points"
"""Substring of the ``pybaselines`` warning that means the fit found nothing."""

DEFAULT_FOLDER = "nn1120-4_pd_ceo2_000"
"""Dataset :data:`DEFAULT_FILES` belongs to."""

DEFAULT_FILES: tuple[str, ...] = (
    "20260715_094622_pd_ceo2_000-007_delta10.0042",
    "20260717_203829_pd_ceo2_000-008_delta10.0042",
    "20260728_032548_pd_ceo2_000-012_delta10.0052",
    "20260806_105210_pd_ceo2_000-017_delta10.0022",
    "20260811_072450_pd_ceo2_000-021_delta10.0022",
    "20260825_052349_pd_ceo2_000-027_delta10.0052",
    "20260813_195617_pd_ceo2_000-022_delta10.0022",
    "20260813_195617_pd_ceo2_000-022_delta10.0042",
)
"""subIFG files run when none are named -- the eight in spec.md section 9."""

ANCHOR_POINTS_CM1: tuple[float, ...] = (2240.0, 2006.0, 1955.0, 1955.0, 1955.0)
"""Default full-ROI anchors. Order and duplicates are kept.

Each entry is one residual in the least-squares correction, so a repeat is an
integer weight: 1955 is listed three times for triple weight. Never deduplicate.
"""

LOWER_ANCHOR_POINTS_CM1: tuple[float, ...] = (1955.0, 1800.0, 1820.0)
"""Default anchors for the segment below :data:`LOWER_SPLIT_POINT_CM1`."""

LOWER_SPLIT_POINT_CM1 = 1955.0
"""Default cut. Below it a second ``create_baseline`` replaces the first."""

ANCHOR_GUARD_CM1 = 25.0
"""Half-width of the window an anchor (or the cut) is rejected for containing
a dominant extremum."""

ANCHOR_PROMINENCE_FRAC = 0.5
"""Prominence, as a fraction of the file's **whole ROI** signal range, that
makes an extremum dominant enough to gate an anchor or the cut."""


@dataclass
class BaselineOutcome:
    """The baseline :meth:`BaselineVariant.compute` produced."""

    values: np.ndarray
    degenerate: bool = False
    anchors_applied: tuple[float, ...] = ()
    lower_anchors_applied: tuple[float, ...] = ()
    split_applied: float | None = None
    """Wavenumber the baseline was cut at; ``None`` if uncut or the cut was gated."""


@dataclass(frozen=True)
class BaselineVariant:
    """One baseline recipe.

    Args:
        label: Name shown in figure legends.
        settings: Overrides for ``std_distribution``, any of
            ``config.BASELINE_KEYS``; omitted keys keep their
            ``config/analysis.yaml`` value. Applies to the full-ROI curve only.
        window: ``(high, low)`` cm-1 extent handed to ``create_baseline``.
        anchors: Wavenumbers the full-ROI baseline is pulled toward by an
            affine correction. ``()`` leaves it unanchored.
        lower_split_cm1: Cut below which a second, independently computed
            baseline replaces the first, or ``None`` for one baseline.
        lower_anchors: The lower segment's own anchors. Require a cut.
        anchor_guard_cm1: See :data:`ANCHOR_GUARD_CM1`.
        anchor_prominence_frac: See :data:`ANCHOR_PROMINENCE_FRAC`.
    """

    label: str
    settings: dict = field(default_factory=dict)
    window: Window = DEFAULT_WINDOW
    anchors: tuple[float, ...] = ()
    lower_split_cm1: float | None = None
    lower_anchors: tuple[float, ...] = ()
    anchor_guard_cm1: float = ANCHOR_GUARD_CM1
    anchor_prominence_frac: float = ANCHOR_PROMINENCE_FRAC

    def __post_init__(self) -> None:
        high, low = self.window
        if not high > low:
            raise ValueError(
                f"window must be (high, low) with high > low; got {self.window!r}"
            )
        # Validate eagerly: create_baseline reads settings with .get(), so a
        # typo'd key would silently run the unmodified baseline.
        ir_config.get_baseline_settings(override=dict(self.settings) or None)

        for name in ("anchor_guard_cm1", "anchor_prominence_frac"):
            value = float(getattr(self, name))
            object.__setattr__(self, name, value)
            if not np.isfinite(value):
                raise ValueError(f"{name} must be finite; got {value!r}")
        if self.anchor_guard_cm1 < 0:
            raise ValueError(
                f"anchor_guard_cm1 must be >= 0; got {self.anchor_guard_cm1!r}"
            )
        if self.anchor_prominence_frac <= 0:
            raise ValueError(
                "anchor_prominence_frac must be > 0; got "
                f"{self.anchor_prominence_frac!r}"
            )

        object.__setattr__(self, "anchors", tuple(float(a) for a in self.anchors))
        for anchor in self.anchors:
            if not low <= anchor <= high:
                raise ValueError(
                    f"anchor {anchor:.0f} cm-1 lies outside the window {self.window!r}"
                )

        object.__setattr__(
            self, "lower_anchors", tuple(float(a) for a in self.lower_anchors)
        )
        if self.lower_anchors and self.lower_split_cm1 is None:
            raise ValueError(
                f"variant {self.label!r} declares lower_anchors but no "
                "lower_split_cm1; there is no lower segment to anchor"
            )

        if self.lower_split_cm1 is not None:
            object.__setattr__(self, "lower_split_cm1", float(self.lower_split_cm1))
            if not low < self.lower_split_cm1 < high:
                raise ValueError(
                    f"lower_split_cm1 {self.lower_split_cm1:.0f} must lie strictly "
                    f"inside the window {self.window!r}"
                )

        for anchor in self.lower_anchors:
            if not low <= anchor <= self.lower_split_cm1:
                raise ValueError(
                    f"lower anchor {anchor:.0f} cm-1 must lie between the window "
                    f"floor {low:.0f} and the cut {self.lower_split_cm1:.0f}"
                )

    def compute(
        self,
        intensity: np.ndarray,
        voigt_settings: dict | None = None,
        wavenumbers: np.ndarray | None = None,
    ) -> BaselineOutcome:
        """Return the baseline for one intensity array.

        ``wavenumbers`` is required whenever anchors or a cut are set.
        """
        intensity = np.asarray(intensity, dtype=float)
        if (self.anchors or self.lower_split_cm1 is not None) and wavenumbers is None:
            raise ValueError(
                f"variant {self.label!r} declares anchors or a cut but compute() "
                "was called without wavenumbers"
            )

        settings = ir_config.get_baseline_settings(
            voigt_settings, override=dict(self.settings) or None
        )
        values, degenerate = self._segment_baseline(intensity, settings, "")
        outcome = BaselineOutcome(values=values, degenerate=degenerate)
        if self.anchors:
            outcome.values, outcome.anchors_applied = apply_anchors(
                np.asarray(wavenumbers, dtype=float),
                intensity,
                values,
                self.anchors,
                guard_cm1=self.anchor_guard_cm1,
                prominence_frac=self.anchor_prominence_frac,
            )

        if self.lower_split_cm1 is None:
            return outcome
        return self._compute_lower_split(
            np.asarray(wavenumbers, dtype=float), intensity, outcome, voigt_settings
        )

    def _compute_lower_split(
        self,
        wavenumbers: np.ndarray,
        intensity: np.ndarray,
        outcome: BaselineOutcome,
        voigt_settings: dict | None,
    ) -> BaselineOutcome:
        """Replace the baseline below the cut with a second, anchored one.

        The full-ROI curve is computed and anchored first (in :meth:`compute`),
        so at and above the cut the result is exactly the unsplit anchored
        baseline. A cut beside a dominant band is gated, and the unsplit
        baseline is returned as is.
        """
        cut = float(self.lower_split_cm1)
        if gating_extremum(
            wavenumbers,
            intensity,
            cut,
            guard_cm1=self.anchor_guard_cm1,
            prominence_frac=self.anchor_prominence_frac,
        ):
            LOGGER.debug("variant %r: cut at %.0f gated", self.label, cut)
            return outcome

        # Split by wavenumber value, never by position: wavenumbers descend.
        upper = wavenumbers >= cut
        lower = ~upper
        if upper.sum() < 2 or lower.sum() < 2:
            raise ValueError(
                f"variant {self.label!r}: splitting at {cut:.0f} leaves "
                f"{int(upper.sum())} / {int(lower.sum())} samples; each segment "
                "needs at least two"
            )

        # The lower segment runs on the unmodified voigt_fit.baseline settings;
        # this variant's `settings` belong to the full-ROI curve.
        lower_values, lower_degenerate = self._segment_baseline(
            intensity[lower], ir_config.get_baseline_settings(voigt_settings), "lower"
        )

        # The guard and data estimate read the FULL ROI: the prominence
        # threshold is a fraction of the whole ROI range, and the local fit at
        # an anchor on the cut would otherwise be one-sided.
        if self.lower_anchors:
            lower_values, outcome.lower_anchors_applied = apply_anchors(
                wavenumbers[lower],
                intensity[lower],
                lower_values,
                self.lower_anchors,
                guard_wavenumbers=wavenumbers,
                guard_intensity=intensity,
                guard_cm1=self.anchor_guard_cm1,
                prominence_frac=self.anchor_prominence_frac,
            )

        spliced = np.array(outcome.values, dtype=float, copy=True)
        spliced[lower] = lower_values
        outcome.values = spliced
        outcome.degenerate = outcome.degenerate or lower_degenerate
        outcome.split_applied = cut
        return outcome

    def _segment_baseline(
        self,
        intensity: np.ndarray,
        settings: dict,
        segment: str,
    ) -> tuple[np.ndarray, bool]:
        """Run ``create_baseline``, flagging the "no baseline points" warning.

        ``std_distribution`` still returns a plausible-looking curve in that
        case, so it has to be surfaced.
        """
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _, values = create_baseline(intensity, settings)
        degenerate = any(DEGENERATE_WARNING in str(item.message) for item in caught)
        if degenerate:
            LOGGER.warning(
                "variant %r produced a degenerate baseline%s (no baseline points "
                "found); the curve is not meaningful",
                self.label,
                f" on its {segment} segment" if segment else "",
            )
        return np.asarray(values, dtype=float), degenerate


def signal_range(y: np.ndarray) -> float:
    """``max(y) - min(y)``, or ``nan`` for a flat array."""
    span = float(np.nanmax(y) - np.nanmin(y))
    return span if span > 0 else float("nan")


def gating_extremum(
    wavenumbers: np.ndarray,
    intensity: np.ndarray,
    anchor: float,
    guard_cm1: float = ANCHOR_GUARD_CM1,
    prominence_frac: float = ANCHOR_PROMINENCE_FRAC,
) -> tuple[float, float] | None:
    """Return the dominant extremum within ``guard_cm1`` of ``anchor``, if any.

    Prominence is measured against the whole ROI signal range, not the local
    excursion -- these spectra are oscillatory, so a locally scaled prominence
    would gate every anchor.

    Returns:
        ``(wavenumber, prominence fraction)`` of the most prominent qualifying
        extremum, or ``None`` when the region is clear.
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
    guard_cm1: float = ANCHOR_GUARD_CM1,
    prominence_frac: float = ANCHOR_PROMINENCE_FRAC,
) -> tuple[np.ndarray, tuple[float, ...]]:
    """Add an affine correction fitted at every anchor the guard lets through.

    Residuals ``data(w) - baseline(w)`` at the surviving anchors set the
    correction: three or more give a least-squares line (no anchor is hit
    exactly), two give the exact line through both, one gives a constant
    shift, and none leaves the baseline unchanged.

    ``guard_wavenumbers`` / ``guard_intensity`` are the arrays the guard and
    data estimate read when they differ from the array being corrected (the
    full ROI, for the lower segment).

    Returns:
        ``(corrected baseline, anchors applied)``.
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
