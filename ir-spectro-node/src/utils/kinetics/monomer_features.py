"""Relate the monomer/secondary-process kinetic model to the LaMer picture.

Loop instance: docs/prompt_monomer-kinetics.md / docs/JOURNAL_monomer-kinetics.md.
Standalone module, no CLI -- plain functions plus an editable-constants
``__main__`` block (see prompt_monomer-kinetics.md for why). Scope: monomer_sum
in the 34 files under C:\\Data\\peakFit\\nn1120-4_pd_ceo2_000\\ only. Does not
touch cluster_sum's own detector code, and does not use the classifier's
growth_onset_s as a reference (flagged errant in round 3); no metrics beyond
monomer_sum/cluster_sum/pfo-sec.

Round 4: the bridge between the two species is their two maxima -- the
monomer_sum max (the anchor, ``monomer_peak_feature``, unchanged) and the
cluster_sum max (``peak_by_delta_group``) -- and the lag between them. Round
3's threshold-based ``cluster_rise_onset_feature`` was removed: the Delta_Group
offsets it was tripping on are an artifact, not signal (see peak_by_delta_group).
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

from src.utils.kinetics.writer import SEARCH_ROOT

PFO_SEC_COLUMNS = [
    "pfo-sec_k_a_s-1",
    "pfo-sec_q_e_au",
    "pfo-sec_k_s_s-1",
    "pfo-sec_k_p_s-1",
    "pfo-sec_q_inf_au",
    "pfo-sec_q0_au",
]


def monomer_trajectory(df: pd.DataFrame) -> pd.DataFrame:
    """monomer_sum trajectory, averaged across Delta_Group at equal Time (s).

    Different from how the cluster classifier reads cluster_sum (no dedup --
    see cluster_trajectory below): this module wants one clean curve per time
    to detect a single peak and read a single fit-parameter series, not to
    reproduce the classifier's own point-by-point behavior.
    """
    columns = ["Time (s)", "Cumulative_Peak_Area", *PFO_SEC_COLUMNS]
    rows = df.loc[df["Peak_Name"] == "monomer_sum", columns].copy()
    rows["Time (s)"] = pd.to_numeric(rows["Time (s)"], errors="coerce")
    rows["Cumulative_Peak_Area"] = pd.to_numeric(
        rows["Cumulative_Peak_Area"], errors="coerce"
    )
    rows = rows.dropna(subset=["Time (s)", "Cumulative_Peak_Area"])
    grouped = rows.groupby("Time (s)", as_index=False).mean(numeric_only=True)
    return grouped.sort_values("Time (s)").reset_index(drop=True)


def monomer_with_groups(df: pd.DataFrame) -> pd.DataFrame:
    """monomer_sum rows keeping Delta_Group -- input for the per-group check
    on the peak picker (see ``process_file``). The reported monomer anchor
    still comes from ``monomer_peak_feature`` on the averaged curve."""
    rows = df.loc[
        df["Peak_Name"] == "monomer_sum",
        ["Time (s)", "Delta_Group", "Cumulative_Peak_Area"],
    ].copy()
    rows["Time (s)"] = pd.to_numeric(rows["Time (s)"], errors="coerce")
    rows["Cumulative_Peak_Area"] = pd.to_numeric(
        rows["Cumulative_Peak_Area"], errors="coerce"
    )
    rows = rows.dropna(subset=["Time (s)", "Cumulative_Peak_Area"])
    return rows.sort_values("Time (s)").reset_index(drop=True)


def cluster_trajectory(df: pd.DataFrame) -> pd.DataFrame:
    """cluster_sum rows, time-sorted, keeping Delta_Group.

    Delta_Group is retained rather than averaged away because the groups are
    systematically offset from one another (see ``peak_by_delta_group``), so
    the right unit of analysis here is one group's own curve, not a pooled
    series. Round 2's reason for reading this un-deduped (to reproduce what
    the nuc-clf classifier harness would see) no longer applies -- that call
    was removed in round 3.
    """
    rows = df.loc[
        df["Peak_Name"] == "cluster_sum",
        ["Time (s)", "Delta_Group", "Cumulative_Peak_Area"],
    ].copy()
    rows["Time (s)"] = pd.to_numeric(rows["Time (s)"], errors="coerce")
    rows["Cumulative_Peak_Area"] = pd.to_numeric(
        rows["Cumulative_Peak_Area"], errors="coerce"
    )
    rows = rows.dropna(subset=["Time (s)", "Cumulative_Peak_Area"])
    return rows.sort_values("Time (s)").reset_index(drop=True)


def monomer_peak_feature(monomer: pd.DataFrame) -> dict[str, float]:
    """Time and amplitude of the monomer_sum maximum.

    A 3-point centered rolling mean is used only to pick *which* point is the
    peak (avoids latching onto a single-sample noise spike); the reported
    amplitude is the raw (unsmoothed) value at that time.
    """
    if monomer.empty:
        return {
            "peak_time_s": np.nan,
            "peak_amplitude_au": np.nan,
            "peak_index_frac": np.nan,
        }
    smoothed = (
        monomer["Cumulative_Peak_Area"].rolling(3, center=True, min_periods=1).mean()
    )
    idx = smoothed.idxmax()
    return {
        "peak_time_s": float(monomer.loc[idx, "Time (s)"]),
        "peak_amplitude_au": float(monomer.loc[idx, "Cumulative_Peak_Area"]),
        "peak_index_frac": float(idx) / max(len(monomer) - 1, 1),
    }


def peak_by_delta_group(
    rows: pd.DataFrame, prefix: str, min_points: int = 5
) -> dict[str, float]:
    """Peak picked inside each Delta_Group separately, then aggregated by median.

    Why not pool the groups first: the Delta_Group levels are systematically
    offset from each other. In this dataset's late-time window a group's own
    scatter is ~0.02-0.04 a.u. while the spread *between* group means is
    ~0.30 a.u. -- comparable to cluster_sum's entire dynamic range. A pooled
    time-sorted series therefore zigzags between six offset levels, and which
    group happens to be sampled at a given time moves the pooled value more
    than the chemistry does. (This is what made round 3's rate-threshold onset
    fire on "noise" bumps; they were composition artifacts, not noise.)

    Each group spans >90% of the trajectory in every file here, so each yields
    a legitimate peak on an internally consistent curve. The median across
    groups is the reported peak; the spread across groups is carried as a free
    uncertainty estimate. Groups with fewer than ``min_points`` samples are
    skipped as too short to peak-pick.
    """
    keys = [
        f"{prefix}_peak_time_s",
        f"{prefix}_peak_amplitude_au",
        f"{prefix}_peak_time_spread_s",
        f"{prefix}_peak_index_frac",
        f"{prefix}_n_groups",
    ]
    empty = dict.fromkeys(keys, np.nan)
    if rows.empty or "Delta_Group" not in rows:
        return empty

    times: list[float] = []
    amplitudes: list[float] = []
    index_fractions: list[float] = []
    for _, group in rows.groupby("Delta_Group"):
        group = group.sort_values("Time (s)").reset_index(drop=True)
        if len(group) < min_points:
            continue
        smoothed = (
            group["Cumulative_Peak_Area"].rolling(3, center=True, min_periods=1).mean()
        )
        idx = int(smoothed.idxmax())
        times.append(float(group.loc[idx, "Time (s)"]))
        amplitudes.append(float(group.loc[idx, "Cumulative_Peak_Area"]))
        index_fractions.append(float(idx) / max(len(group) - 1, 1))

    if not times:
        return empty
    return {
        f"{prefix}_peak_time_s": float(np.median(times)),
        f"{prefix}_peak_amplitude_au": float(np.median(amplitudes)),
        f"{prefix}_peak_time_spread_s": float(np.max(times) - np.min(times)),
        f"{prefix}_peak_index_frac": float(np.median(index_fractions)),
        f"{prefix}_n_groups": float(len(times)),
    }


def q_inf_onset_feature(
    monomer: pd.DataFrame, frac_of_max: float = 0.1
) -> dict[str, float]:
    """First sustained (2 consecutive fit rows) time the rolling secondary-PFO
    fit's q_inf exceeds ``frac_of_max`` of its own eventual max in this file.

    Physical reading: q_inf is the model's own read on how much monomer
    capacity secondary depletion will eventually remove (q_eq - q_inf per the
    LaMer/adsorption derivation). Early in a trajectory, while monomer is
    still net accumulating, an expanding-window fit has little reason to need
    q_inf > 0 to explain the data -- it only needs to grow once the data
    itself starts declining. So a jump in the *rolling* q_inf is a candidate
    marker for when the fit "notices" net depletion has begun, i.e. a
    model-internal analog of LaMer's nucleation-burst-ending / growth-starting
    transition, distinct from (and comparable to) the raw peak time.
    """
    q_inf = pd.to_numeric(monomer.get("pfo-sec_q_inf_au"), errors="coerce")
    valid = q_inf.dropna()
    if valid.empty or valid.max() <= 0:
        return {"q_inf_onset_time_s": np.nan, "q_inf_final_au": np.nan}
    threshold = frac_of_max * valid.max()
    above = q_inf >= threshold
    onset_time = np.nan
    for i in range(len(above) - 1):
        if bool(above.iloc[i]) and bool(above.iloc[i + 1]):
            onset_time = float(monomer["Time (s)"].iloc[i])
            break
    return {"q_inf_onset_time_s": onset_time, "q_inf_final_au": float(valid.iloc[-1])}


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
    peak: dict[str, float],
    q_inf_onset: dict[str, float],
    cluster_peak: dict[str, float],
    lag_s: float,
    output_dir: Path,
) -> Path:
    fig, ax1 = plt.subplots(figsize=(9, 5))
    ax1.plot(
        monomer["Time (s)"],
        monomer["Cumulative_Peak_Area"],
        "o-",
        color="tab:blue",
        ms=3,
        lw=1,
        label="monomer_sum",
    )
    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("monomer_sum (a.u.)", color="tab:blue")
    ax1.tick_params(axis="y", labelcolor="tab:blue")

    ax2 = ax1.twinx()
    # One thin line per Delta_Group rather than a pooled series -- the groups
    # are offset by ~the whole cluster_sum dynamic range, so pooling them is
    # what produced the apparent sawtooth in earlier rounds' plots.
    for name, group in cluster.groupby("Delta_Group"):
        group = group.sort_values("Time (s)")
        ax2.plot(
            group["Time (s)"],
            group["Cumulative_Peak_Area"],
            "o-",
            color="tab:orange",
            ms=2,
            lw=0.8,
            alpha=0.5,
            label=str(name),
        )
    ax2.set_ylabel("cluster_sum per Delta_Group (a.u.)", color="tab:orange")
    ax2.tick_params(axis="y", labelcolor="tab:orange")

    handles: list[Any] = []
    labels: list[str] = []

    monomer_t = peak["peak_time_s"]
    cluster_t = cluster_peak.get("cluster_peak_time_s", np.nan)

    if not np.isnan(monomer_t):
        ax1.axvline(monomer_t, color="tab:blue", ls="--", lw=1.2)
        (h,) = ax1.plot(
            monomer_t, peak["peak_amplitude_au"], "*", color="tab:blue", ms=16
        )
        handles.append(h)
        labels.append(f"monomer max t={monomer_t:.0f}s")

    if not np.isnan(cluster_t):
        ax2.axvline(cluster_t, color="tab:red", ls="--", lw=1.2)
        (h,) = ax2.plot(
            cluster_t,
            cluster_peak["cluster_peak_amplitude_au"],
            "*",
            color="tab:red",
            ms=16,
        )
        handles.append(h)
        spread = cluster_peak.get("cluster_peak_time_spread_s", np.nan)
        labels.append(f"cluster max t={cluster_t:.0f}s (group spread {spread:.0f}s)")

    if not np.isnan(lag_s):
        h = ax1.axvspan(
            min(monomer_t, cluster_t),
            max(monomer_t, cluster_t),
            color="tab:grey",
            alpha=0.15,
        )
        handles.append(h)
        labels.append(f"lag = {lag_s:.0f}s")

    q_inf_t = q_inf_onset.get("q_inf_onset_time_s", np.nan)
    if not np.isnan(q_inf_t):
        h = ax1.axvline(q_inf_t, color="tab:green", ls=":", lw=1.8)
        handles.append(h)
        labels.append(f"q_inf onset t={q_inf_t:.0f}s")

    ax1.legend(handles, labels, loc="upper right", fontsize=8)
    ax1.set_title(csv_path.stem)
    fig.tight_layout()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{csv_path.stem}_monomer_lamer.png"
    fig.savefig(output_path, dpi=130)
    plt.close(fig)
    return output_path


def process_file(csv_path: Path, output_dir: Path) -> dict[str, Any]:
    df = pd.read_csv(csv_path)

    monomer = monomer_trajectory(df)
    cluster = cluster_trajectory(df)

    peak = monomer_peak_feature(monomer)
    q_inf_onset = q_inf_onset_feature(monomer)
    finals = final_fit_params(monomer)
    cluster_peak = peak_by_delta_group(cluster, "cluster")
    # Same per-group method run on monomer_sum purely as a check on the method:
    # monomer's hump is large against the group offset, so its anchor peak
    # (monomer_peak_feature, unchanged) and this should agree. If they don't,
    # the per-group picker is suspect before it is trusted on cluster_sum.
    monomer_check = peak_by_delta_group(monomer_with_groups(df), "monomer_pergroup")

    row: dict[str, Any] = {
        "file": csv_path.name,
        "n_monomer_points": len(monomer),
        "n_cluster_points": len(cluster),
        **peak,
        **q_inf_onset,
        **finals,
        **cluster_peak,
        **monomer_check,
    }

    monomer_t = row.get("peak_time_s", np.nan)
    cluster_t = row.get("cluster_peak_time_s", np.nan)
    row["cluster_minus_monomer_peak_lag_s"] = (
        cluster_t - monomer_t
        if not np.isnan(monomer_t) and not np.isnan(cluster_t)
        else np.nan
    )
    row["monomer_pergroup_minus_anchor_s"] = (
        row["monomer_pergroup_peak_time_s"] - monomer_t
        if not np.isnan(monomer_t) and not np.isnan(row["monomer_pergroup_peak_time_s"])
        else np.nan
    )

    _plot_file(
        csv_path,
        monomer,
        cluster,
        peak,
        q_inf_onset,
        cluster_peak,
        row["cluster_minus_monomer_peak_lag_s"],
        output_dir,
    )
    return row


def run_folder(dataset_folder: Path, output_folder: str = "_test") -> pd.DataFrame:
    csv_files = sorted(dataset_folder.glob("*_CarbonylPeakArea.csv"))
    output_dir = dataset_folder / output_folder

    rows: list[dict[str, Any]] = []
    for csv_file in csv_files:
        try:
            rows.append(process_file(csv_file, output_dir))
        except Exception as exc:  # noqa: BLE001 - record and keep going
            rows.append({"file": csv_file.name, "error": str(exc)})

    catalog = pd.DataFrame(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = output_dir / "monomer_features_lamer_mapping.csv"
    catalog.to_csv(catalog_path, index=False)
    return catalog


if __name__ == "__main__":
    dataset_folder = SEARCH_ROOT / "nn1120-4_pd_ceo2_000"
    result = run_folder(dataset_folder)
    with pd.option_context("display.max_rows", None, "display.width", 200):
        print(
            result[
                [
                    "file",
                    "peak_time_s",
                    "peak_index_frac",
                    "cluster_peak_time_s",
                    "cluster_peak_index_frac",
                    "cluster_peak_time_spread_s",
                    "cluster_minus_monomer_peak_lag_s",
                    "monomer_pergroup_minus_anchor_s",
                ]
            ]
        )
