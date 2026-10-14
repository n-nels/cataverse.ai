"""Dataframe and output utilities shared by kinetics models and classification."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from src.utils.ir_fitting import config as ir_config

LOGGER = logging.getLogger(__name__)

REPROCESS_FOLDER = "_reprocess"
"""The reprocessed dataset: refit params plus every file derived from them."""


def select_measurements(
    names: Sequence[str], patterns: Sequence[str] | None, where: Path | str
) -> list[str]:
    """``names`` matching any of ``patterns`` (exact or glob, e.g. ``"*-043"``).

    Matches as ``ir_fitting.api.fit_folder`` does. ``None`` keeps every name.
    Raises ``ValueError`` when patterns are given and nothing matches.
    """
    if patterns is None:
        return list(names)
    if isinstance(patterns, str):
        raise TypeError("measurements must be a list of patterns, not a string")
    selected = [
        name
        for name in names
        if any(name == pattern or fnmatchcase(name, pattern) for pattern in patterns)
    ]
    if not selected:
        raise ValueError(f"no measurements in {where} matched {list(patterns)}")
    return selected


class _KineticUtilities:
    """Dataframe and output utilities."""

    @staticmethod
    def calculate_metrics(
        intensity: NDArray[np.float64],
        y_pred: NDArray[np.float64],
    ) -> tuple[float, float, float]:
        residuals = intensity - y_pred
        ss_tot = np.sum((intensity - np.mean(intensity)) ** 2)
        rss = np.sum(residuals**2)
        r_squared = 1 - (rss / ss_tot) if ss_tot > 0 else np.nan
        rmse = np.sqrt(np.mean(residuals**2))
        return r_squared, rmse, rss

    @staticmethod
    def resolve_output_dir(source_dir: Path, output_folder_name: str) -> Path:
        """Resolve the output directory for a source dataset folder.

        Offline reprocessing must never write next to live data: the live
        ``*_CarbonylPeakArea.csv`` is read back as fit history, so overwriting
        it in place corrupts the dataset. Output lands in a subfolder of the
        source folder, normally ``_reprocess``. An input that is already in a
        folder of that name is written in place there: the area, kinetic
        params and kinetic features CSVs in ``_reprocess`` are derived files.

        Rejects any folder name that would resolve back to the source folder
        or escape it -- ``""`` and ``"."`` both collapse to the parent under
        ``Path.__truediv__``, and an absolute right-hand side discards the
        left side entirely.
        """
        if not isinstance(output_folder_name, str) or not output_folder_name.strip():
            raise ValueError(
                "output_folder_name must be a non-empty subfolder name "
                "(e.g. '_reprocess'); got "
                f"{output_folder_name!r}. Writing into the source folder "
                "would overwrite the input CarbonylPeakArea CSV."
            )
        name = output_folder_name.strip()
        if name in {".", ".."} or "/" in name or "\\" in name:
            raise ValueError(
                f"output_folder_name must be a single subfolder name; got {name!r}."
            )
        if Path(name).is_absolute() or Path(name).drive or Path(name).anchor:
            raise ValueError(
                f"output_folder_name must be relative, not an absolute path; got {name!r}."
            )

        # Input already inside the output subfolder: write in place there.
        output_dir = source_dir if source_dir.name == name else source_dir / name
        if name == REPROCESS_FOLDER and source_dir.name != name:
            # e.g. a live area CSV given with --path: its derived files would
            # replace the reprocessed ones of the same measurement.
            raise ValueError(
                f"{source_dir} is not a {REPROCESS_FOLDER} folder; writing to "
                f"{output_dir} would replace reprocessed files. Pass another "
                "output folder name (e.g. '_test')."
            )
        if output_dir.resolve() == source_dir.resolve() and source_dir.name != name:
            raise ValueError(
                f"output_folder_name {name!r} resolves to the source folder; refusing "
                "to overwrite source data."
            )
        return output_dir

    @staticmethod
    def prefix_fit_results(fit_result: dict[str, Any], prefix: str) -> dict[str, Any]:
        return {f"{prefix}{k}": v for k, v in fit_result.items() if k not in {"rmse"}}

    @staticmethod
    def group_peak_names(group: str, fit_settings: dict | None = None) -> list[str]:
        """``Peak_Name`` values of one peak group (``"monomer"``/``"cluster"``/``"unknown"``).

        Groups come from the ``ir_fitting.fit`` block of ``config/analysis.yaml``
        (the refit's peak set), not from live ``voigt_fit``. Pass
        ``fit_settings=config.get_analysis_setting("voigt_fit")`` to get the
        live groups instead (same keys), e.g. for a parity check.
        """
        return [
            ir_config.peak_name(peak)
            for peak in ir_config.get_group_peaks(group, fit_settings)
        ]

    def build_group_sum(self, df: pd.DataFrame, peak_names: list[str]) -> pd.DataFrame:
        """Sum ``Cumulative_Peak_Area`` over ``peak_names`` at each time point.

        One row per ``(Time (s), Delta_Group, File)``, as live
        ``src/analysis/output.py`` builds its sums. Rows with a NaN area (a
        spectrum with no fit) contribute nothing, so that time gets no sum row.
        """
        df = df.copy()
        df["Time (s)"] = pd.to_numeric(df["Time (s)"], errors="coerce")
        df["Cumulative_Peak_Area"] = pd.to_numeric(
            df["Cumulative_Peak_Area"], errors="coerce"
        )
        df = df.dropna(subset=["Time (s)", "Cumulative_Peak_Area"])
        group_rows = df[df["Peak_Name"].isin(peak_names)]
        if group_rows.empty:
            return pd.DataFrame()

        group_cols = ["Time (s)"]
        if "Delta_Group" in group_rows.columns:
            group_cols.append("Delta_Group")
        if "File" in group_rows.columns:
            group_cols.append("File")
        return group_rows.groupby(group_cols)["Cumulative_Peak_Area"].sum().reset_index()

    def append_sum_rows(
        self,
        df: pd.DataFrame,
        monomer_sum_peaks: list[str] | None = None,
        cluster_sum_peaks: list[str] | None = None,
    ) -> pd.DataFrame:
        """Append monomer_sum/cluster_sum rows if not already present.

        ``monomer_sum_peaks``/``cluster_sum_peaks`` override which Peak_Name
        rows get summed into that group. When given, any existing row of
        that sum type is dropped first and rebuilt from the atomic peak
        rows -- the source CSV already has monomer_sum/cluster_sum baked in
        by the live pipeline, so without dropping it first an override would
        have nothing to do.
        """
        if monomer_sum_peaks is not None and "Peak_Name" in df.columns:
            df = df[df["Peak_Name"] != "monomer_sum"]
        if cluster_sum_peaks is not None and "Peak_Name" in df.columns:
            df = df[df["Peak_Name"] != "cluster_sum"]

        sum_peaks = {
            "monomer_sum": monomer_sum_peaks
            if monomer_sum_peaks is not None
            else self.group_peak_names("monomer"),
            "cluster_sum": cluster_sum_peaks
            if cluster_sum_peaks is not None
            else self.group_peak_names("cluster"),
        }
        template_columns = list(df.columns)
        sum_frames: list[pd.DataFrame] = []

        for sum_name, peak_names in sum_peaks.items():
            if "Peak_Name" in df.columns and (df["Peak_Name"] == sum_name).any():
                continue
            sum_df = self.build_group_sum(df, peak_names)
            if sum_df.empty:
                continue
            sum_df = sum_df.copy()
            sum_df["Peak_Name"] = sum_name
            for column in template_columns:
                if column not in sum_df:
                    sum_df[column] = np.nan
            sum_df = sum_df[template_columns]
            sum_frames.append(cast(pd.DataFrame, sum_df))

        if not sum_frames:
            return df
        frames: list[pd.DataFrame] = [df]
        frames.extend(sum_frames)
        return pd.concat(frames, ignore_index=True)

    def prepare_peak_area_df(
        self,
        df: pd.DataFrame,
        monomer_sum_peaks: list[str] | None = None,
        cluster_sum_peaks: list[str] | None = None,
    ) -> pd.DataFrame:
        df = df.copy()
        df["Time (s)"] = pd.to_numeric(df["Time (s)"], errors="coerce")
        df["Cumulative_Peak_Area"] = pd.to_numeric(
            df["Cumulative_Peak_Area"], errors="coerce"
        )
        df = df.dropna(subset=["Time (s)", "Cumulative_Peak_Area"])
        return self.append_sum_rows(
            df,
            monomer_sum_peaks=monomer_sum_peaks,
            cluster_sum_peaks=cluster_sum_peaks,
        )
