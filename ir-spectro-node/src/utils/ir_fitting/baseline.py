"""Baseline variants for offline baseline experimentation.

One place defines what "a baseline to try" means: which slice of the spectrum
the algorithm sees, and what settings it runs with. Everything else --
``api.compare_baselines``, the plots -- consumes :class:`BaselineVariant` and
never calls ``create_baseline`` itself.

**This is the expansion point.** A new baseline behaviour gets a field on
:class:`BaselineVariant` and a branch in :meth:`BaselineVariant.compute`, not a
parallel module. Four knobs are wired up: the ``std_distribution`` settings, the
wavenumber window, the anchor points of ``spec.md`` section 14.7, and the split
point of section 14.8 -- the two readings of section 14.4 step 3, both built.
The anchor is the one that is recommended; the split is measured and kept as a
knob.
"""

from __future__ import annotations

import logging
import sys
import warnings
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
"""``(high, low)`` cm-1, matching ``io.py::import_data``'s ROI.

Written high-to-low because that is the order the instrument writes and the
order the plots display.
"""

DEGENERATE_WARNING = "no baseline points"
"""Substring of the ``pybaselines`` warning that means the fit found nothing.

``std_distribution`` still *returns* an array in that case, so a degenerate
baseline plots as a plausible-looking curve. Confirmed to fire for
``num_std: 0.8`` on ``20260717_203829_pd_ceo2_000-008_delta10.0042``.
"""

JUDGED_FILES: tuple[tuple[str, str], ...] = (
    ("20260715_094622_pd_ceo2_000-007_delta10.0042", "bad"),
    ("20260717_203829_pd_ceo2_000-008_delta10.0042", "bad"),
    ("20260728_032548_pd_ceo2_000-012_delta10.0052", "bad"),
    ("20260806_105210_pd_ceo2_000-017_delta10.0022", "bad"),
    ("20260811_072450_pd_ceo2_000-021_delta10.0022", "bad"),
    ("20260825_052349_pd_ceo2_000-027_delta10.0052", "bad"),
    ("20260813_195617_pd_ceo2_000-022_delta10.0022", "guard"),
    ("20260813_195617_pd_ceo2_000-022_delta10.0042", "guard"),
)
"""subIFG files whose baselines were judged by eye (spec.md sections 14.2/14.3).

All from ``nn1120-4_pd_ceo2_000``. ``"guard"`` marks the two files that carry a
band at the wavenumber under test -- ``...-022``'s raw subIFG minimum sits at
1942 cm-1 -- so they are the cases an anchor or truncation rule must *detect and
skip*, not baselines certified as correct. An earlier label of ``"good"`` was
wrong and is what section 14.7 recalibrated the guard against.

Every other file in the dataset is **unlabelled**. Six files were looked at;
they are not necessarily the only wrong ones.
"""

BASELINE_KEYS = ir_config.BASELINE_KEYS
"""Re-exported so callers can discover the settings without importing config."""

ANCHOR_HIGH_PIN_CM1 = 2240.0
"""High-wavenumber anchor. Not optional -- it pins the correction's tilt.

Nothing absorbs in 2235-2250, so the current baseline is already right there and
an anchor costs nothing. Without it the other two anchors sit only 50 cm-1
apart, the affine correction's slope is barely determined, and it extrapolates
over the remaining 250 cm-1: measured, that lifts the flat 2250-2200 region
1.5e-3 off zero, roughly 30x the level the current baseline achieves. With this
pin the same region returns to ~5e-5 (spec.md section 14.7).
"""

