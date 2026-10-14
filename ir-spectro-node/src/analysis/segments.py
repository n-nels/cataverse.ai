"""Segment-wise kinetics: one fit per (peak, segment) over the trajectory so far.

Port of ``src/utils/kinetics/segments.py`` (``SegmentWriter``), the offline
default (``run_kinetics_fit.py --mode segments``). Design and validation:
``src/utils/kinetics/spec.md`` section 8 and ``spec-working.md``. Parameters come
from yaml ``kinetics_segments`` (offline reads ``kinetics_reprocess_segments``).

Live runs it after every spectrum on the trajectory so far, with the causal
label so far in place of offline's final label, so every output is
provisional until the run ends (docs/spec-live-migration.md L4).

The measurement's label picks the regime. Segment boundaries come from the
pooled sum trajectories, smoothed by a centered running median of
``smooth_n`` points:

- monomer_sum + constituents. Continuous: ``adsorption`` (secondary_pfo).
  Discontinuous: ``supersaturation`` (secondary_pfo) up to the later of the
  monomer_sum max and the growth onset, then ``depletion`` (exp_decay).
- cluster_sum + constituents. Continuous: ``adsorption`` (pfo).
  Discontinuous without a spike: ``pre_nucleation`` (pfo) up to the growth
  onset, then ``ripening`` (pfo). With a spike: ``pre_nucleation`` (pfo) up
  to the spike base, ``burst_nucleation`` up to the cluster_sum max, and
  ``diffusion_growth`` after it. The last two have no model yet: their rows
  are written with NaN parameters.

A boundary row belongs to both adjacent segments. Each segment's model clock
starts at its first row (``t_ref_s``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from ..core import config
from .classification import classify_by_time, sorted_trajectory
from .kinetics_fitting import (
    _get_monomer_peak_names,
    _get_peak_names,
    _select_secondary_p0,
    fit_and_evaluate,
    fit_exp_decay_with_errors,
    fit_secondary_pfo_with_errors,
)

_SETTINGS = config.get_analysis_setting("kinetics_segments") or {}
SMOOTH_N = int(_SETTINGS["smooth_n"])
SPIKE_WINDOW_BEFORE_S = float(_SETTINGS["spike_window_before_s"])
SPIKE_WINDOW_AFTER_S = float(_SETTINGS["spike_window_after_s"])
SPIKE_PLATEAU_GAP_S = float(_SETTINGS["spike_plateau_gap_s"])
SPIKE_MIN_PLATEAU_POINTS = int(_SETTINGS["spike_min_plateau_points"])
SPIKE_MIN_PROMINENCE = float(_SETTINGS["spike_min_prominence"])
SPIKE_MIN_RISE = float(_SETTINGS["spike_min_rise"])

SUM_OF_GROUP = {"monomer": "monomer_sum", "cluster": "cluster_sum"}

MODEL_FITS: dict[
    str,
    Callable[
        [NDArray[np.float64], NDArray[np.float64], list[float] | None],
        tuple[NDArray[np.float64], NDArray[np.float64], float, float],
    ],
] = {
    "pfo": fit_and_evaluate,
    "secondary_pfo": fit_secondary_pfo_with_errors,
    "exp_decay": fit_exp_decay_with_errors,
}

PARAM_MAPS: dict[str, list[tuple[str, str | None]]] = {
    "pfo": [
        ("pfo_k_s-1", "pfo_k_stderr"),
        ("pfo_q_e_au", "pfo_q_e_stderr"),
        ("pfo_q0_au", None),
    ],
    "secondary_pfo": [
        ("pfo-sec_k_a_s-1", "pfo-sec_k_a_stderr"),
        ("pfo-sec_q_e_au", "pfo-sec_q_e_stderr"),
        ("pfo-sec_k_s_s-1", "pfo-sec_k_s_stderr"),
        ("pfo-sec_k_p_s-1", "pfo-sec_k_p_stderr"),
        ("pfo-sec_q_inf_au", "pfo-sec_q_inf_stderr"),
        ("pfo-sec_q0_au", None),
    ],
    "exp_decay": [
        ("exp_k_s-1", "exp_k_stderr"),
        ("exp_y_inf_au", "exp_y_inf_stderr"),
        ("exp_y_b_au", None),
    ],
}

ID_COLUMNS = [
    "Measurement",
    "Peak_Name",
    "group",
    "regime",
    "segment",
    "model",
    "t_start_s",
    "t_end_s",
    "t_ref_s",
    "n_points",
    "r^2",
    "rmse",
]
FEATURE_COLUMNS = [
    "Measurement",
    "n_points",
    "classification",
    "growth_onset_s",
    "latch_time_s",
    "monomer_max_s",
    "monomer_max_au",
    "depletion_start_s",
    "spike_detected",
    "spike_base_s",
    "cluster_max_s",
    "cluster_max_au",
    "cluster_plateau_au",
    "cluster_noise_au",
    "spike_prominence",
    "spike_rise",
    "spike_note",
]


def param_columns() -> list[str]:
    """Model parameter columns of the params file, pfo, secondary_pfo, exp_decay."""
    columns: list[str] = []
    for key in ("pfo", "secondary_pfo", "exp_decay"):
        for value_key, stderr_key in PARAM_MAPS[key]:
            columns.append(value_key)
            if stderr_key is not None:
                columns.append(stderr_key)
    return columns


PARAMS_COLUMNS = [*ID_COLUMNS, *param_columns()]


@dataclass
class Segment:
    """One time range of a trajectory. ``None`` ends are the trajectory's own."""

    name: str
    model: str | None
    t_start: float | None
    t_end: float | None


