"""Baseline variants for offline baseline experimentation.

One place defines what "a baseline to try" means: which slice of the spectrum
the algorithm sees, and what settings it runs with. Everything else --
``api.compare_baselines``, the plots -- consumes :class:`BaselineVariant` and
never calls ``create_baseline`` itself.

**This is the expansion point.** A new baseline behaviour gets a field on
:class:`BaselineVariant` and a branch in :meth:`BaselineVariant.compute`, not a
parallel module. Five knobs are wired up: the ``std_distribution`` settings, the
wavenumber window, the anchor points of ``spec.md`` section 14.7, and the split
point of section 14.8 -- the two readings of section 14.4 step 3, both built.
The anchor is the one that is recommended; the truncating split is measured and
kept as a knob. ``lower_split_cm1`` is a third form -- section 14.9's
lower-only cut, which leaves the anchored full-ROI baseline untouched above the
cut and only replaces it below. ``lower_anchors`` pins *that* second baseline
-- section 14.10's anchors on the lower half, which only mean anything under
``lower_split_cm1``. ``lower_method`` replaces the lower segment's *algorithm*
-- section 14.12: any ``pybaselines.Baseline`` method instead of
``std_distribution``, which is the one knob no earlier section turned.
``lower_floor_cm1`` ties that second baseline off above the ROI floor --
section 14.13's answer to the edge artefact 14.12 left at 1750.
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
from pybaselines import Baseline
from pybaselines.classification import std_distribution
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

TRUNCATED_WINDOW_1800: Window = (2250.0, 1800.0)
"""``(high, low)`` cm-1 -- the full ROI with its bottom 50 cm-1 removed.

A **window**, so it reaches the one thing a floor cannot: ``create_baseline``
receives only ``y`` (spec.md section 0), so the window *is* the array and
``std_distribution`` classifies background over it globally. Truncating here
therefore changes the baseline *everywhere*, not just below 1800 -- which is
the point, and is why this cannot be read off section 14.13's figures.

**Three earlier things sit at 1800 or at truncation, and this is none of them.**
Confusing them is the likeliest misreading of section 14.16:

- :data:`LOWER_FLOOR_POINT_CM1` is also 1800, but is a *floor on a split form*
  (section 14.13): the second baseline stops there and the anchored full-ROI
  curve -- computed over the whole 2250-1750 array -- stands below it. Here
  there is no second baseline and nothing below 1800 at all.
- :data:`LOWER_MID_PROBE_CM1` is also 1800 and is a diagnostic readout
  (section 14.10.1). Under this window it lands on the array edge, so the
  probe's number stops being an interior measurement for this variant.
- Section 14.6 finding 7's rejected truncation was **bare** and at **1955** --
  no anchors, and 205 cm-1 lower. Anchors plus truncation at 1800 is a
  combination section 14 has not run, and finding 7 does not rule it out.

**The 1795/1775 bands leave the array**, as they do under the floor -- the
reading section 14.12 confirmed with the user. One measurement consequence
follows and is reported rather than assumed: :data:`INT_WINDOW_CM1` is
1838-1750, so a variant on this window has ``int`` over 1838-1800 only, ~40% of
the samples the full-ROI variants average over. It is a different statistic
under the same column name -- the run prints its sample count beside it, and
section 14.16 does not rank it against the others.
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

LOWER_SPLIT_POINT_CM1 = SPLIT_POINT_CM1
"""Default cut for the *lower-only* split of spec.md section 14.9.

The same wavenumber as :data:`SPLIT_POINT_CM1`; a separate name because the two
splits are different operations at the same point, and a reader who sees only
the number cannot tell which one is meant.

Under :attr:`BaselineVariant.split_cm1` the array is cut and **both** segments
are recomputed on their own shortened arrays, which is what section 14.8
measured and rejected: the upper segment's ``std_distribution`` sees a
different array, and the 1955 anchor then reads the corrupted truncation edge,
tilting the least-squares line so the 2006 anchor lands -8.2% off instead of
-2.1%. Under :attr:`BaselineVariant.lower_split_cm1` the upper side is never
recomputed at all -- the full-ROI anchored baseline is kept above the cut, so
that region provably does not move, and only the region below gets a second
``create_baseline``.
"""

LOWER_MID_PROBE_CM1 = 1800.0
"""Mid-segment diagnostic wavenumber. **Not an anchor** -- see section 14.10.1.

1800 *was* the interior lower anchor, and was removed after the figures were
judged. It is kept as a named probe because two anchors leave the middle of the
lower segment unconstrained, and ``data(1800) - baseline(1800)`` is the number
that says how far it drifted there. The run prints it beside the guard's verdict.

It is also the wavenumber section 14.10 finding 16 is about: at the default 13CO
isotope the low peaks sit at 1795/1775 (section 4), so 1800 is ~5 cm-1 from a
band and well inside :data:`ANCHOR_GUARD_CM1` -- yet the guard passes it on every
file, scoring 0.002-0.089 against the 0.5 threshold, because
:data:`ANCHOR_PROMINENCE_FRAC` is a fraction of the whole ROI range and the low
bands are 2-9% of it. That is a standing limit of the guard, not a fact about
this one wavenumber: **the guard does not protect a low-wavenumber anchor.**
"""

LOWER_ANCHOR_POINTS_CM1: tuple[float, ...] = (
    LOWER_SPLIT_POINT_CM1,
    DEFAULT_WINDOW[1],
)
"""Default anchors for the lower segment: **both endpoints of it, and nothing else.**

Only meaningful with :attr:`BaselineVariant.lower_split_cm1` -- there is no
"lower segment" without a cut, and :class:`BaselineVariant` raises rather than
ignore them.

**Two anchors, so they are hit exactly.** With three or more the correction is a
least-squares line and every anchor is a pull (the most misread property of
:data:`ANCHOR_POINTS_CM1`); with exactly two it is the unique line through both
residuals. The lower baseline therefore passes through the data estimate at the
cut and at the ROI floor. One consequence is worth stating because it retires a
thread: the seam is then **fixed by the upper side alone** -- it is the anchored
full-ROI baseline's own residual at 1955, which section 14.7 measured -- and
nothing done below the cut can shrink it further.

**Structurally different from :data:`ANCHOR_POINTS_CM1`, not a variant of it.**
The full-ROI set pins only the top (2240) and fits the other two below it, so
everything under 1955 is extrapolation -- the 205 cm-1 excursion section 14.9
finding 14 measured as the anchored baseline's single largest. This set pins
**both ends of its own 205 cm-1 segment**, so nothing in it is extrapolated.

**This is not section 14.7.1 being re-litigated.** That subsection removed a
*fourth* anchor at 1854 because one least-squares line cannot satisfy four points
over 400 cm-1 of curved residuals. Here the lower segment carries its own line,
fitted to its own points, over its own 205 cm-1; the full-ROI correction above the
cut is untouched and provably so (section 14.9 finding 13). It is the third answer
to section 14.7.1's closing "a non-affine correction or per-anchor weights" -- a
separate line on a separate segment.

**1800 is deliberately absent.** It was the interior third anchor, was built and
measured (section 14.10), and was removed by the user on the figures
(section 14.10.1). Removing it is what makes the remaining two exact; what it
costs is the only constraint on the middle of the segment, where the `.0022`
files' residuals are curved by 4-6% of range. :data:`LOWER_MID_PROBE_CM1` keeps
that cost measurable. Do not re-add it without re-reading 14.10.1.

The two values track :data:`LOWER_SPLIT_POINT_CM1` and :data:`DEFAULT_WINDOW` so
"both endpoints" stays true if either moves;
:meth:`BaselineVariant.__post_init__` re-checks it per variant, because a variant
with its own window or cut would otherwise silently anchor at a point that is no
longer an endpoint.
"""

