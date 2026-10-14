"""Nucleation classification of a measurement, and the causal latch (live).

Port of ``src/utils/kinetics/classification.py`` (the offline detector, scored
287/289 against ``ground_truth.json``), plus ``classify_by_time`` from
``src/utils/kinetics/writer.py``. The functions are the offline ones verbatim;
only the yaml block differs: live reads ``kinetics_classification``. A change
to one side has to land in both (docs/spec-live-migration.md).

``classify_nucleation`` is the detector (docs/JOURNAL_nuc-clf-refit.md). It
watches one cluster peak, Peak_1988 (13CO), which sits on a floating baseline
and leaves it at about the time ``monomer_sum`` peaks. At each prefix it fires
``discontinuous`` when all three hold:

- **rise**: per ``Delta_Group`` (so the ~0.3 au group offsets cancel), the
  newest causally smoothed value minus ``max(0, min)`` of the smoothed values
  in the last ``window_s``, median over groups, exceeds ``rise_threshold``.
  Peak_1988 usually starts at or below 0, so recovery from a negative start
  is not a departure;
- **monomer present**: the median over groups of the newest smoothed
  ``monomer_sum`` is > 0;
- **amplitude**: the median-over-groups peak-to-trough of the smoothed
  Peak_1988 prefix is at least ``amplitude_min``.

Parameters come from the ``kinetics_classification`` block of
config/analysis.yaml. ``latch_sweep`` turns the detector into the causal,
monotonic-once-triggered label used both by the ground-truth harness and the
written column.

``growth_onset`` times the event once the latch has engaged. The latch's
own fires lag the visible departure (each group is sampled every ~1 h and
smoothed over 3 of its points), so the onset is the first row of the pooled,
unsmoothed Peak_1988 prefix -- all Delta_Groups as one series against time,
as plotted -- that passes the same three gates, with
``growth_onset_amplitude_min``. Its time is written as ``growth_onset_s``; the
latch's own time is ``latch_time_s``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from ..core import config

_SETTINGS = config.get_analysis_setting("kinetics_classification") or {}
PEAK_NAME = str(_SETTINGS["peak_name"])
WINDOW_S = float(_SETTINGS["window_s"])
SMOOTH_N = int(_SETTINGS["smooth_n"])
RISE_THRESHOLD = float(_SETTINGS["rise_threshold"])
AMPLITUDE_MIN = float(_SETTINGS["amplitude_min"])
ZERO_FLOOR = bool(_SETTINGS["zero_floor"])
REQUIRED_CONSECUTIVE_FIRES = int(_SETTINGS["required_consecutive"])
GROWTH_ONSET_AMPLITUDE_MIN = float(_SETTINGS["growth_onset_amplitude_min"])


@dataclass
class Latch:
    """Where a causal prefix sweep latched ``discontinuous``, if it did."""

    n_points: int | None
    """Prefix length at which the latch engaged. Row ``n_points - 1`` of the
    time-sorted trajectory is the first latched row. ``None``: never latched."""
    result: dict[str, Any]
    """The classifier's output at the first ``discontinuous`` fire of the
    sweep, even one in a streak that broke before latching. ``fire_time_s``
    is therefore the first fire's time, not the prefix where the latch
    engaged. Empty if the latch never engaged."""


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
    ``intensity`` may be any row-aligned array; only ``[:k]`` is sliced.
    """
    consecutive = 0
    first_fire: dict[str, Any] = {}
    for k in range(min_points, len(time_s) + 1):
        result = classify_fn(time_s[:k], intensity[:k])
        if result.get("classification") == "discontinuous":
            consecutive += 1
            if not first_fire:
                first_fire = result
            if consecutive >= required_consecutive:
                return Latch(n_points=k, result=first_fire)
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