def smoothed(
    values: NDArray[np.float64], smooth_n: int = SMOOTH_N
) -> NDArray[np.float64]:
    """Centered running median of ``smooth_n`` points (shrinks at the ends)."""
    return (
        pd.Series(values)
        .rolling(smooth_n, center=True, min_periods=smooth_n // 2 + 1)
        .median()
        .to_numpy(dtype=float)
    )


def smoothed_max(
    time_s: NDArray[np.float64], values: NDArray[np.float64]
) -> tuple[float, float]:
    """``(time, value)`` of the smoothed trajectory's max; NaN if empty.

    Also NaN while the trajectory is shorter than the smoothing window needs
    (every smoothed value NaN), as at the start of a live run.
    """
    if values.size == 0:
        return np.nan, np.nan
    smooth = smoothed(values)
    if not np.isfinite(smooth).any():
        return np.nan, np.nan
    i = int(np.nanargmax(smooth))
    return float(time_s[i]), float(smooth[i])


def detect_spike(
    time_s: NDArray[np.float64],
    values: NDArray[np.float64],
    *,
    monomer_max_s: float,
    growth_onset_s: float,
) -> dict[str, Any]:
    """Spike features of the cluster_sum trajectory of a discontinuous measurement.

    The candidate max is the smoothed max within
    ``[monomer max - before, monomer max + after]``. Its prominence is its
    height above the plateau (median smoothed value from ``plateau_gap``
    after it), and its rise is its height above the smoothed value at the
    spike base (``growth_onset_s``), both divided by the noise
    (1.4826 * MAD of raw minus smoothed). Detected when both reach their
    minimum and the base precedes the max.
    """
    out: dict[str, Any] = {"spike_detected": False, "spike_base_s": growth_onset_s}
    if values.size == 0 or not np.isfinite(monomer_max_s):
        out["spike_note"] = "no monomer max"
        return out
    smooth = smoothed(values)
    noise = 1.4826 * float(np.nanmedian(np.abs(values - smooth)))
    noise = max(noise, np.finfo(float).tiny)
    out["cluster_noise_au"] = noise
    window = np.flatnonzero(
        (time_s >= monomer_max_s - SPIKE_WINDOW_BEFORE_S)
        & (time_s <= monomer_max_s + SPIKE_WINDOW_AFTER_S)
    )
    if window.size == 0:
        out["spike_note"] = "no points near monomer max"
        return out
    if not np.isfinite(smooth[window]).any():
        out["spike_note"] = "too few points near monomer max"
        return out
    i = int(window[np.nanargmax(smooth[window])])
    cluster_max_s, cluster_max_au = float(time_s[i]), float(smooth[i])
    out.update(cluster_max_s=cluster_max_s, cluster_max_au=cluster_max_au)

    plateau = smooth[time_s >= cluster_max_s + SPIKE_PLATEAU_GAP_S]
    if plateau.size < SPIKE_MIN_PLATEAU_POINTS:
        out["spike_note"] = "no plateau after max"
        return out
    plateau_au = float(np.nanmedian(plateau))
    out["cluster_plateau_au"] = plateau_au
    out["spike_prominence"] = (cluster_max_au - plateau_au) / noise

    if not np.isfinite(growth_onset_s):
        out["spike_note"] = "no growth onset"
        return out
    if growth_onset_s >= cluster_max_s:
        out["spike_note"] = "growth onset at or after cluster max"
        return out
    base = min(int(np.searchsorted(time_s, growth_onset_s)), time_s.size - 1)
    out["spike_rise"] = (cluster_max_au - float(smooth[base])) / noise
    out["spike_detected"] = bool(
        out["spike_prominence"] >= SPIKE_MIN_PROMINENCE
        and out["spike_rise"] >= SPIKE_MIN_RISE
    )
    return out


def _finite_or_none(value: Any) -> float | None:
    """``value`` as a float, or ``None`` if missing or NaN."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def depletion_start(features: dict[str, Any]) -> float:
    """Where ``depletion`` starts in a discontinuous file; NaN otherwise."""
    if features.get("classification") != "discontinuous":
        return np.nan
    t_start = next(
        s.t_start for s in plan_segments(features)["monomer"] if s.name == "depletion"
    )
    return t_start if t_start is not None else np.nan


def plan_segments(features: dict[str, Any]) -> dict[str, list[Segment]]:
    """Segments per peak group, from the measurement's features."""
    if features.get("classification") != "discontinuous":
        return {
            "monomer": [Segment("adsorption", "secondary_pfo", None, None)],
            "cluster": [Segment("adsorption", "pfo", None, None)],
        }
    monomer_max_s = _finite_or_none(features.get("monomer_max_s"))
    growth_onset_s = _finite_or_none(features.get("growth_onset_s"))
    # Depletion starts once the monomer has peaked and growth has begun.
    ends = [t for t in (monomer_max_s, growth_onset_s) if t is not None]
    depletion_start_s = max(ends) if ends else None
    monomer = [
        Segment("supersaturation", "secondary_pfo", None, depletion_start_s),
        Segment("depletion", "exp_decay", depletion_start_s, None),
    ]
    # `in`, not truthiness: a features row read back from CSV may hold NaN.
    if features.get("spike_detected") not in (True, 1):
        if growth_onset_s is None:
            cluster = [Segment("ripening", "pfo", None, None)]
        else:
            cluster = [
                Segment("pre_nucleation", "pfo", None, growth_onset_s),
                Segment("ripening", "pfo", growth_onset_s, None),
            ]
        return {"monomer": monomer, "cluster": cluster}
    base_s, max_s = features["spike_base_s"], features["cluster_max_s"]
    return {
        "monomer": monomer,
        "cluster": [
            Segment("pre_nucleation", "pfo", None, base_s),
            Segment("burst_nucleation", None, base_s, max_s),
            Segment("diffusion_growth", None, max_s, None),
        ],
    }


def kinetic_features(
    df: pd.DataFrame,
    measurement: str,
    *,
    min_points: int,
    by_time: dict[float, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Classification so far, boundary times and spike features.

    ``by_time`` is ``classify_by_time(df)``; pass it when already computed.
    """
    if by_time is None:
        by_time = classify_by_time(df, min_points=min_points)
    labels = [v.get("classification") for v in by_time.values()]
    features: dict[str, Any] = {"Measurement": measurement}
    if "discontinuous" in labels:
        latched = next(
            v for v in by_time.values() if v.get("classification") == "discontinuous"
        )
        features.update(
            classification="discontinuous",
            growth_onset_s=latched.get("growth_onset_s", np.nan),
            latch_time_s=latched.get("latch_time_s", np.nan),
        )
    elif "continuous" in labels:
        features["classification"] = "continuous"
    else:
        features["classification"] = np.nan

    time_m, monomer = sorted_trajectory(df, "monomer_sum")
    features["monomer_max_s"], features["monomer_max_au"] = smoothed_max(
        time_m, monomer
    )
    features["depletion_start_s"] = depletion_start(features)
    time_c, cluster = sorted_trajectory(df, "cluster_sum")
    features["n_points"] = int(time_c.size)
    if features["classification"] == "discontinuous":
        features.update(
            detect_spike(
                time_c,
                cluster,
                monomer_max_s=features["monomer_max_s"],
                growth_onset_s=features["growth_onset_s"],
            )
        )
    return features


def fit_segment(
    time_s: NDArray[np.float64],
    intensity: NDArray[np.float64],
    segment: Segment,
    *,
    min_points: int,
) -> dict[str, Any]:
    """Fit one segment (both ends inclusive); NaN parameters if unfitted.

    Every model's clock starts at the segment's first point, ``t_ref_s``,
    where ``q0`` (or exp_decay's ``y_b``) is set: time before the first row,
    including the ~420 s before a trajectory's first row, is ignored. Only the
    slow kinetics are modelled (``src/utils/kinetics/spec-working.md`` D24).
    """
    t_start = segment.t_start if segment.t_start is not None else float(time_s[0])
    t_end = segment.t_end if segment.t_end is not None else float(time_s[-1])
    mask = (time_s >= t_start) & (time_s <= t_end)
    record: dict[str, Any] = {
        "segment": segment.name,
        "model": segment.model or "none",
        "t_start_s": t_start,
        "t_end_s": t_end,
        "n_points": int(mask.sum()),
    }
    if segment.model is None or record["n_points"] < min_points:
        return record
    t_slice, y_slice = time_s[mask], intensity[mask]
    t_ref = float(t_slice[0])
    record["t_ref_s"] = t_ref
    p0 = None
    if segment.model == "secondary_pfo":
        p0 = _select_secondary_p0(
            t_slice, y_slice, threshold_r2=0.96, min_points=min_points
        )
    elif segment.model == "exp_decay":
        # y_b: the smoothed trajectory at the segment start, not one raw
        # point (at the monomer max a raw point is biased high).
        start = int(np.flatnonzero(mask)[0])
        p0 = [np.nan, np.nan, float(smoothed(intensity)[start])]
    # pfo is the one model on absolute time: shift it. exp_decay counts from
    # the first time itself, and secondary_pfo's ODE starts there.
    t_fit = t_slice - t_ref if segment.model == "pfo" else t_slice
    popt, std_errors, r_squared, rmse = MODEL_FITS[segment.model](t_fit, y_slice, p0)
    record["r^2"], record["rmse"] = r_squared, rmse
    for idx, (value_key, stderr_key) in enumerate(PARAM_MAPS[segment.model]):
        value = popt[idx] if idx < len(popt) else np.nan
        record[value_key] = float(value) if np.isfinite(value) else np.nan
        if stderr_key is not None:
            stderr = std_errors[idx] if idx < len(std_errors) else np.nan
            record[stderr_key] = float(stderr) if np.isfinite(stderr) else np.nan
    return record


def group_peak_names() -> dict[str, list[str]]:
    """Atomic ``Peak_Name`` values per group, from ``voigt_fit``."""
    return {
        "monomer": _get_monomer_peak_names(isotope=None),
        "cluster": _get_peak_names("cluster_peaks_base", isotope=None),
    }


def compute_segment_kinetics(
    df_area: pd.DataFrame,
    measurement: str,
    *,
    min_points: int = 4,
    by_time: dict[float, dict[str, Any]] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """``(params rows, features)`` for one measurement's area frame (no file I/O).

    ``df_area`` holds the atomic peaks plus ``monomer_sum`` / ``cluster_sum``
    rows. Fits every monomer and cluster peak and both sums, per segment.
    """
    df = df_area.copy()
    df["Time (s)"] = pd.to_numeric(df["Time (s)"], errors="coerce")
    df["Cumulative_Peak_Area"] = pd.to_numeric(
        df["Cumulative_Peak_Area"], errors="coerce"
    )
    features = kinetic_features(df, measurement, min_points=min_points, by_time=by_time)
    regime = features["classification"]
    regime = regime if isinstance(regime, str) else "unclassified"
    plan = plan_segments(features)
    records: list[dict[str, Any]] = []
    for group, atomic in group_peak_names().items():
        for peak_name in [*atomic, SUM_OF_GROUP[group]]:
            time_s, intensity = sorted_trajectory(df, peak_name)
            if time_s.size == 0:
                continue
            for segment in plan[group]:
                records.append(
                    {
                        "Measurement": measurement,
                        "Peak_Name": peak_name,
                        "group": group,
                        "regime": regime,
                        **fit_segment(time_s, intensity, segment, min_points=min_points),
                    }
                )
    return pd.DataFrame(records).reindex(columns=PARAMS_COLUMNS), features