LOWER_METHOD_CANDIDATE = "pspline_arpls"
"""The lower-segment algorithm spec.md section 14.12 measured, at its defaults.

A ``pybaselines.Baseline`` method name for :attr:`BaselineVariant.lower_method`.
**Not a default** -- ``lower_method`` is ``None`` unless a variant asks for it,
and nothing in ``config/analysis.yaml`` changed.

Named because it is the one candidate that satisfied all three of the user's
stated targets at once (section 14.12): the baseline through the midpoint of the
dispersive ~1850 feature on the post-crossing files, under the base of the 1850
and 1870-1880 bands on the pre-crossing ones, and a near-zero mean residual over
1838-1750. Every parameter variant tried was worse on at least one of them, so
the defaults are where it is used -- that is evidence against a tuned optimum,
not a reason to stop looking.

Its cost is the seam, which no longer has an anchor holding it: ~1.5x the
two-anchor form of section 14.10.1 on both samples measured.
"""

LOWER_FLOOR_POINT_CM1 = 1800.0
"""Default floor for :attr:`BaselineVariant.lower_floor_cm1` (spec.md 14.13).

**The lower segment's lowest wavenumber, not the ROI's.** Under
:attr:`BaselineVariant.lower_split_cm1` alone the second baseline runs
1955-1750 and its algorithm therefore sees the ROI's own edge, where
section 14.12's figures found the cost of that form: on
``...-012_delta10.0052`` the spline flattens below ~1790 while the data climbs
to the floor, leaving the subtracted trace at +0.0005 at 1750 -- that file's
``int`` of +1.11, the largest of the judged six, and the end behaviour of an
unanchored spline at an array edge rather than anything about the spectrum.
Tying the segment off here removes that edge from the fit.

Two consequences, both deliberate and both measured rather than assumed:

- **Below the floor the anchored full-ROI baseline stands.** There is no
  extrapolation and no hold -- the splice simply does not reach there, so that
  region is section 14.7 exactly, the same fallback a gated cut gets. The price
  is a *second* seam, at the floor; :attr:`BaselineOutcome.floor_seam_jump`
  reports it next to the first.
- **The 1795/1775 bands leave the fit.** They sit below the floor, which is
  the reading section 14.12 confirmed with the user -- *"Include the bands at
  1795/1775. There is a reason these are no longer in production."* -- and
  section 4's two dormant peaks are on that same path out.

The same number as :data:`LOWER_MID_PROBE_CM1`, and **not the same thing**: the
probe asks how far the segment drifted in its middle, and under a floor here
1800 is no longer its middle but its end, where the correction (if any anchors
are asked for) is exact. Do not read one for the other.
"""


LOWER_CONTINUATION_LAM = 1e3
"""Default curvature penalty for :attr:`BaselineVariant.lower_continuation_lam`
(spec.md section 14.14).

**Not a default** -- ``lower_continuation_lam`` is ``None`` unless a variant
asks for it, and nothing in ``config/analysis.yaml`` changed. Named so a sweep
has a centre to sweep around and the recommended value has one home.

The number is the weight on the squared second difference against a unit weight
on each classified sample, the same balance ``pybaselines``' Whittaker methods
use ``lam`` for -- so values in the 1e2-1e8 range read the way they do there.
It is the form's **only** parameter: everything else about the curve is fixed
by the two pinned nodes at the cut and by which samples ``std_distribution``
classified.

**1e3 is where section 14.15 measured it**, swept over seven decades (1e1 to
1e8) on the judged six and again on the 60-file breadth sample. It is not a
sharp optimum and it is not recommended as a default -- it wins most of the
columns and loses two, and the visual call has not been made (section 14.3
finding 4).

What it trades is stated plainly because the two ends of the range are both
wrong: small ``lam`` lets the curve chase the ~3-24 classified samples of
section 14.14 finding 42 and it ripples; large ``lam`` drives the second
difference to zero and the continuation becomes the straight extrapolation of
the anchored curve's slope at 1955, which is section 14.7's behaviour below the
cut written a second way.
"""

LOWER_CONTINUATION_SETTINGS: dict = {"num_std": 3.0}
"""The classifier setting the continuation is measured with (spec.md 14.15).

Passed as ``lower_settings`` beside :attr:`BaselineVariant.lower_continuation_lam`.
**Not a default** -- ``config/analysis.yaml`` is untouched and the live path
never sees this. Under a continuation ``lower_settings`` configures the
*classifier* rather than a second baseline, so this is the one lever on
section 14.14 finding 42 that stays inside the form.

**What it is for.** At the unmodified ``num_std`` of 1.1 the classifier supplies
**nothing below ~1910** on both pre-crossing files -- zero samples in the whole
1838-1750 window section 14.12's ``int`` is measured over (section 14.15
finding 44). The continuation then extrapolates the last ~160 cm-1 under its
curvature penalty alone, which is why ``int`` misses by +5.6 to +6.6% of range
at *every* ``lam`` across seven decades. At 3.0 the classifier reaches to
~1807, and ``int`` comes back.

**The risk, stated because it is contingent and not designed.** ``num_std``
raises the tolerance for calling a sample background, so a larger value
classifies *more* of the spectrum -- the opposite direction from a mask. At 3.0
it calls **all 17** samples of the 1870-1836 band window background on four of
the six judged files, which is precisely the "pure centre-line method" section
14.12 finding 31 predicts should fail the pre-crossing regime. It does not fail,
for one measured reason: on both pre-crossing files it still classifies **0 of
17** there, exactly as at 1.1. So the threshold happens to fall on opposite
sides of the same window in the two regimes, and the form's shape-adaptivity
survives *because of* that coincidence rather than in spite of it. Nothing here
guarantees it holds on a file neither regime describes. At 5.0 it breaks --
``...-017`` flips to 17/17 and its ``mid`` error triples (finding 46).
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

INT_SHARED_WINDOW_CM1: Window = (1838.0, 1800.0)
"""``(high, low)`` -- :data:`INT_WINDOW_CM1` clipped to what a 1800-truncated
variant also covers.

Exists because ``int`` is otherwise **not comparable across a window change**
(spec.md 14.16). A variant on :data:`TRUNCATED_WINDOW_1800` keeps only 1838-1800
of the ``int`` window, so its ``int`` averages ~20 samples where a full-ROI
variant averages ~46: the same column name over a different statistic, which is
exactly the kind of silent mismatch section 0's trap list is about.

``int_shared`` is that number on the **same samples for every variant**, so a
truncated form and a full-ROI form can be ranked against each other directly. It
is a real column rather than a probe on section 14.15's precedent -- that
section had to rebuild ``mid``/``und``/``int`` because 14.12, 14.13 and 14.14
each re-derived them in a scratchpad that was not kept, and section 14.16's
load-bearing comparison would have been the fourth.

