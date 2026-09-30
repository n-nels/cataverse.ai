"""Relate the monomer/secondary-process kinetic model to the LaMer picture.

Loop instance: docs/prompt_monomer-kinetics.md / docs/JOURNAL_monomer-kinetics.md.
Standalone module, no CLI -- plain functions plus an editable-constants
``__main__`` block (see prompt_monomer-kinetics.md for why). Scope: monomer_sum
in the 34 files under C:\\Data\\peakFit\\nn1120-4_pd_ceo2_000\\ only. Does not
touch cluster_sum's own detector code, and does not use the classifier's
growth_onset_s as a reference (flagged errant in round 3); no metrics beyond
monomer_sum/cluster_sum/pfo-sec.

Round 6: the derivative-based cluster inflection of round 5 is **removed**
(argmax of a smoothed d/dt bounded at the cluster max -- smoothing-window and
bound were free parameters). Replaced by four threshold-free landmark
coordinates: each species' maximum, and the vertical cast of that maximum's
time onto the other species' curve. The two landmark times slice the run into
the three LaMer stages -- I prenucleation (t0 -> monomer max), II nucleation
burst + growth (monomer max -> cluster max), III growth/ripening (cluster max
-> end). Delta_Group stays collapsed to its mean at equal Time (s).

No normalised curve-crossing landmark is computed on purpose: the two species
sit on a twin y-axis at different scales, so a literal crossing is an artifact
of the axis choice. The vertical cast is the scale-free reading.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

path = Path(__file__).resolve().parents[3]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.utils.kinetics.writer import SEARCH_ROOT, UTILS

PFO_SEC_COLUMNS = [
    "pfo-sec_k_a_s-1",
    "pfo-sec_q_e_au",
    "pfo-sec_k_s_s-1",
    "pfo-sec_k_p_s-1",
    "pfo-sec_q_inf_au",
    "pfo-sec_q0_au",
]

# A maximum at the very first or very last sample is an endpoint, not a peak
# (round 4's boundary gate). Both landmarks must clear it before the three
# LaMer regions are meaningful.
INTERIOR_FRAC = (0.05, 0.95)


def collapse_delta_groups(df: pd.DataFrame, peak_name: str) -> pd.DataFrame:
    """One curve per species: Delta_Group collapsed to its mean at equal Time (s).

    Round 4 established the Delta_Group levels are systematically offset
    (within-group scatter ~0.03 au vs ~0.30 au between group means), which is
    why the pooled time-sorted series looked like a sawtooth. Collapsing by the
    mean is the requested treatment; ``group_std_au``/``n_groups`` are kept per
    time point so the scatter behind each mean stays visible in the catalog.
    """
    columns = ["Time (s)", "Cumulative_Peak_Area"]
    if peak_name == "monomer_sum":
        columns += PFO_SEC_COLUMNS
    rows = df.loc[df["Peak_Name"] == peak_name, columns].copy()
    for column in rows.columns:
        rows[column] = pd.to_numeric(rows[column], errors="coerce")
    rows = rows.dropna(subset=["Time (s)", "Cumulative_Peak_Area"])
    if rows.empty:
        return rows

    collapsed = rows.groupby("Time (s)", as_index=False).mean(numeric_only=True)
    scatter = (
        rows.groupby("Time (s)")["Cumulative_Peak_Area"]
        .agg(group_std_au="std", n_groups="count")
        .reset_index()
    )
    collapsed = collapsed.merge(scatter, on="Time (s)", how="left")
    return collapsed.sort_values("Time (s)").reset_index(drop=True)


def _peak(curve: pd.DataFrame, prefix: str) -> dict[str, float]:
    """Time/amplitude/position of a collapsed curve's maximum.

    The 3-point centered mean only chooses *which* point is the peak (so a
    single-sample spike cannot win); the reported amplitude is the raw
    collapsed value there. ``index_frac`` supports the boundary check.
    """
    keys = [f"{prefix}_time_s", f"{prefix}_amplitude_au", f"{prefix}_index_frac"]
    if curve.empty:
        return dict.fromkeys(keys, np.nan)
    smoothed = (
        curve["Cumulative_Peak_Area"].rolling(3, center=True, min_periods=1).mean()
    )
    idx = int(smoothed.idxmax())
    return {
        f"{prefix}_time_s": float(curve.loc[idx, "Time (s)"]),
        f"{prefix}_amplitude_au": float(curve.loc[idx, "Cumulative_Peak_Area"]),
        f"{prefix}_index_frac": float(idx) / max(len(curve) - 1, 1),
    }


def _cast(curve: pd.DataFrame, time_s: float) -> tuple[float, bool]:
    """Value of ``curve`` at ``time_s``, plus whether that time was in range.

    ``np.interp`` clamps silently outside the grid, which would return a
    plausible-looking endpoint value for a landmark the other species never
    observed. The flag is carried into the catalog rather than the clamp being
    hidden -- the two collapsed grids are not guaranteed identical (hence
    ``n_monomer_points``/``n_cluster_points``).
    """
    if curve.empty or np.isnan(time_s):
        return np.nan, False
    grid = curve["Time (s)"].to_numpy(dtype=float)
    in_range = bool(grid[0] <= time_s <= grid[-1])
    value = float(
        np.interp(time_s, grid, curve["Cumulative_Peak_Area"].to_numpy(dtype=float))
    )
    return value, in_range


def landmark_coordinates(
    monomer: pd.DataFrame, cluster: pd.DataFrame
) -> dict[str, Any]:
    """The four coordinates that slice the run, and nothing else.

    Each species' maximum is one coordinate; casting that maximum's *time*
    vertically onto the other species' curve gives the second. No threshold,
    no derivative, no smoothing window beyond the 3-point tie-break already
    used to choose which sample is the maximum.
    """
    row: dict[str, Any] = {
        **_peak(monomer, "monomer_max"),
        **_peak(cluster, "cluster_max"),
    }

    t_m = row["monomer_max_time_s"]
    t_c = row["cluster_max_time_s"]

    value, in_range = _cast(cluster, t_m)
    row["cluster_at_monomer_max_au"] = value
    row["cluster_at_monomer_max_in_range"] = in_range

    value, in_range = _cast(monomer, t_c)
    row["monomer_at_cluster_max_au"] = value
    row["monomer_at_cluster_max_in_range"] = in_range
    return row


def lamer_regions(
    monomer: pd.DataFrame, cluster: pd.DataFrame, row: dict[str, Any]
) -> dict[str, Any]:
    """Slice the run at the two landmark times into LaMer I / II / III.

    I   t0 -> monomer max      prenucleation accumulation
    II  monomer max -> cluster max   nucleation burst and growth
    III cluster max -> end     growth / ripening after the cluster maximum

    Only defined when both maxima are interior and ordered (monomer max before
    cluster max); otherwise ``region_order_ok`` is False and the durations are
    NaN, so a net-declining cluster curve cannot report a negative region II.
    """
    t_m = row["monomer_max_time_s"]
    t_c = row["cluster_max_time_s"]

    interior = all(
        not np.isnan(row[key]) and INTERIOR_FRAC[0] <= row[key] <= INTERIOR_FRAC[1]
        for key in ("monomer_max_index_frac", "cluster_max_index_frac")
    )
    ordered = not np.isnan(t_m) and not np.isnan(t_c) and t_m < t_c
    ok = bool(interior and ordered)

    times = np.concatenate(
        [
            monomer["Time (s)"].to_numpy(dtype=float),
            cluster["Time (s)"].to_numpy(dtype=float),
        ]
    )
    t_start = float(times.min()) if times.size else np.nan
    t_end = float(times.max()) if times.size else np.nan

    return {
        "run_start_s": t_start,
        "run_end_s": t_end,
        "landmarks_interior": interior,
        "region_order_ok": ok,
        "region_I_duration_s": t_m - t_start if ok else np.nan,
        "region_II_duration_s": t_c - t_m if ok else np.nan,
        "region_III_duration_s": t_end - t_c if ok else np.nan,
    }


def _slope(curve: pd.DataFrame, t_lo: float, t_hi: float) -> tuple[float, int]:
    """Least-squares slope (au/s) of a curve over a half-open time slice.

    A slope, not an endpoint difference, so a single noisy sample at a region
    boundary cannot set the sign the LaMer test is about to read.
    """
    if curve.empty or np.isnan(t_lo) or np.isnan(t_hi):
        return np.nan, 0
    time_s = curve["Time (s)"].to_numpy(dtype=float)
    mask = (time_s >= t_lo) & (time_s <= t_hi)
    n = int(mask.sum())
    if n < 3:
        return np.nan, n
    values = curve["Cumulative_Peak_Area"].to_numpy(dtype=float)[mask]
    return float(np.polyfit(time_s[mask], values, 1)[0]), n


def lamer_sign_test(
    monomer: pd.DataFrame, cluster: pd.DataFrame, row: dict[str, Any]
) -> dict[str, Any]:
    """Per-region slopes plus the three sign expectations LaMer implies.

    I is accumulation (monomer rising), II is the burst consuming monomer into
    clusters (monomer falling, cluster accumulating faster than it did in I).
    All three are sign comparisons, so nothing here introduces a threshold.
    Only evaluated where ``region_order_ok``; otherwise the regions themselves
    are not defined.
    """
    keys = [
        "monomer_slope_I_au_s",
        "monomer_slope_II_au_s",
        "cluster_slope_I_au_s",
        "cluster_slope_II_au_s",
        "n_points_region_I",
        "n_points_region_II",
        "lamer_monomer_rises_in_I",
        "lamer_monomer_falls_in_II",
        "lamer_cluster_faster_in_II",
        "lamer_all_three_ok",
    ]
    if not row["region_order_ok"]:
        return dict.fromkeys(keys, np.nan)

    t0 = row["run_start_s"]
    t_m = row["monomer_max_time_s"]
    t_c = row["cluster_max_time_s"]

    m_i, n_i = _slope(monomer, t0, t_m)
    m_ii, n_ii = _slope(monomer, t_m, t_c)
    c_i, _ = _slope(cluster, t0, t_m)
    c_ii, _ = _slope(cluster, t_m, t_c)

    rises = m_i > 0 if not np.isnan(m_i) else np.nan
    falls = m_ii < 0 if not np.isnan(m_ii) else np.nan
    faster = c_ii > c_i if not (np.isnan(c_i) or np.isnan(c_ii)) else np.nan
    return {
        "monomer_slope_I_au_s": m_i,
        "monomer_slope_II_au_s": m_ii,
        "cluster_slope_I_au_s": c_i,
        "cluster_slope_II_au_s": c_ii,
        "n_points_region_I": n_i,
        "n_points_region_II": n_ii,
        "lamer_monomer_rises_in_I": rises,
        "lamer_monomer_falls_in_II": falls,
        "lamer_cluster_faster_in_II": faster,
        "lamer_all_three_ok": bool(rises and falls and faster)
        if not any(isinstance(v, float) and np.isnan(v) for v in (rises, falls, faster))
        else np.nan,
    }


def final_fit_params(monomer: pd.DataFrame) -> dict[str, float]:
    """Last non-NaN value of each pfo-sec_* column -- the ODE's own end-of-run
    parameter estimates, reported for context (not used as onset markers)."""
    out: dict[str, float] = {}
    for column in PFO_SEC_COLUMNS:
        series = pd.to_numeric(monomer.get(column), errors="coerce").dropna()
        out[f"final_{column}"] = float(series.iloc[-1]) if not series.empty else np.nan
    return out


def _plot_file(
    csv_path: Path,
    monomer: pd.DataFrame,
    cluster: pd.DataFrame,
    row: dict[str, Any],
    output_dir: Path,
) -> Path:
    fig, ax1 = plt.subplots(figsize=(9.5, 5))

    t_m = row["monomer_max_time_s"]
    t_c = row["cluster_max_time_s"]

    # LaMer stage shading, mirroring the textbook figure's vertical dividers.
    if row["region_order_ok"]:
        spans = [
            (row["run_start_s"], t_m, "tab:green", "I  prenucleation"),
            (t_m, t_c, "tab:purple", "II  burst + growth"),
            (t_c, row["run_end_s"], "tab:grey", "III  growth / ripening"),
        ]
        # Regions I and II are narrow (median 5.7% / 10.3% of the run), so the
        # labels are staggered vertically rather than centered on one line.
        for height, (left, right, color, label) in zip((0.99, 0.94, 0.99), spans):
            ax1.axvspan(left, right, color=color, alpha=0.10)
            ax1.text(
                (left + right) / 2,
                height,
                label,
                transform=ax1.get_xaxis_transform(),
                ha="center",
                va="top",
                fontsize=8,
                color=color,
            )

    ax1.plot(
        monomer["Time (s)"],
        monomer["Cumulative_Peak_Area"],
        "o-",
        color="tab:blue",
        ms=3,
        lw=1.2,
    )
    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("monomer_sum, groups collapsed (a.u.)", color="tab:blue")
    ax1.tick_params(axis="y", labelcolor="tab:blue")

    ax2 = ax1.twinx()
    ax2.plot(
        cluster["Time (s)"],
        cluster["Cumulative_Peak_Area"],
        "o-",
        color="tab:orange",
        ms=3,
        lw=1.2,
    )
    ax2.set_ylabel("cluster_sum, groups collapsed (a.u.)", color="tab:orange")
    ax2.tick_params(axis="y", labelcolor="tab:orange")

    handles: list[Any] = []
    labels: list[str] = []

    if not np.isnan(t_m):
        h = ax1.axvline(t_m, color="tab:blue", ls="--", lw=1.6)
        handles.append(h)
        labels.append(f"monomer max t={t_m:.0f}s")
        (h,) = ax1.plot(
            t_m, row["monomer_max_amplitude_au"], "*", color="tab:blue", ms=16
        )
        handles.append(h)
        labels.append(f"  ({t_m:.0f}, {row['monomer_max_amplitude_au']:.3f})")
        if not np.isnan(row["cluster_at_monomer_max_au"]):
            (h,) = ax2.plot(
                t_m,
                row["cluster_at_monomer_max_au"],
                "o",
                mfc="none",
                mec="tab:blue",
                mew=2,
                ms=14,
            )
            handles.append(h)
            labels.append(
                f"  cast on cluster ({t_m:.0f}, {row['cluster_at_monomer_max_au']:.3f})"
            )

    if not np.isnan(t_c):
        h = ax2.axvline(t_c, color="tab:orange", ls="--", lw=1.6)
        handles.append(h)
        labels.append(f"cluster max t={t_c:.0f}s")
        (h,) = ax2.plot(
            t_c, row["cluster_max_amplitude_au"], "*", color="tab:orange", ms=16
        )
        handles.append(h)
        labels.append(f"  ({t_c:.0f}, {row['cluster_max_amplitude_au']:.3f})")
        if not np.isnan(row["monomer_at_cluster_max_au"]):
            (h,) = ax1.plot(
                t_c,
                row["monomer_at_cluster_max_au"],
                "o",
                mfc="none",
                mec="tab:orange",
                mew=2,
                ms=14,
            )
            handles.append(h)
            labels.append(
                f"  cast on monomer ({t_c:.0f}, {row['monomer_at_cluster_max_au']:.3f})"
            )

    ax1.legend(handles, labels, loc="upper right", fontsize=7.5)
    if row["region_order_ok"]:
        marks = "".join(
            "Y" if row[key] is True else "n"
            for key in (
                "lamer_monomer_rises_in_I",
                "lamer_monomer_falls_in_II",
                "lamer_cluster_faster_in_II",
            )
        )
        gate = f"   LaMer sign test (M+ in I / M- in II / C faster in II): {marks}"
    else:
        gate = "  [regions undefined: landmark gate failed]"
    ax1.set_title(f"{csv_path.stem}{gate}", fontsize=10)
    fig.tight_layout()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{csv_path.stem}_monomer_lamer.png"
    fig.savefig(output_path, dpi=130)
    plt.close(fig)
    return output_path


def process_file(csv_path: Path, output_dir: Path) -> dict[str, Any]:
    df = pd.read_csv(csv_path)

    monomer = collapse_delta_groups(df, "monomer_sum")
    cluster = collapse_delta_groups(df, "cluster_sum")

    row: dict[str, Any] = {
        "file": csv_path.name,
        "sample_date": csv_path.name[:8],
        "n_monomer_points": len(monomer),
        "n_cluster_points": len(cluster),
        **landmark_coordinates(monomer, cluster),
        **final_fit_params(monomer),
    }
    row.update(lamer_regions(monomer, cluster, row))
    row.update(lamer_sign_test(monomer, cluster, row))

    # Model-side half of the bridge: region II is the burst-plus-growth
    # duration read off the curves; 1/k_a is the ODE's own uptake timescale.
    k_a = row.get("final_pfo-sec_k_a_s-1", np.nan)
    row["k_a_timescale_s"] = 1.0 / k_a if k_a and not np.isnan(k_a) else np.nan
    row["region_II_over_k_a_timescale"] = (
        row["region_II_duration_s"] / row["k_a_timescale_s"]
        if not np.isnan(row["region_II_duration_s"])
        and not np.isnan(row["k_a_timescale_s"])
        else np.nan
    )

    row["monomer_group_std_mean_au"] = float(
        monomer["group_std_au"].mean(skipna=True) if not monomer.empty else np.nan
    )
    row["cluster_group_std_mean_au"] = float(
        cluster["group_std_au"].mean(skipna=True) if not cluster.empty else np.nan
    )

    _plot_file(csv_path, monomer, cluster, row, output_dir)
    return row


def run_folder(dataset_folder: Path, output_folder: str = "_test") -> pd.DataFrame:
    csv_files = sorted(dataset_folder.glob("*_CarbonylPeakArea.csv"))
    # Same guard as the CSV writers: never resolve back onto the source folder.
    output_dir = UTILS.resolve_output_dir(dataset_folder, output_folder)

    rows: list[dict[str, Any]] = []
    for csv_file in csv_files:
        try:
            rows.append(process_file(csv_file, output_dir))
        except Exception as exc:  # noqa: BLE001 - record and keep going
            rows.append({"file": csv_file.name, "error": str(exc)})

    catalog = pd.DataFrame(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = output_dir / "monomer_features_lamer_slices.csv"
    catalog.to_csv(catalog_path, index=False)
    return catalog


if __name__ == "__main__":
    dataset_folder = SEARCH_ROOT / "nn1120-4_pd_ceo2_000"
    result = run_folder(dataset_folder)
    with pd.option_context("display.max_rows", None, "display.width", 240):
        print(
            result[
                [
                    "file",
                    "monomer_max_time_s",
                    "cluster_at_monomer_max_au",
                    "cluster_max_time_s",
                    "monomer_at_cluster_max_au",
                    "region_order_ok",
                    "region_I_duration_s",
                    "region_II_duration_s",
                    "region_III_duration_s",
                    "lamer_monomer_rises_in_I",
                    "lamer_monomer_falls_in_II",
                    "lamer_cluster_faster_in_II",
                    "lamer_all_three_ok",
                ]
            ]
        )
