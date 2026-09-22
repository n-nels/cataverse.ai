"""Baseline variants for offline baseline experimentation.

One place defines what "a baseline to try" means: which slice of the spectrum
the algorithm sees, and what settings it runs with. Everything else --
``api.compare_baselines``, the plots -- consumes :class:`BaselineVariant` and
never calls ``create_baseline`` itself.

**This is the expansion point.** A new baseline behaviour gets a field on
:class:`BaselineVariant` and a branch in :meth:`BaselineVariant.compute`, not a
parallel module. Four knobs are wired up: the ``std_distribution`` settings, the
wavenumber window, the anchor points of ``spec.md`` section 14.7, and the
lower-only cut of section 14.9 with the :attr:`BaselineVariant.lower_anchors`
that pin the segment below it (sections 14.10, 14.19).

Those four are the selected form of section 14.22 and nothing else. The other
constructions section 14 measured -- the truncating split (14.8), a different
algorithm below the cut (14.12), the floor at 1800 (14.13), the C1 continuation
(14.14/14.15), the truncated windows (14.16-14.18) and the seven-anchor full ROI
(14.20) -- were rejected or superseded, and have been removed from the code.
They remain recorded in ``spec.md`` as measurements; see section 0.
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
order the plots display. The selected form of spec.md section 14.22 uses this
window whole: every truncation section 14 tried was rejected (14.6 finding 7,
14.16-14.18).
"""

DEGENERATE_WARNING = "no baseline points"
"""Substring of the ``pybaselines`` warning that means the fit found nothing.

``std_distribution`` still *returns* an array in that case, so a degenerate
baseline plots as a plausible-looking curve. Confirmed to fire for
``num_std: 0.8`` on ``20260717_203829_pd_ceo2_000-008_delta10.0042``.
"""

JUDGED_FOLDER = "nn1120-4_pd_ceo2_000"
"""The one dataset :data:`JUDGED_FILES` belongs to.

The stems below carry no folder, so anything keying on them has to check this
first -- a file of the same name in another dataset is not a judged file.
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
"""The three calibrated anchor wavenumbers -- points the correction is fitted to.

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

The selected form uses :data:`DENSE_UPPER_ANCHOR_POINTS_CM1`, which extends
this set; these three remain named because they are what that one is built from
and what every comparison in section 14 is calibrated against.

Anchoring is **not** truncation -- the array stays 1750-2250 and the baseline
keeps the shape ``std_distribution`` gave it; only an affine correction is added
(section 14.7).
"""

DENSE_UPPER_ANCHOR_POINTS_CM1: tuple[float, ...] = (
    *ANCHOR_POINTS_CM1,
    2011.0,
    2010.0,
    2009.0,
    2008.0,
    2007.0,
    2006.0,
    2005.0,
    2004.0,
    2003.0,
    2002.0,
    2001.0,
    2000.0,
)
"""The full-ROI anchor set of the selected form (spec.md sections 14.21/14.22).

:data:`ANCHOR_POINTS_CM1` plus a dense cluster over 2011-2000, which at ROI
scale renders as one blob around the 2006 valley.

**2006 appears twice, and that is deliberate.** :data:`ANCHOR_POINTS_CM1`
already contains it and the dense run covers it again, so that wavenumber
carries double weight in the least-squares affine correction. Section 14.21
locked the set in this form and section 14.22 measured the candidate on it. Do
not deduplicate it without a new comparison run -- the correction would change.
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

It does **not** protect a low-wavenumber anchor: the low bands are only 2-9% of
the ROI range, so 1800 -- ~5 cm-1 from the 1795 band -- passes on every file,
scoring 0.002-0.089 (spec.md section 14.10 finding 16). That is a standing limit
of the guard and applies to all four of the lower anchors below 1955.
"""

LOWER_SPLIT_POINT_CM1 = 1955.0
"""Default cut for the lower-only split of spec.md section 14.9.

