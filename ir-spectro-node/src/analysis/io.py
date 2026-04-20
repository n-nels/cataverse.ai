"""Input/output helpers for Voigt spectral analysis."""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from typing import cast

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

from .kinetics_fitting import linfunc, linfunc_no_intercept


@dataclass
class ImportedData:
    """Container for imported spectral data and metadata."""

    arr_subifg_roi: np.ndarray
    arr_fsd_roi: np.ndarray
    subifg_log: pd.DataFrame
    exp_params: pd.DataFrame


@dataclass
class CalibrationData:
    """Container for calibration data and fit covariance."""

    peak_area: pd.Series
    moles: pd.Series
    peak_area_mole_carbonyl_slope: np.ndarray
    pcov: np.ndarray


def add_milliseconds(time_str: str) -> str:
    """Ensure the time string includes fractional seconds."""
    if "." not in time_str:
        return time_str + ".000000"
    return time_str


def import_data(
    file_path: str,
    fsd_dir: str,
    subifg_log_dir: str,
    time_dir: str,
) -> ImportedData:
    """Load subIFG, FSD, subIFG log, and experiment parameters."""
    # import subifg data
    df_subifg = pd.read_csv(file_path, header=None)
    df_subifg_roi_cm1 = df_subifg.loc[(df_subifg[0] >= 1750) & (df_subifg[0] <= 2250)]
    if df_subifg_roi_cm1.empty:
        raise ValueError(f"No subifg data in ROI for {file_path}")
    arr_subifg_roi = df_subifg_roi_cm1.values

    # import fsd data
    df_fsd = pd.read_csv(fsd_dir, header=None)
    df_fsd_roi_cm1 = df_fsd.loc[(df_fsd[0] >= 1750) & (df_fsd[0] <= 2250)]
    if df_fsd_roi_cm1.empty:
        raise ValueError(f"No FSD data in ROI for {fsd_dir}")
    arr_fsd_roi = df_fsd_roi_cm1.values

    # import subifg file log
    subifg_log = pd.read_csv(
        subifg_log_dir, header=None, names=["sample_name", "sample", "background"]
    )
    if subifg_log.empty:
        raise ValueError(f"No subifg log entries found in {subifg_log_dir}")

    subifg_log["sample_name"] = (
        subifg_log["sample_name"].str.replace(r"[\'\(\)]", "", regex=True).str.strip()
    )

    subifg_log["sample"] = (
        subifg_log["sample"]
        .str.extract(r"([^\s\'\"]+)")
        .replace(r"\\\\", r"\\", regex=True)
    )

    subifg_log["background"] = (
        subifg_log["background"]
        .str.extract(r"([^\s\'\"]+)")
        .replace(r"\\\\", r"\\", regex=True)
    )

    # import experimental parameters
    exp_params = pd.read_csv(
        time_dir,
        header=None,
        names=["file_directory", "Date", "Time", "PKA", "NSS"],
    )
    if exp_params.empty:
        raise ValueError(f"No experiment parameters found in {time_dir}")

    exp_params["file_directory"] = exp_params["file_directory"].apply(
        lambda x: x.split()[0].strip("\"'")
    )

    exp_params["Time"] = exp_params["Time"].str.strip()
    exp_params["Time"] = exp_params["Time"].apply(add_milliseconds)

    exp_params["datetime"] = pd.to_datetime(
        exp_params["Date"] + " " + exp_params["Time"],
        format=" %Y-%m-%d %H:%M:%S.%f",
        errors="coerce",
    )

    exp_params["datetime"] = exp_params["datetime"].fillna(
        pd.to_datetime(exp_params["Time"], format="%H:%M:%S.", errors="coerce")
    )

    return ImportedData(
        arr_subifg_roi=arr_subifg_roi,
        arr_fsd_roi=arr_fsd_roi,
        subifg_log=subifg_log,
        exp_params=exp_params,
    )


def load_peak_parameters(file_path: str) -> pd.DataFrame | None:
    """Load peak parameter data from a CSV file."""
    try:
        return pd.read_csv(file_path)
    except Exception as e:
        print(f"Error reading peak parameter file {file_path}: {e}")
        return None


def import_calibration_data(
    folder_name: str,
    calibration_dir: str,
) -> CalibrationData | None:
    """Load calibration data and compute slope for moles conversion."""
    calibration_frames = []
    df_calibration_data = None

    if folder_name == "nn1120-2_pd_ceo2_000":
        skip_files = [
            "allData",
            "000-003",
            "000-005",
            "000-007",
            "000-009",
            "000-011",
            "000-013",
            "000-014",
            "000-016",
            "000-017",
        ]
        try:
            for file in glob.glob(os.path.join(calibration_dir, "*")):
                if any(string in file for string in skip_files):
                    continue
                df = pd.read_csv(file)
                calibration_frames.append(df)

            df_calibration_data = pd.concat(calibration_frames, ignore_index=True)
        except Exception:
            return None

    if folder_name == "nn1120-3_pd_ceo2_000":
        skip_files = [
            "allData",
            "000-005",
            "000-007",
            "000-009",
            "000-010",
            "000-012",
        ]
        try:
            for file in glob.glob(os.path.join(calibration_dir, "*")):
                if any(string in file for string in skip_files):
                    continue
                df = pd.read_csv(file)
                calibration_frames.append(df)

            df_calibration_data = pd.concat(calibration_frames, ignore_index=True)
        except Exception:
            return None

    # clean data
    if df_calibration_data is None:
        return None

    try:
        df_calibration_data["Peak_Area"] = df_calibration_data["Peak_Area"] * -1
        df_calibration_data["Peak_Area"] = df_calibration_data["Peak_Area"].mask(
            df_calibration_data["Peak_Area"] < 0, 0
        )

        mask = (
            (df_calibration_data["Peak_Area"] >= 0)
            & (df_calibration_data["Peak_Area"] <= 0.05)
            & (df_calibration_data["co_moles"] >= 0)
            & (df_calibration_data["co_moles"] > 2.5e-10)
            & ~(
                (df_calibration_data["Peak_Area"] == 0)
                & (df_calibration_data["co_moles"] > 1e-9)
            )
        )
        df_calibration_data = df_calibration_data[mask]

        # find slope between carbonyl area and moles
        x = cast(pd.Series, df_calibration_data["Peak_Area"])
        y = cast(pd.Series, df_calibration_data["co_moles"])
        popt, pcov = curve_fit(linfunc, x, y)
        slope, intercept = popt

        df_calibration_data["co_moles"] = df_calibration_data["co_moles"] - intercept
        y = cast(pd.Series, df_calibration_data["co_moles"])
        popt, pcov = curve_fit(linfunc_no_intercept, x, y)
        peak_area_mole_carbonyl_slope = popt

        # output calibration data
        output = os.path.join(calibration_dir, folder_name + "_allData.csv")
        df_calibration_data.to_csv(output, index=False)
        return CalibrationData(
            peak_area=x,
            moles=y,
            peak_area_mole_carbonyl_slope=peak_area_mole_carbonyl_slope,
            pcov=pcov,
        )
    except Exception:
        return None
