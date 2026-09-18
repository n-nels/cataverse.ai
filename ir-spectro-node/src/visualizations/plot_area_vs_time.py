"""Plot cumulative peak-area sums versus time."""

from __future__ import annotations

from pathlib import Path
import logging
import sys
from typing import Literal

import matplotlib.pyplot as plt
import pandas as pd

path = Path(__file__).parent.parent.parent
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.analysis.spectral_fitting import get_shifted_monomer_peaks
from src.core import config


LOGGER = logging.getLogger(__name__)


def _get_peak_names(base_list_key: str, isotope: str | None) -> list[str]:
    config_settings = config.get_analysis_setting("voigt_fit")
    base_list = config_settings.get(base_list_key, [])
    if not base_list:
        return []
    isotope_value = isotope or config_settings.get("isotope_default", "13CO")
    base_isotope = config_settings.get("monomer_peaks_base_isotope", isotope_value)
    shifts = config_settings.get("isotope_shift_cm1", {})
    shift_value = shifts.get(isotope_value, 0) - shifts.get(base_isotope, 0)
    return [f"Peak_{int(peak + shift_value)}" for peak in base_list]


def _get_monomer_peak_names(isotope: str | None) -> list[str]:
    config_settings = config.get_analysis_setting("voigt_fit")
    isotope_value = isotope or config_settings.get("isotope_default", "13CO")
    merged_settings = dict(config_settings)
    merged_settings["isotope_default"] = isotope_value
    return [f"Peak_{int(peak)}" for peak in get_shifted_monomer_peaks(merged_settings)]


def _group_peak_sum(df: pd.DataFrame, peak_names: list[str]) -> pd.DataFrame:
    if not peak_names:
        return pd.DataFrame()
    peak_rows = df[df["Peak_Name"].isin(peak_names)]
    if peak_rows.empty:
        return pd.DataFrame()
    group_cols = ["Time (s)"]
    if "Delta_Group" in peak_rows.columns:
        group_cols.append("Delta_Group")
    grouped = peak_rows.groupby(group_cols)["Cumulative_Peak_Area"].sum().reset_index()
    grouped["Time (h)"] = grouped["Time (s)"] / 3600
    return grouped


def plot_area_vs_time(
    csv_path: Path,
    figure_path: Path,
    isotope: str | None = None,
    include_unknown: bool = False,
    time_unit: Literal["s", "h"] = "s",
    constituents: dict | None = None,
) -> None:
    if not csv_path.exists():
        LOGGER.warning("Missing CSV: %s", csv_path)
        return

    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        LOGGER.error("Error reading CSV %s: %s", csv_path, exc)
        return
    if df.empty:
        LOGGER.warning("Empty CSV: %s", csv_path)
        return

    df = df.copy()
    df["Time (s)"] = pd.to_numeric(df["Time (s)"], errors="coerce")
    df["Time (h)"] = df["Time (s)"] / 3600
    df["Cumulative_Peak_Area"] = pd.to_numeric(
        df["Cumulative_Peak_Area"], errors="coerce"
    )
    df = df.dropna(subset=["Time (s)", "Cumulative_Peak_Area"])

    monomer_peaks = _get_monomer_peak_names(isotope)
    cluster_peaks = _get_peak_names("cluster_peaks_base", isotope)
    unknown_peaks = _get_peak_names("unknown_peaks_base", isotope)

    monomer_sum = _group_peak_sum(df, monomer_peaks)
    cluster_sum = _group_peak_sum(df, cluster_peaks)
    unknown_sum = (
        _group_peak_sum(df, unknown_peaks) if include_unknown else pd.DataFrame()
    )

    if constituents is None:
        constituents = {
            "monomer": {"peaks": "all", "sum": True},
            "cluster": {"peaks": "all", "sum": True},
        }
        if include_unknown:
            constituents["unknown"] = {"peaks": "all", "sum": True}

    for category in constituents:
        if category == "monomer" and monomer_sum.empty:
            LOGGER.warning("No monomer peak rows found in %s", csv_path)
        elif category == "cluster" and cluster_sum.empty:
            LOGGER.warning("No cluster peak rows found in %s", csv_path)
        elif category == "unknown" and unknown_sum.empty:
            LOGGER.warning("No unknown peak rows found in %s", csv_path)

    figure_path.parent.mkdir(parents=True, exist_ok=True)
    time_col = "Time (h)" if time_unit == "h" else "Time (s)"
    time_label = "Time (h)" if time_unit == "h" else "Time (s)"

    fig, ax = plt.subplots(figsize=(5, 4))

    sum_map = {
        "monomer": monomer_sum,
        "cluster": cluster_sum,
        "unknown": unknown_sum,
    }
    peak_map = {
        "monomer": monomer_peaks,
        "cluster": cluster_peaks,
        "unknown": unknown_peaks,
    }
    for category, opts in constituents.items():
        if opts.get("sum", False):
            sum_data = sum_map.get(category)
            if sum_data is not None and not sum_data.empty:
                label = f"{category}_sum"
                ax.scatter(
                    sum_data[time_col],
                    sum_data["Cumulative_Peak_Area"],
                    label=label,
                    s=12,
                )

        peak_config = opts.get("peaks")
        if not peak_config:
            continue
        if peak_config == "all":
            peaks = peak_map.get(category, [])
        else:
            peaks = [f"Peak_{p}" for p in peak_config]
        if not peaks:
            continue
        individual = df[df["Peak_Name"].isin(peaks)]
        if individual.empty:
            LOGGER.warning(
                "No individual peak rows found for %s in %s", category, csv_path
            )
            continue
        markers = ["o", "s", "^", "D", "v", "<", ">", "p", "*", "h"]
        for i, peak in enumerate(peaks):
            peak_data: pd.DataFrame = individual[individual["Peak_Name"] == peak]  # type: ignore[assignment]
            if peak_data.empty:
                continue
            marker = markers[i % len(markers)]
            ax.scatter(
                peak_data[time_col],
                peak_data["Cumulative_Peak_Area"],
                label=peak,
                marker=marker,
                s=12,
                alpha=0.7,
            )

    ax.set_xlabel(time_label)
    ax.set_ylabel("Cumulative Peak Area")
    ax.legend(loc="best")
    # ax.set_title(csv_path.stem)

    plt.savefig(figure_path, dpi=600, bbox_inches="tight")
    plt.close(fig)


def process_all_area_vs_time(
    folder: str,
    isotope: str | None = None,
    include_unknown: bool = False,
    time_unit: Literal["s", "h"] = "s",
    constituents: dict | None = None,
) -> None:
    search_root = Path(config.get_path("data.peak_fit", folder))
    if not search_root.exists():
        LOGGER.warning("Missing folder: %s", search_root)
        return

    figure_dir = Path(
        config.get_path(
            "data.figures",
            folder,
            config.get_path("data.plot_area_vs_time"),
        )
    )
    for csv_path in sorted(search_root.rglob("*_CarbonylPeakArea.csv")):
        if "arxiv" in csv_path.parts:
            continue
        figure_name = f"{csv_path.stem}_area_vs_time.tiff"
        plot_area_vs_time(
            csv_path,
            figure_dir / figure_name,
            isotope=isotope,
            include_unknown=include_unknown,
            time_unit=time_unit,
            constituents=constituents,
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    process_all_area_vs_time(
        folder="nn1120-4_pd_ceo2_000",
        isotope=None,
        include_unknown=False,
        time_unit="s",
        constituents={
            "monomer": {"peaks": "all", "sum": True},
            "cluster": {"peaks": None, "sum": True},
                      },
    )
