"""Plot cluster/monomer trajectory fits from stored parameters."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal, cast
import sys

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
import numpy as np
import pandas as pd
from pandas.api.types import is_scalar
from numpy.typing import NDArray

path = Path(__file__).parent.parent.parent
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.core import config

LOGGER = logging.getLogger(__name__)

SEARCH_ROOT = Path(config.get_path("data.peak_fit"))
OUTPUT_ROOT = Path(config.get_path("data.figures"))
DEFAULT_OUTPUT_SUBDIR = config.get_path("data.plot_kinetics_fit")
SUM_PEAKS = {"cluster_sum", "monomer_sum"}


def pfo(
    time_s: NDArray[np.float64],
    k_a: float,
    k_d: float,
    q_e: float,
    K_eq: float,
    q_0: float,
) -> NDArray[np.float64]:
    """PFO uptake with exponential decay toward equilibrium offset."""
    adsorption = q_e * (1.0 - np.exp(-k_a * time_s)) * np.exp(-k_d * time_s)
    equilibrium = K_eq * (1.0 - np.exp(-k_d * time_s))
    return q_0 + adsorption + equilibrium


def _extract_sum_trace(
    df: Any,
    peak_name: str,
    *,
    min_points: int = 3,
) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()
    trace = cast(pd.DataFrame, df[df["Peak_Name"] == peak_name].copy())
    if trace.empty:
        return pd.DataFrame()
    trace["Time (s)"] = pd.to_numeric(trace["Time (s)"], errors="coerce")
    trace["Cumulative_Peak_Area"] = pd.to_numeric(
        trace["Cumulative_Peak_Area"], errors="coerce"
    )
    mask = trace["Time (s)"].notna() & trace["Cumulative_Peak_Area"].notna()
    trace = trace.loc[mask].copy()
    if len(trace) < min_points:
        return pd.DataFrame()
    trace = cast(pd.DataFrame, trace)
    return trace.sort_values(by="Time (s)")


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    if not is_scalar(value):
        return None
    try:
        numeric_float = float(cast(Any, value))
    except (TypeError, ValueError):
        return None
    if pd.isna(numeric_float):
        return None
    if not np.isfinite(numeric_float):
        return None
    return numeric_float


def _extract_pfo_fit_params(df: pd.DataFrame) -> dict[str, float]:
    if df.empty:
        return {}
    final_row = df.iloc[-1]
    param_keys = [
        "pfo_ka_s-1",
        "pfo_kd_s-1",
        "pfo_qe_au",
        "pfo_Keq_au",
        "pfo_q0_au",
    ]
    params: dict[str, float] = {}
    for key in param_keys:
        value = _coerce_float(final_row.get(key))
        if value is None or not np.isfinite(value):
            return {}
        params[key] = value
    return params


def _extract_prefixed_pfo_params(
    df: pd.DataFrame,
    prefix: str,
) -> dict[str, float]:
    if df.empty:
        return {}
    final_row = df.iloc[-1]
    param_keys = [
        "pfo_ka_s-1",
        "pfo_kd_s-1",
        "pfo_qe_au",
        "pfo_Keq_au",
        "pfo_q0_au",
    ]
    params: dict[str, float] = {}
    for key in param_keys:
        value = _coerce_float(final_row.get(f"{prefix}{key}"))
        if value is None or not np.isfinite(value):
            return {}
        params[key] = value
    return params


def _plot_pfo_fit_curve(
    ax: Axes,
    time_s: NDArray[np.float64],
    params: dict[str, float],
    *,
    label: str,
    color: str,
    time_unit: Literal["s", "h"],
) -> None:
    time_grid = np.linspace(np.min(time_s), np.max(time_s), 200)
    curve = pfo(
        time_grid,
        params["pfo_ka_s-1"],
        params["pfo_kd_s-1"],
        params["pfo_qe_au"],
        params["pfo_Keq_au"],
        params["pfo_q0_au"],
    )
    curve_time = time_grid / 3600 if time_unit == "h" else time_grid
    ax.plot(curve_time, curve, label=label, color=color)


def plot_monomer_cluster_fit(
    cluster_df: pd.DataFrame,
    monomer_df: pd.DataFrame,
    *,
    output_path: Path,
    title: str,
    time_unit: Literal["s", "h"] = "s",
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5))

    time_label = "Time (h)" if time_unit == "h" else "Time (s)"
    cluster_time = cluster_df["Time (s)"].to_numpy(dtype=float)
    cluster_area = cluster_df["Cumulative_Peak_Area"].to_numpy(dtype=float)
    cluster_time_values = cluster_time / 3600 if time_unit == "h" else cluster_time
    ax.scatter(cluster_time_values, cluster_area, s=18, label="cluster_sum", alpha=0.7)

    cluster_params = _extract_pfo_fit_params(cluster_df)
    cluster_row = cluster_df.iloc[-1]
    cluster_classification = cluster_row.get("classification")
    growth_onset = _coerce_float(cluster_row.get("growth_onset_s"))
    if growth_onset is None:
        growth_onset = _coerce_float(cluster_row.get("breakpoint_s"))
    pre_params = _extract_prefixed_pfo_params(cluster_df, "pre_")
    post_params = _extract_prefixed_pfo_params(cluster_df, "post_")
    if (
        cluster_classification == "discontinuous"
        and growth_onset is not None
        and pre_params
        and post_params
    ):
        pre_mask = cluster_time <= growth_onset
        post_mask = cluster_time > growth_onset
        if np.any(pre_mask):
            _plot_pfo_fit_curve(
                ax,
                cluster_time[pre_mask],
                pre_params,
                label="cluster_pre_fit",
                color="red",
                time_unit=time_unit,
            )
        if np.any(post_mask):
            _plot_pfo_fit_curve(
                ax,
                cluster_time[post_mask],
                post_params,
                label="cluster_post_fit",
                color="darkred",
                time_unit=time_unit,
            )
        onset_time = growth_onset / 3600 if time_unit == "h" else growth_onset
        ax.axvline(onset_time, color="gray", linestyle="--", label="growth onset")
    elif cluster_params:
        _plot_pfo_fit_curve(
            ax,
            cluster_time,
            cluster_params,
            label="cluster_fit",
            color="red",
            time_unit=time_unit,
        )

    if not monomer_df.empty:
        monomer_time = monomer_df["Time (s)"].to_numpy(dtype=float)
        monomer_area = monomer_df["Cumulative_Peak_Area"].to_numpy(dtype=float)
        monomer_time_values = monomer_time / 3600 if time_unit == "h" else monomer_time
        ax.scatter(
            monomer_time_values, monomer_area, s=14, label="monomer_sum", alpha=0.7
        )

        monomer_params = _extract_pfo_fit_params(monomer_df)
        if monomer_params:
            _plot_pfo_fit_curve(
                ax,
                monomer_time,
                monomer_params,
                label="monomer_fit",
                color="blue",
                time_unit=time_unit,
            )

    ax.set_xlabel(time_label)
    ax.set_ylabel("Cumulative Peak Area")
    ax.set_title(title)
    ax.legend(fontsize=8, loc="best", ncol=2)
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_kinetic_fit(
    file_path: str | Path,
    *,
    time_unit: Literal["s", "h"] = "s",
) -> None:
    """Plot monomer/cluster fits from a kinetic-fit CSV."""
    file_path_obj = Path(file_path)
    data_root = SEARCH_ROOT

    if file_path_obj.name.endswith("_CarbonylPeakArea.csv"):
        csv_path = (
            file_path_obj if file_path_obj.is_absolute() else data_root / file_path_obj
        )
        base_name = csv_path.stem.replace("_CarbonylPeakArea", "")
    else:
        base_name = file_path_obj.stem if file_path_obj.suffix else file_path_obj.name
        relative_parent = file_path_obj.parent
        folder_root = data_root / relative_parent
        csv_path = folder_root / f"{base_name}_CarbonylPeakArea.csv"

    try:
        dataset_folder = str(csv_path.parent.relative_to(data_root))
    except ValueError:
        dataset_folder = csv_path.parent.name
    if not csv_path.exists():
        LOGGER.warning("Missing carbonyl peak area CSV: %s", csv_path)
        return

    df = pd.read_csv(csv_path)
    df = cast(pd.DataFrame, df)
    df_filtered = df[df["Peak_Name"].isin(list(SUM_PEAKS))].copy()
    df_filtered = cast(pd.DataFrame, df_filtered)
    if df_filtered.empty:
        LOGGER.warning("Missing monomer/cluster sums in %s", csv_path)
        return

    cluster_sum = _extract_sum_trace(df_filtered, "cluster_sum")
    if cluster_sum.empty:
        LOGGER.warning("Insufficient cluster data in %s", csv_path)
        return

    monomer_sum = _extract_sum_trace(df_filtered, "monomer_sum")

    output_path = (
        OUTPUT_ROOT
        / dataset_folder
        / DEFAULT_OUTPUT_SUBDIR
        / f"{base_name}_monomer_cluster_fit.tiff"
    )
    plot_monomer_cluster_fit(
        cluster_sum,
        monomer_sum,
        output_path=output_path,
        title=base_name,
        time_unit=time_unit,
    )


if __name__ == "__main__":
    # Example usage:
    directory = SEARCH_ROOT / "nn1120-3_pd_ceo2_000" / "deduped"
    for file in directory.glob("*_CarbonylPeakArea.csv"):
        plot_kinetic_fit(file)