Read it *beside* ``int``, never instead of it: it says nothing about 1800-1750,
which is where section 14.12's edge artefact lived and where a truncated variant
has no baseline at all.
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
    """Which segments reported no baseline points.

    ``"upper"`` / ``"lower"`` under :attr:`BaselineVariant.split_cm1`;
    ``"full"`` / ``"lower"`` under :attr:`BaselineVariant.lower_split_cm1`,
    where the upper side is not a segment at all but the whole ROI.

    A single flag for the pair would lose which side broke, and the lower
    segment is the one at risk under either form: it is ~106 samples, so the
    sample-count settings (``half_window`` and friends) are ~2.4x larger
    relative to the array than the values they were tuned at.
    """

    lower_anchors_applied: tuple[float, ...] = ()
    """Anchor wavenumbers the **lower segment's** baseline was corrected at.

    Separate from :attr:`anchors_applied` because they are two corrections on
    two arrays -- least-squares above the cut, exact through both ends below it
    -- and one merged tuple could not say which of them a gated 1955 was dropped
    from (spec.md sections 14.10/14.10.1). Empty unless
    :attr:`BaselineVariant.lower_anchors` was asked for.
    """

    lower_anchors_gated: tuple[tuple[float, float, float], ...] = ()
    """``(anchor, extremum wavenumber, prominence fraction)`` per rejected
    lower-segment anchor. Reported for the reason this class exists: with the
    default two-anchor set a gated anchor leaves the correction a constant shift
    instead of an exact line through both ends, and a lower baseline that was
    silently left half-corrected looks exactly like one where correcting did
    little."""

    lower_method_applied: str = ""
    """The ``pybaselines`` method the lower segment ran, under
    :attr:`BaselineVariant.lower_method`. Empty when the lower segment ran
    ``create_baseline``/``std_distribution`` -- which is every variant before
    spec.md section 14.12 -- or when there is no lower segment at all.

    Reported rather than inferred from the variant, because a gated cut leaves
    no lower segment and therefore no method, and a variant that *asked* for one
    looks identical to one that did not unless the outcome says which ran.
    """

    lower_method_degeneracy_checked: bool = True
    """False when the lower segment's degeneracy could not be tested.

    ``std_distribution`` warns *"there were no baseline points found"* and
    :meth:`BaselineVariant._segment_baseline` catches it; a ``pybaselines``
    method called directly emits no such warning, so under
    :attr:`BaselineVariant.lower_method` the ``"lower"`` entry of
    :attr:`degenerate_segments` rests on a **weaker, structural** check
    (non-finite or constant output) and not on the algorithm's own verdict. The
    traps list in spec.md section 0 says not to drop the degenerate flag; this
    says how far to trust it, because a flag that is clean for want of anyone
    asking reads exactly like one that was checked.
    """

    lower_floor_applied: float | None = None
    """Wavenumber the lower segment was tied off at, or ``None``.

    ``None`` means it ran to the ROI floor, which is every variant before
    spec.md section 14.13. Reported rather than inferred from the variant for
    :attr:`lower_method_applied`'s reason: a gated cut leaves no lower segment
    and therefore no floor either.
    """

    floor_edges: tuple[float, float] | None = None
    """``(lowest wavenumber of the lower segment, highest below the floor)``.

    The second seam, sitting between two samples exactly as
    :attr:`segment_edges` does. ``None`` when no floor was applied.
    """

    floor_seam_jump: float = float("nan")
    """``lower(floor edge) - anchored(floor edge)``: the jump at the floor.

    The direct price of :attr:`lower_floor_applied` and the thing to weigh the
    edge artefact against, so it is reported on the same terms as
    :attr:`seam_jump` -- measured, not blended away. Below the floor the curve
    is the anchored full-ROI baseline, so this is also the size of the
    disagreement between the two forms at that point.
    """

    lower_continuation_lam_applied: float | None = None
    """The curvature penalty the continuation of spec.md section 14.14 ran with.

    ``None`` when no continuation was built -- which is every variant before
    14.14, and also a variant that asked for one but had its cut gated.
    Reported rather than inferred from the variant for
    :attr:`lower_method_applied`'s reason.
    """

    lower_continuation_points: int = -1
    """How many samples below the cut ``std_distribution`` classified as
    background, i.e. how many fidelity points the continuation was fitted to.

    ``-1`` when no continuation was built. **This is finding 42's number, made
    a per-run column.** It is the whole diagnosis of the region below the cut:
    on ``...-021`` it is 3 over a 205 cm-1 span, and a continuation fitted to 3
    points is carried almost entirely by its curvature penalty. A run where this
    comes back 0 produced the straight extrapolation of the anchored slope and
    nothing else -- a curve that looks fitted and is not.
    """

    seam_excess_jump: float = float("nan")
    """:attr:`seam_jump` minus the unsplit anchored curve's own step across the
    same sample pair, in raw units.

    The column that makes the seam comparable **across forms**, which
    :attr:`seam_jump` alone is not. No two adjacent samples of a continuous
    curve have equal values -- the grid step is ~1.9 cm-1 -- so a form that is
    continuous at the cut still reports a non-zero ``seam_jump`` of roughly
    slope x step. Subtracting what the anchored baseline does across that same
    pair leaves the part that is a genuine *discontinuity*.

    For two independently computed segments (sections 14.9-14.13) this is
    within rounding of ``seam_jump`` itself, because the two curves have no
    relation. For section 14.14's continuation it is the number to read: the
    claim is that it goes to zero by construction, and this is where that is
    checked rather than asserted.
    """

    split_form: str = ""
    """Which cut produced this baseline -- ``""``, ``"truncate"`` or ``"lower_only"``.

    Both forms report through :attr:`split_applied`, :attr:`segment_edges` and
    :attr:`seam_jump`, because a cut at 1955 is a cut at 1955 either way. They
    are not the same operation, though (see :data:`LOWER_SPLIT_POINT_CM1`), and
    a comparison table carrying both is unreadable without a column saying
    which is which.
    """

    @property
    def anchor_note(self) -> str:
        """One-line summary for a legend, empty when nothing was requested."""
        if not any(
            (
                self.anchors_applied,
                self.anchors_gated,
                self.split_applied,
                self.split_gated,
                self.lower_anchors_applied,
                self.lower_anchors_gated,
                self.lower_method_applied,
                self.lower_floor_applied,
            )
        ):
            return ""
        parts = []
        if self.split_applied is not None:
            form = f" {self.split_form}" if self.split_form else ""
            parts.append(f"split {self.split_applied:.0f}{form}")
        if self.lower_method_applied:
            parts.append(f"lower {self.lower_method_applied}")
        if self.lower_floor_applied is not None:
            parts.append(f"floor {self.lower_floor_applied:.0f}")
        if self.split_gated is not None:
            split, where, prominence = self.split_gated
            parts.append(
                f"SPLIT GATED {split:.0f} (band at {where:.0f}, p={prominence:.2f})"
            )
        if self.anchors_applied:
            parts.append("anchored " + "/".join(f"{a:.0f}" for a in self.anchors_applied))
        for anchor, where, prominence in self.anchors_gated:
            parts.append(f"GATED {anchor:.0f} (band at {where:.0f}, p={prominence:.2f})")
        if self.lower_anchors_applied:
            parts.append(
                "lower-anchored "
                + "/".join(f"{a:.0f}" for a in self.lower_anchors_applied)
            )
        for anchor, where, prominence in self.lower_anchors_gated:
            parts.append(
                f"LOWER GATED {anchor:.0f} (band at {where:.0f}, p={prominence:.2f})"
            )
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
        lower_split_cm1: Wavenumber below which the baseline is replaced by a
            second, independently computed one -- or ``None``, the default.
            Mutually exclusive with ``split_cm1``: both cut at a wavenumber,
            but only this one leaves the region *above* the cut alone.
            ``create_baseline`` runs on the full window and ``anchors`` are
            applied to that full-ROI result, so above the cut this variant is
            equal to the unsplit anchored baseline by construction -- bit for
            bit, which is the check spec.md section 14.9 is built on. Below the
            cut a second ``create_baseline`` runs with the **unmodified**
            ``voigt_fit.baseline`` settings and no anchors. See
            :data:`LOWER_SPLIT_POINT_CM1` for why this is a separate field
            rather than a mode of ``split_cm1``.
        lower_floor_cm1: Wavenumber the **lower segment is tied off at**, or
            ``None`` -- the default -- to run it to the bottom of the window,
            which is what every section through 14.12 measured. Requires
            ``lower_split_cm1``, and must lie strictly between the window's low
            edge and the cut: at the edge it is a no-op that reads like a
            setting, which is the silent-no-op failure the other fields raise
            for.

            The second baseline then covers ``lower_split_cm1`` down to here
            and **nothing below**, where the anchored full-ROI baseline stands
            unchanged -- the same fallback a gated cut gets, reached by the
            splice not reaching rather than by a rule. Its price is a second
            seam, at the floor, reported in
            :attr:`BaselineOutcome.floor_seam_jump`.

            The knob exists because ``create_baseline`` and a ``pybaselines``
            method alike see *only* the array handed to them (spec.md section
            0), so the segment's lowest wavenumber is an array edge with
            whatever end behaviour the algorithm has there -- section 14.12's
            figures caught a spline flattening against it. See
            :data:`LOWER_FLOOR_POINT_CM1`.
        lower_anchors: Wavenumbers the **lower segment's** own baseline is
            corrected at, under ``lower_split_cm1`` -- ``()``, the default,
            leaves it unanchored as spec.md sections 14.8/14.9 measured it. Its
            own affine correction, fitted to its own residuals; the full-ROI
            correction above the cut is untouched, so ``upper_max_abs_diff``
            stays 0.0 exactly. Requires ``lower_split_cm1``: without a cut
            there is no lower segment, and a silently ignored anchor list is the
            same failure mode as an unknown ``settings`` key. Use
            :data:`LOWER_ANCHOR_POINTS_CM1` for the both-endpoints pair of
            sections 14.10/14.10.1, which being exactly two are hit exactly.
        lower_settings: ``std_distribution`` overrides for the **lower segment
            only**, or ``None`` -- the default -- to run it with the unmodified
            ``voigt_fit.baseline`` settings, which is what sections 14.8, 14.9
            and 14.10 measured. Validated on the same terms as ``settings``: an
            unknown key raises. Requires a cut (either kind); without one there
            is no lower segment and the override would silently do nothing.

            Exposed because the lower segment has a real reason to want
            different values, not as a general knob: it is ~106 samples against
            the full ROI's ~259, so ``half_window`` and the other sample-count
            settings are ~2.4x larger *relative to the array* than the values
            they were tuned at (section 14.8's "no degenerate segments" note).
            Those are the knobs to reach for first. No default is changed here
            and none is recommended -- this is the instrument, not a tuning.
        lower_method: Name of a ``pybaselines.Baseline`` method to run on the
            **lower segment** in place of ``std_distribution``, or ``None`` --
            the default -- to keep ``create_baseline``, which is what every
            section through 14.11 measured. Requires ``lower_split_cm1``, on
            ``lower_anchors``' precedent: without a cut there is no lower
            segment, and a silently ignored method name is the same failure as a
            misspelled settings key. Mutually exclusive with ``lower_settings``
            for the same reason -- those keys are ``std_distribution``'s and
            another algorithm would ignore them without saying so. An unknown
            method name raises at variant construction.

            This is the knob spec.md section 14.3 finding 1 could not turn: that
            sweep, and section 14.11's re-sweep under the anchor, both varied
            ``std_distribution``'s *parameters*, never the algorithm. Section
            14.12 varies the algorithm and is the first thing in section 14 to
            move the pre-crossing `.0022` regime in a direction the figures
            accepted. See :data:`LOWER_METHOD_CANDIDATE`.

            The segment is handed to ``pybaselines`` with **ascending**
            wavenumbers as ``x_data`` and the result flipped back, because
            wavenumbers descend here (spec.md section 0) and a method that uses
            ``x`` would otherwise see the axis reversed.
        lower_method_kwargs: Keyword arguments for ``lower_method``. ``{}`` --
            the default -- runs the method at *its own* defaults, which is where
            section 14.12 measured the candidate and where it scored best; every
            parameter variant tried was worse on at least one target. Not
            validated here: ``pybaselines`` raises a ``TypeError`` on an unknown
            keyword, which is already loud, and the accepted keywords differ per
            method so there is no key list to check against.
        lower_continuation_lam: Curvature penalty for the **C1 continuation**
            of spec.md section 14.14, or ``None`` -- the default -- for the
            second independent ``create_baseline`` every section through
            14.13 measured. Requires ``lower_split_cm1``; must be strictly
            positive.

            This changes the lower segment's *construction*, which is the
            knob no earlier section turned: 14.11 varied
            ``std_distribution``'s parameters, 14.12 its algorithm, 14.10
            the anchors on top of it -- all of them a **second,
            independent** curve spliced on at the cut. Here there is no
            second curve. The anchored full-ROI baseline is **continued
            downward** from the cut: its value *and* its slope there are
            pinned -- as the two grid nodes just above the cut, so the pin
            is exact and needs no sign convention -- and below them the
            curve is the penalised least-squares fit to whatever
            ``std_distribution`` classified as background, with this as the
            weight on its squared second difference.

            The point is section 14.14 finding 42: on ``...-021`` the lower
            segment rests on **3** classified samples over 205 cm-1, so the
            defect is an **under-constrained** curve rather than a
            misclassified one -- which is why every mask-style fix
            (``weights``, a curvature or peak-list mask) measured as a
            bit-for-bit no-op there. A starting value, a starting slope and
            a stated amount of allowed bend are exactly the constraints
            that are missing. See :data:`LOWER_CONTINUATION_LAM`.

            Mutually exclusive with ``lower_method`` (that *is* the second
            curve), ``lower_anchors`` (an affine correction applied on top
            would shift and tilt the curve away from the value and slope it
            was pinned to) and ``lower_floor_cm1`` (a continuation has no
            independent segment to tie off, and a floor would reintroduce
            the second interface section 14.13.1 removed).

            ``lower_settings`` **is** accepted, and this is the one place
            its meaning differs from its docstring above: there is no
            second baseline for it to configure, so it configures the
            **classifier** that supplies the continuation's fidelity points
            -- which samples below the cut count as background. That is the
            same object those keys always named, reached one step earlier,
            and finding 42 is what makes it the interesting lever here
            rather than a leftover.
    """

    label: str
    settings: dict = field(default_factory=dict)
    window: Window = DEFAULT_WINDOW
    anchors: tuple[float, ...] = ()
    split_cm1: float | None = None
    lower_split_cm1: float | None = None
    lower_anchors: tuple[float, ...] = ()
    lower_settings: dict | None = None
    lower_method: str | None = None
    lower_method_kwargs: dict = field(default_factory=dict)
    lower_floor_cm1: float | None = None
    lower_continuation_lam: float | None = None

    @classmethod
    def coerce(cls, item: BaselineVariant | tuple) -> BaselineVariant:
        """Build a variant from itself or a ``(label, settings[, window])`` tuple.

        Tuples keep the calling code readable in a ``__main__`` block:

            [("current", {}), ("num_std 1.4", {"num_std": 1.4})]
        """
        if isinstance(item, cls):
            return item
        if not isinstance(item, (tuple, list)) or not 2 <= len(item) <= 12:
            raise TypeError(
                "each variant must be a BaselineVariant or a "
                "(label, settings[, window[, anchors[, split_cm1"
                "[, lower_split_cm1[, lower_anchors[, lower_settings"
                "[, lower_method[, lower_method_kwargs"
                "[, lower_floor_cm1[, lower_continuation_lam]]]]]]]]]]) "
                f"tuple; got {item!r}. Past the 5th slot the keyword form "
                "BaselineVariant(label=..., lower_split_cm1=...) reads better "
                "-- positional tuples were for the two-element case."
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

        object.__setattr__(
            self, "lower_anchors", tuple(float(a) for a in self.lower_anchors)
        )
        if self.lower_settings is not None:
            if self.split_cm1 is None and self.lower_split_cm1 is None:
                raise ValueError(
                    f"variant {self.label!r} declares lower_settings "
                    f"{self.lower_settings} but makes no cut. There is no lower "
                    "segment to configure without split_cm1 or lower_split_cm1, "
                    "and silently ignoring them would look exactly like settings "
                    "that did nothing -- use `settings` for the full-ROI baseline."
                )
            # Same eager check `settings` gets, and for the same reason: a
            # misspelled key would fall back to the default and silently run the
            # unmodified lower baseline.
            ir_config.get_baseline_settings(override=dict(self.lower_settings))

        if self.lower_method is not None:
            if self.lower_split_cm1 is None:
                raise ValueError(
                    f"variant {self.label!r} declares "
                    f"lower_method={self.lower_method!r} but no lower_split_cm1. "
                    "There is no lower segment to run it on without a cut, and "
                    "silently ignoring it would look exactly like a method that "
                    "changed nothing -- pass "
                    "lower_split_cm1=LOWER_SPLIT_POINT_CM1."
                )
            if self.lower_settings is not None:
                raise ValueError(
                    f"variant {self.label!r} sets both lower_method="
                    f"{self.lower_method!r} and lower_settings "
                    f"{self.lower_settings}. Those keys belong to "
                    "std_distribution and another algorithm would ignore them "
                    "without saying so -- the same silent no-op an unknown "
                    "settings key is rejected for. Pass lower_method_kwargs "
                    "instead, or drop one of the two."
                )
            if self.lower_method.startswith("_") or not callable(
                getattr(Baseline, self.lower_method, None)
            ):
                raise ValueError(
                    f"variant {self.label!r}: lower_method "
                    f"{self.lower_method!r} is not a pybaselines.Baseline "
                    "method. A typo here would otherwise surface only when the "
                    "first file is computed, partway through a batch."
                )

        if self.lower_method_kwargs and self.lower_method is None:
            raise ValueError(
                f"variant {self.label!r} declares lower_method_kwargs "
                f"{self.lower_method_kwargs} but no lower_method; there is "
                "nothing to pass them to."
            )

        if self.lower_floor_cm1 is not None:
            if self.lower_split_cm1 is None:
                raise ValueError(
                    f"variant {self.label!r} declares "
                    f"lower_floor_cm1={self.lower_floor_cm1:.0f} but no "
                    "lower_split_cm1. There is no lower segment to tie off "
                    "without a cut, and silently ignoring the floor would look "
                    "exactly like a floor that changed nothing -- pass "
                    "lower_split_cm1=LOWER_SPLIT_POINT_CM1."
                )
            object.__setattr__(self, "lower_floor_cm1", float(self.lower_floor_cm1))
            if not low < self.lower_floor_cm1 < float(self.lower_split_cm1):
                raise ValueError(
                    f"lower_floor_cm1 {self.lower_floor_cm1:.0f} must lie "
                    f"strictly between this variant's window floor {low:.0f} "
                    f"and its cut at {float(self.lower_split_cm1):.0f}. At the "
                    "window floor it is the unfloored form written as if it "
                    "were a setting -- pass None for that; at or above the cut "
                    "it leaves no segment to fit."
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

        if self.split_cm1 is not None and self.lower_split_cm1 is not None:
            raise ValueError(
                f"variant {self.label!r} sets both split_cm1 and lower_split_cm1. "
                "They are two different cuts at a wavenumber -- split_cm1 "
                "recomputes both sides on truncated arrays (spec.md 14.8), "
                "lower_split_cm1 leaves the anchored full-ROI baseline standing "
                "above the cut (14.9) -- so combining them has no meaning. "
                "Declare them as two variants and compare."
            )

        for name in ("split_cm1", "lower_split_cm1"):
            value = getattr(self, name)
            if value is None:
                continue
            object.__setattr__(self, name, float(value))
            value = getattr(self, name)
            if not low < value < high:
                raise ValueError(
                    f"{name} {value:.0f} must lie strictly inside this variant's "
                    f"window {self.window!r}; a cut at the edge leaves one segment "
                    "empty"
                )

        for anchor in self.lower_anchors:
            if not low <= anchor <= high:
                raise ValueError(
                    f"lower anchor {anchor:.0f} cm-1 lies outside this variant's "
                    f"window {self.window!r}"
                )
            if self.lower_split_cm1 is not None and anchor > self.lower_split_cm1:
                raise ValueError(
                    f"lower anchor {anchor:.0f} cm-1 sits above this variant's cut "
                    f"at {self.lower_split_cm1:.0f}; the lower segment does not "
                    "cover it. Anchors above the cut belong in `anchors`, which "
                    "corrects the full-ROI baseline."
                )
            if self.lower_floor_cm1 is not None and anchor < self.lower_floor_cm1:
                raise ValueError(
                    f"lower anchor {anchor:.0f} cm-1 sits below this variant's "
                    f"floor at {self.lower_floor_cm1:.0f}; the lower segment "
                    "stops there and does not cover it. The both-endpoints pair "
                    "of LOWER_ANCHOR_POINTS_CM1 ends at the ROI floor, so a "
                    "floored variant wanting the same idea asks for "
                    "(lower_split_cm1, lower_floor_cm1) instead."
                )

        if self.lower_continuation_lam is not None:
            if self.lower_split_cm1 is None:
                raise ValueError(
                    f"variant {self.label!r} declares lower_continuation_lam "
                    f"{self.lower_continuation_lam} but no lower_split_cm1. The "
                    "continuation starts *at* the cut -- without one there is "
                    "nothing to continue from and nothing below to continue "
                    "into, and silently ignoring it would look exactly like a "
                    "penalty that changed nothing. Pass "
                    "lower_split_cm1=LOWER_SPLIT_POINT_CM1."
                )
            object.__setattr__(
                self, "lower_continuation_lam", float(self.lower_continuation_lam)
            )
            if not (
                np.isfinite(self.lower_continuation_lam)
                and self.lower_continuation_lam > 0
            ):
                raise ValueError(
                    f"variant {self.label!r}: lower_continuation_lam must be a "
                    f"finite positive weight; got {self.lower_continuation_lam}. "
                    "At 0 the curvature penalty vanishes and the fit is "
                    "undetermined wherever the classifier supplied no points -- "
                    "which on the .0022 files is most of the segment (spec.md "
                    "14.14 finding 42). See LOWER_CONTINUATION_LAM."
                )
            if self.lower_method is not None:
                raise ValueError(
                    f"variant {self.label!r} sets both lower_continuation_lam "
                    f"and lower_method={self.lower_method!r}. They are two "
                    "answers to the same question: lower_method computes a "
                    "second, independent baseline below the cut (spec.md 14.12), "
                    "and the continuation is the form that computes none. "
                    "Declare them as two variants and compare."
                )
            if self.lower_anchors:
                raise ValueError(
                    f"variant {self.label!r} sets both lower_continuation_lam "
                    f"and lower_anchors {self.lower_anchors}. The anchors are an "
                    "affine correction applied *after* the lower curve is built, "
                    "so they would shift and tilt it away from the value and "
                    "slope it was pinned to at the cut -- destroying the one "
                    "property this form exists for. Drop one of the two."
                )
            if self.lower_floor_cm1 is not None:
                raise ValueError(
                    f"variant {self.label!r} sets both lower_continuation_lam "
                    f"and lower_floor_cm1={self.lower_floor_cm1:.0f}. The floor "
                    "ties off an independent segment so its algorithm stops "
                    "seeing the ROI edge (spec.md 14.13); a continuation has no "
                    "independent segment, and stopping it early would leave the "
                    "anchored baseline standing below it behind a second "
                    "interface -- the thing 14.13.1 removed from consideration. "
                    "The 1750 edge is a real exposure here, and is measured "
                    "rather than floored."
                )

    def resolved_lower_settings(self, voigt_settings: dict | None = None) -> dict:
        """Settings the lower segment runs with.

        The current baseline's own parameters by default -- ``settings`` belongs
        to the full-ROI/upper baseline and is deliberately *not* inherited, so a
        variant that changes ``num_std`` above the cut leaves the region below it
        on the recipe the file has today. :attr:`lower_settings` overrides that,
        and only that.
        """
        return ir_config.get_baseline_settings(
            voigt_settings, override=dict(self.lower_settings or {}) or None
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

        When :attr:`lower_split_cm1` is set instead, the anchored full-ROI
        baseline is computed first and kept unchanged above the cut; only below
        it is a second baseline substituted, carrying its own
        :attr:`lower_anchors` if any were asked for. See
        :meth:`_compute_lower_split`.
        """
        settings = self.resolved_settings(voigt_settings)
        intensity = np.asarray(intensity, dtype=float)

        if self.lower_split_cm1 is not None:
            if wavenumbers is None:
                raise ValueError(
                    f"variant {self.label!r} declares "
                    f"lower_split_cm1={self.lower_split_cm1} but compute() was "
                    "called without wavenumbers"
                )
            return self._compute_lower_split(
                np.asarray(wavenumbers, dtype=float),
                intensity,
                settings,
                voigt_settings,
            )

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
            outcome.split_form = "truncate"
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
        # not this variant's -- unless lower_settings overrides them.
        lower_values, lower_degenerate = self._segment_baseline(
            intensity[lower], self.resolved_lower_settings(voigt_settings), "lower"
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
            split_form="truncate",
            segment_edges=(
                float(wavenumbers[upper_edge]),
                float(wavenumbers[lower_edge]),
            ),
            seam_jump=float(values[upper_edge] - values[lower_edge]),
            degenerate_segments=segments,
        )

    def _compute_lower_split(
        self,
        wavenumbers: np.ndarray,
        intensity: np.ndarray,
        settings: dict,
        voigt_settings: dict | None,
    ) -> BaselineOutcome:
        """The lower-only cut of spec.md section 14.9.

        Every failure section 14.8 measured traces to the *upper* segment being
        computed on a shortened array, so this form never shortens it:

        1. ``create_baseline`` on the full window, this variant's settings;
        2. :func:`apply_anchors` on the **full** wavenumbers and intensity;
        3. ``create_baseline`` on the sub-array below the cut -- and at or
           above :attr:`lower_floor_cm1` where one is set -- with the
           unmodified ``voigt_fit.baseline`` settings, or
           :attr:`lower_settings` where given;
        3b. :func:`apply_anchors` on that lower baseline at
           :attr:`lower_anchors`, if any -- its own least-squares line, on its
           own array, fitted before the splice (spec.md section 14.10);
        4. splice -- step 2's values at and above the cut, step 3b's below.

        Under a floor, step 4 splices into ``[floor, cut)`` only, so *below* the
        floor step 2's anchored full-ROI baseline stands untouched. That is the
        section 14.7 curve exactly, for the same reason the gated path returns
        it: it is what was already there, not a fallback constructed here. The
        cost is a second discontinuity at the floor, reported separately in
        ``floor_seam_jump`` -- the floor cannot move the first seam, which sits
        at the cut and is fixed by the two curves meeting there.

        Step 2 must precede step 4. Anchoring the *spliced* curve would fit the
        least-squares line to a mixture of two baselines, which is the premise
        of this form collapsing: the point is that no anchor ever reads a
        truncation edge, and that above the cut the result is bit-for-bit the
        unsplit anchored baseline. Step 3b obeys the same rule from the other
        side -- it corrects the lower segment alone, never the spliced curve, so
        it cannot reach above the cut and ``upper_max_abs_diff`` stays 0.0.

        The cut is gated by the same test as an anchor at that wavenumber. A
        gated cut returns the plain anchored full-ROI baseline -- which is
        steps 1 and 2 alone, so the fallback is the section 14.7 path exactly,
        not a re-derivation of it. :attr:`lower_anchors` go with it: there is no
        lower segment to anchor, so ``lower_anchors_applied`` comes back empty
        rather than reporting anchors that were never fitted.
        """
        cut = float(self.lower_split_cm1)

        # Steps 1-2: full ROI throughout. No guard_* override is needed or
        # wanted here -- unlike the truncating split, the array being corrected
        # *is* the full ROI, so the guard and anchor_data_value already read it.
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

        split_hit = gating_extremum(wavenumbers, intensity, cut)
        if split_hit is not None:
            LOGGER.debug(
                "variant %r: lower split at %.0f gated by a band at %.0f "
                "(prominence %.2f of signal range); returning the anchored "
                "full-ROI baseline unchanged",
                self.label, cut, split_hit[0], split_hit[1],
            )
            outcome.split_gated = (cut, float(split_hit[0]), float(split_hit[1]))
            outcome.split_form = "lower_only"
            return outcome

        # Split by wavenumber value, never by position: wavenumbers descend, so
        # a positional slice takes the wrong end of the array.
        upper = wavenumbers >= cut
        floor = self.lower_floor_cm1
        # The lower segment is [floor, cut) where a floor is set, so what falls
        # below it is neither segment and keeps the anchored full-ROI values
        # the splice never writes over (spec.md 14.13).
        lower = ~upper if floor is None else (~upper) & (wavenumbers >= floor)
        if upper.sum() < 2 or lower.sum() < 2:
            where = f"splitting at {cut:.0f}"
            if floor is not None:
                where += f" with a floor at {floor:.0f}"
            raise ValueError(
                f"variant {self.label!r}: {where} leaves "
                f"{int(upper.sum())} / {int(lower.sum())} samples; each segment "
                "needs at least two"
            )

        # Step 3. The lower segment takes the current baseline's own parameters
        # -- not this variant's -- unless lower_settings overrides them, or
        # lower_method replaces the algorithm outright (spec.md 14.12).
        continuation_points = -1
        if self.lower_continuation_lam is not None:
            # Not a second baseline: the anchored curve, continued (14.14).
            # `outcome.values` and not `values` -- the pin has to be taken from
            # the curve the splice will sit beside, which is the one the affine
            # correction has already been applied to.
            lower_values, lower_degenerate, continuation_points = (
                self._segment_continuation(
                    wavenumbers,
                    intensity,
                    outcome.values,
                    upper,
                    lower,
                    self.resolved_lower_settings(voigt_settings),
                )
            )
            method_applied = "continuation"
            degeneracy_checked = True
        elif self.lower_method is not None:
            lower_values, lower_degenerate = self._segment_pybaselines(
                wavenumbers[lower], intensity[lower]
            )
            method_applied = self.lower_method
            degeneracy_checked = False
        else:
            lower_values, lower_degenerate = self._segment_baseline(
                intensity[lower], self.resolved_lower_settings(voigt_settings), "lower"
            )
            method_applied = ""
            degeneracy_checked = True

        # Step 3b. The lower segment's own anchors, on the lower segment's own
        # array. Unanchored by default, which is what sections 14.8 and 14.9
        # measured.
        if self.lower_anchors:
            # The guard and the data estimate read the FULL ROI, as under the
            # truncating split and for the same two reasons:
            # ANCHOR_PROMINENCE_FRAC is calibrated against the whole ROI signal
            # range, so measuring it on a ~106-sample segment would rescale the
            # threshold; and anchor_data_value's +/-10 cm-1 window would go
            # one-sided at the anchor sitting on the cut. At the ROI floor it is
            # one-sided regardless -- there is no data below 1750 -- so that
            # residual is the noisiest of the three, and for the same reason the
            # guard cannot see an extremum peaking at the array's own edge.
            lower_outcome = apply_anchors(
                wavenumbers[lower],
                intensity[lower],
                lower_values,
                self.lower_anchors,
                guard_wavenumbers=wavenumbers,
                guard_intensity=intensity,
                degenerate=lower_degenerate,
                label=self.label,
            )
            lower_values = lower_outcome.values
            lower_anchors_applied = lower_outcome.anchors_applied
            lower_anchors_gated = lower_outcome.anchors_gated
        else:
            lower_anchors_applied = ()
            lower_anchors_gated = ()

        # Step 4. Assign through the boolean masks so the result comes back in
        # the order it was loaded in -- overlap_shift and the plots index the
        # baseline against the wavenumbers positionally.
        spliced = np.array(outcome.values, dtype=float, copy=True)
        spliced[lower] = lower_values

        upper_edge = int(np.argmin(np.where(upper, wavenumbers, np.inf)))
        lower_edge = int(np.argmax(np.where(lower, wavenumbers, -np.inf)))

        # The floor's own seam, on the same terms as the cut's: the value just
        # inside the fitted segment minus the anchored value just below it.
        below = (~upper) & (~lower)
        floor_edges = None
        floor_seam = float("nan")
        if floor is not None and bool(below.any()):
            floor_top = int(np.argmin(np.where(lower, wavenumbers, np.inf)))
            below_top = int(np.argmax(np.where(below, wavenumbers, -np.inf)))
            floor_edges = (
                float(wavenumbers[floor_top]),
                float(wavenumbers[below_top]),
            )
            floor_seam = float(spliced[floor_top] - spliced[below_top])

        segments = tuple(
            name
            for name, flag in (("full", degenerate), ("lower", lower_degenerate))
            if flag
        )
        # What the unsplit anchored curve does across the same sample pair. A
        # continuous curve still steps by ~slope x 1.9 cm-1 there, so this is
        # what has to come off seam_jump before two forms can be compared on it
        # (BaselineOutcome.seam_excess_jump).
        anchored_step = float(
            outcome.values[upper_edge] - outcome.values[lower_edge]
        )
        return BaselineOutcome(
            values=spliced,
            degenerate=bool(segments),
            anchors_applied=outcome.anchors_applied,
            anchors_gated=outcome.anchors_gated,
            lower_anchors_applied=lower_anchors_applied,
            lower_anchors_gated=lower_anchors_gated,
            split_applied=cut,
            split_form="lower_only",
            segment_edges=(
                float(wavenumbers[upper_edge]),
                float(wavenumbers[lower_edge]),
            ),
            seam_jump=float(spliced[upper_edge] - spliced[lower_edge]),
            seam_excess_jump=float(
                spliced[upper_edge] - spliced[lower_edge] - anchored_step
            ),
            degenerate_segments=segments,
            lower_continuation_lam_applied=self.lower_continuation_lam,
            lower_continuation_points=continuation_points,
            lower_method_applied=method_applied,
            lower_method_degeneracy_checked=degeneracy_checked,
            lower_floor_applied=floor,
            floor_edges=floor_edges,
            floor_seam_jump=floor_seam,
        )

    def _segment_continuation(
        self,
        wavenumbers: np.ndarray,
        intensity: np.ndarray,
        anchored: np.ndarray,
        upper: np.ndarray,
        lower: np.ndarray,
        settings: dict,
    ) -> tuple[np.ndarray, bool, int]:
        """Continue the anchored baseline below the cut (spec.md section 14.14).

        The third sibling of :meth:`_segment_baseline` and
        :meth:`_segment_pybaselines`, and the one that is **not** a second
        baseline. Those two compute an independent curve on the sub-array and
        hand it back to be spliced on; this one extends the curve that is
        already there.

        **The pin is two grid nodes, not a value and a derivative.** The node
        array is the two lowest-wavenumber samples *above* the cut followed by
        every sample below it -- one contiguous run of the original grid. The
        first two nodes are held at the anchored baseline's own values there.
        Holding two adjacent nodes fixes the curve's value and its slope at the
        join exactly, on the grid the seam is measured on, which is why nothing
        here has to reason about the sign of a derivative on a descending axis
        (spec.md section 0's first trap).

        **The fit.** With ``b`` the node values, ``m`` the samples
        ``std_distribution`` classified as background below the cut, and ``D2``
        the second-difference operator on the node grid::

            minimise  sum_m (b - y)^2  +  lam * ||D2 b||^2
            subject to  b[0] = anchored[0],  b[1] = anchored[1]

        solved as one small dense least-squares problem in the ``n - 2`` free
        nodes (``n`` is ~108, so there is nothing to gain from a banded solver).
        ``D2`` uses the exact non-uniform three-point second-derivative weights
        scaled by the mean spacing squared, so on a uniform grid it is exactly
        ``[1, -2, 1]`` and ``lam`` reads as it does in ``pybaselines``' Whittaker
        methods -- while staying correct if the grid is not quite uniform.

        **With no classified samples at all the system is still determined**, and
        determined as the straight line continuing the anchored slope: the
        constrained ``D2`` block alone is square and triangular. That is the
        honest degenerate case rather than a failure, and it is reported through
        the returned count rather than inferred -- a curve carried entirely by
        its penalty looks fitted and is not.

        Returns:
            ``(values below the cut, degenerate, number of fidelity points)``.
        """
        lam = float(self.lower_continuation_lam)

        upper_idx = np.flatnonzero(upper)
        lower_idx = np.flatnonzero(lower)
        if upper_idx.size < 2:
            raise ValueError(
                f"variant {self.label!r}: the continuation pins the two samples "
                f"above the cut at {float(self.lower_split_cm1):.0f} and only "
                f"{int(upper_idx.size)} is available; a single node fixes a value "
                "but not a slope, which is the whole construction"
            )
        # Wavenumbers descend, so `upper` is a prefix and its last two entries
        # are the ones nearest the cut -- the tail, never the head (spec.md 0).
        join_idx = upper_idx[-2:]
        node_idx = np.concatenate([join_idx, lower_idx])
        x = wavenumbers[node_idx]
        n = int(node_idx.size)

        # Which samples below the cut the classifier calls background. Read from
        # std_distribution directly because create_baseline discards the mask --
        # it returns (corrected, baseline), not (mask, baseline).
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _, params = std_distribution(
                intensity[lower],
                half_window=settings.get("half_window", 10),
                interp_half_window=settings.get("interp_half_window", 5),
                fill_half_window=settings.get("fill_half_window", 6),
                num_std=settings.get("num_std", 1.1),
                smooth_half_window=settings.get("smooth_half_window"),
                weights=settings.get("weights"),
            )
        classifier_degenerate = any(
            DEGENERATE_WARNING in str(item.message) for item in caught
        )
        mask = np.asarray(params["mask"], dtype=bool)
        # Node positions of the fidelity points: the lower samples start at 2.
        fit_nodes = 2 + np.flatnonzero(mask)
        n_fit = int(fit_nodes.size)

        # Second-difference rows, non-uniform and scaled to the uniform [1,-2,1].
        spacing = float(np.mean(np.abs(np.diff(x))))
        rows = np.zeros((n - 2, n), dtype=float)
        for i in range(1, n - 1):
            h_a = abs(x[i] - x[i - 1])
            h_b = abs(x[i + 1] - x[i])
            scale = spacing * spacing * 2.0 / (h_a + h_b)
            rows[i - 1, i - 1] = scale / h_a
            rows[i - 1, i] = -scale * (1.0 / h_a + 1.0 / h_b)
            rows[i - 1, i + 1] = scale / h_b

        design = np.zeros((n_fit + n - 2, n), dtype=float)
        target = np.zeros(n_fit + n - 2, dtype=float)
        if n_fit:
            design[np.arange(n_fit), fit_nodes] = 1.0
            target[:n_fit] = intensity[lower][mask]
        design[n_fit:] = np.sqrt(lam) * rows

        pinned = anchored[join_idx]
        free, _, rank, _ = np.linalg.lstsq(
            design[:, 2:], target - design[:, :2] @ pinned, rcond=None
        )
        values = np.concatenate([pinned, free])[2:]

        if n_fit == 0:
            LOGGER.warning(
                "variant %r: std_distribution classified no background samples "
                "below the cut, so the continuation is the straight "
                "extrapolation of the anchored slope and nothing more",
                self.label,
            )
        if rank < n - 2:
            LOGGER.warning(
                "variant %r: the continuation system is rank %d of %d; the "
                "curve is a least-norm solution, not a determined fit",
                self.label, int(rank), n - 2,
            )
        degenerate = bool(
            classifier_degenerate
            or not np.all(np.isfinite(values))
            or np.ptp(values) == 0.0
        )
        if degenerate:
            LOGGER.warning(
                "variant %r: the continuation below the cut is degenerate "
                "(classifier found no baseline points, or the curve is "
                "non-finite or flat); it is not meaningful",
                self.label,
            )
        return values, degenerate, n_fit

    def _segment_pybaselines(
        self,
        wavenumbers: np.ndarray,
        intensity: np.ndarray,
    ) -> tuple[np.ndarray, bool]:
        """Run :attr:`lower_method` on one segment (spec.md section 14.12).

        The sibling of :meth:`_segment_baseline` for a ``pybaselines`` method
        called directly rather than through ``create_baseline``. Two things
        differ and both are deliberate:

        **Ascending x.** Wavenumbers descend here, so the arrays are flipped
        before the call and the result flipped back. Methods that ignore ``x``
        are unaffected; the spline and polynomial ones are not, and would fit a
        reversed axis.

        **The degeneracy check is weaker.** There is no *"no baseline points
        found"* warning to catch -- that is ``std_distribution``'s own -- so
        this reports the structural failures any method can have: a non-finite
        value, or a baseline with no variation at all. It is not the same
        verdict, which is why :attr:`BaselineOutcome.lower_method_degeneracy_checked`
        comes back False and says so.
        """
        ascending = wavenumbers[::-1]
        fitter = Baseline(x_data=ascending, assume_sorted=True)
        result = getattr(fitter, self.lower_method)(
            intensity[::-1], **dict(self.lower_method_kwargs)
        )
        values = np.asarray(result[0], dtype=float)[::-1]
        if values.shape != intensity.shape:
            raise ValueError(
                f"variant {self.label!r}: lower_method {self.lower_method!r} "
                f"returned {values.shape} for a {intensity.shape} segment"
            )
        degenerate = bool(not np.all(np.isfinite(values)) or np.ptp(values) == 0.0)
        if degenerate:
            LOGGER.warning(
                "variant %r: lower_method %r returned a non-finite or constant "
                "baseline on its lower segment; the curve is not meaningful",
                self.label,
                self.lower_method,
            )
        return values, degenerate

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


def int_shared(
    wavenumbers: np.ndarray,
    raw: np.ndarray,
    baseline: np.ndarray,
    scale: float,
) -> float:
    """``mean(data - baseline)`` over :data:`INT_SHARED_WINDOW_CM1`, as % of ``scale``.

    The window-change-proof twin of ``lower_target_metrics``'s ``int``
    (spec.md 14.16). Target 0, like ``int``, and subject to the same warning:
    a signed mean alone ranks a strict lower envelope first (14.12 finding 33).

    ``scale`` is passed in rather than taken from ``raw`` deliberately. Callers
    hand it the **reference** variant's ``signal_range`` so that a truncated
    variant -- whose own range can differ where the dropped region held the
    extremum, as it does on ``...-022`` (14.16 finding 48) -- is not measured
    against a different denominator than the form it is being compared to.

    Returns ``nan`` when the variant does not cover the window at all.
    """
    mask = (wavenumbers <= INT_SHARED_WINDOW_CM1[0]) & (
        wavenumbers >= INT_SHARED_WINDOW_CM1[1]
    )
    if not mask.any():
        return float("nan")
    return 100 * float(np.mean(raw[mask] - baseline[mask])) / scale


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
