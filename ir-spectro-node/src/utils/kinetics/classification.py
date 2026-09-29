"""Trajectory classification: flat-then-rise and drawdown detectors, and the causal latch.

``classify_trajectory_combined`` (flat-then-rise OR drawdown) is the detector
in use; ``classify_trajectory`` (flat-then-rise) and
``classify_trajectory_drawdown`` are its two parts, kept selectable via
``--classifier`` for scoring against ``ground_truth.json`` (docs/spec_nuc-clf.md).
The sustained-rise variant was removed: it scored net worse (spec_nuc-clf §6.2).

``latch_sweep`` turns any detector into the causal, monotonic-once-triggered
label used both by the ground-truth harness and the written column.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from src.core import config

from .models import KineticModels
from .utils import _KineticUtilities

# Thresholds from the kinetics_classification block of config/analysis.yaml,
# the same block live src/analysis/kinetics_fitting.py reads.
_SETTINGS = config.get_analysis_setting("kinetics_classification") or {}
FLAT_WINDOW_S = float(_SETTINGS["flat_window_s"])
MIN_FLAT_START_S = float(_SETTINGS["min_flat_start_s"])
SMOOTHING_WINDOW = int(_SETTINGS["smoothing_window"])
EPS_FLAT_DEFAULT = float(_SETTINGS["eps_flat"])
RISE_DELTA_DEFAULT = float(_SETTINGS["rise_delta"])

# The two known transient false positives in nn1120-3_pd_ceo2_003 fire for at
# most 2 consecutive prefixes before reverting (...-097: runs of 1 and 2;
# ...-115: runs of 1 and 1). Requiring 3 consecutive "discontinuous" prefixes
# before latching sits just above that measured noise ceiling
# (docs/spec_nuc-clf.md §4).
REQUIRED_CONSECUTIVE_FIRES = 3


@dataclass
class Latch:
    """Where a causal prefix sweep latched ``discontinuous``, if it did."""

    n_points: int | None
    """Prefix length at which the latch engaged. Row ``n_points - 1`` of the
    time-sorted trajectory is the first latched row. ``None``: never latched."""
    result: dict[str, Any]
    """The classifier's output at that prefix (``growth_onset_s``, ``pre_*``/``post_*``)."""


def latch_sweep(
    classify_fn: Callable[..., dict[str, Any]],
    time_s: NDArray[np.float64],
    intensity: NDArray[np.float64],
    *,
    min_points: int,
    required_consecutive: int = REQUIRED_CONSECUTIVE_FIRES,
) -> Latch:
    """Sweep growing prefixes; latch once ``discontinuous`` fires on
    ``required_consecutive`` consecutive prefixes, and never revert.

    This is the monotonic-once-triggered aggregation of docs/spec_nuc-clf.md
    §4: what a real-time pipeline sees, one incoming point at a time. It is the
    single definition shared by the ground-truth harness (``validation.ever_fires``)
    and the written per-row ``classification`` column, so the two cannot drift.
    """
    consecutive = 0
    for k in range(min_points, len(time_s) + 1):
        result = classify_fn(time_s[:k], intensity[:k])
        if result.get("classification") == "discontinuous":
            consecutive += 1
            if consecutive >= required_consecutive:
                return Latch(n_points=k, result=result)
        else:
            consecutive = 0
    return Latch(n_points=None, result={})


