"""Plot cumulative peak-area sums (and constituent peaks) versus time.

Peak groups come from ``config/analysis.yaml``: the ``ir_fitting.fit`` block
(the refit's 24 peaks; default) or live ``voigt_fit``, via ``groups``. The sums
are the ``monomer_sum`` / ``cluster_sum`` rows baked into the CSV when present
(the definition kinetics and classification ran on); they are re-summed from the
group's peaks only when a CSV has no such rows.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Literal

import matplotlib.pyplot as plt
import pandas as pd

path = Path(__file__).parent.parent.parent
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.core import config
from src.utils.kinetics.utils import _KineticUtilities

LOGGER = logging.getLogger(__name__)

GROUPS = ("monomer", "cluster", "unknown")
SUM_ROWS = {"monomer": "monomer_sum", "cluster": "cluster_sum"}
MARKERS = ["o", "s", "^", "D", "v", "<", ">", "p", "*", "h"]


def _group_peaks(
    groups: Literal["ir_fitting", "voigt_fit"],
) -> dict[str, list[str]]:
    """``Peak_Name`` lists per group from the chosen yaml block."""
    fit_settings = (
        config.get_analysis_setting("voigt_fit") if groups == "voigt_fit" else None
    )
    return {
        group: _KineticUtilities.group_peak_names(group, fit_settings)
        for group in GROUPS
    }


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


def _sum_series(df: pd.DataFrame, group: str, peak_names: list[str]) -> pd.DataFrame:
    """The baked sum rows for ``group`` if the CSV has them, else a re-sum."""
    sum_name = SUM_ROWS.get(group)
    if sum_name is not None:
        baked = df[df["Peak_Name"] == sum_name]
        if not baked.empty:
            return baked
    return _group_peak_sum(df, peak_names)


def plot_area_vs_time(
    csv_path: Path,
    figure_path: Path,
    include_unknown: bool = False,
    time_unit: Literal["s", "h"] = "s",
    constituents: dict | None = None,
    groups: Literal["ir_fitting", "voigt_fit"] = "ir_fitting",
) -> None:
    """Plot one ``*_CarbonylPeakArea.csv``.

    Args:
        constituents: ``{group: {"peaks": ..., "sum": bool}}``. ``"peaks"`` is
            ``"all"`` (every peak of the group), a list of wavenumbers, or
            ``None``/``[]`` (no constituent peaks). Default: monomer and cluster,
            all peaks and the sum (plus unknown with ``include_unknown``).
        groups: Which yaml block defines the groups: ``"ir_fitting"`` for the
            refit (``_reprocess``) CSVs, ``"voigt_fit"`` for live CSVs.
    """
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

    if constituents is None:
        constituents = {
            "monomer": {"peaks": "all", "sum": True},
            "cluster": {"peaks": "all", "sum": True},
        }
        if include_unknown:
            constituents["unknown"] = {"peaks": "all", "sum": True}

    peak_map = _group_peaks(groups)

    figure_path.parent.mkdir(parents=True, exist_ok=True)
    time_col = "Time (h)" if time_unit == "h" else "Time (s)"

    fig, ax = plt.subplots(figsize=(5, 4))

    for category, opts in constituents.items():
        if opts.get("sum", False):
            sum_data = _sum_series(df, category, peak_map.get(category, []))
            if sum_data.empty:
                LOGGER.warning("No %s peak rows found in %s", category, csv_path)
            else:
                ax.scatter(
                    sum_data[time_col],
                    sum_data["Cumulative_Peak_Area"],
                    label=f"{category}_sum",
                    s=12,
                )

        peak_config = opts.get("peaks")
        if not peak_config:
            continue
        if peak_config == "all":
            peaks = peak_map.get(category, [])
        else:
            peaks = [f"Peak_{p}" for p in peak_config]
        individual = df[df["Peak_Name"].isin(peaks)]
        if individual.empty:
            LOGGER.warning(
                "No individual peak rows found for %s in %s", category, csv_path
            )
            continue
        for i, peak in enumerate(peaks):
            peak_data: pd.DataFrame = individual[individual["Peak_Name"] == peak]  # type: ignore[assignment]
            if peak_data.empty:
                continue
            ax.scatter(
                peak_data[time_col],
                peak_data["Cumulative_Peak_Area"],
                label=peak,
                marker=MARKERS[i % len(MARKERS)],
                s=12,
                alpha=0.7,
            )

    ax.set_xlabel(time_col)
    ax.set_ylabel("Cumulative Peak Area")
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1), fontsize="small", ncol=2)

    plt.savefig(figure_path, dpi=600, bbox_inches="tight")
    plt.close(fig)


def process_all_area_vs_time(
    folder: str,
    subfolder: str | None = None,
    include_unknown: bool = False,
    time_unit: Literal["s", "h"] = "s",
    constituents: dict | None = None,
    groups: Literal["ir_fitting", "voigt_fit"] = "ir_fitting",
) -> None:
    """Plot every ``*_CarbonylPeakArea.csv`` in exactly one folder.

    Reads ``<data.peak_fit>/<folder>/<subfolder>/`` non-recursively (e.g.
    ``subfolder="_reprocess/_test"``), so live, ``_reprocess`` and ``_test``
    CSVs sharing a name are never mixed. Figures go to
    ``<data.figures>/<folder>/plot_area_vs_time/<subfolder>/``.
    """
    search_dir = Path(config.get_path("data.peak_fit", folder))
    figure_dir = Path(
        config.get_path(
            "data.figures",
            folder,
            config.get_path("data.plot_area_vs_time"),
        )
    )
    if subfolder:
        search_dir = search_dir / subfolder
        figure_dir = figure_dir / subfolder
    if not search_dir.exists():
        LOGGER.warning("Missing folder: %s", search_dir)
        return

    for csv_path in sorted(search_dir.glob("*_CarbonylPeakArea.csv")):
        plot_area_vs_time(
            csv_path,
            figure_dir / f"{csv_path.stem}_area_vs_time.tiff",
            include_unknown=include_unknown,
            time_unit=time_unit,
            constituents=constituents,
            groups=groups,
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    process_all_area_vs_time(
        folder="nn1120-4_pd_ceo2_000",
        subfolder="_reprocess",
        include_unknown=False,
        time_unit="s",
        constituents={
            "monomer": {"peaks": None, "sum": True},
            "cluster": {"peaks": [1928, 1988, 2030, 2062, 2073], "sum": True},
        },
        groups="ir_fitting",
    )
