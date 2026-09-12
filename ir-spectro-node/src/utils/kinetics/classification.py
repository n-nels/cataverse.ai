"""Trajectory classification: flat-then-rise, sustained-rise, and drawdown detectors.

Several detection variants live side by side here deliberately -- they are
active nucleation-classifier detection candidates being scored against
``ground_truth.json`` (see ``validation.py`` and ``docs/spec.md``), not dead
alternatives. ``classify_trajectory`` is the default/baseline detector;
``classify_trajectory_sustained_rise``, ``classify_trajectory_drawdown`` and
``classify_trajectory_combined`` are candidates under evaluation, selectable
via ``classify_cli.py``'s ``--classifier`` flag.
"""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np
from numpy.typing import NDArray

from .models import KineticModels
from .utils import _KineticUtilities

FLAT_WINDOW_S = 20000.0
MIN_FLAT_START_S = 10000.0
SMOOTHING_WINDOW = 4
EPS_FLAT_DEFAULT = 1e-6
RISE_DELTA_DEFAULT = 1.1e-1


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

    def detect_discontinuity_sustained_rise(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        eps_flat: float,
        rise_delta: float,
    ) -> tuple[bool, float | None]:
        """Like ``detect_discontinuity``, but doesn't require the trajectory
        to still be elevated at the very last ~5% of points.

        ``detect_discontinuity`` rejects any trajectory that has decayed back
        toward baseline by its final points, no matter how large the rise was
        in between (spec.md §5's diagnosed mechanism for why
        ``nn1120-4_pd_ceo2_000`` positives go undetected: they rise sharply
        mid-run and decay back down by the end). This variant instead checks
        whether a *sustained* (smoothed, not single-point) elevation above
        baseline ever occurred anywhere after the flat-window transition,
        tolerating a later decay.
        """
        flat_window, transition_end = self.find_flat_transition(
            time_s, intensity, eps_flat, MIN_FLAT_START_S, FLAT_WINDOW_S
        )
        if flat_window is None or transition_end is None:
            return False, None

        flat_start, flat_end, _ = flat_window
        start_idx = np.searchsorted(time_s, flat_start, side="left")
        end_idx = np.searchsorted(time_s, flat_end, side="right")
        baseline = float(np.mean(intensity[start_idx:end_idx]))

        post_idx = np.searchsorted(time_s, transition_end, side="right")
        post_time = time_s[post_idx:]
        post_intensity = intensity[post_idx:]
        if post_intensity.size == 0:
            return False, None

        smooth_result = self.running_mean(post_time, post_intensity, SMOOTHING_WINDOW)
        if smooth_result is not None:
            _, smooth_post = smooth_result
            max_post = float(np.max(smooth_post)) if smooth_post.size else -np.inf
        else:
            max_post = float(np.max(post_intensity))

        if max_post < baseline + rise_delta:
            return False, None

        return True, transition_end

    def classify_trajectory_sustained_rise(
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        eps_flat: float = EPS_FLAT_DEFAULT,
        rise_delta: float = RISE_DELTA_DEFAULT,
    ) -> dict[str, Any]:
        """``classify_trajectory`` using ``detect_discontinuity_sustained_rise``."""
        result: dict[str, Any] = {}
        if len(time_s) < 3:
            result["classification"] = "fit_failed"
            return result

        is_disc, breakpoint_s = self.detect_discontinuity_sustained_rise(
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
        monotonically for the rest of the run (see docs/JOURNAL.md round 3).
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
