"""Dataframe and output utilities shared by kinetics models and classification."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray

path = Path(__file__).resolve().parents[3]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.analysis.spectral_fitting import get_shifted_monomer_peaks
from src.core import config

LOGGER = logging.getLogger(__name__)


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

        Offline reprocessing must never write next to its own input: the
        source ``*_CarbonylPeakArea.csv`` is read back as fit history, so
        overwriting it in place corrupts the dataset. Output always lands in
        a subfolder of the source folder (normally ``_test``).

        Rejects any folder name that would resolve back to the source folder
        or escape it -- ``""`` and ``"."`` both collapse to the parent under
        ``Path.__truediv__``, and an absolute right-hand side discards the
        left side entirely.
        """
        if not isinstance(output_folder_name, str) or not output_folder_name.strip():
            raise ValueError(
                "output_folder_name must be a non-empty subfolder name "
                "(e.g. '_test'); got "
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
    def get_peak_names(base_list_key: str, isotope: str | None) -> list[str]:
        config_settings = config.get_analysis_setting("voigt_fit")
        base_list = config_settings.get(base_list_key, [])
        if not base_list:
            return []
        isotope_value = isotope or config_settings.get("isotope_default", "13CO")
        base_isotope = config_settings.get("monomer_peaks_base_isotope", isotope_value)
        shifts = config_settings.get("isotope_shift_cm1", {})
        shift_value = shifts.get(isotope_value, 0) - shifts.get(base_isotope, 0)
        return [f"Peak_{int(peak + shift_value)}" for peak in base_list]

    @staticmethod
    def get_monomer_peak_names(isotope: str | None) -> list[str]:
        config_settings = config.get_analysis_setting("voigt_fit")
        isotope_value = isotope or config_settings.get("isotope_default", "13CO")
        merged_settings = dict(config_settings)
        merged_settings["isotope_default"] = isotope_value
        return [
            f"Peak_{int(peak)}" for peak in get_shifted_monomer_peaks(merged_settings)
        ]

    def build_cluster_sum(
        self,
        df: pd.DataFrame,
        isotope: str | None = None,
        peak_names_override: list[str] | None = None,
    ) -> pd.DataFrame:
        df = df.copy()
        df["Time (s)"] = pd.to_numeric(df["Time (s)"], errors="coerce")
        df["Cumulative_Peak_Area"] = pd.to_numeric(
            df["Cumulative_Peak_Area"], errors="coerce"
        )
        df = df.dropna(subset=["Time (s)", "Cumulative_Peak_Area"])

        peak_names = (
            peak_names_override
            if peak_names_override is not None
            else self.get_peak_names("cluster_peaks_base", isotope)
        )
        cluster_rows = df[df["Peak_Name"].isin(peak_names)]
        if cluster_rows.empty:
            return pd.DataFrame()

        group_cols = ["Time (s)"]
        if "Delta_Group" in cluster_rows.columns:
            group_cols.append("Delta_Group")
        if "File" in cluster_rows.columns:
            group_cols.append("File")
        return (
            cluster_rows.groupby(group_cols)["Cumulative_Peak_Area"].sum().reset_index()
        )

    def build_monomer_sum(
        self,
        df: pd.DataFrame,
        isotope: str | None = None,
        peak_names_override: list[str] | None = None,
    ) -> pd.DataFrame:
        df = df.copy()
        df["Time (s)"] = pd.to_numeric(df["Time (s)"], errors="coerce")
        df["Cumulative_Peak_Area"] = pd.to_numeric(
            df["Cumulative_Peak_Area"], errors="coerce"
        )
        df = df.dropna(subset=["Time (s)", "Cumulative_Peak_Area"])

        peak_names = (
            peak_names_override
            if peak_names_override is not None
            else self.get_monomer_peak_names(isotope)
        )
        monomer_rows = df[df["Peak_Name"].isin(peak_names)]
        if monomer_rows.empty:
            return pd.DataFrame()

        group_cols = ["Time (s)"]
        if "Delta_Group" in monomer_rows.columns:
            group_cols.append("Delta_Group")
        if "File" in monomer_rows.columns:
            group_cols.append("File")
        return (
            monomer_rows.groupby(group_cols)["Cumulative_Peak_Area"].sum().reset_index()
        )

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

        sum_builders = {
            "monomer_sum": (self.build_monomer_sum, monomer_sum_peaks),
            "cluster_sum": (self.build_cluster_sum, cluster_sum_peaks),
        }
        template_columns = list(df.columns)
        sum_frames: list[pd.DataFrame] = []

        for sum_name, (builder, override) in sum_builders.items():
            if "Peak_Name" in df.columns and (df["Peak_Name"] == sum_name).any():
                continue
            sum_df = cast(pd.DataFrame, builder(df, peak_names_override=override))
            if not isinstance(sum_df, pd.DataFrame):
                LOGGER.warning("Unexpected sum output for %s", sum_name)
                continue
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

    @staticmethod
    def write_fit_params_to_legacy(
        legacy_path: str | Path,
        fit_params: pd.DataFrame,
        *,
        join_columns: tuple[str, ...] = ("Peak_Name", "Time (s)"),
        output_folder_name: str = "_test",
        legacy_df: pd.DataFrame | None = None,
    ) -> Path:
        legacy_path = Path(legacy_path)
        df_legacy = pd.read_csv(legacy_path) if legacy_df is None else legacy_df.copy()

        # Remove legacy PFO columns that should not persist in new outputs.
        legacy_pfo_columns = [
            "pfo_ka_s-1",
            "pfo_ka_stderr",
            "pfo_kd_s-1",
            "pfo_kd_stderr",
            "pfo_qe_au",
            "pfo_qe_au_stderr",
            "pfo_qe_stderr",
            "pfo_Keq_au",
            "pfo_Keq_au_stderr",
            "pfo_q0_au_stderr",
        ]
        df_legacy = df_legacy.drop(columns=legacy_pfo_columns, errors="ignore")

        join_columns_present = tuple(
            col
            for col in join_columns
            if col in df_legacy.columns and col in fit_params.columns
        )
        if not join_columns_present:
            raise ValueError(
                "No shared join columns found between legacy data and fit parameters."
            )

        df_merged = pd.merge(
            df_legacy,
            fit_params,
            on=list(join_columns_present),
            how="left",
            suffixes=("", "_new"),
        )

        for column in df_merged.columns:
            if not column.endswith("_new"):
                continue
            base_column = column.removesuffix("_new")
            if base_column in df_merged.columns:
                df_merged[base_column] = df_merged[column]
            else:
                df_merged.rename(columns={column: base_column}, inplace=True)
            df_merged.drop(columns=[column], inplace=True)

        output_dir = _KineticUtilities.resolve_output_dir(
            legacy_path.parent, output_folder_name
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / legacy_path.name
        df_merged.to_csv(output_path, index=False)
        return output_path

    @staticmethod
    def drop_columns_with_prefixes(
        df: pd.DataFrame,
        prefixes: tuple[str, ...],
    ) -> tuple[pd.DataFrame, list[str]]:
        """Drop columns whose names start with any prefix.

        Returns a tuple of (cleaned_df, dropped_columns).
        """
        if not prefixes:
            return df.copy(), []
        dropped = [
            column
            for column in df.columns
            if any(column.startswith(prefix) for prefix in prefixes)
        ]
        if not dropped:
            return df.copy(), []
        return df.drop(columns=dropped, errors="ignore"), dropped

    @staticmethod
    def write_plain_legacy_output(
        legacy_path: str | Path,
        output_df: pd.DataFrame,
        *,
        output_folder_name: str = "_test",
    ) -> Path:
        """Write a plain legacy CSV (no merge), preserving file name."""
        legacy_path = Path(legacy_path)
        output_dir = _KineticUtilities.resolve_output_dir(
            legacy_path.parent, output_folder_name
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / legacy_path.name
        output_df.to_csv(output_path, index=False)
        return output_path
