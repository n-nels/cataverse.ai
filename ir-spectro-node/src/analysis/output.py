"""Output helpers for saving Voigt fitting results.

This module separates computation from I/O:
- compute_* functions: Pure computation, return DataFrames
- save_* functions: File I/O only, accept pre-computed DataFrames
"""

from __future__ import annotations

import os
from typing import Any, cast

import numpy as np
import pandas as pd

from .kinetics_fitting import (
    append_fit_results,
    build_cluster_sum,
    linfunc_no_intercept,
)


def _coerce_df(value: Any) -> pd.DataFrame:
    """Ensure a DataFrame output for downstream helpers."""
    if isinstance(value, pd.DataFrame):
        return value
    if isinstance(value, pd.Series):
        return value.to_frame().T
    return pd.DataFrame(value)


def save_data(new_data: pd.DataFrame, file_path: str, axis: int) -> None:
    """Save or append CSV data along the provided axis."""
    if os.path.isfile(file_path):
        try:
            existing_data = pd.read_csv(file_path, header=0)
        except Exception as e:
            existing_data = pd.DataFrame()
            print(f"Error reading existing data {file_path}: {e}")
        if "Wavenumber (cm-1)" in existing_data.columns:
            new_data = new_data.drop(columns=["Wavenumber (cm-1)"])
        combined_data = cast(
            pd.DataFrame,
            pd.concat([existing_data, new_data], axis=axis, ignore_index=False),
        )
        try:
            combined_data = cast(
                pd.DataFrame,
                cast(Any, combined_data).sort_values(by=["Peak_Name", "File"]),
            )
        except Exception as e:
            if (
                "Peak_Name" not in combined_data.columns
                or "File" not in combined_data.columns
            ):
                pass
            else:
                print(f"Error sorting combined data for {file_path}: {e}")
    else:
        combined_data = new_data

    combined_data.to_csv(file_path, index=False)


def compute_peak_parameters_df(
    peak_fit_records: list[dict[str, Any]],
    calibration_peak_area: pd.Series | None,
    peak_area_mole_carbonyl_slope: float | np.ndarray | None,
    see: float | None,
) -> pd.DataFrame:
    """Compute per-peak fit parameters DataFrame (no file I/O)."""
    df_fit_peaks = pd.DataFrame(peak_fit_records)
    try:
        peak_area = cast(pd.Series, df_fit_peaks["Peak_Area"])
        slope = cast(float | np.ndarray, peak_area_mole_carbonyl_slope)
        cal_peak_area = cast(pd.Series, calibration_peak_area)
        df_fit_peaks["PdCO_mol"] = linfunc_no_intercept(peak_area, slope)
        df_fit_peaks["PdCO_mol_stderr"] = cast(float, see) * np.sqrt(
            1
            + 1 / len(cal_peak_area)
            + (peak_area - np.mean(cal_peak_area)) ** 2
            / np.sum((cal_peak_area - np.mean(cal_peak_area)) ** 2)
        )
    except Exception:
        pass
    return df_fit_peaks


def save_peak_parameters_df(
    df_fit_peaks: pd.DataFrame,
    file_name: str,
    save_dir: str,
) -> str:
    """Save pre-computed peak parameters DataFrame to CSV."""
    filename = f"{file_name}_CarbonylPeakFitParams.csv"
    path = os.path.join(save_dir, filename)
    save_data(new_data=df_fit_peaks, file_path=path, axis=0)
    return path


