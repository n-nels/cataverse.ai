"""Baseline-departure nucleation detector (loop: docs/prompt_nuc-clf-refit.md).

Hypothesis (user): a single cluster peak -- Peak_1988 (13CO) -- sits on a
floating baseline and leaves it at about the time ``monomer_sum`` peaks.
"Off baseline" is judged against the noise measured while the peak is still
on its baseline, not against a fixed absolute delta.

``Cumulative_Peak_Area`` is a running sum within each ``Delta_Group``, so its
baseline behaves partly like a random walk (on the user-confirmed nulls,
var of lag-L differences grows ~linearly for L >= 4). A level test on the
cumulative value would false-alarm on long runs; this detector works on the
per-group increments instead and runs a one-sided CUSUM on them:

    z_i = (dv_i - mu) / sigma          mu, sigma: median / MAD-sd of the
                                        first ``n_base`` increments (causal)
    S_i = max(0, S_{i-1} + z_i - k)     fire while S_i > h

Increments from all Delta_Groups are pooled in time order. Every quantity at
row i uses rows 0..i only, so the detector is safe inside ``latch_sweep``.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

PEAK_NAME = "Peak_1988"
N_BASE = 12
DRIFT_K = 1.0
THRESHOLD_H = 10.0


def peak_trajectory(
    df: pd.DataFrame, peak_name: str = PEAK_NAME
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """``(Time (s), payload)`` of one peak, time-sorted, for ``latch_sweep``.

    ``payload`` is ``(n, 2)``: column 0 the cumulative area, column 1 an
    integer code for the row's ``Delta_Group``. ``latch_sweep`` only slices
    ``payload[:k]``, so the detector gets the group back without a new
    latch interface.
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


