"""Build ``*_CarbonylPeakArea.csv`` from a params CSV and the per-spectrum timeline.

The refit (``src/utils/ir_fitting``) writes only ``*_CarbonylPeakFitParams.csv``.
Kinetics reads ``*_CarbonylPeakArea.csv``. This module builds the latter.

- **Time comes from the timeline** (``timeline.build_timeline``), not from which
  params rows exist. Every spectrum advances cumulative time. A spectrum with no
  params row (a failed fit) gets a row with the correct ``Time (s)`` and a NaN
  area. Its area change is unknown, so later cumulative areas in that delta group
  lack it. That is left as is, with no interpolation, and logged.
- **Cumulation is live's own**: ``src/analysis/output.py::compute_cumulative_peak_area_df``
  (per ``(Peak_Name, Delta_Group)``, seeded from the first two delta1 rows).
- **Sums are baked in** from the ``ir_fitting.fit`` groups
  (``_KineticUtilities.group_peak_names``). Live's own sums are dropped, because
  its cluster_sum always reads ``voigt_fit``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from src.analysis.output import compute_cumulative_peak_area_df
from src.core import config
from src.utils.kinetics.timeline import build_timeline
from src.utils.kinetics.utils import _KineticUtilities

LOGGER = logging.getLogger(__name__)

PARAMS_SUFFIX = config.get_setting("filenames.carbonyl_fit.params_suffix")
AREA_SUFFIX = config.get_setting("filenames.carbonyl_fit.area_suffix")
SUM_NAMES = ("monomer_sum", "cluster_sum")
UTILS = _KineticUtilities()


@dataclass
class AreaBuildReport:
    """What the builder had to work around for one measurement."""

    measurement: str
    n_spectra: int = 0
    missing: dict[str, list[str]] = field(default_factory=dict)
    """Delta group -> spectra with no fitted area (no params row, or a NaN
    ``Peak_Area``): time kept, area NaN."""
    unmatched: list[str] = field(default_factory=list)
    """Params ``File`` values not in the timeline (dropped)."""
    output_path: Path | None = None

    @property
    def n_missing(self) -> int:
        return sum(len(files) for files in self.missing.values())


def _peak_fit_dir(folder: str) -> Path:
    return Path(config.get_path("data.peak_fit", folder))


def build_peak_area_df(
    params: pd.DataFrame,
    timeline: pd.DataFrame,
    *,
    monomer_peaks: list[str] | None = None,
    cluster_peaks: list[str] | None = None,
    measurement: str = "",
) -> tuple[pd.DataFrame, AreaBuildReport]:
    """Cumulative peak areas for one measurement, on the full timeline.

    Args:
        params: One measurement's ``*_CarbonylPeakFitParams.csv`` rows.
        timeline: ``timeline.build_timeline`` output for the same measurement.
        monomer_peaks / cluster_peaks: ``Peak_Name`` lists for the sums.
            ``None`` means the ``ir_fitting.fit`` group.
        measurement: Name used in the report and log lines.

    Returns:
        The area frame (live column layout) and a report of missing spectra.
    """
    report = AreaBuildReport(measurement=measurement, n_spectra=len(timeline))
    params = params.copy()
    params["File"] = params["File"].astype(str)
    in_timeline = params["File"].isin(timeline["File"])
    report.unmatched = sorted(params.loc[~in_timeline, "File"].unique())
    params = params[in_timeline]

    peaks = sorted(params["Peak_Name"].unique())
    # A row whose Peak_Area is NaN (a failed live fit) is as unfitted as no row.
    fitted = set(params.loc[params["Peak_Area"].notna(), "File"])
    for delta_group, files in timeline.groupby("Delta_Group", sort=False)["File"]:
        gaps = [f for f in files if f not in fitted]
        if gaps:
            report.missing[str(delta_group)] = gaps

    # Full (spectrum x peak) grid, with time from the timeline, never from the params.
    grid = timeline.merge(pd.DataFrame({"Peak_Name": peaks}), how="cross")
    grid["_order"] = np.arange(len(grid))
    fit_columns = [
        c for c in params.columns if c not in {"Delta_Group", "Time_Delta (s)"}
    ]
    full = grid.merge(params[fit_columns], on=["File", "Peak_Name"], how="left")
    full = full.sort_values(["Peak_Name", "_order"]).drop(columns="_order")
    has_fit = full["Peak_Area"].notna()

    areas = compute_cumulative_peak_area_df(full, sum_areas_peaks=[])
    if areas.empty or "Peak_Name" not in areas.columns:
        # Only delta1 spectra (which seed, never emit): no area rows exist.
        return pd.DataFrame(), report
    areas = areas[~areas["Peak_Name"].isin(SUM_NAMES)].reset_index(drop=True)

    # compute_cumulative_peak_area_df emits one row per non-delta1 input row, in
    # the same (Peak_Name, Delta_Group) group order; mark rows with no fit as NaN.
    no_fit = full.loc[~has_fit & (full["Delta_Group"] != "delta1"), ["File", "Peak_Name"]]
    if not no_fit.empty:
        key = pd.MultiIndex.from_frame(areas[["File", "Peak_Name"]])
        mask = key.isin(pd.MultiIndex.from_frame(no_fit))
        areas.loc[mask, ["Cumulative_Peak_Area", "Peak_Center"]] = np.nan

    areas = UTILS.append_sum_rows(
        areas,
        monomer_sum_peaks=monomer_peaks
        if monomer_peaks is not None
        else UTILS.group_peak_names("monomer"),
        cluster_sum_peaks=cluster_peaks
        if cluster_peaks is not None
        else UTILS.group_peak_names("cluster"),
    )
    return areas, report


def build_measurement_areas(
    folder: str,
    measurement: str,
    *,
    input_subfolder: str | None = "_reprocess",
    monomer_peaks: list[str] | None = None,
    cluster_peaks: list[str] | None = None,
    write: bool = True,
) -> tuple[pd.DataFrame, AreaBuildReport]:
    """Build one measurement's area CSV next to its params CSV.

    ``input_subfolder=None`` reads the live params in the dataset folder itself;
    ``write`` must then be False, so source data is never overwritten.
    """
    params_dir = _peak_fit_dir(folder)
    if input_subfolder:
        params_dir = params_dir / input_subfolder
    elif write:
        raise ValueError("Refusing to write area CSVs into the source dataset folder.")

    params = pd.read_csv(params_dir / f"{measurement}{PARAMS_SUFFIX}")
    timeline = build_timeline(folder, measurement)
    areas, report = build_peak_area_df(
        params,
        timeline,
        monomer_peaks=monomer_peaks,
        cluster_peaks=cluster_peaks,
        measurement=measurement,
    )
    for delta_group, files in report.missing.items():
        LOGGER.warning(
            "%s %s: %d spectra without a fit (time kept, area NaN, later "
            "cumulative area lacks their step): %s",
            measurement,
            delta_group,
            len(files),
            " ".join(files),
        )
    if report.unmatched:
        LOGGER.warning(
            "%s: %d params File values not in the timeline, dropped: %s",
            measurement,
            len(report.unmatched),
            " ".join(report.unmatched),
        )
    if areas.empty:
        LOGGER.warning(
            "%s: no area rows (only delta1 spectra); nothing written", measurement
        )
        return areas, report
    if write:
        report.output_path = params_dir / f"{measurement}{AREA_SUFFIX}"
        areas.to_csv(report.output_path, index=False)
    return areas, report


def build_folder_areas(
    folder: str,
    *,
    input_subfolder: str = "_reprocess",
    measurements: list[str] | None = None,
) -> list[AreaBuildReport]:
    """Build area CSVs for every params CSV in ``<folder>/<input_subfolder>``."""
    params_dir = _peak_fit_dir(folder) / input_subfolder
    names = sorted(
        p.name.removesuffix(PARAMS_SUFFIX) for p in params_dir.glob(f"*{PARAMS_SUFFIX}")
    )
    if measurements is not None:
        names = [n for n in names if n in set(measurements)]
    reports = []
    for name in names:
        try:
            _, report = build_measurement_areas(
                folder, name, input_subfolder=input_subfolder
            )
        except Exception:
            LOGGER.exception("%s: area build failed", name)
            continue
        reports.append(report)
    return reports