def compute_cumulative_peak_area_df(
    df_fit_peaks: pd.DataFrame,
    sum_areas_peaks: list[str],
) -> pd.DataFrame:
    """Compute cumulative peak area DataFrame from fit parameters (no file I/O)."""
    cumulative_area_rows = []

    if df_fit_peaks.empty:
        return cast(pd.DataFrame, df_fit_peaks)

    cumulative_area_delta1 = None
    cumulative_integral_delta1 = None
    time_sec_delta1 = None
    cumulative_pdco_delta1 = None
    cumulative_stderr_delta1 = None

    grouped = cast(Any, df_fit_peaks.groupby(["Peak_Name", "Delta_Group"]))
    for (peak_name, delta_group), group in grouped:
        group = cast(pd.DataFrame, group)
        if delta_group == "delta1":
            delta1_group = cast(
                pd.DataFrame,
                group.loc[group["Delta_Group"] == "delta1"],
            )
            cumulative_area_delta1 = (
                cast(pd.Series, delta1_group["Peak_Area"]).iloc[:2].sum()
            )
            cumulative_integral_delta1 = (
                cast(pd.Series, delta1_group["Data_Integral"]).iloc[:2].sum()
            )
            time_sec_delta1 = (
                cast(pd.Series, delta1_group["Time_Delta (s)"]).iloc[:2].sum()
            )
            try:
                cumulative_pdco_delta1 = (
                    cast(pd.Series, delta1_group["PdCO_mol"]).iloc[:2].sum()
                )
                cumulative_stderr_sumSqrs_delta1 = (
                    cast(pd.Series, delta1_group["PdCO_mol_stderr"]).iloc[:2] ** 2
                ).sum()
                cumulative_stderr_delta1 = np.sqrt(cumulative_stderr_sumSqrs_delta1)
            except Exception:
                pass
            continue

        if cumulative_area_delta1 is None:
            continue
        cumulative_area = cumulative_area_delta1
        cumulative_integral = cumulative_integral_delta1
        time_sec = time_sec_delta1
        cumulative_pdco = cumulative_pdco_delta1
        cumulative_stderr = cumulative_stderr_delta1

        for index, row in group.iterrows():
            cumulative_area += np.nan_to_num(row["Peak_Area"])
            cumulative_integral += np.nan_to_num(row["Data_Integral"])
            time_sec += row["Time_Delta (s)"]
            try:
                cumulative_pdco += np.nan_to_num(row["PdCO_mol"])
                cumulative_stderr += np.sqrt(np.nan_to_num(row["PdCO_mol_stderr"]) ** 2)
            except Exception:
                pass

            row_payload = {
                "File": row["File"],
                "Delta_Group": row["Delta_Group"],
                "Peak_Name": peak_name,
                "Peak_Center": row["Center"],
                "Time (s)": time_sec,
                "Cumulative_Peak_Area": cumulative_area,
                "Cumulative_Integral": cumulative_integral,
            }
            if cumulative_pdco is not None:
                row_payload["Cumulative_PdCO_mol"] = cumulative_pdco
            if cumulative_stderr is not None:
                row_payload["Cumul_PdCO_mol_stderr"] = cumulative_stderr
            cumulative_area_rows.append(row_payload)

    df_cumulative_areas = pd.DataFrame(cumulative_area_rows)
    if df_cumulative_areas.empty or "Peak_Name" not in df_cumulative_areas.columns:
        return df_cumulative_areas

    df_monomer_peaks = df_cumulative_areas[
        df_cumulative_areas["Peak_Name"].isin(sum_areas_peaks)
    ]
    if all(
        col in df_cumulative_areas.columns
        for col in ["Delta_Group", "Time (s)", "Peak_Name", "Cumulative_Peak_Area"]
    ):
        grouped = cast(Any, df_monomer_peaks.groupby(["Delta_Group", "Time (s)"]))
        monomer_rows = []
        for (delta_group, time_s), group in grouped:
            group = cast(pd.DataFrame, group)
            summed_area = group["Cumulative_Peak_Area"].sum()
            file_val = group["File"].iloc[0] if "File" in group else ""
            row = {
                "File": file_val,
                "Delta_Group": delta_group,
                "Peak_Name": "monomer_sum",
                "Time (s)": time_s,
                "Cumulative_Peak_Area": summed_area,
            }
            for col in df_cumulative_areas.columns:
                if col not in row:
                    row[col] = ""
            monomer_rows.append(row)
        # Append monomer_sum rows
        df_cumulative_areas = pd.concat(
            [df_cumulative_areas, pd.DataFrame(monomer_rows)], ignore_index=True
        )

    if (
        "Peak_Name" in df_cumulative_areas.columns
        and (df_cumulative_areas["Peak_Name"] == "cluster_sum").any()
    ):
        return df_cumulative_areas

    cluster_sum = build_cluster_sum(df_cumulative_areas)
    if cluster_sum.empty:
        return df_cumulative_areas

    template_columns = list(df_cumulative_areas.columns)
    cluster_sum = cluster_sum.copy()
    cluster_sum["Peak_Name"] = "cluster_sum"
    for column in template_columns:
        if column not in cluster_sum:
            cluster_sum[column] = ""
    cluster_sum = cluster_sum[template_columns]
    df_cumulative_areas = pd.concat(
        [df_cumulative_areas, cluster_sum], ignore_index=True
    )

    return df_cumulative_areas


