"""Draw the LaMer domains of each measurement from the classified refit areas.

Origin: the monomer-kinetics loop (docs/JOURNAL_monomer-kinetics.md, rounds
6-7). Standalone, no CLI -- edit ``FOLDER_NAME`` in ``__main__``.

Input: ``<data.peak_fit>/<folder>/_reprocess/_test_classification/`` area
CSVs, written by ``scripts\\run_kinetics_classification.py``. They carry
``monomer_sum`` / ``cluster_sum`` and, once the nucleation detector latches,
``latch_time_s`` (the latch time) and ``growth_onset_s`` (the growth onset,
``classification.growth_onset``) on the ``cluster_sum`` rows. No kinetic fit
columns are used. The detector's peak (``PEAK_NAME``, Peak_1988) is drawn on
its own axis for reference; it does not enter the domains or the catalog.

Domains, from three threshold-free landmarks and the latch:

    I    t0 -> monomer max            prenucleation accumulation
    IIa  monomer max -> latch         nucleation burst, before detection
    IIb  latch -> cluster max         growth after detection
    III  cluster max -> end           growth / ripening

The landmarks are each species' maximum (Delta_Group collapsed to its mean at
equal Time (s)). I/II/III need both maxima interior and ordered
(``region_order_ok``); II is split into IIa/IIb only when the latch falls
strictly inside it (``latch_position == "in_II"``). Otherwise II stays whole
and the latch, if any, is drawn as a line only. The growth onset does not
split a domain: it is drawn as a line, cast onto both curves and placed
against the landmarks (``growth_onset_position``) like the latch.

Output: one ``*_lamer_domains.png`` per file plus ``lamer_domains.csv`` under
``<data.figures>/<folder>/plot_lamer_domains/``.
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

path = Path(__file__).resolve().parents[2]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.core import config
from src.utils.kinetics.classification import PEAK_NAME
from src.utils.kinetics.writer import AREA_SUFFIX, SEARCH_ROOT

INPUT_SUBFOLDER = Path("_reprocess") / "_test_classification"

# A maximum at the very first or very last sample is an endpoint, not a peak
# (monomer-kinetics round 4's boundary gate). Both landmarks must clear it
# before the LaMer domains are meaningful.
INTERIOR_FRAC = (0.05, 0.95)


def input_dir(folder_name: str) -> Path:
    return SEARCH_ROOT / folder_name / INPUT_SUBFOLDER


def output_dir(folder_name: str) -> Path:
    return Path(
        config.get_path(
            "data.figures", folder_name, config.get_path("data.plot_lamer_domains")
        )
    )


def collapse_delta_groups(df: pd.DataFrame, peak_name: str) -> pd.DataFrame:
    """One curve per species: Delta_Group collapsed to its mean at equal Time (s).

    The Delta_Group levels are systematically offset (within-group scatter
    ~0.03 au vs ~0.30 au between group means), which is why the pooled
    time-sorted series looks like a sawtooth. ``group_std_au``/``n_groups``
    are kept per time point so the scatter behind each mean stays visible.
    """
    rows = df.loc[
        df["Peak_Name"] == peak_name, ["Time (s)", "Cumulative_Peak_Area"]
    ].copy()
    for column in rows.columns:
        rows[column] = pd.to_numeric(rows[column], errors="coerce")
    rows = rows.dropna()
    if rows.empty:
        return rows

    collapsed = rows.groupby("Time (s)", as_index=False).mean()
    scatter = (
        rows.groupby("Time (s)")["Cumulative_Peak_Area"]
        .agg(group_std_au="std", n_groups="count")
        .reset_index()
    )
    collapsed = collapsed.merge(scatter, on="Time (s)", how="left")
    return collapsed.sort_values("Time (s)").reset_index(drop=True)


def _cluster_sum_time(df: pd.DataFrame, column: str) -> float:
    """First ``column`` value on the cluster_sum rows; NaN if absent or empty."""
    if column not in df.columns:
        return np.nan
    values = pd.to_numeric(
        df.loc[df["Peak_Name"] == "cluster_sum", column], errors="coerce"
    ).dropna()
    return float(values.iloc[0]) if not values.empty else np.nan


def latch_time(df: pd.DataFrame) -> float:
    """The latch time (``latch_time_s`` on cluster_sum); NaN if none."""
    return _cluster_sum_time(df, "latch_time_s")


def growth_onset_time(df: pd.DataFrame) -> float:
    """The growth onset (``growth_onset_s`` on cluster_sum); NaN if none."""
    return _cluster_sum_time(df, "growth_onset_s")


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
    observed, so the in-range flag is carried into the catalog.
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
    monomer: pd.DataFrame, cluster: pd.DataFrame, t_latch: float, t_onset: float
) -> dict[str, Any]:
    """Each species' maximum, its time cast onto the other curve, and the
    latch time and growth onset cast onto both curves."""
    row: dict[str, Any] = {
        **_peak(monomer, "monomer_max"),
        **_peak(cluster, "cluster_max"),
        "latch_time_s": t_latch,
        "growth_onset_s": t_onset,
    }
    for name, curve, time_key in (
        ("cluster_at_monomer_max", cluster, "monomer_max_time_s"),
        ("monomer_at_cluster_max", monomer, "cluster_max_time_s"),
        ("monomer_at_latch", monomer, "latch_time_s"),
        ("cluster_at_latch", cluster, "latch_time_s"),
        ("monomer_at_growth_onset", monomer, "growth_onset_s"),
        ("cluster_at_growth_onset", cluster, "growth_onset_s"),
    ):
        value, in_range = _cast(curve, row[time_key])
        row[f"{name}_au"] = value
        row[f"{name}_in_range"] = in_range
    return row


def _position(t: float, t_m: float, t_c: float, ok: bool) -> str:
    """Where a time falls against the two maxima (``latch_position`` values)."""
    if np.isnan(t):
        return "none"
    if not ok:
        return "regions_undefined"
    if t <= t_m:
        return "before_monomer_max"
    if t >= t_c:
        return "after_cluster_max"
    return "in_II"


def lamer_domains(
    monomer: pd.DataFrame, cluster: pd.DataFrame, row: dict[str, Any]
) -> dict[str, Any]:
    """Slice the run into I / II (IIa + IIb) / III (module docstring).

    Durations are NaN where the domain is undefined, so a net-declining
    cluster curve cannot report a negative II, and a latch outside II does
    not produce a split.
    """
    t_m = row["monomer_max_time_s"]
    t_c = row["cluster_max_time_s"]
    t_l = row["latch_time_s"]

    interior = all(
        not np.isnan(row[key]) and INTERIOR_FRAC[0] <= row[key] <= INTERIOR_FRAC[1]
        for key in ("monomer_max_index_frac", "cluster_max_index_frac")
    )
    ordered = not np.isnan(t_m) and not np.isnan(t_c) and t_m < t_c
    ok = bool(interior and ordered)

    position = _position(t_l, t_m, t_c, ok)
    split = position == "in_II"

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
        "latch_position": position,
        "growth_onset_position": _position(row["growth_onset_s"], t_m, t_c, ok),
        "region_I_duration_s": t_m - t_start if ok else np.nan,
        "region_II_duration_s": t_c - t_m if ok else np.nan,
        "region_IIa_duration_s": t_l - t_m if split else np.nan,
        "region_IIb_duration_s": t_c - t_l if split else np.nan,
        "region_III_duration_s": t_end - t_c if ok else np.nan,
    }


def _slope(curve: pd.DataFrame, t_lo: float, t_hi: float) -> tuple[float, int]:
    """Least-squares slope (au/s) of a curve over a closed time slice.

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
    """Per-domain slopes plus the three sign expectations LaMer implies.

    I is accumulation (monomer rising); II is the burst consuming monomer into
    clusters (monomer falling, cluster accumulating faster than in I). All
    three are sign comparisons, so nothing here introduces a threshold. Only
    evaluated where ``region_order_ok``.
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


def _domain_spans(row: dict[str, Any]) -> list[tuple[float, float, str, str]]:
    """``(left, right, color, label)`` per drawn domain."""
    if not row["region_order_ok"]:
        return []
    t_m, t_c, t_l = (
        row["monomer_max_time_s"],
        row["cluster_max_time_s"],
        row["latch_time_s"],
    )
    middle = (
        [
            (t_m, t_l, "tab:purple", "IIa  burst"),
            (t_l, t_c, "tab:red", "IIb  growth"),
        ]
        if row["latch_position"] == "in_II"
        else [(t_m, t_c, "tab:purple", "II  burst + growth")]
    )
    return [
        (row["run_start_s"], t_m, "tab:green", "I  prenucleation"),
        *middle,
        (t_c, row["run_end_s"], "tab:grey", "III  growth / ripening"),
    ]


def _plot_file(
    csv_path: Path,
    monomer: pd.DataFrame,
    cluster: pd.DataFrame,
    detector_peak: pd.DataFrame,
    row: dict[str, Any],
    out_dir: Path,
) -> Path:
    fig, ax1 = plt.subplots(figsize=(10.5, 5))

    t_m = row["monomer_max_time_s"]
    t_c = row["cluster_max_time_s"]
    t_l = row["latch_time_s"]
    t_g = row["growth_onset_s"]

    # The early domains are narrow, so labels alternate between two heights.
    for i, (left, right, color, label) in enumerate(_domain_spans(row)):
        ax1.axvspan(left, right, color=color, alpha=0.10)
        ax1.text(
            (left + right) / 2,
            0.99 if i % 2 == 0 else 0.94,
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

    # The detector's peak sits ~an order of magnitude below cluster_sum, so it
    # gets its own axis, offset outside ax2's.
    if not detector_peak.empty:
        ax3 = ax1.twinx()
        ax3.spines["right"].set_position(("axes", 1.12))
        (h,) = ax3.plot(
            detector_peak["Time (s)"],
            detector_peak["Cumulative_Peak_Area"],
            "s-",
            color="tab:brown",
            ms=2.5,
            lw=1.0,
            alpha=0.8,
        )
        handles.append(h)
        labels.append(f"{PEAK_NAME} (detector peak)")
        ax3.set_ylabel(f"{PEAK_NAME}, groups collapsed (a.u.)", color="tab:brown")
        ax3.tick_params(axis="y", labelcolor="tab:brown")

    if not np.isnan(t_m):
        handles.append(ax1.axvline(t_m, color="tab:blue", ls="--", lw=1.6))
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

    if not np.isnan(t_l):
        handles.append(ax1.axvline(t_l, color="tab:red", ls=":", lw=2.0))
        labels.append(f"latch t={t_l:.0f}s")

    if not np.isnan(t_g):
        handles.append(ax1.axvline(t_g, color="tab:brown", ls="-.", lw=1.6))
        labels.append(f"growth onset t={t_g:.0f}s")

    if not np.isnan(t_c):
        handles.append(ax2.axvline(t_c, color="tab:orange", ls="--", lw=1.6))
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
        gate = "  [domains undefined: landmark gate failed]"
    ax1.set_title(f"{csv_path.stem}{gate}", fontsize=10)
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"{csv_path.stem}_lamer_domains.png"
    fig.savefig(output_path, dpi=130)
    plt.close(fig)
    return output_path


def process_file(csv_path: Path, out_dir: Path) -> dict[str, Any]:
    df = pd.read_csv(csv_path)

    monomer = collapse_delta_groups(df, "monomer_sum")
    cluster = collapse_delta_groups(df, "cluster_sum")

    row: dict[str, Any] = {
        "file": csv_path.name,
        "sample_date": csv_path.name[:8],
        "n_monomer_points": len(monomer),
        "n_cluster_points": len(cluster),
        **landmark_coordinates(monomer, cluster, latch_time(df), growth_onset_time(df)),
    }
    row.update(lamer_domains(monomer, cluster, row))
    row.update(lamer_sign_test(monomer, cluster, row))
    row["monomer_group_std_mean_au"] = float(
        monomer["group_std_au"].mean(skipna=True) if not monomer.empty else np.nan
    )
    row["cluster_group_std_mean_au"] = float(
        cluster["group_std_au"].mean(skipna=True) if not cluster.empty else np.nan
    )

    detector_peak = collapse_delta_groups(df, PEAK_NAME)
    _plot_file(csv_path, monomer, cluster, detector_peak, row, out_dir)
    return row


def run_folder(folder_name: str) -> pd.DataFrame:
    """Every classified area CSV of one dataset: figures + ``lamer_domains.csv``."""
    source = input_dir(folder_name)
    csv_files = sorted(source.glob(f"*{AREA_SUFFIX}"))
    if not csv_files:
        raise FileNotFoundError(
            f"no *{AREA_SUFFIX} in {source}; run "
            f"scripts\\run_kinetics_classification.py --folder {folder_name} first"
        )
    out_dir = output_dir(folder_name)

    rows: list[dict[str, Any]] = []
    for csv_file in csv_files:
        try:
            rows.append(process_file(csv_file, out_dir))
        except Exception as exc:  # noqa: BLE001 - record and keep going
            rows.append({"file": csv_file.name, "error": str(exc)})

    catalog = pd.DataFrame(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    catalog.to_csv(out_dir / "lamer_domains.csv", index=False)
    return catalog


if __name__ == "__main__":
    FOLDER_NAME = "nn1120-4_pd_ceo2_000"
    result = run_folder(FOLDER_NAME)
    print(f"Wrote {len(result)} files' domains to {output_dir(FOLDER_NAME)}")
    with pd.option_context("display.max_rows", None, "display.width", 240):
        print(
            result[
                [
                    "file",
                    "monomer_max_time_s",
                    "growth_onset_s",
                    "latch_time_s",
                    "cluster_max_time_s",
                    "region_order_ok",
                    "growth_onset_position",
                    "latch_position",
                    "region_I_duration_s",
                    "region_IIa_duration_s",
                    "region_IIb_duration_s",
                    "region_III_duration_s",
                    "lamer_all_three_ok",
                ]
            ]
        )