def sorted_trajectory(
    df: pd.DataFrame, peak_name: str
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """``(Time (s), Cumulative_Peak_Area)`` of one ``Peak_Name``, time-sorted.

    Sorted exactly as live ``kinetics_fitting`` sorts (pandas' default sort):
    rows sharing a time (one per Delta_Group) then reach the optimizer in the
    same order, so floating-point sums -- and ill-conditioned fits -- match
    live bit for bit. NaN areas (spectra with no fit) are dropped.
    """
    rows = df[df["Peak_Name"] == peak_name].dropna(
        subset=["Time (s)", "Cumulative_Peak_Area"]
    )
    rows = rows.sort_values("Time (s)")
    return (
        rows["Time (s)"].to_numpy(dtype=float),
        rows["Cumulative_Peak_Area"].to_numpy(dtype=float),
    )


class KineticClassification:
    """Trajectory classification helpers."""

    def __init__(self, models: KineticModels, utils: _KineticUtilities) -> None:
        self.models = models
        self.utils = utils

    @staticmethod
    def window_slope(
        time_s: NDArray[np.float64], intensity: NDArray[np.float64]
    ) -> float:
        if len(time_s) < 2:
            return np.nan
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", message="Polyfit may be poorly conditioned"
            )
            slope, _ = np.polyfit(time_s, intensity, 1)
        return float(slope)

    def find_flat_transition(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        eps_flat: float,
        min_start_s: float,
        window_s: float,
    ) -> tuple[tuple[float, float, float] | None, float | None]:
        flat_window: tuple[float, float, float] | None = None
        transition_end: float | None = None
        for start_idx, start_time in enumerate(time_s):
            if start_time < min_start_s:
                continue
            end_time = start_time + window_s
            end_idx = np.searchsorted(time_s, end_time, side="right") - 1
            if end_idx <= start_idx + 1:
                continue
            window_time = time_s[start_idx : end_idx + 1]
            window_intensity = intensity[start_idx : end_idx + 1]
            slope = self.window_slope(window_time, window_intensity)
            if not np.isfinite(slope):
                continue
            is_flat = abs(slope) <= eps_flat
            if flat_window is not None and not is_flat:
                transition_end = float(time_s[end_idx])
                break
            if is_flat:
                flat_window = (float(start_time), float(time_s[end_idx]), float(slope))
        return flat_window, transition_end

    @staticmethod
    def running_mean(
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        window: int,
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]] | None:
        if len(time_s) < window:
            return None
        kernel = np.ones(window) / float(window)
        smoothed = np.convolve(intensity, kernel, mode="valid")
        smoothed_time = time_s[window - 1 :]
        return smoothed_time, smoothed

    def detect_discontinuity(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        eps_flat: float,
        rise_delta: float,
    ) -> tuple[bool, float | None]:
        flat_window, transition_end = self.find_flat_transition(
            time_s, intensity, eps_flat, MIN_FLAT_START_S, FLAT_WINDOW_S
        )
        if flat_window is None or transition_end is None:
            return False, None

        flat_start, flat_end, _ = flat_window
        start_idx = np.searchsorted(time_s, flat_start, side="left")
        end_idx = np.searchsorted(time_s, flat_end, side="right")
        baseline = float(np.mean(intensity[start_idx:end_idx]))
        last_count = max(int(round(len(time_s) * 0.05)), 1)
        tail_mean = float(np.mean(intensity[-last_count:]))
        if tail_mean < baseline + rise_delta:
            return False, None

        smooth_result = self.running_mean(time_s, intensity, SMOOTHING_WINDOW)
        smooth_transition: float | None = None
        if smooth_result is not None:
            smooth_time, smooth_intensity = smooth_result
            _, smooth_transition = self.find_flat_transition(
                smooth_time,
                smooth_intensity,
                eps_flat,
                MIN_FLAT_START_S,
                FLAT_WINDOW_S,
            )

        breakpoint_used = (
            smooth_transition if smooth_transition is not None else transition_end
        )
        return True, breakpoint_used

    def _pre_post_pfo_summary(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        breakpoint_s: float,
    ) -> dict[str, Any]:
        """Fit PFO separately before/after a breakpoint and prefix the results.

        Shared by every ``classify_trajectory*`` variant that reports a
        discontinuity with pre_/post_ PFO summaries.
        """
        pre_mask = time_s <= breakpoint_s
        post_mask = time_s > breakpoint_s
        pre_fit = self.models.summarize_pfo_fit(time_s[pre_mask], intensity[pre_mask])
        post_fit = self.models.summarize_pfo_fit(
            time_s[post_mask], intensity[post_mask]
        )
        result: dict[str, Any] = {}
        result.update(self.utils.prefix_fit_results(pre_fit, "pre_"))
        result.update(self.utils.prefix_fit_results(post_fit, "post_"))
        return result

    def classify_trajectory(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        eps_flat: float = EPS_FLAT_DEFAULT,
        rise_delta: float = RISE_DELTA_DEFAULT,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if len(time_s) < 3:
            result["classification"] = "fit_failed"
            return result

        is_disc, breakpoint_s = self.detect_discontinuity(
            time_s, intensity, eps_flat, rise_delta
        )
        if not is_disc or breakpoint_s is None:
            result["classification"] = "continuous"
            return result

        result["classification"] = "discontinuous"
        result["growth_onset_s"] = breakpoint_s
        result.update(self._pre_post_pfo_summary(time_s, intensity, breakpoint_s))
        return result

    def detect_discontinuity_drawdown(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        rise_delta: float,
        drawdown_delta: float,
    ) -> tuple[bool, float | None]:
        """Detect a rise-then-decay "hump", instead of a flat-then-rise.

        Different mathematical approach from ``find_flat_transition`` /
        ``detect_discontinuity``: no forward search for a flat window at all.
        Inspecting the ``nn1120-4_pd_ceo2_000`` trajectories this was built
        for showed they have *no* flat lead-in anywhere -- they rise sharply
        from the very first recorded point, peak, then decay almost
        monotonically for the rest of the run (see docs/JOURNAL_nuc-clf.md round 3).
        That shape is a peak-then-reversal, not a level shift, so this checks
        two purely causal, running quantities computed from the (smoothed)
        trajectory-so-far:

        - ``rise_magnitude``: the running max so far, minus the minimum value
          at or before that running max was reached -- did it really rise
          before peaking?
        - ``drawdown``: the running max so far, minus the current (last)
          value -- has it fallen back substantially from its own peak?

        Both causal: computed only from ``time_s[:k]``/``intensity[:k]`` for
        whatever prefix length ``k`` is passed in, so this is safe to run
        inside a growing-prefix sweep exactly like ``detect_discontinuity``.
        Smoothing (existing ``SMOOTHING_WINDOW`` running mean) is applied
        first so single-point noise doesn't set a spurious running max.
        """
        smooth_result = self.running_mean(time_s, intensity, SMOOTHING_WINDOW)
        if smooth_result is None:
            return False, None
        smooth_time, smooth_intensity = smooth_result
        if smooth_intensity.size < 2:
            return False, None

        peak_idx = int(np.argmax(smooth_intensity))
        running_max = float(smooth_intensity[peak_idx])
        pre_peak_min = float(np.min(smooth_intensity[: peak_idx + 1]))
        rise_magnitude = running_max - pre_peak_min

        current = float(smooth_intensity[-1])
        drawdown = running_max - current

        if rise_magnitude < rise_delta or drawdown < drawdown_delta:
            return False, None

        return True, float(smooth_time[peak_idx])

    def classify_trajectory_drawdown(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        eps_flat: float = EPS_FLAT_DEFAULT,
        rise_delta: float = RISE_DELTA_DEFAULT,
        drawdown_delta: float | None = None,
    ) -> dict[str, Any]:
        """``classify_trajectory`` using ``detect_discontinuity_drawdown`` only
        (no flat-window branch) -- for isolating this rule's own behavior."""
        result: dict[str, Any] = {}
        if len(time_s) < 3:
            result["classification"] = "fit_failed"
            return result

        drawdown_threshold = (
            drawdown_delta if drawdown_delta is not None else rise_delta
        )
        is_disc, breakpoint_s = self.detect_discontinuity_drawdown(
            time_s, intensity, rise_delta, drawdown_threshold
        )
        if not is_disc or breakpoint_s is None:
            result["classification"] = "continuous"
            return result

        result["classification"] = "discontinuous"
        result["growth_onset_s"] = breakpoint_s
        return result

    def classify_trajectory_combined(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        eps_flat: float = EPS_FLAT_DEFAULT,
        rise_delta: float = RISE_DELTA_DEFAULT,
        drawdown_delta: float | None = None,
    ) -> dict[str, Any]:
        """Multi-rule detector (spec.md §4: if/then branches are acceptable
        provided they're computed from the trajectory itself): flags
        discontinuous if EITHER the original flat-then-rise rule
        (``detect_discontinuity``, handles the ``nn1120-3_pd_ceo2_003/004``
        reference set) OR the new rise-then-decay rule
        (``detect_discontinuity_drawdown``, targets ``nn1120-4_pd_ceo2_000``)
        fires. Branch choice depends only on the trajectory's own shape, never
        on which file/sample it came from.
        """
        result: dict[str, Any] = {}
        if len(time_s) < 3:
            result["classification"] = "fit_failed"
            return result

        is_disc, breakpoint_s = self.detect_discontinuity(
            time_s, intensity, eps_flat, rise_delta
        )
        if not is_disc or breakpoint_s is None:
            drawdown_threshold = (
                drawdown_delta if drawdown_delta is not None else rise_delta
            )
            is_disc, breakpoint_s = self.detect_discontinuity_drawdown(
                time_s, intensity, rise_delta, drawdown_threshold
            )

        if not is_disc or breakpoint_s is None:
            result["classification"] = "continuous"
            return result

        result["classification"] = "discontinuous"
        result["growth_onset_s"] = breakpoint_s
        result.update(self._pre_post_pfo_summary(time_s, intensity, breakpoint_s))
        return result
