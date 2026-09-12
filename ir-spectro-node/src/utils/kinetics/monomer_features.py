"""Relate the monomer/secondary-process kinetic model to the LaMer picture.

Loop instance: docs/prompt_monomer-kinetics.md / docs/JOURNAL_monomer-kinetics.md.
Standalone module, no CLI -- plain functions plus an editable-constants
``__main__`` block (see prompt_monomer-kinetics.md for why). Scope: monomer_sum
in the 34 files under C:\\Data\\peakFit\\nn1120-4_pd_ceo2_000\\ only. Does not
touch cluster_sum's own detector code -- classify_trajectory_combined is called
read-only, purely to plot a reference growth_onset_s next to this loop's own
monomer-side features.
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

from src.utils.kinetics.writer import CLASSIFIER, SEARCH_ROOT, WRITER

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


def cluster_trajectory(df: pd.DataFrame) -> pd.DataFrame:
    """cluster_sum trajectory, time-sorted only -- matches validation.py's own
    ``_cluster_sum_trajectory`` (no dedup across Delta_Group), so that calling
    the existing combined classifier here reproduces what the real harness
    would compute, not a version reshaped by this module's own averaging.
    """
    rows = df.loc[
        df["Peak_Name"] == "cluster_sum", ["Time (s)", "Cumulative_Peak_Area"]
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
        return {"peak_time_s": np.nan, "peak_amplitude_au": np.nan}
    smoothed = (
        monomer["Cumulative_Peak_Area"].rolling(3, center=True, min_periods=1).mean()
    )
    idx = smoothed.idxmax()
    return {
        "peak_time_s": float(monomer.loc[idx, "Time (s)"]),
        "peak_amplitude_au": float(monomer.loc[idx, "Cumulative_Peak_Area"]),
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


def cluster_reference_onset(cluster: pd.DataFrame) -> dict[str, Any]:
    """Batch (whole-trajectory, not prefix-swept) classify_trajectory_combined
    on cluster_sum -- a read-only reference point for comparison. This does
    not run the nuc-clf loop's own validation harness/aggregation policy; it's
    a single best-effort growth_onset_s to plot next to this loop's monomer
    features, not a claim about that loop's own correctness metric.
    """
    if cluster.empty or len(cluster) < 4:
        return {
            "cluster_classification": "insufficient_data",
            "cluster_growth_onset_s": np.nan,
        }
    time_s = cluster["Time (s)"].to_numpy(dtype=float)
    intensity = cluster["Cumulative_Peak_Area"].to_numpy(dtype=float)
    result = CLASSIFIER.classify_trajectory_combined(time_s, intensity)
    return {
        "cluster_classification": result.get("classification"),
        "cluster_growth_onset_s": result.get("growth_onset_s", np.nan),
    }


def _plot_file(
    csv_path: Path,
    monomer: pd.DataFrame,
    cluster: pd.DataFrame,
    peak: dict[str, float],
    q_inf_onset: dict[str, float],
    cluster_ref: dict[str, Any],
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
    if not cluster.empty:
        ax2.plot(
            cluster["Time (s)"],
            cluster["Cumulative_Peak_Area"],
            "o-",
            color="tab:orange",
            ms=3,
            lw=1,
            label="cluster_sum",
        )
    ax2.set_ylabel("cluster_sum (a.u.)", color="tab:orange")
    ax2.tick_params(axis="y", labelcolor="tab:orange")

    handles: list[Any] = []
    labels: list[str] = []

    if not np.isnan(peak["peak_time_s"]):
        ax1.axvline(peak["peak_time_s"], color="tab:blue", ls="--", lw=1.2)
        (h,) = ax1.plot(
            peak["peak_time_s"],
            peak["peak_amplitude_au"],
            "*",
            color="tab:blue",
            ms=16,
        )
        handles.append(h)
        labels.append(f"monomer peak t={peak['peak_time_s']:.0f}s")

    q_inf_t = q_inf_onset.get("q_inf_onset_time_s", np.nan)
    if not np.isnan(q_inf_t):
        h = ax1.axvline(q_inf_t, color="tab:green", ls=":", lw=1.8)
        handles.append(h)
        labels.append(f"q_inf onset t={q_inf_t:.0f}s")

    cluster_onset = cluster_ref.get("cluster_growth_onset_s", np.nan)
    if cluster_onset is not None and not (
        isinstance(cluster_onset, float) and np.isnan(cluster_onset)
    ):
        h = ax2.axvline(cluster_onset, color="tab:red", ls="-.", lw=1.8)
        handles.append(h)
        labels.append(f"cluster growth_onset (combined) t={cluster_onset:.0f}s")

    ax1.legend(handles, labels, loc="upper right", fontsize=8)
    ax1.set_title(
        f"{csv_path.stem}\ncluster_classification="
        f"{cluster_ref.get('cluster_classification')}"
    )
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
    cluster_ref = cluster_reference_onset(cluster)

    row: dict[str, Any] = {
        "file": csv_path.name,
        "n_monomer_points": len(monomer),
        "n_cluster_points": len(cluster),
        **peak,
        **q_inf_onset,
        **finals,
        **cluster_ref,
    }

    onset_s = row.get("cluster_growth_onset_s", np.nan)
    peak_t = row.get("peak_time_s", np.nan)
    row["monomer_peak_minus_cluster_onset_s"] = (
        peak_t - onset_s
        if not np.isnan(peak_t) and onset_s is not None and not np.isnan(onset_s)
        else np.nan
    )

    _plot_file(csv_path, monomer, cluster, peak, q_inf_onset, cluster_ref, output_dir)
    return row


def run_folder(
    dataset_folder: Path, output_folder: str = "_test"
) -> pd.DataFrame:
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
                    "peak_amplitude_au",
                    "q_inf_onset_time_s",
                    "cluster_classification",
                    "cluster_growth_onset_s",
                    "monomer_peak_minus_cluster_onset_s",
                ]
            ]
        )
