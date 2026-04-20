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

MONOMER_SUM_NAME = "monomer_sum"
CLUSTER_SUM_NAME = "cluster_sum"
UNKNOWN_SUM_NAME = "unknown_sum"


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

    if monomer_sum.empty:
        LOGGER.warning("No monomer peak rows found in %s", csv_path)
    if cluster_sum.empty:
        LOGGER.warning("No cluster peak rows found in %s", csv_path)
    if include_unknown and unknown_sum.empty:
        LOGGER.warning("No unknown peak rows found in %s", csv_path)
    if monomer_sum.empty and cluster_sum.empty and unknown_sum.empty:
        return

    figure_path.parent.mkdir(parents=True, exist_ok=True)
    time_col = "Time (h)" if time_unit == "h" else "Time (s)"
    time_label = "Time (h)" if time_unit == "h" else "Time (s)"

    fig, ax = plt.subplots(figsize=(5, 4))

    if not monomer_sum.empty:
        ax.scatter(
            monomer_sum[time_col],
            monomer_sum["Cumulative_Peak_Area"],
            label=MONOMER_SUM_NAME,
            s=12,
        )
    if not cluster_sum.empty:
        ax.scatter(
            cluster_sum[time_col],
            cluster_sum["Cumulative_Peak_Area"],
            label=CLUSTER_SUM_NAME,
            s=12,
        )
    if not unknown_sum.empty:
        ax.scatter(
            unknown_sum[time_col],
            unknown_sum["Cumulative_Peak_Area"],
            label=UNKNOWN_SUM_NAME,
            s=12,
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
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    process_all_area_vs_time(
        "nn1120-3_pd_ceo2_004", include_unknown=False, time_unit="s"
    )
