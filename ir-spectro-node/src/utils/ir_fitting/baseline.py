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

    @classmethod
    def coerce(cls, item: BaselineVariant | tuple) -> BaselineVariant:
        """Build a variant from itself or a ``(label, settings[, window])`` tuple.

        Tuples keep the calling code readable in a ``__main__`` block:

            [("current", {}), ("num_std 1.4", {"num_std": 1.4})]
        """
        if isinstance(item, cls):
            return item
        if not isinstance(item, (tuple, list)) or not 2 <= len(item) <= 11:
            raise TypeError(
                "each variant must be a BaselineVariant or a "
                "(label, settings[, window[, anchors[, split_cm1"
                "[, lower_split_cm1[, lower_anchors[, lower_settings"
                "[, lower_method[, lower_method_kwargs"
                "[, lower_floor_cm1]]]]]]]]]) "
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
        if self.lower_method is not None:
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
            degenerate_segments=segments,
            lower_method_applied=method_applied,
            lower_method_degeneracy_checked=degeneracy_checked,
            lower_floor_applied=floor,
            floor_edges=floor_edges,
            floor_seam_jump=floor_seam,
        )

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
