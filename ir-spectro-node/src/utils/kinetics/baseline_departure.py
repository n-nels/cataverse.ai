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