def peak_trajectory(
    df: pd.DataFrame, peak_name: str = PEAK_NAME
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """``(Time (s), payload)`` of one peak, time-sorted, for ``latch_sweep``.

    ``payload`` is ``(n, 2)``: column 0 the cumulative area, column 1 an
    integer code for the row's ``Delta_Group``.
    """
    rows = df[df["Peak_Name"] == peak_name].dropna(
        subset=["Time (s)", "Cumulative_Peak_Area"]
    )
    rows = rows.sort_values("Time (s)", kind="stable")
    codes = pd.factorize(rows["Delta_Group"])[0].astype(float)
    payload = np.column_stack(
        [rows["Cumulative_Peak_Area"].to_numpy(dtype=float), codes]
    )
    return rows["Time (s)"].to_numpy(dtype=float), payload


def nucleation_trajectory(
    df: pd.DataFrame, peak_name: str = PEAK_NAME
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """``peak_trajectory`` plus a column 2: ``monomer_sum`` of the same
    ``(Time (s), Delta_Group)`` spectrum (NaN if that row is missing).

    The swept trajectory of ``classify_nucleation``.
    """
    time_s, payload = peak_trajectory(df, peak_name)
    rows = df[df["Peak_Name"] == peak_name].dropna(
        subset=["Time (s)", "Cumulative_Peak_Area"]
    )
    rows = rows.sort_values("Time (s)", kind="stable")
    monomer = df[df["Peak_Name"] == "monomer_sum"].drop_duplicates(
        ["Time (s)", "Delta_Group"]
    )
    merged = rows[["Time (s)", "Delta_Group"]].merge(
        monomer[["Time (s)", "Delta_Group", "Cumulative_Peak_Area"]],
        on=["Time (s)", "Delta_Group"],
        how="left",
    )
    return time_s, np.column_stack(
        [payload, merged["Cumulative_Peak_Area"].to_numpy(dtype=float)]
    )


def _smoothed(values: NDArray[np.float64], smooth_n: int) -> NDArray[np.float64]:
    """Causal running median of the last ``smooth_n`` points."""
    return np.array(
        [
            np.median(values[j - smooth_n + 1 : j + 1])
            for j in range(smooth_n - 1, values.size)
        ]
    )


def window_rise(
    time_s: NDArray[np.float64],
    payload: NDArray[np.float64],
    *,
    window_s: float = WINDOW_S,
    smooth_n: int = SMOOTH_N,
) -> float:
    """Median-over-groups rise of the newest smoothed point in ``window_s``."""
    now = float(time_s[-1])
    rises: list[float] = []
    for code in np.unique(payload[:, 1]):
        in_group = payload[:, 1] == code
        values = payload[in_group, 0]
        if values.size < smooth_n:
            continue
        times = time_s[in_group][smooth_n - 1 :]
        smoothed = _smoothed(values, smooth_n)
        recent = times >= now - window_s
        if not recent.any():
            continue
        rises.append(smoothed[-1] - max(0.0, float(smoothed[recent].min())))
    return float(np.median(rises)) if rises else 0.0


def monomer_present(payload: NDArray[np.float64], *, smooth_n: int = SMOOTH_N) -> bool:
    """Median over groups of the newest smoothed ``monomer_sum`` is > 0.

    Continuous runs with no monomer (``monomer_sum`` < 0 throughout, e.g.
    nn1120-4 013/016) still show Peak_1988 recovering upward from a
    negative start; that is not a departure.
    """
    latest: list[float] = []
    for code in np.unique(payload[:, 1]):
        values = payload[payload[:, 1] == code, 2]
        values = values[np.isfinite(values)]
        if values.size >= smooth_n:
            latest.append(float(np.median(values[-smooth_n:])))
    return bool(latest) and float(np.median(latest)) > 0.0


def prefix_amplitude(
    payload: NDArray[np.float64],
    *,
    smooth_n: int = SMOOTH_N,
    zero_floor: bool = ZERO_FLOOR,
) -> float:
    """Median-over-groups peak-to-trough of the smoothed Peak_1988 prefix.

    ``zero_floor``: the trough is ``max(0, min)``, as in ``window_rise``, so
    recovery from a negative start does not count.
    """
    spans: list[float] = []
    for code in np.unique(payload[:, 1]):
        values = payload[payload[:, 1] == code, 0]
        if values.size < smooth_n:
            continue
        smoothed = _smoothed(values, smooth_n)
        trough = float(smoothed.min())
        if zero_floor:
            trough = max(0.0, trough)
        spans.append(float(smoothed.max()) - trough)
    return float(np.median(spans)) if spans else 0.0


def classify_nucleation(
    time_s: NDArray[np.float64],
    payload: NDArray[np.float64],
    *,
    window_s: float = WINDOW_S,
    smooth_n: int = SMOOTH_N,
    rise_threshold: float = RISE_THRESHOLD,
    amplitude_min: float = AMPLITUDE_MIN,
    zero_floor: bool = ZERO_FLOOR,
) -> dict[str, Any]:
    """``discontinuous`` while rise, monomer and amplitude all hold (module doc).

    ``payload`` is ``nucleation_trajectory``'s. ``fire_time_s`` is the
    newest time of the prefix; ``latch_sweep`` reports the one from the
    sweep's first fire.
    """
    continuous = {"classification": "continuous"}
    if (
        window_rise(time_s, payload, window_s=window_s, smooth_n=smooth_n)
        <= rise_threshold
    ):
        return continuous
    if not monomer_present(payload, smooth_n=smooth_n):
        return continuous
    if (
        prefix_amplitude(payload, smooth_n=smooth_n, zero_floor=zero_floor)
        < amplitude_min
    ):
        return continuous
    return {"classification": "discontinuous", "fire_time_s": float(time_s[-1])}


def growth_onset(
    time_s: NDArray[np.float64],
    payload: NDArray[np.float64],
    *,
    window_s: float = WINDOW_S,
    rise_threshold: float = RISE_THRESHOLD,
    amplitude_min: float = GROWTH_ONSET_AMPLITUDE_MIN,
    zero_floor: bool = ZERO_FLOOR,
) -> float:
    """Time of the first row whose pooled, unsmoothed prefix passes the gates.

    ``payload`` is ``nucleation_trajectory``'s; the Delta_Group column is
    ignored, so every row is one point of a single Peak_1988 series. A row
    passes when the rise (its value minus ``max(0, min)`` over the last
    ``window_s``) exceeds ``rise_threshold``, the prefix peak-to-trough is at
    least ``amplitude_min``, and that row's ``monomer_sum`` is > 0. Pass the
    prefix up to the latch so the result stays causal. NaN if no row passes.
    """
    values = payload[:, 0]
    monomer = payload[:, 2]
    for k in range(1, values.size):
        prefix = values[: k + 1]
        recent = prefix[time_s[: k + 1] >= time_s[k] - window_s]
        rise = prefix[-1] - max(0.0, float(recent.min()))
        trough = float(prefix.min())
        if zero_floor:
            trough = max(0.0, trough)
        if (
            rise > rise_threshold
            and float(prefix.max()) - trough >= amplitude_min
            and monomer[k] > 0
        ):
            return float(time_s[k])
    return np.nan


def classify_by_time(
    df: pd.DataFrame,
    *,
    min_points: int = 4,
) -> dict[float, dict[str, Any]]:
    """Causal per-time nucleation classification (written on ``cluster_sum``).

    Copy of ``src/utils/kinetics/writer.py::KineticWriter.classify_by_time``.
    Runs ``latch_sweep`` of ``classify_nucleation`` once over the time-sorted
    ``nucleation_trajectory``. A time is ``discontinuous`` once the latch has
    engaged at or before its last row (rows sharing a time, one per
    Delta_Group, take the state after the last of them), ``continuous`` before
    that, and NaN while fewer than ``min_points`` points exist. Latched times
    also carry ``growth_onset_s`` (``growth_onset`` over the prefix up to the
    latch, or the sweep's first fire if no pooled row passes by then) and
    ``latch_time_s`` (the time of the first latched row).

    The sweep is causal, so recomputing it after each new spectrum leaves the
    labels of earlier times unchanged.
    """
    time_s, payload = nucleation_trajectory(df)
    if time_s.size == 0:
        return {}
    latch = latch_sweep(classify_nucleation, time_s, payload, min_points=min_points)
    latched_extra: dict[str, Any] = {}
    if latch.n_points is not None:
        onset = growth_onset(time_s[: latch.n_points], payload[: latch.n_points])
        if np.isnan(onset):
            onset = latch.result.get("fire_time_s")
        latched_extra["growth_onset_s"] = float(onset) if onset is not None else np.nan
        latched_extra["latch_time_s"] = float(time_s[latch.n_points - 1])

    by_time: dict[float, dict[str, Any]] = {}
    for unique_time in np.unique(time_s):
        n_points = int(np.searchsorted(time_s, unique_time, side="right"))
        if n_points < min_points:
            by_time[float(unique_time)] = {"classification": np.nan}
        elif latch.n_points is not None and n_points >= latch.n_points:
            by_time[float(unique_time)] = {
                "classification": "discontinuous",
                **latched_extra,
            }
        else:
            by_time[float(unique_time)] = {"classification": "continuous"}
    return by_time