def compute_peak_area_with_kinetics_df(
    df_cumulative_areas: pd.DataFrame,
    df_prior_kinetics: pd.DataFrame | None = None,
    *,
    latest_only: bool = True,
) -> pd.DataFrame:
    """Compute peak area DataFrame with kinetics fit results (no file I/O).

    Parameters
    ----------
    df_cumulative_areas : pd.DataFrame
        Fresh cumulative peak areas (no kinetics columns).
    df_prior_kinetics : pd.DataFrame | None
        Previously saved CarbonylPeakArea data containing kinetics
        columns from earlier runs.  Kinetics rows are carried forward
        and only the latest time point is re-fitted.
    latest_only : bool
        If True (default, real-time mode), only the latest time point
        is fitted.  If False (batch mode), every time point is fitted.
    """
    if df_cumulative_areas.empty:
        return cast(pd.DataFrame, df_cumulative_areas)
    return cast(
        pd.DataFrame,
        append_fit_results(
            df_cumulative_areas, df_prior_kinetics, latest_only=latest_only
        ),
    )


def save_peak_area_versus_time_df(
    df_peak_area_output: pd.DataFrame,
    file_name: str,
    save_dir: str,
) -> str:
    """Save pre-computed peak area versus time DataFrame to CSV."""
    filename = f"{file_name}_CarbonylPeakArea.csv"
    path = os.path.join(save_dir, filename)
    df_peak_area_output.to_csv(path, index=False)
    return path


def compute_residual_df(
    file_path: str,
    arr_subifg_roi: np.ndarray,
    residual: np.ndarray,
) -> pd.DataFrame:
    """Compute residual DataFrame (no file I/O)."""
    df = pd.DataFrame()
    df["Wavenumber (cm-1)"] = arr_subifg_roi[:, 0]
    df.reset_index(drop=True, inplace=True)
    df_key = pd.DataFrame({file_path.split("_")[-1]: residual})
    df = pd.concat([df, df_key], axis=1)
    return df


def save_residual_df(
    df_residual: pd.DataFrame,
    file_name: str,
    save_dir: str,
) -> str:
    """Save pre-computed residual DataFrame to CSV."""
    filename = f"{file_name}_CarbonylFitResidual.csv"
    path = os.path.join(save_dir, filename)
    save_data(new_data=df_residual, file_path=path, axis=1)
    return path


def compute_baseline_df(
    file_path: str,
    arr_subifg_roi: np.ndarray,
    baseline_std_distribution: np.ndarray,
) -> pd.DataFrame:
    """Compute baseline DataFrame (no file I/O)."""
    df = pd.DataFrame()
    df["Wavenumber (cm-1)"] = arr_subifg_roi[:, 0]
    df_key = pd.DataFrame({file_path.split("_")[-1]: baseline_std_distribution})
    df.reset_index(drop=True, inplace=True)
    df = pd.concat([df, df_key], axis=1)
    return df


def save_baseline_df(
    df_baseline: pd.DataFrame,
    file_name: str,
    save_dir: str,
) -> str:
    """Save pre-computed baseline DataFrame to CSV."""
    filename = f"{file_name}_CarbonylFitBaseline.csv"
    path = os.path.join(save_dir, filename)
    save_data(new_data=df_baseline, file_path=path, axis=1)
    return path


def save_monomer_max_df(
    df_monomer_max: pd.DataFrame,
    file_name: str,
    save_dir: str,
) -> str:
    """Save monomer max results to CSV (overwrites existing file)."""
    filename = f"{file_name}_monomerMax.csv"
    path = os.path.join(save_dir, filename)
    df_monomer_max.to_csv(path, index=False)
    return path