ANCHOR_POINTS_CM1: tuple[float, ...] = (ANCHOR_HIGH_PIN_CM1, 2006.0, 1955.0)
"""Default anchor wavenumbers -- points the baseline correction is fitted to.

With more than two anchors the correction is a least-squares line, so none is
hit exactly; the baseline is *pulled toward* the data at each, not constrained
to it. This is the single most misread property of the anchor: measured
residuals at these three are 0.4-3.2% of signal range (spec.md section 14.7).
Adding a point does not tighten them -- it re-weights where the one line sits,
which is why a fourth anchor was tried and removed (section 14.7.1).

- **2240** pins the tilt. Not optional; dropping it breaks the high end -- see
  :data:`ANCHOR_HIGH_PIN_CM1`.
- **2006** is the valley between the 2040 and 1980 bands, the two the current
  baseline cuts in half. Chosen by eye.
- **1955** is where the lgRefl spectra cross (section 14.6 finding 5: 27 of 35
  measurements pinch at 1955-1959). The one anchor with a measurement behind it.

**1854 is deliberately absent.** It was added as a fourth anchor and removed: it
sits where the current baseline already lies on the data, so its residual is
near zero and it drags the least-squares line back toward no correction at all,
costing 2040 band recovery on most files (section 14.7.1). Do not re-add it
without re-reading that subsection.

Anchoring is **not** truncation -- the array stays 1750-2250 and the baseline
keeps the shape ``std_distribution`` gave it; only an affine correction is added
(section 14.7).
"""

ANCHOR_GUARD_CM1 = 25.0
"""Half-width of the window an anchor is rejected for containing an extremum.

An anchor is only meaningful where the data is background. If a dominant band
sits within this distance, anchoring would pin the baseline to a peak.
"""

ANCHOR_PROMINENCE_FRAC = 0.5
"""Prominence, as a fraction of the file's full signal range, that makes an
extremum "dominant" enough to gate an anchor.

Measured against the **whole ROI range**, not the local excursion. That
distinction is the whole guard: these spectra are oscillatory, so every anchor
has *some* local wiggle near it, and a locally-scaled prominence gates
everything. Calibrated on the judged files (spec.md section 14.7): at 1955 the
gated file scores 0.75-0.82 while every file the anchor is meant to help scores
<= 0.24.
"""

SPLIT_POINT_CM1 = 1955.0
"""Default wavenumber at which a two-segment baseline is cut.

The same point as the lowest anchor -- the lgRefl crossing of spec.md section
14.6. Splitting here means the upper segment sees a *truncated* array,
2250-1955, which is the truncation experiment of section 14.6 finding 7; the
difference is that the region below the cut is no longer discarded, it gets a
baseline of its own (section 14.8).

The split is gated by the same test as the anchor at this wavenumber
(:func:`gating_extremum`), for the same reason and more strongly: finding 7
measured a 74% move on ``...-022`` precisely because the cut landed on the
shoulder of that file's 1942 cm-1 band. Gating the split and gating the anchor
are separate consequences of one test -- a file that loses its 1955 anchor
keeps 2240/2006, and a file that cannot be split still gets anchored.
"""


@dataclass
class BaselineOutcome:
    """What :meth:`BaselineVariant.compute` produced, and how.

    Carries more than the curve because the anchor guard is only useful if the
    caller can see when it fired -- a silently un-anchored baseline looks
    exactly like an anchored one that did nothing.
    """

    values: np.ndarray
    degenerate: bool = False
    anchors_applied: tuple[float, ...] = ()
    """Anchor wavenumbers the baseline was forced through."""

    anchors_gated: tuple[tuple[float, float, float], ...] = ()
    """``(anchor, extremum wavenumber, prominence fraction)`` per rejected anchor."""

    split_applied: float | None = None
    """Wavenumber the baseline was actually cut at, or ``None`` for one segment."""

    split_gated: tuple[float, float, float] | None = None
    """``(split, extremum wavenumber, prominence fraction)`` when the guard
    refused the cut. The baseline is then a single segment -- the anchors are
    judged separately and may still have been applied."""

    segment_edges: tuple[float, float] | None = None
    """``(lowest wavenumber of the upper segment, highest of the lower)``.

    The grid step is ~1.9 cm-1 and no sample lands exactly on the split, so the
    seam sits between these two.
    """

    seam_jump: float = float("nan")
    """``upper(edge) - lower(edge)``: the discontinuity across the seam.

    spec.md section 14.4 names the segment interface as the weak point of a
    split baseline. It is measured and reported, not blended away -- two
    baselines with the settings asked for is the thing being judged, and a
    continuity fix would change it into something else.
    """

    degenerate_segments: tuple[str, ...] = ()
    """Which segments reported no baseline points -- ``"upper"`` / ``"lower"``.

    A single flag for the pair would lose which side broke, and the lower
    segment is the one at risk: it is ~106 samples, so the sample-count
    settings (``half_window`` and friends) are ~2.4x larger relative to the
    array than the values they were tuned at.
    """

    @property
    def anchor_note(self) -> str:
        """One-line summary for a legend, empty when nothing was requested."""
        if not any(
            (self.anchors_applied, self.anchors_gated, self.split_applied, self.split_gated)
        ):
            return ""
        parts = []
        if self.split_applied is not None:
            parts.append(f"split {self.split_applied:.0f}")
        if self.split_gated is not None:
            split, where, prominence = self.split_gated
            parts.append(
                f"SPLIT GATED {split:.0f} (band at {where:.0f}, p={prominence:.2f})"
            )
        if self.anchors_applied:
            parts.append("anchored " + "/".join(f"{a:.0f}" for a in self.anchors_applied))
        for anchor, where, prominence in self.anchors_gated:
            parts.append(f"GATED {anchor:.0f} (band at {where:.0f}, p={prominence:.2f})")
        return "; ".join(parts)