The same point as the lowest of :data:`ANCHOR_POINTS_CM1` -- the lgRefl
crossing of section 14.6. Below it a second ``create_baseline`` runs on its own
array; at and above it the anchored full-ROI baseline stands untouched, which
is the property the whole form rests on and which
``BaselineTrace.upper_max_abs_diff`` checks at exactly 0.0.

Section 14.8's other reading of section 14.4 step 3 -- cutting the array and
recomputing **both** sides on truncated arrays -- was built, measured as worse
(the 1955 anchor then reads the corrupted truncation edge and tilts the
least-squares line so 2006 lands -8.2% off instead of -2.1%) and has been
removed from the code.

The cut is gated by the same test as an anchor at this wavenumber
(:func:`gating_extremum`), for the same reason and more strongly: section 14.6
finding 7 measured a 74% move on ``...-022`` precisely because the cut landed on
the shoulder of that file's 1942 cm-1 band. Gating the cut and gating the anchor
are **separate consequences of one test**, evaluated independently -- a file
that loses its 1955 anchor keeps 2240/2006, and a file that cannot be cut still
gets anchored. On ``...-022`` both fire, which is why those two traces are the
uncut fallback rather than the candidate (section 14.22).
"""

LOWER_ANCHOR_POINTS_CM1: tuple[float, ...] = (
    LOWER_SPLIT_POINT_CM1,
    1790.0,
    1800.0,
    1810.0,
    1820.0,
)
"""The lower segment's own anchors in the selected form (spec.md 14.19/14.22).

Only meaningful with :attr:`BaselineVariant.lower_split_cm1` -- there is no
"lower segment" without a cut, and :class:`BaselineVariant` raises rather than
ignore them.

**Five anchors, so the correction is a least-squares pull, not an exact fit.**
An earlier two-anchor set pinned both endpoints of the segment exactly
(sections 14.10/14.10.1), which made the seam predictable from the upper side's
residual at 1955 alone. That identity does **not** hold here: with five points
the lower correction is one line fitted to five residuals and no anchor is hit
exactly. Section 14.19 measured the trade -- against the unanchored cut the seam
shrank on four of the six ungated judged files and grew on two.

**Structurally different from :data:`ANCHOR_POINTS_CM1`, not a variant of it.**
The full-ROI set pins only the top (2240) and fits the rest below it, so
everything under 1955 would be extrapolation -- the 205 cm-1 excursion section
14.9 finding 14 measured as the anchored baseline's single largest. This set
constrains that span directly, with four of its five points in 1820-1790.

The cut wavenumber tracks :data:`LOWER_SPLIT_POINT_CM1` so the anchor at the
segment's top edge stays there if the cut moves;
:meth:`BaselineVariant.__post_init__` re-checks every point against the
variant's own window and cut, because a variant with a different cut would
otherwise silently anchor above its own segment.
"""

MID_PROBE_CM1 = 1850.0
"""Where the dispersive feature's midpoint target is read (spec.md 14.12).

**Interpolated, not sampled.** The grid step is ~1.93 cm-1 and the nearest
samples are 1851.3 and 1849.4, so ``baseline(1850)`` is a linear interpolation
between them on the steepest part of the feature -- the same sub-sample caveat
section 14.10 finding 20 raised for the anchor at 1955. The trough and peak
:data:`MID_EXTREMA_WINDOW_CM1` supplies are sampled, so only this half of the
comparison is interpolated.
"""

MID_EXTREMA_WINDOW_CM1: Window = (1866.0, 1838.0)
"""``(high, low)`` the ~1850 feature's trough and peak are taken from."""

UND_WINDOW_CM1: Window = (1885.0, 1840.0)
"""``(high, low)`` over which ``max(baseline - data)`` is read.

Covers the 1850 and 1870-1880 bands, which the user asked the baseline to run
*under* the base of (spec.md 14.12).
"""