def increments(
    time_s: NDArray[np.float64], payload: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Per-group step increments, in the pooled time order of their end row.

    A group's first row has no predecessor and yields no increment.
    """
    values, codes = payload[:, 0], payload[:, 1]
    last: dict[float, float] = {}
    t_out: list[float] = []
    dv_out: list[float] = []
    for t, v, g in zip(time_s, values, codes):
        if g in last:
            t_out.append(t)
            dv_out.append(v - last[g])
        last[g] = v
    return np.asarray(t_out), np.asarray(dv_out)


def cusum_path(
    dv: NDArray[np.float64],
    *,
    n_base: int = N_BASE,
    drift_k: float = DRIFT_K,
) -> NDArray[np.float64]:
    """One-sided CUSUM of standardized increments after the baseline window.

    Entries ``< n_base`` are 0 (baseline still being measured).
    """
    path = np.zeros(dv.size)
    if dv.size <= n_base:
        return path
    base = dv[:n_base]
    mu = float(np.median(base))
    sigma = 1.4826 * float(np.median(np.abs(base - mu)))
    if not sigma > 0:
        return path
    s = 0.0
    for i in range(n_base, dv.size):
        s = max(0.0, s + (dv[i] - mu) / sigma - drift_k)
        path[i] = s
    return path


def classify_baseline_departure(
    time_s: NDArray[np.float64],
    payload: NDArray[np.float64],
    *,
    n_base: int = N_BASE,
    drift_k: float = DRIFT_K,
    threshold_h: float = THRESHOLD_H,
) -> dict[str, Any]:
    """``discontinuous`` while the CUSUM of the newest increment exceeds ``h``.

    ``growth_onset_s`` is the time the current excursion started (last time
    the CUSUM was 0), the usual CUSUM change-point estimate.
    """
    t_inc, dv = increments(time_s, payload)
    path = cusum_path(dv, n_base=n_base, drift_k=drift_k)
    if path.size == 0 or path[-1] <= threshold_h:
        return {"classification": "continuous"}
    zeros = np.flatnonzero(path[: path.size] == 0)
    onset = float(t_inc[zeros[-1]]) if zeros.size else float(t_inc[0])
    return {"classification": "discontinuous", "growth_onset_s": onset}


# Round 2: windowed rise above a zero-clamped floor.
# Per Delta_Group (so the ~group offsets cancel), smooth with a causal
# median of the last ``smooth_n`` points, then take the latest smoothed value
# minus max(0, min of the smoothed values in the last ``window_s``).
# Peak_1988 usually starts at or below 0, so recovery from a negative start
# does not count as a departure. The file-level rise is the median over
# groups that have a point inside the window.
WINDOW_S = 8 * 3600.0
SMOOTH_N = 3
RISE_THRESHOLD = 0.00275


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
        smoothed = np.array(
            [
                np.median(values[j - smooth_n + 1 : j + 1])
                for j in range(smooth_n - 1, values.size)
            ]
        )
        recent = times >= now - window_s
        if not recent.any():
            continue
        rises.append(smoothed[-1] - max(0.0, float(smoothed[recent].min())))
    return float(np.median(rises)) if rises else 0.0


def peak_monomer_trajectory(
    df: pd.DataFrame, peak_name: str = PEAK_NAME
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """``peak_trajectory`` plus a column 2: ``monomer_sum`` of the same
    ``(Time (s), Delta_Group)`` spectrum (NaN if that row is missing)."""
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


def classify_window_rise(
    time_s: NDArray[np.float64],
    payload: NDArray[np.float64],
    *,
    window_s: float = WINDOW_S,
    smooth_n: int = SMOOTH_N,
    rise_threshold: float = RISE_THRESHOLD,
) -> dict[str, Any]:
    """``discontinuous`` while the windowed rise exceeds ``rise_threshold``
    and, if the payload carries ``monomer_sum`` (column 2), monomer is present."""
    rise = window_rise(time_s, payload, window_s=window_s, smooth_n=smooth_n)
    gated = payload.shape[1] > 2 and not monomer_present(payload, smooth_n=smooth_n)
    if rise <= rise_threshold or gated:
        return {"classification": "continuous"}
    return {"classification": "discontinuous", "growth_onset_s": float(time_s[-1])}


# Round 3: absolute-amplitude gate (user, after round 2). A real departure
# also spans a minimum peak-to-trough in Peak_1988: per group, max - min of
# the smoothed values over the whole prefix so far, median over groups.
# It is non-decreasing in the prefix, so it can only delay a latch.
# The gate must hold on the same 3 prefixes the rise fires on, not just by
# the end of the run: the best such span is 0.0055 for nn1120-3_001-000
# (continuous) and 0.0069 for 003-091/098 (discontinuous), so 0.006. The
# user's ~0.01 would drop 003-091/098/004-016/3_001-034; 0.007 drops 091/098.
AMPLITUDE_MIN = 0.006


def prefix_amplitude(
    payload: NDArray[np.float64],
    *,
    smooth_n: int = SMOOTH_N,
    zero_floor: bool = False,
) -> float:
    """Median-over-groups peak-to-trough of the smoothed Peak_1988 prefix.

    ``zero_floor`` (round 4, user): trough is ``max(0, min)``, as in
    ``window_rise``, so recovery from a negative start does not count.
    """
    spans: list[float] = []
    for code in np.unique(payload[:, 1]):
        values = payload[payload[:, 1] == code, 0]
        if values.size < smooth_n:
            continue
        smoothed = np.array(
            [
                np.median(values[j - smooth_n + 1 : j + 1])
                for j in range(smooth_n - 1, values.size)
            ]
        )
        trough = float(smoothed.min())
        if zero_floor:
            trough = max(0.0, trough)
        spans.append(float(smoothed.max()) - trough)
    return float(np.median(spans)) if spans else 0.0


def classify_window_rise_gated(
    time_s: NDArray[np.float64],
    payload: NDArray[np.float64],
    *,
    amplitude_min: float = AMPLITUDE_MIN,
    zero_floor: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    """``classify_window_rise`` that also needs ``prefix_amplitude`` >= ``amplitude_min``."""
    result = classify_window_rise(time_s, payload, **kwargs)
    if result["classification"] == "discontinuous" and (
        prefix_amplitude(
            payload,
            smooth_n=kwargs.get("smooth_n", SMOOTH_N),
            zero_floor=zero_floor,
        )
        < amplitude_min
    ):
        return {"classification": "continuous"}
    return result
