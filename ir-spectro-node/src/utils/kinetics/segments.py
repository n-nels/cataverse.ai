"""Segment-wise kinetics: one fit per (peak, segment) over the whole trajectory.

``fit_cli --mode segments``. Design: spec-working.md.

The measurement's final nucleation label (the latch ever engaged) picks the
regime. Segment boundaries come from the pooled sum trajectories, smoothed by
a centered running median of ``smooth_n`` points (hindsight, so centered):

- monomer_sum + constituents. Continuous: ``adsorption`` (secondary_pfo).
  Discontinuous: ``supersaturation`` (secondary_pfo) up to the later of the
  monomer_sum max and the growth onset, then ``depletion`` (exp_decay).
- cluster_sum + constituents. Continuous: ``adsorption`` (pfo).
  Discontinuous without a spike: ``pre_nucleation`` (pfo) up to the growth
  onset, then ``ripening`` (pfo). With a
  spike: ``pre_nucleation`` (pfo) up to the spike base, ``burst_nucleation`` up to
  the cluster_sum max, and ``diffusion_growth`` after it. The last two have
  no model yet: their rows are written with NaN parameters.

A boundary row belongs to both adjacent segments. Each segment's model
clock starts at its first row (``t_ref_s``). The spike base is
``growth_onset_s``. The spike is detected when the smoothed cluster_sum max
near the monomer_sum max stands out from the later plateau and from its
base, both in units of the trajectory's noise (yaml
``kinetics_reprocess_segments``).

Outputs per measurement: ``*_CarbonylKineticParams.csv`` (one row per
``(Peak_Name, segment)``) and ``*_CarbonylKineticFeatures.csv`` (one row).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from src.core import config

from .classification import sorted_trajectory
from .writer import (
    AREA_COLUMNS,
    AREA_SUFFIX,
    MODELS,
    SUM_OF_GROUP,
    WRITER,
    KineticWriter,
)

_SETTINGS = config.get_analysis_setting("kinetics_reprocess_segments") or {}
SMOOTH_N = int(_SETTINGS["smooth_n"])
SPIKE_WINDOW_BEFORE_S = float(_SETTINGS["spike_window_before_s"])
SPIKE_WINDOW_AFTER_S = float(_SETTINGS["spike_window_after_s"])
SPIKE_PLATEAU_GAP_S = float(_SETTINGS["spike_plateau_gap_s"])
SPIKE_MIN_PLATEAU_POINTS = int(_SETTINGS["spike_min_plateau_points"])
SPIKE_MIN_PROMINENCE = float(_SETTINGS["spike_min_prominence"])
SPIKE_MIN_RISE = float(_SETTINGS["spike_min_rise"])

PARAMS_SUFFIX = config.get_setting("filenames.carbonyl_fit.kinetic_params_suffix")
FEATURES_SUFFIX = config.get_setting("filenames.carbonyl_fit.kinetic_features_suffix")

EXP_PARAM_MAP: list[tuple[str, str | None]] = [
    ("exp_k_s-1", "exp_k_stderr"),
    ("exp_y_inf_au", "exp_y_inf_stderr"),
    ("exp_y_b_au", None),
]
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
    """``(time, value)`` of the smoothed trajectory's max; NaN if empty."""
    if values.size == 0:
        return np.nan, np.nan
    smooth = smoothed(values)
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


def segment_curve(
    record: dict[str, Any] | pd.Series, time_s: NDArray[np.float64]
) -> NDArray[np.float64]:
    """A params-file row's fitted model evaluated at ``time_s`` (for plotting).

    pfo and exp_decay run on ``t - t_ref_s`` (the segment's first time).
    secondary_pfo integrates from ``time_s[0]``, so pass a grid that starts at
    the segment's first time. Rows without ``t_ref_s`` (written before it
    existed) fall back to absolute pfo and ``t_start_s`` for exp_decay. NaN for
    a blank or failed segment.
    """
    time_s = np.asarray(time_s, dtype=float)
    nan = np.full(time_s.shape, np.nan)
    t_ref = record.get("t_ref_s", np.nan)
    if record["model"] == "pfo" and np.isfinite(record["pfo_k_s-1"]):
        return MODELS.pfo_model.pfo(
            time_s - (t_ref if np.isfinite(t_ref) else 0.0),
            record["pfo_k_s-1"],
            record["pfo_q_e_au"],
            record["pfo_q0_au"],
        )
    if record["model"] == "exp_decay" and np.isfinite(record["exp_k_s-1"]):
        return MODELS.exp_decay_model.exp_decay(
            time_s - (t_ref if np.isfinite(t_ref) else record["t_start_s"]),
            record["exp_k_s-1"],
            record["exp_y_inf_au"],
            record["exp_y_b_au"],
        )
    if record["model"] == "secondary_pfo" and np.isfinite(record["pfo-sec_k_a_s-1"]):
        states = MODELS.secondary_pfo_model.states(
            time_s,
            record["pfo-sec_k_a_s-1"],
            record["pfo-sec_q_e_au"],
            record["pfo-sec_k_s_s-1"],
            record["pfo-sec_k_p_s-1"],
            record["pfo-sec_q_inf_au"],
            record["pfo-sec_q0_au"],
        )
        return states[0] if states is not None else nan
    return nan