INT_WINDOW_CM1: Window = (1838.0, 1750.0)
"""``(high, low)`` over which ``mean(data - baseline)`` is read.

**1838, not 1860**: the top edge excludes the ~1850 feature, which is what keeps
this out of section 14.10.1 finding 24's trap -- a signed residual over a window
containing a negative-going band rewards a baseline pulled down onto it. The
1795/1775 bands are counted *in*, on the user's instruction (spec.md 14.12).
"""


def lower_target_metrics(
    wavenumbers: np.ndarray,
    raw: np.ndarray,
    baseline: np.ndarray,
) -> dict[str, float]:
    """The three targets the user stated for the region below the cut.

    Rebuilt here rather than in a probe script because sections 14.12, 14.13 and
    14.14 each needed them and each re-derived them: the probes behind them were
    written to a scratchpad and not preserved (spec.md 14.14, closing note).

    Every value is a **percentage of the file's signal range**, so they read on
    the same scale as ``moved_pct_of_range`` and ``seam_pct_of_range``.

    Returns a dict of:

    - ``mid`` -- ``baseline(1850) - (trough + peak)/2`` over
      :data:`MID_EXTREMA_WINDOW_CM1`. Target **0 on post-crossing files**: the
      baseline through the midpoint of the dispersive feature.
    - ``mid_pre_target`` -- ``-(peak - trough)/2``, what ``mid`` reads when the
      baseline sits on the flanking trough. That is what *"under the base of
      those peaks"* means in ``mid``'s units, so it is the target for
      **pre-crossing** files. Reported beside ``mid`` rather than subtracted
      from it: which target applies is a regime judgement, not a measurement.
    - ``und`` -- ``max(baseline - data)`` over :data:`UND_WINDOW_CM1`. Target
      **0 approached from below**; positive means the baseline cuts into the
      bands.
    - ``int`` -- ``mean(data - baseline)`` over :data:`INT_WINDOW_CM1`. Target
      **0** on every file.

    **Never sum them and never quote one alone.** Section 14.12 finding 33 has
    the worked case: ``irsqr`` is the best of 44 methods on ``int`` while
    sitting 9% of range below where it belongs, because a strict lower envelope
    games a signed mean. They are three separate statements about where the
    curve should be, and a form is judged on all three at once (spec.md
    section 0's trap list).
    """
    scale = signal_range(raw)
    ascending = np.argsort(wavenumbers)
    x_sorted = wavenumbers[ascending]

    mid_hi, mid_lo = MID_EXTREMA_WINDOW_CM1
    feature = (wavenumbers <= mid_hi) & (wavenumbers >= mid_lo)
    if feature.any():
        trough = float(raw[feature].min())
        peak = float(raw[feature].max())
        fitted = float(np.interp(MID_PROBE_CM1, x_sorted, baseline[ascending]))
        mid = 100 * (fitted - 0.5 * (trough + peak)) / scale
        mid_pre_target = -100 * 0.5 * (peak - trough) / scale
    else:
        mid = mid_pre_target = float("nan")

    und_hi, und_lo = UND_WINDOW_CM1
    under = (wavenumbers <= und_hi) & (wavenumbers >= und_lo)
    und = (
        100 * float(np.max(baseline[under] - raw[under])) / scale
        if under.any()
        else float("nan")
    )

    int_hi, int_lo = INT_WINDOW_CM1
    flat = (wavenumbers <= int_hi) & (wavenumbers >= int_lo)
    integral = (
        100 * float(np.mean(raw[flat] - baseline[flat])) / scale
        if flat.any()
        else float("nan")
    )

    return {
        "mid": mid,
        "mid_pre_target": mid_pre_target,
        "und": und,
        "int": integral,
    }


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
    refused the cut. The baseline is then the anchored full-ROI curve alone --
    the anchors are judged separately and may still have been applied."""

    segment_edges: tuple[float, float] | None = None
    """``(lowest wavenumber above the cut, highest below it)``.

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
    """Which segments reported no baseline points -- ``"full"`` for the
    full-ROI curve, ``"lower"`` for the one below the cut.

    A single flag for the pair would lose which side broke, and the lower
    segment is the one at risk: it is ~106 samples, so the sample-count settings
    (``half_window`` and friends) are ~2.4x larger relative to the array than
    the values they were tuned at.
    """

    lower_anchors_applied: tuple[float, ...] = ()
    """Anchor wavenumbers the **lower segment's** baseline was corrected at.

    Separate from :attr:`anchors_applied` because they are two corrections on
    two arrays -- and one merged tuple could not say which of them a gated 1955
    was dropped from, since that wavenumber is in both sets (spec.md 14.10).
    Empty unless :attr:`BaselineVariant.lower_anchors` was asked for, and empty
    on a gated cut: there is then no lower segment to anchor.
    """

    lower_anchors_gated: tuple[tuple[float, float, float], ...] = ()
    """``(anchor, extremum wavenumber, prominence fraction)`` per rejected
    lower-segment anchor. Reported for the reason this class exists: a lower
    baseline that was silently left short an anchor looks exactly like one where
    correcting did little."""


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

            The selected form leaves this empty: every sweep of these
            parameters was measured and none recommended (spec.md sections
            14.3 finding 1, 14.11).
        window: ``(high, low)`` cm-1 extent of the data handed to the
            algorithm. This genuinely changes the result everywhere, not just
            near the edges: ``create_baseline`` receives only ``y``, so the
            window *is* the array, and ``std_distribution`` classifies
            background points globally. Measured in spec.md section 14.3
            finding 2 -- narrowing the top edge to 2200 moves the baseline by up
            to 13% of signal range.

            The selected form keeps the full :data:`DEFAULT_WINDOW`; every
            truncation tried was rejected (14.6 finding 7, 14.16-14.18).
        anchors: Wavenumbers the baseline is forced to pass through, applied
            *after* ``create_baseline`` as an affine correction. ``()`` -- the
            default -- reproduces the unanchored baseline exactly. The selected
            form uses :data:`DENSE_UPPER_ANCHOR_POINTS_CM1`. Anchoring leaves
            the array at 1750-2250 and only shifts and tilts the result
            (spec.md section 14.7).
        lower_split_cm1: Wavenumber below which the baseline is replaced by a
            second, independently computed one -- or ``None``, the default, for
            one baseline over the whole window.

            ``create_baseline`` runs on the full window and ``anchors`` are
            applied to that full-ROI result, so at and above the cut this
            variant equals the unsplit anchored baseline **bit for bit**, which
            is the check spec.md section 14.9 is built on. Below the cut a
            second ``create_baseline`` runs on its own array with the
            **unmodified** ``voigt_fit.baseline`` settings -- deliberately not
            this variant's ``settings``. See :data:`LOWER_SPLIT_POINT_CM1`.
        lower_anchors: Wavenumbers the **lower segment's** own baseline is
            corrected at -- ``()``, the default, leaves it unanchored as
            spec.md section 14.9 measured it. Its own affine correction, fitted
            to its own residuals on its own array; the full-ROI correction above
            the cut is untouched, so ``upper_max_abs_diff`` stays 0.0 exactly.

            Requires ``lower_split_cm1``: without a cut there is no lower
            segment, and a silently ignored anchor list is the same failure mode
            as an unknown ``settings`` key. Use
            :data:`LOWER_ANCHOR_POINTS_CM1` for the five-point set of the
            selected form.
        anchor_guard_cm1: Half-width of the window an anchor -- or the cut -- is
            rejected for containing a dominant extremum. Defaults to
            :data:`ANCHOR_GUARD_CM1`, the value every measurement in spec.md
            section 14 ran with; it was introduced by section 14.7 and never
            swept.
        anchor_prominence_frac: Prominence, **as a fraction of the file's whole
            ROI signal range**, that makes such an extremum dominant enough to
            gate. Defaults to :data:`ANCHOR_PROMINENCE_FRAC`. Raising it gates
            less, lowering it gates more; at 1955 the guard file scores
            0.75-0.82 while every file the anchor is meant to help scores
            <= 0.24 (section 14.7 finding 8).

            Making this settable does **not** lift the standing limit of section
            14.10 finding 16: the low bands are only 2-9% of the ROI range, so no
            value that leaves the 1955 guard working also protects an anchor
            below ~1900.

            Both guard values configure all three gate sites together -- each
            full-ROI anchor, each lower anchor, and the cut -- because the anchor
            guard and the cut guard are two verdicts from one test (section
            14.22), and a variant that gated them differently would not be the
            form section 14 measured.
    """

    label: str
    settings: dict = field(default_factory=dict)
    window: Window = DEFAULT_WINDOW
    anchors: tuple[float, ...] = ()
    lower_split_cm1: float | None = None
    lower_anchors: tuple[float, ...] = ()
    anchor_guard_cm1: float = ANCHOR_GUARD_CM1
    anchor_prominence_frac: float = ANCHOR_PROMINENCE_FRAC

    @classmethod
    def coerce(cls, item: BaselineVariant | tuple) -> BaselineVariant:
        """Build a variant from itself or a ``(label, settings[, window])`` tuple.

        Tuples keep the calling code readable in a ``__main__`` block:

            [("current", {}), ("num_std 1.4", {"num_std": 1.4})]
        """
        if isinstance(item, cls):
            return item
        if not isinstance(item, (tuple, list)) or not 2 <= len(item) <= 6:
            raise TypeError(
                "each variant must be a BaselineVariant or a "
                "(label, settings[, window[, anchors[, lower_split_cm1"
                "[, lower_anchors]]]]) tuple; got "
                f"{item!r}. Past the 4th slot the keyword form "
                "BaselineVariant(label=..., lower_split_cm1=...) reads better "
                "-- positional tuples were for the two-element case. "
                "anchor_guard_cm1 and anchor_prominence_frac have no positional "
                "slot at all and must be passed by keyword."
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

        # Validated on `settings`' precedent: rejected, never clamped. A guard
        # value silently corrected to something workable would run a different
        # recipe under the label that was asked for.
        for name in ("anchor_guard_cm1", "anchor_prominence_frac"):
            value = float(getattr(self, name))
            object.__setattr__(self, name, value)
            if not np.isfinite(value):
                raise ValueError(f"{name} must be finite; got {value!r}")
        if self.anchor_guard_cm1 < 0:
            raise ValueError(
                f"anchor_guard_cm1 must be >= 0; got {self.anchor_guard_cm1!r}. "
                "Zero disables the guard's reach, which is the widest setting "
                "that still has a meaning -- there is no negative half-width."
            )
        if self.anchor_prominence_frac <= 0:
            raise ValueError(
                "anchor_prominence_frac must be > 0; got "
                f"{self.anchor_prominence_frac!r}. At 0 every extremum is "
                "dominant and every anchor is gated, which is the unanchored "
                "baseline written as a guard setting."
            )

        object.__setattr__(self, "anchors", tuple(float(a) for a in self.anchors))
        for anchor in self.anchors:
            if not low <= anchor <= high:
                raise ValueError(
                    f"anchor {anchor:.0f} cm-1 lies outside this variant's window "
                    f"{self.window!r}; the baseline cannot be pinned to a point it "
                    "does not cover"
                )

        object.__setattr__(
            self, "lower_anchors", tuple(float(a) for a in self.lower_anchors)
        )
        if self.lower_anchors and self.lower_split_cm1 is None:
            raise ValueError(
                f"variant {self.label!r} declares lower_anchors "
                f"{self.lower_anchors} but no lower_split_cm1. There is no lower "
                "segment to anchor without a cut, and silently ignoring them "
                "would look exactly like anchors that did nothing -- pass "
                "lower_split_cm1=LOWER_SPLIT_POINT_CM1, or put these in "
                "`anchors` if the full-ROI correction was meant."
            )

        if self.lower_split_cm1 is not None:
            object.__setattr__(self, "lower_split_cm1", float(self.lower_split_cm1))
            if not low < self.lower_split_cm1 < high:
                raise ValueError(
                    f"lower_split_cm1 {self.lower_split_cm1:.0f} must lie strictly "
                    f"inside this variant's window {self.window!r}; a cut at the "
                    "edge leaves one segment empty"
                )

        for anchor in self.lower_anchors:
            if not low <= anchor <= high:
                raise ValueError(
                    f"lower anchor {anchor:.0f} cm-1 lies outside this variant's "
                    f"window {self.window!r}"
                )
            if anchor > self.lower_split_cm1:
                raise ValueError(
                    f"lower anchor {anchor:.0f} cm-1 sits above this variant's cut "
                    f"at {self.lower_split_cm1:.0f}; the lower segment does not "
                    "cover it. Anchors above the cut belong in `anchors`, which "
                    "corrects the full-ROI baseline."
                )

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

        ``wavenumbers`` is required whenever :attr:`anchors` or
        :attr:`lower_split_cm1` is set. Anchors sitting on a dominant band are
        dropped and reported in ``anchors_gated`` rather than silently skipped
        (:func:`apply_anchors`); a cut beside one falls back to the plain
        anchored baseline and is reported in ``split_gated``. See
        :meth:`_compute_lower_split`.
        """
        settings = self.resolved_settings(voigt_settings)
        intensity = np.asarray(intensity, dtype=float)

        if (self.anchors or self.lower_split_cm1 is not None) and wavenumbers is None:
            raise ValueError(
                f"variant {self.label!r} declares anchors or a cut but compute() "
                "was called without wavenumbers"
            )

        # Steps 1-2 of the form, and the whole of it for an uncut variant: one
        # create_baseline over the full window, then the affine correction
        # fitted to that full-ROI result.
        values, degenerate = self._segment_baseline(intensity, settings, "")
        if not self.anchors:
            outcome = BaselineOutcome(values=values, degenerate=degenerate)
        else:
            outcome = apply_anchors(
                np.asarray(wavenumbers, dtype=float),
                intensity,
                values,
                self.anchors,
                guard_cm1=self.anchor_guard_cm1,
                prominence_frac=self.anchor_prominence_frac,
                degenerate=degenerate,
                label=self.label,
            )

        if self.lower_split_cm1 is None:
            return outcome
        return self._compute_lower_split(
            np.asarray(wavenumbers, dtype=float),
            intensity,
            outcome,
            degenerate,
            voigt_settings,
        )

    def _compute_lower_split(
        self,
        wavenumbers: np.ndarray,
        intensity: np.ndarray,
        outcome: BaselineOutcome,
        degenerate: bool,
        voigt_settings: dict | None,
    ) -> BaselineOutcome:
        """The lower-only cut of spec.md section 14.9.

        Every failure section 14.8 measured traces to the *upper* segment being
        computed on a shortened array, so this form never shortens it. Steps 1
        and 2 -- ``create_baseline`` on the full window and
        :func:`apply_anchors` on the full wavenumbers and intensity -- have
        already run in :meth:`compute` and arrive here as ``outcome``. What is
        left is:

        3. ``create_baseline`` on the sub-array below the cut, with the
           **unmodified** ``voigt_fit.baseline`` settings;
        3b. :func:`apply_anchors` on that lower baseline at
           :attr:`lower_anchors`, if any -- its own least-squares line, on its
           own array, fitted before the splice (spec.md section 14.10);
        4. splice -- step 2's values at and above the cut, step 3b's below.

        Step 2 must precede step 4. Anchoring the *spliced* curve would fit the
        least-squares line to a mixture of two baselines, which is the premise
        of this form collapsing: the point is that no anchor ever reads a
        truncation edge, and that above the cut the result is bit-for-bit the
        unsplit anchored baseline. Step 3b obeys the same rule from the other
        side -- it corrects the lower segment alone, never the spliced curve, so
        it cannot reach above the cut and ``upper_max_abs_diff`` stays 0.0.

        The cut is gated by the same test as an anchor at that wavenumber. A
        gated cut returns ``outcome`` as it stands -- steps 1 and 2 alone, which
        is the section 14.7 anchored baseline exactly, not a re-derivation of
        it. :attr:`lower_anchors` go with it: there is no lower segment to
        anchor, so ``lower_anchors_applied`` comes back empty rather than
        reporting anchors that were never fitted.
        """
        cut = float(self.lower_split_cm1)

        split_hit = gating_extremum(
            wavenumbers,
            intensity,
            cut,
            guard_cm1=self.anchor_guard_cm1,
            prominence_frac=self.anchor_prominence_frac,
        )
        if split_hit is not None:
            LOGGER.debug(
                "variant %r: lower split at %.0f gated by a band at %.0f "
                "(prominence %.2f of signal range); returning the anchored "
                "full-ROI baseline unchanged",
                self.label,
                cut,
                split_hit[0],
                split_hit[1],
            )
            outcome.split_gated = (cut, float(split_hit[0]), float(split_hit[1]))
            return outcome

        # Split by wavenumber value, never by position: wavenumbers descend, so
        # a positional slice takes the wrong end of the array.
        upper = wavenumbers >= cut
        lower = ~upper
        if upper.sum() < 2 or lower.sum() < 2:
            raise ValueError(
                f"variant {self.label!r}: splitting at {cut:.0f} leaves "
                f"{int(upper.sum())} / {int(lower.sum())} samples; each segment "
                "needs at least two"
            )

        # Step 3. The lower segment takes the CURRENT baseline's own parameters
        # -- `voigt_fit.baseline` unmodified, deliberately not this variant's
        # `settings`, which belong to the full-ROI curve above the cut. A
        # variant that changes num_std up there leaves the region below it on
        # the recipe the file has today.
        lower_values, lower_degenerate = self._segment_baseline(
            intensity[lower],
            ir_config.get_baseline_settings(voigt_settings),
            "lower",
        )

        # Step 3b. The lower segment's own anchors, on the lower segment's own
        # array. The guard and the data estimate read the FULL ROI, for two
        # reasons: ANCHOR_PROMINENCE_FRAC is calibrated against the whole ROI
        # signal range, so measuring it on a ~106-sample segment would rescale
        # the threshold; and anchor_data_value's +/-10 cm-1 window would go
        # one-sided at the anchor sitting on the cut.
        if self.lower_anchors:
            lower_outcome = apply_anchors(
                wavenumbers[lower],
                intensity[lower],
                lower_values,
                self.lower_anchors,
                guard_wavenumbers=wavenumbers,
                guard_intensity=intensity,
                guard_cm1=self.anchor_guard_cm1,
                prominence_frac=self.anchor_prominence_frac,
                degenerate=lower_degenerate,
                label=self.label,
            )
            lower_values = lower_outcome.values
            outcome.lower_anchors_applied = lower_outcome.anchors_applied
            outcome.lower_anchors_gated = lower_outcome.anchors_gated

        # Step 4. Assign through the boolean mask so the result comes back in
        # the order it was loaded in -- overlap_shift and the plots index the
        # baseline against the wavenumbers positionally.
        spliced = np.array(outcome.values, dtype=float, copy=True)
        spliced[lower] = lower_values

        upper_edge = int(np.argmin(np.where(upper, wavenumbers, np.inf)))
        lower_edge = int(np.argmax(np.where(lower, wavenumbers, -np.inf)))

        outcome.values = spliced
        outcome.degenerate_segments = tuple(
            name
            for name, flag in (("full", degenerate), ("lower", lower_degenerate))
            if flag
        )
        outcome.degenerate = bool(outcome.degenerate_segments)
        outcome.split_applied = cut
        outcome.segment_edges = (
            float(wavenumbers[upper_edge]),
            float(wavenumbers[lower_edge]),
        )
        outcome.seam_jump = float(spliced[upper_edge] - spliced[lower_edge])
        return outcome

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

    Called once per anchor and once for the cut, independently -- on
    ``...-022`` it fires for both at 1955, which is two separate verdicts on one
    test rather than one verdict used twice (spec.md 14.22).

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
    guard_cm1: float = ANCHOR_GUARD_CM1,
    prominence_frac: float = ANCHOR_PROMINENCE_FRAC,
    degenerate: bool = False,
    label: str = "",
) -> BaselineOutcome:
    """Fit an affine correction to ``baseline`` at each anchor that survives the guard.

    The correction is affine in wavenumber, so the baseline keeps the shape
    ``std_distribution`` gave it and is only shifted and tilted:

    - **three or more anchors** -- a least-squares line through the residuals
      ``d_i = data(w_i) - baseline(w_i)``. No anchor is hit exactly; each is a
      pull. Both anchor sets of the selected form are in this case.
    - **two anchors** -- the unique line through both residuals; the baseline
      passes through both exactly.
    - **one anchor** -- a constant shift. A tilt is not determined by one point,
      so none is applied.
    - **no anchors** (all gated) -- the baseline is returned unchanged. This is
      the deliberate fallback: where the guard fires, the current baseline is
      what the file gets.

    Anchors outside the array's wavenumber coverage are gated with a prominence
    of ``nan``, since the correction cannot be evaluated there. Coverage is
    tested with one grid step of tolerance so that an anchor sitting exactly on
    a segment edge -- which is where 1955 lands under a cut at 1955 -- is
    kept rather than being reported as outside the window.

    ``guard_wavenumbers`` / ``guard_intensity`` supply the arrays the guard and
    the data estimate read, when they must differ from the array being
    corrected. For the lower segment that is the **full** ROI:
    :data:`ANCHOR_PROMINENCE_FRAC` is a fraction of the whole ROI signal range,
    so measuring it on a segment would rescale the threshold, and
    :func:`anchor_data_value`'s window would go one-sided at the edge anchor.

    ``guard_cm1`` / ``prominence_frac`` override the guard's two thresholds.
    They default to the module constants, so an omitted pair is bit-for-bit the
    baseline every measurement in spec.md section 14 ran with;
    :class:`BaselineVariant` passes its own values here and to the cut's gate
    together.
    """
    ascending = np.argsort(wavenumbers)
    grid_w = wavenumbers[ascending]
    grid_b = baseline[ascending]
    guard_w = (
        wavenumbers
        if guard_wavenumbers is None
        else np.asarray(guard_wavenumbers, dtype=float)
    )
    guard_y = (
        intensity
        if guard_intensity is None
        else np.asarray(guard_intensity, dtype=float)
    )
    tolerance = float(np.median(np.diff(grid_w))) if grid_w.size > 1 else 0.0

    applied: list[float] = []
    gated: list[tuple[float, float, float]] = []
    residuals: list[tuple[float, float]] = []

    for anchor in anchors:
        if not grid_w[0] - tolerance <= anchor <= grid_w[-1] + tolerance:
            gated.append((float(anchor), float("nan"), float("nan")))
            continue
        hit = gating_extremum(
            guard_w,
            guard_y,
            anchor,
            guard_cm1=guard_cm1,
            prominence_frac=prominence_frac,
        )
        if hit is not None:
            gated.append((float(anchor), hit[0], hit[1]))
            continue
        value = anchor_data_value(guard_w, guard_y, anchor)
        residuals.append(
            (float(anchor), value - float(np.interp(anchor, grid_w, grid_b)))
        )
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
                label,
                anchor,
                where,
                fraction,
            )

    return BaselineOutcome(
        values=baseline + correction,
        degenerate=degenerate,
        anchors_applied=tuple(applied),
        anchors_gated=tuple(gated),
    )
