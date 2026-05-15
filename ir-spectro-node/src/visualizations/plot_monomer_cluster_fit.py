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
from scipy.integrate import solve_ivp
from scipy.interpolate import interp1d

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
    k: float,
    q_e: float,
    q_0: float,
) -> NDArray[np.float64]:
    """True pseudo-first-order uptake with fixed offset."""
    return q_0 + q_e * (1.0 - np.exp(-k * time_s))


def coupled_pfo_odes(
    t: float,
    y: list[float],
    k_a: float,
    q_e: float,
    k_s: float,
    k_p: float,
    q_inf: float,
) -> list[float]:
    """Coupled ODE system for PFO with secondary process."""
    q, p = y
    dq = k_a * (q_e - q) - k_s * p
    dp = k_p * (q - q_inf - p)
    return [dq, dp]


def pfo_with_secondary(
    time_s: NDArray[np.float64],
    k_a: float,
    q_e: float,
    k_s: float,
    k_p: float,
    q_inf: float,
    q_0: float,
) -> NDArray[np.float64]:
    """PFO with secondary process via coupled ODEs."""
    # Get unique sorted times
    _, unique_indices = np.unique(time_s, return_index=True)
    time_s_unique = np.sort(time_s[unique_indices])

    # Solve ODE at unique times
    sol = solve_ivp(
        coupled_pfo_odes,
        t_span=(time_s_unique[0], time_s_unique[-1]),
        y0=[q_0, 0.0],
        args=(k_a, q_e, k_s, k_p, q_inf),
        t_eval=time_s_unique,
        method="RK45",
        rtol=1e-8,
    )

    result_unique = sol.y[0]

    # Map back to original times using interpolation
    interp_func = interp1d(
        time_s_unique,
        result_unique,
        kind="linear",
        fill_value=cast(Any, "extrapolate"),
    )
    result = interp_func(time_s)

    return result


def get_primary_component(
    time_s: NDArray[np.float64],
    k_a: float,
    q_e: float,
    q_0: float,
) -> NDArray[np.float64]:
    """Primary adsorption component (uncoupled exponential uptake)."""
    return q_0 + q_e * (1.0 - np.exp(-k_a * time_s))