@dataclass(frozen=True)
class BaselineVariant:
    """One baseline recipe: a data window plus algorithm settings.

    Args:
        label: Name shown in legends and the output CSV.
        settings: Overrides for ``std_distribution``, any of
            :data:`BASELINE_KEYS`. Keys left out keep their
            ``config/analysis.yaml`` value. An unknown key raises rather than
            being ignored -- ``create_baseline`` reads settings with
            ``.get(...)`` and falls back to a default, so a typo would silently
            run the *unmodified* baseline and look like a knob that does
            nothing.
        window: ``(high, low)`` cm-1 extent of the data handed to the
            algorithm. This genuinely changes the result everywhere, not just
            near the edges: ``create_baseline`` receives only ``y``, so the
            window *is* the array, and ``std_distribution`` classifies
            background points globally. Measured in spec.md section 14.3 finding 2 --
            narrowing the top edge to 2200 moves the baseline by up to 13% of
            signal range on the file whose baseline was then believed good --
            a label section 14.2 has since withdrawn, though the measurement of
            how far the window moves it stands.
        anchors: Wavenumbers the baseline is forced to pass through, applied
            *after* ``create_baseline`` as an affine correction. ``()`` -- the
            default -- reproduces the unanchored baseline exactly. Use
            :data:`ANCHOR_POINTS_CM1` for the calibrated pair. Truncation is a
            rejected alternative (spec.md section 14.6 finding 7); anchoring
            leaves the array at 1750-2250 and only shifts/tilts the result.
        split_cm1: Wavenumber at which the ROI is cut into two independently
            computed baselines, or ``None`` -- the default -- for one baseline
            over the whole window. The upper segment runs with this variant's
            ``settings`` and receives the ``anchors``; the lower segment runs
            with the **unmodified** ``voigt_fit.baseline`` settings and no
            anchors, so below the cut the file keeps the baseline it has today
            in recipe, though not in value -- the algorithm sees a shorter
            array (spec.md section 14.8). See :data:`SPLIT_POINT_CM1`.
    """

    label: str
    settings: dict = field(default_factory=dict)
    window: Window = DEFAULT_WINDOW
    anchors: tuple[float, ...] = ()
    split_cm1: float | None = None

    @classmethod
    def coerce(cls, item: BaselineVariant | tuple) -> BaselineVariant:
        """Build a variant from itself or a ``(label, settings[, window])`` tuple.

        Tuples keep the calling code readable in a ``__main__`` block:

            [("current", {}), ("num_std 1.4", {"num_std": 1.4})]
        """
        if isinstance(item, cls):
            return item
        if not isinstance(item, (tuple, list)) or not 2 <= len(item) <= 5:
            raise TypeError(
                "each variant must be a BaselineVariant or a "
                f"(label, settings[, window[, anchors[, split_cm1]]]) tuple; "
                f"got {item!r}"
            )
        return cls(*item)

    def __post_init__(self) -> None:
        high, low = self.window
        if not high > low:
            raise ValueError(
                f"window must be (high, low) with high > low; got {self.window!r}"
            )
        # Validate the settings eagerly so a typo surfaces when the variant is
        # declared, not partway through a batch.
        ir_config.get_baseline_settings(override=dict(self.settings) or None)

        object.__setattr__(self, "anchors", tuple(float(a) for a in self.anchors))
        for anchor in self.anchors:
            if not low <= anchor <= high:
                raise ValueError(
                    f"anchor {anchor:.0f} cm-1 lies outside this variant's window "
                    f"{self.window!r}; the baseline cannot be pinned to a point it "
                    "does not cover"
                )

        if self.split_cm1 is not None:
            object.__setattr__(self, "split_cm1", float(self.split_cm1))
            if not low < self.split_cm1 < high:
                raise ValueError(
                    f"split_cm1 {self.split_cm1:.0f} must lie strictly inside this "
                    f"variant's window {self.window!r}; a cut at the edge leaves one "
                    "segment empty"
                )

    @property
    def is_default_window(self) -> bool:
        """True when this variant uses the standard 1750-2250 ROI."""
        return tuple(self.window) == DEFAULT_WINDOW

    def resolved_settings(self, voigt_settings: dict | None = None) -> dict:
        """Return the full settings dict this variant will run with."""
        return ir_config.get_baseline_settings(
            voigt_settings, override=dict(self.settings) or None
        )

    def compute(
        self,
        intensity: np.ndarray,
        voigt_settings: dict | None = None,
        wavenumbers: np.ndarray | None = None,
    ) -> BaselineOutcome:
        """Return the baseline for an intensity array, plus how it was made.

        ``BaselineOutcome.degenerate`` is True when ``std_distribution``
        reported that it found no baseline points. The returned array is still
        whatever it produced -- callers must surface the flag, because the curve
        looks plausible.

        When :attr:`anchors` is non-empty, ``wavenumbers`` is required and the
        baseline is corrected to pass through the data at each surviving anchor
        (:func:`apply_anchors`). Anchors sitting on a dominant band are dropped
        and reported in ``anchors_gated`` rather than silently skipped.

        When :attr:`split_cm1` is set, ``wavenumbers`` is required and two
        baselines are computed -- the upper segment with this variant's
        settings and anchors, the lower with the unmodified
        ``voigt_fit.baseline`` settings and none. The same guard that rejects an
        anchor rejects the cut, and the two consequences are independent: a
        gated split falls back to one segment while the anchors are still
        applied where they survive.
        """
        settings = self.resolved_settings(voigt_settings)
        intensity = np.asarray(intensity, dtype=float)

        if self.split_cm1 is None:
            values, degenerate = self._segment_baseline(intensity, settings, "")
            if not self.anchors:
                return BaselineOutcome(values=values, degenerate=degenerate)
            if wavenumbers is None:
                raise ValueError(
                    f"variant {self.label!r} declares anchors {self.anchors} but "
                    "compute() was called without wavenumbers"
                )
            return apply_anchors(
                np.asarray(wavenumbers, dtype=float),
                intensity,
                values,
                self.anchors,
                degenerate=degenerate,
                label=self.label,
            )

        if wavenumbers is None:
            raise ValueError(
                f"variant {self.label!r} declares split_cm1={self.split_cm1} but "
                "compute() was called without wavenumbers"
            )
        wavenumbers = np.asarray(wavenumbers, dtype=float)

        # One guard test, two independent consequences. A band beside the cut
        # is exactly the failure spec.md section 14.6 finding 7 measured, so the
        # split falls back to a single segment -- but the anchors away from that
        # band are unaffected and are still applied.
        split_hit = gating_extremum(wavenumbers, intensity, self.split_cm1)
        if split_hit is not None:
            LOGGER.debug(
                "variant %r: split at %.0f gated by a band at %.0f (prominence "
                "%.2f of signal range); falling back to one segment",
                self.label, self.split_cm1, split_hit[0], split_hit[1],
            )
            values, degenerate = self._segment_baseline(intensity, settings, "")
            if self.anchors:
                outcome = apply_anchors(
                    wavenumbers,
                    intensity,
                    values,
                    self.anchors,
                    degenerate=degenerate,
                    label=self.label,
                )
            else:
                outcome = BaselineOutcome(values=values, degenerate=degenerate)
            outcome.split_gated = (
                float(self.split_cm1),
                float(split_hit[0]),
                float(split_hit[1]),
            )
            return outcome

        # Split by wavenumber value, never by position: wavenumbers descend, so
        # a positional slice takes the wrong end of the array.
        upper = wavenumbers >= self.split_cm1
        lower = ~upper
        if upper.sum() < 2 or lower.sum() < 2:
            raise ValueError(
                f"variant {self.label!r}: splitting at {self.split_cm1:.0f} leaves "
                f"{int(upper.sum())} / {int(lower.sum())} samples; each segment "
                "needs at least two"
            )

        upper_values, upper_degenerate = self._segment_baseline(
            intensity[upper], settings, "upper"
        )
        # The lower segment takes the current baseline's own parameters --
        # get_baseline_settings with no override -- not this variant's.
        lower_values, lower_degenerate = self._segment_baseline(
            intensity[lower], ir_config.get_baseline_settings(voigt_settings), "lower"
        )

        if self.anchors:
            # The guard and the data estimate read the FULL ROI, not the
            # segment: ANCHOR_PROMINENCE_FRAC is calibrated against the whole
            # ROI signal range, and anchor_data_value's +/-10 cm-1 window would
            # otherwise go one-sided at the 1955 anchor, which now sits on the
            # segment edge.
            upper_outcome = apply_anchors(
                wavenumbers[upper],
                intensity[upper],
                upper_values,
                self.anchors,
                guard_wavenumbers=wavenumbers,
                guard_intensity=intensity,
                degenerate=upper_degenerate,
                label=self.label,
            )
        else:
            upper_outcome = BaselineOutcome(
                values=upper_values, degenerate=upper_degenerate
            )

        # Assign through the boolean masks so the result comes back in the
        # order it was loaded in -- overlap_shift and the plots index the
        # baseline against the wavenumbers positionally.
        values = np.empty_like(intensity)
        values[upper] = upper_outcome.values
        values[lower] = lower_values

        upper_edge = int(np.argmin(np.where(upper, wavenumbers, np.inf)))
        lower_edge = int(np.argmax(np.where(lower, wavenumbers, -np.inf)))
        segments = tuple(
            name
            for name, flag in (("upper", upper_degenerate), ("lower", lower_degenerate))
            if flag
        )
        return BaselineOutcome(
            values=values,
            degenerate=bool(segments),
            anchors_applied=upper_outcome.anchors_applied,
            anchors_gated=upper_outcome.anchors_gated,
            split_applied=float(self.split_cm1),
            segment_edges=(
                float(wavenumbers[upper_edge]),
                float(wavenumbers[lower_edge]),
            ),
            seam_jump=float(values[upper_edge] - values[lower_edge]),
            degenerate_segments=segments,
        )

    def _segment_baseline(
        self,
        intensity: np.ndarray,
        settings: dict,
        segment: str,
    ) -> tuple[np.ndarray, bool]:
        """Run ``create_baseline`` on one array, capturing the degenerate warning.

        Split out so each segment's warning is caught separately: a single
        ``catch_warnings`` around both would report that *something* found no
        baseline points without saying which side.
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


def union_window(items: Sequence[Any]) -> Window:
    """Return the ``(high, low)`` window covering every item's ``window``.

    Accepts anything carrying a ``window`` attribute -- :class:`BaselineVariant`
    or :class:`~src.utils.ir_fitting.result_types.BaselineTrace` -- so the
    renderer and the orchestrator agree on display limits without one importing
    the other's types.

    Display limits come from the union rather than from any one variant, so a
    narrower variant's trace visibly *stops* instead of being cropped out of
    view -- which is the point of plotting a window change at all.
    """
    if not items:
        return DEFAULT_WINDOW
    return (
        max(item.window[0] for item in items),
        min(item.window[1] for item in items),
    )


def overlap_shift(
    x_reference: np.ndarray,
    y_reference: np.ndarray,
    x_variant: np.ndarray,
    y_variant: np.ndarray,
) -> tuple[float, Window]:
    """Max ``|variant - reference|`` over the wavenumbers the two share.

    Two variants with different windows produce arrays of different length, so
    they cannot be differenced elementwise. Both derive from the same file on
    the same grid, so intersecting on wavenumber value is exact -- and it is
    done by *value*, not by position, because wavenumbers descend and a
    narrower top edge drops samples from the **front** of the array. A
    positional head-slice would sit ~26 samples out of register at 2200 while
    still looking like the right length.

    Returns:
        ``(max absolute difference, (high, low) of the compared region)``.
    """
    low = max(float(x_reference.min()), float(x_variant.min()))
    high = min(float(x_reference.max()), float(x_variant.max()))
    if not high > low:
        raise ValueError(
            f"variant windows do not overlap: reference covers "
            f"{x_reference.min():.0f}-{x_reference.max():.0f}, variant covers "
            f"{x_variant.min():.0f}-{x_variant.max():.0f}"
        )

    mask_reference = (x_reference >= low) & (x_reference <= high)
    mask_variant = (x_variant >= low) & (x_variant <= high)
    if mask_reference.sum() != mask_variant.sum() or not np.allclose(
        x_reference[mask_reference], x_variant[mask_variant]
    ):
        raise ValueError(
            "the two variants are not on the same wavenumber grid over their "
            "overlap; they cannot be compared"
        )

    shift = float(np.abs(y_variant[mask_variant] - y_reference[mask_reference]).max())
    return shift, (high, low)


def signal_range(y: np.ndarray) -> float:
    """``max(y) - min(y)``, the denominator for reporting a baseline shift.

    Raw log-reflectance differences are ~1e-4 and unreadable on their own;
    dividing by the span makes files comparable. For scale, the 2040 cm-1 peak
    is about 20% of signal range in the files of :data:`JUDGED_FILES`.
    """
    span = float(np.nanmax(y) - np.nanmin(y))
    return span if span > 0 else float("nan")


def band_height(
    wavenumbers: np.ndarray,
    intensity: np.ndarray,
    baseline: np.ndarray,
    center: float,
    half_width: float = 15.0,
) -> float:
    """Height of the band near ``center`` above ``baseline``.

    ``max(intensity - baseline)`` within ``half_width`` of ``center``, so a
    band that has drifted a few cm-1 is still measured at its own maximum.

    This is **not** the envelope-style quality score rejected in spec.md
    section 14.3 finding 4. That score asked "does the baseline stay below the
    data everywhere", which is wrong here because the low bands are
    negative-going and the baseline is a centre-line estimator. This measures
    one named band the user identified as being cut in half -- 2040 and 1980 --
    and says how tall it comes out. It answers "did this band stop being
    halved", not "is this baseline good".
    """
    near = np.abs(wavenumbers - center) <= half_width
    if not near.any():
        return float("nan")
    return float(np.max(intensity[near] - baseline[near]))


def gating_extremum(
    wavenumbers: np.ndarray,
    intensity: np.ndarray,
    anchor: float,
    guard_cm1: float = ANCHOR_GUARD_CM1,
    prominence_frac: float = ANCHOR_PROMINENCE_FRAC,
) -> tuple[float, float] | None:
    """Return the dominant extremum within ``guard_cm1`` of ``anchor``, if any.

    An anchor claims "the data here is background". That is false if a strong
    band sits next to it, and anchoring there would pull the baseline onto the
    peak -- the failure the user identified on
    ``20260813_195617_pd_ceo2_000-022``, whose subIFG minimum sits at 1942 cm-1,
    13 cm-1 from the 1955 anchor.

    Prominence is measured as a fraction of the file's **full ROI signal
    range**, not of the local excursion. That choice is the guard: these
    spectra are oscillatory (spec.md section 14.4), so a locally-scaled
    prominence finds a wiggle beside every anchor and gates all of them,
    including on the files the anchor exists to fix.

    Returns:
        ``(wavenumber, prominence fraction)`` of the most prominent qualifying
        extremum, or ``None`` when the anchor region is clear.
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
    """Estimate the data's value at ``anchor`` by a local straight-line fit.

    A single sample is noisy. The guard has already certified that this region
    holds no dominant band, so the data here is flat or monotonic and a least
    squares line over +/- ``half_width`` is a better estimator than either the
    bare sample or a median.
    """
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
    degenerate: bool = False,
    label: str = "",
) -> BaselineOutcome:
    """Fit an affine correction to ``baseline`` at each anchor that survives the guard.

    The correction is affine in wavenumber, so the baseline keeps the shape
    ``std_distribution`` gave it and is only shifted and tilted:

    - **two anchors** -- the unique line through both residuals
      ``d_i = data(w_i) - baseline(w_i)``; the baseline passes through both
      exactly.
    - **one anchor** -- a constant shift. A tilt is not determined by one point,
      so none is applied.
    - **no anchors** (all gated) -- the baseline is returned unchanged. This is
      the deliberate fallback: where the guard fires, the current baseline is
      what the file gets.

    Anchors outside the array's wavenumber coverage are gated with a prominence
    of ``nan``, since the correction cannot be evaluated there. Coverage is
    tested with one grid step of tolerance so that an anchor sitting exactly on
    a segment edge -- which is where 1955 lands under a split at 1955 -- is
    kept rather than being reported as outside the window.

    ``guard_wavenumbers`` / ``guard_intensity`` supply the arrays the guard and
    the data estimate read, when they must differ from the array being
    corrected. Under a split that is the **full** ROI:
    :data:`ANCHOR_PROMINENCE_FRAC` is a fraction of the whole ROI signal range,
    so measuring it on a segment would rescale the threshold, and
    :func:`anchor_data_value`'s window would go one-sided at the edge anchor.
    """
    ascending = np.argsort(wavenumbers)
    grid_w = wavenumbers[ascending]
    grid_b = baseline[ascending]
    guard_w = wavenumbers if guard_wavenumbers is None else np.asarray(
        guard_wavenumbers, dtype=float
    )
    guard_y = intensity if guard_intensity is None else np.asarray(
        guard_intensity, dtype=float
    )
    tolerance = float(np.median(np.diff(grid_w))) if grid_w.size > 1 else 0.0

    applied: list[float] = []
    gated: list[tuple[float, float, float]] = []
    residuals: list[tuple[float, float]] = []

    for anchor in anchors:
        if not grid_w[0] - tolerance <= anchor <= grid_w[-1] + tolerance:
            gated.append((float(anchor), float("nan"), float("nan")))
            continue
        hit = gating_extremum(guard_w, guard_y, anchor)
        if hit is not None:
            gated.append((float(anchor), hit[0], hit[1]))
            continue
        value = anchor_data_value(guard_w, guard_y, anchor)
        residuals.append((float(anchor), value - float(np.interp(anchor, grid_w, grid_b))))
        applied.append(float(anchor))

    if not residuals:
        correction = np.zeros_like(baseline)
    elif len(residuals) == 1:
        correction = np.full_like(baseline, residuals[0][1])
    else:
        # Two or more: least squares line through the residuals. With exactly
        # two this is the unique line, so both anchors are hit exactly.
        anchor_w = np.array([item[0] for item in residuals], dtype=float)
        anchor_d = np.array([item[1] for item in residuals], dtype=float)
        slope, intercept = np.polyfit(anchor_w, anchor_d, 1)
        correction = slope * wavenumbers + intercept

    if gated and label:
        for anchor, where, fraction in gated:
            LOGGER.debug(
                "variant %r: anchor %.0f gated by a band at %.0f (prominence "
                "%.2f of signal range)",
                label, anchor, where, fraction,
            )

    return BaselineOutcome(
        values=baseline + correction,
        degenerate=degenerate,
        anchors_applied=tuple(applied),
        anchors_gated=tuple(gated),
    )