class SegmentWriter:
    """Features, segment plan and one-shot segment fits for one measurement."""

    def __init__(self, writer: KineticWriter) -> None:
        self.writer = writer
        self.param_maps: dict[str, list[tuple[str, str | None]]] = {
            key: spec.param_map for key, spec in writer.model_specs.items()
        }
        self.param_maps["exp_decay"] = EXP_PARAM_MAP

    def param_columns(self) -> list[str]:
        columns: list[str] = []
        for key in ("pfo", "secondary_pfo", "exp_decay"):
            for value_key, stderr_key in self.param_maps[key]:
                columns.append(value_key)
                if stderr_key is not None:
                    columns.append(stderr_key)
        return columns

    def features(
        self, df: pd.DataFrame, measurement: str, *, min_points: int
    ) -> dict[str, Any]:
        """Final classification, boundary times and spike features."""
        by_time = self.writer.classify_by_time(df, min_points=min_points)
        labels = [v.get("classification") for v in by_time.values()]
        features: dict[str, Any] = {"Measurement": measurement}
        if "discontinuous" in labels:
            latched = next(
                v
                for v in by_time.values()
                if v.get("classification") == "discontinuous"
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
        self,
        time_s: NDArray[np.float64],
        intensity: NDArray[np.float64],
        segment: Segment,
        *,
        min_points: int,
    ) -> dict[str, Any]:
        """Fit one segment (both ends inclusive); NaN parameters if unfitted.

        Every model's clock starts at the segment's first point, ``t_ref_s``,
        where ``q0`` (or exp_decay's ``y_b``) is set: time before the first
        row, including the ~420 s before a trajectory's first row, is ignored.
        Only the slow kinetics are modelled (spec-working.md D24).
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
            p0 = self.writer._select_secondary_p0(
                t_slice, y_slice, threshold_r2=0.96, min_points=min_points
            )
        elif segment.model == "exp_decay":
            # y_b: the smoothed trajectory at the segment start, not one raw
            # point (at the monomer max a raw point is biased high).
            start = int(np.flatnonzero(mask)[0])
            p0 = [np.nan, np.nan, float(smoothed(intensity)[start])]
        fit_fn = self.writer.models.registry[segment.model]
        # pfo is the one model on absolute time: shift it. exp_decay counts
        # from the first time itself, and secondary_pfo's ODE starts there.
        t_fit = t_slice - t_ref if segment.model == "pfo" else t_slice
        popt, std_errors, r_squared, rmse = fit_fn(t_fit, y_slice, p0)
        record["r^2"], record["rmse"] = r_squared, rmse
        for idx, (value_key, stderr_key) in enumerate(self.param_maps[segment.model]):
            value = popt[idx] if idx < len(popt) else np.nan
            record[value_key] = float(value) if np.isfinite(value) else np.nan
            if stderr_key is not None:
                stderr = std_errors[idx] if idx < len(std_errors) else np.nan
                record[stderr_key] = float(stderr) if np.isfinite(stderr) else np.nan
        return record

    def prepare(
        self,
        df_area: pd.DataFrame,
        measurement: str,
        *,
        fit: bool = True,
        min_points: int = 4,
        groups: dict[str, list[str]] | None = None,
        peak_names: list[str] | None = None,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        """``(params rows, features)`` for one measurement's area frame."""
        df = df_area.copy()
        df["Time (s)"] = pd.to_numeric(df["Time (s)"], errors="coerce")
        df["Cumulative_Peak_Area"] = pd.to_numeric(
            df["Cumulative_Peak_Area"], errors="coerce"
        )
        features = self.features(df, measurement, min_points=min_points)
        columns = [*ID_COLUMNS, *self.param_columns()]
        if not fit:
            return pd.DataFrame(columns=columns), features

        regime = features["classification"]
        regime = regime if isinstance(regime, str) else "unclassified"
        plan = plan_segments(features)
        groups = groups or {
            group: self.writer.utils.group_peak_names(group) for group in SUM_OF_GROUP
        }
        records: list[dict[str, Any]] = []
        for group, atomic in groups.items():
            for peak_name in [*atomic, SUM_OF_GROUP[group]]:
                if peak_names is not None and peak_name not in peak_names:
                    continue
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
                            **self.fit_segment(
                                time_s, intensity, segment, min_points=min_points
                            ),
                        }
                    )
        return pd.DataFrame(records).reindex(columns=columns), features

    def write_measurement(
        self,
        area_path: str | Path,
        *,
        output_folder_name: str = "_test",
        **kwargs: Any,
    ) -> tuple[Path | None, Path, pd.DataFrame]:
        """Write the params (unless ``fit=False``) and features CSVs.

        Returns ``(params path or None, features path, params rows)``. Both
        files are built fresh.
        """
        area_path = Path(area_path)
        measurement = area_path.name.removesuffix(str(AREA_SUFFIX))
        df_area = pd.read_csv(area_path)
        df_area = df_area.drop(
            columns=[c for c in df_area.columns if c not in AREA_COLUMNS]
        )
        rows, features = self.prepare(df_area, measurement, **kwargs)
        output_dir = self.writer.utils.resolve_output_dir(
            area_path.parent, output_folder_name
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        features_path = output_dir / f"{measurement}{FEATURES_SUFFIX}"
        pd.DataFrame([features]).reindex(columns=FEATURE_COLUMNS).to_csv(
            features_path, index=False
        )
        params_path = None
        if kwargs.get("fit", True):
            params_path = output_dir / f"{measurement}{PARAMS_SUFFIX}"
            rows.to_csv(params_path, index=False)
        return params_path, features_path, rows


SEGMENT_WRITER = SegmentWriter(WRITER)