def pfo_with_secondary_states(
    time_s: NDArray[np.float64],
    k_a: float,
    q_e: float,
    k_s: float,
    k_p: float,
    q_inf: float,
    q_0: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return both q(t) and p(t) from the coupled ODE system."""
    _, unique_indices = np.unique(time_s, return_index=True)
    time_s_unique = np.sort(time_s[unique_indices])

    sol = solve_ivp(
        coupled_pfo_odes,
        t_span=(time_s_unique[0], time_s_unique[-1]),
        y0=[q_0, 0.0],
        args=(k_a, q_e, k_s, k_p, q_inf),
        t_eval=time_s_unique,
        method="RK45",
        rtol=1e-8,
    )

    q_unique = cast(NDArray[np.float64], sol.y[0])
    p_unique = cast(NDArray[np.float64], sol.y[1])

    interp_q = interp1d(
        time_s_unique,
        q_unique,
        kind="linear",
        fill_value=cast(Any, "extrapolate"),
    )
    interp_p = interp1d(
        time_s_unique,
        p_unique,
        kind="linear",
        fill_value=cast(Any, "extrapolate"),
    )

    q = cast(NDArray[np.float64], interp_q(time_s))
    p = cast(NDArray[np.float64], interp_p(time_s))
    return q, p


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

    def get_first(keys: list[str]) -> float | None:
        for key in keys:
            value = _coerce_float(final_row.get(key))
            if value is not None and np.isfinite(value):
                return value
        return None

    k = get_first(["pfo_k_s-1"])
    q_e = get_first(["pfo_q_e_au"])
    q_0 = get_first(["pfo_q0_au"])
    if k is None or q_e is None or q_0 is None:
        return {}
    return {"pfo_k_s-1": k, "pfo_q_e_au": q_e, "pfo_q0_au": q_0}


def _extract_prefixed_pfo_params(
    df: pd.DataFrame,
    prefix: str,
) -> dict[str, float]:
    if df.empty:
        return {}
    final_row = df.iloc[-1]

    def get_first(keys: list[str]) -> float | None:
        for key in keys:
            value = _coerce_float(final_row.get(f"{prefix}{key}"))
            if value is not None and np.isfinite(value):
                return value
        return None

    k = get_first(["pfo_k_s-1"])
    q_e = get_first(["pfo_q_e_au"])
    q_0 = get_first(["pfo_q0_au"])
    if k is None or q_e is None or q_0 is None:
        return {}
    return {"pfo_k_s-1": k, "pfo_q_e_au": q_e, "pfo_q0_au": q_0}


def _extract_secondary_pfo_params(df: pd.DataFrame) -> dict[str, float]:
    """Extract secondary PFO fit parameters from DataFrame."""
    if df.empty:
        return {}
    final_row = df.iloc[-1]

    def get_first(keys: list[str]) -> float | None:
        for key in keys:
            value = _coerce_float(final_row.get(key))
            if value is not None and np.isfinite(value):
                return value
        return None

    k_a = get_first(["pfo-sec_k_a_s-1"])
    q_e = get_first(["pfo-sec_q_e_au"])
    k_s = get_first(["pfo-sec_k_s_s-1"])
    k_p = get_first(["pfo-sec_k_p_s-1"])
    q_inf = get_first(["pfo-sec_q_inf_au"])
    q_0 = get_first(["pfo-sec_q0_au"])
    if k_a is None or q_e is None or k_s is None or k_p is None or q_inf is None or q_0 is None:
        return {}
    return {
        "sec_k_a_s-1": k_a,
        "sec_q_e_au": q_e,
        "sec_k_s_s-1": k_s,
        "sec_k_p_s-1": k_p,
        "sec_q_inf_au": q_inf,
        "sec_q0_au": q_0,
    }


def _extract_prefixed_secondary_params(
    df: pd.DataFrame,
    prefix: str,
) -> dict[str, float]:
    """Extract prefixed secondary PFO parameters (for pre/post fit)."""
    if df.empty:
        return {}
    final_row = df.iloc[-1]

    def get_first(keys: list[str]) -> float | None:
        for key in keys:
            value = _coerce_float(final_row.get(f"{prefix}{key}"))
            if value is not None and np.isfinite(value):
                return value
        return None

    k_a = get_first(["pfo-sec_k_a_s-1"])
    q_e = get_first(["pfo-sec_q_e_au"])
    k_s = get_first(["pfo-sec_k_s_s-1"])
    k_p = get_first(["pfo-sec_k_p_s-1"])
    q_inf = get_first(["pfo-sec_q_inf_au"])
    q_0 = get_first(["pfo-sec_q0_au"])
    if k_a is None or q_e is None or k_s is None or k_p is None or q_inf is None or q_0 is None:
        return {}
    return {
        "sec_k_a_s-1": k_a,
        "sec_q_e_au": q_e,
        "sec_k_s_s-1": k_s,
        "sec_k_p_s-1": k_p,
        "sec_q_inf_au": q_inf,
        "sec_q0_au": q_0,
    }


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
        params["pfo_k_s-1"],
        params["pfo_q_e_au"],
        params["pfo_q0_au"],
    )
    curve_time = time_grid / 3600 if time_unit == "h" else time_grid
    ax.plot(curve_time, curve, label=label, color=color)


def _plot_secondary_pfo_fit_curve(
    ax: Axes,
    time_s: NDArray[np.float64],
    params: dict[str, float],
    *,
    label: str,
    color: str,
    time_unit: Literal["s", "h"],
) -> None:
    """Plot secondary PFO (coupled ODE) fit curve."""
    time_grid = np.linspace(np.min(time_s), np.max(time_s), 200)
    curve = pfo_with_secondary(
        time_grid,
        params["sec_k_a_s-1"],
        params["sec_q_e_au"],
        params["sec_k_s_s-1"],
        params["sec_k_p_s-1"],
        params["sec_q_inf_au"],
        params["sec_q0_au"],
    )
    curve_time = time_grid / 3600 if time_unit == "h" else time_grid
    ax.plot(curve_time, curve, label=label, color=color)


def _plot_secondary_diagnostics(
    ax: Axes,
    secondary_axis: Axes | None,
    time_s: NDArray[np.float64],
    params: dict[str, float],
    *,
    time_unit: Literal["s", "h"],
    include_primary_component: bool,
    include_secondary_effect: bool,
    include_p_state: bool,
) -> None:
    """Plot optional secondary decomposition diagnostics.

    Components:
    - primary adsorption: q_primary(t)
    - secondary effect: q_composite(t) - q_primary(t)
    - secondary state: p(t)
    """
    q_fit, p_state = pfo_with_secondary_states(
        time_s,
        params["sec_k_a_s-1"],
        params["sec_q_e_au"],
        params["sec_k_s_s-1"],
        params["sec_k_p_s-1"],
        params["sec_q_inf_au"],
        params["sec_q0_au"],
    )
    q_primary = get_primary_component(
        time_s,
        params["sec_k_a_s-1"],
        params["sec_q_e_au"],
        params["sec_q0_au"],
    )
    q_secondary_effect = q_fit - q_primary
    time_values = time_s / 3600 if time_unit == "h" else time_s

    if include_primary_component:
        ax.plot(
            time_values,
            q_primary,
            linestyle="--",
            linewidth=1.6,
            color="orange",
            alpha=0.7,
            label="monomer primary adsorption",
        )

    if include_secondary_effect:
        ax.plot(
            time_values,
            q_secondary_effect,
            linestyle="-.",
            linewidth=1.6,
            color="gray",
            alpha=0.8,
            label="monomer secondary effect",
        )

    if include_p_state and secondary_axis is not None:
        secondary_axis.plot(
            time_values,
            p_state,
            linestyle=":",
            linewidth=1.6,
            color="green",
            alpha=0.8,
            label="monomer p(t)",
        )


def plot_monomer_cluster_fit(
    cluster_df: pd.DataFrame,
    monomer_df: pd.DataFrame,
    *,
    output_path: Path,
    title: str,
    time_unit: Literal["s", "h"] = "s",
    include_primary_component: bool = False,
    include_secondary_effect: bool = False,
    include_p_state: bool = False,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    diagnostics_axis: Axes | None = None
    if include_p_state:
        diagnostics_axis = ax.twinx()

    time_label = "Time (h)" if time_unit == "h" else "Time (s)"

    if not cluster_df.empty:
        cluster_time = cluster_df["Time (s)"].to_numpy(dtype=float)
        cluster_area = cluster_df["Cumulative_Peak_Area"].to_numpy(dtype=float)
        cluster_time_values = cluster_time / 3600 if time_unit == "h" else cluster_time
        ax.scatter(cluster_time_values, cluster_area, s=18, label="cluster_sum", alpha=0.7)

        # Cluster trajectories are always fit with PFO.
        cluster_params = _extract_pfo_fit_params(cluster_df)
        pre_params = _extract_prefixed_pfo_params(cluster_df, "pre_")
        post_params = _extract_prefixed_pfo_params(cluster_df, "post_")

        cluster_row = cluster_df.iloc[-1]
        cluster_classification = cluster_row.get("classification")
        growth_onset = _coerce_float(cluster_row.get("growth_onset_s"))
        if growth_onset is None:
            growth_onset = _coerce_float(cluster_row.get("breakpoint_s"))
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

        # Monomer trajectories are always fit with secondary PFO.
        monomer_params = _extract_secondary_pfo_params(monomer_df)

        if monomer_params:
            _plot_secondary_pfo_fit_curve(
                ax,
                monomer_time,
                monomer_params,
                label="monomer_fit",
                color="red",
                time_unit=time_unit,
            )
            if diagnostics_axis is not None:
                _plot_secondary_diagnostics(
                    ax,
                    diagnostics_axis,
                    monomer_time,
                    monomer_params,
                    time_unit=time_unit,
                    include_primary_component=include_primary_component,
                    include_secondary_effect=include_secondary_effect,
                    include_p_state=include_p_state,
                )
            elif include_primary_component or include_secondary_effect:
                _plot_secondary_diagnostics(
                    ax,
                    None,
                    monomer_time,
                    monomer_params,
                    time_unit=time_unit,
                    include_primary_component=include_primary_component,
                    include_secondary_effect=include_secondary_effect,
                    include_p_state=False,
                )

    ax.set_xlabel(time_label)
    ax.set_ylabel("Cumulative Peak Area")
    if diagnostics_axis is not None:
        diagnostics_axis.set_ylabel("Secondary diagnostics")
    ax.set_title(title)

    handles, labels = ax.get_legend_handles_labels()
    if diagnostics_axis is not None:
        d_handles, d_labels = diagnostics_axis.get_legend_handles_labels()
        handles.extend(d_handles)
        labels.extend(d_labels)
    ax.legend(handles, labels, fontsize=8, loc="best", ncol=2)

    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_kinetic_fit(
    file_path: str | Path,
    *,
    time_unit: Literal["s", "h"] = "s",
    include_primary_component: bool = False,
    include_secondary_effect: bool = False,
    include_p_state: bool = False,
) -> None:
    """Plot monomer/cluster fits from a kinetic-fit CSV.

    Args:
        file_path: Path to the CarbonylPeakArea CSV or related file.
        time_unit: Time unit for plotting ("s" or "h").
        include_primary_component: If True, overlay monomer q_primary(t).
        include_secondary_effect: If True, overlay monomer
            q_composite(t) - q_primary(t).
        include_p_state: If True, overlay monomer secondary state p(t).
        Cluster traces are rendered with PFO columns and monomer traces with
        secondary PFO columns.
    """
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
    if "cluster_sum" in SUM_PEAKS and cluster_sum.empty:
        LOGGER.warning("Insufficient cluster data in %s", csv_path)
        return

    monomer_sum = _extract_sum_trace(df_filtered, "monomer_sum")

    # Update filename to include model name
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
        include_primary_component=include_primary_component,
        include_secondary_effect=include_secondary_effect,
        include_p_state=include_p_state,
    )


if __name__ == "__main__":
    # Example usage:
    directory = SEARCH_ROOT / "nn1120-3_pd_ceo2_004"
    # directory = SEARCH_ROOT
    for file in directory.glob("*_CarbonylPeakArea.csv"):
        plot_kinetic_fit(
            file_path=file,
            time_unit="s",
            include_primary_component=True,
            include_secondary_effect=True,
            include_p_state=True,
        )
