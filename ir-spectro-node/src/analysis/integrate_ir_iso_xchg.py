import os
import pandas as pd
import numpy as np
import pybaselines
from scipy.signal import find_peaks
from scipy.integrate import trapezoid
from ..core import config


def integrate_irIsoXchg(file_path):
    """
    This function processes IR isotopic exchange data by performing baseline correction,
    peak detection, and integration to quantify CO adsorption and exchange.
    """

    def save_data(new_data, file_path, axis):
        """Appends or creates a CSV file with the given data."""
        if os.path.isfile(file_path):
            try:
                existing_data = pd.read_csv(file_path, header=0)
            except pd.errors.EmptyDataError:
                existing_data = pd.DataFrame()

            if (
                "Wavenumber (cm-1)" in existing_data.columns
                and "Wavenumber (cm-1)" in new_data.columns
            ):
                new_data = new_data.drop(columns=["Wavenumber (cm-1)"])

            combined_data = pd.concat([existing_data, new_data], axis=axis)
        else:
            combined_data = new_data

        combined_data.to_csv(file_path, index=False)

    def create_baseline(y):
        """Creates and subtracts a baseline from the spectral data."""
        bsln_stdDis = pybaselines.classification.std_distribution(
            y,
            half_window=10,
            interp_half_window=5,
            fill_half_window=6,
            num_std=1.1,
            smooth_half_window=None,
            weights=None,
        )[0]
        y_bs_1 = y - bsln_stdDis
        return y_bs_1, bsln_stdDis

    # --- Main function logic ---

    # Define paths using the config system
    foldername = os.path.basename(os.path.dirname(file_path))
    filename_base = "_".join(os.path.basename(file_path).split("_")[:-1])

    save_dir = config.get_path("data.peak_fit", foldername)
    calibration_dir = config.get_path("data.calibration_data", foldername)

    # Ensure save directory exists
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    # Import data
    try:
        df_subIFG = pd.read_csv(file_path, header=None)
    except pd.errors.EmptyDataError:
        print(f"Skipping empty file: {file_path}")
        return

    # ROI for 13CO and 12CO
    df_subIFG_13co_roi = df_subIFG.loc[(df_subIFG[0] >= 2000) & (df_subIFG[0] <= 2200)]
    arr_subIFG_13co_roi = df_subIFG_13co_roi.values

    df_subIFG_12co_roi = df_subIFG.loc[(df_subIFG[0] >= 2100) & (df_subIFG[0] <= 2300)]
    arr_subIFG_12co_roi = df_subIFG_12co_roi.values

    # Process 13CO data
    x_13co = arr_subIFG_13co_roi[:, 0]
    y_13co = arr_subIFG_13co_roi[:, 1]
    y_bs_13co, bsln_13co = create_baseline(y_13co)

    integral_13co = -trapezoid(y_bs_13co, x_13co)

    # Process 12CO data
    x_12co = arr_subIFG_12co_roi[:, 0]
    y_12co = arr_subIFG_12co_roi[:, 1]
    y_bs_12co, bsln_12co = create_baseline(y_12co)

    integral_12co = -trapezoid(y_bs_12co, x_12co)

    # Save integrated data
    peak_data = {
        "File": os.path.basename(file_path),
        "13CO_Integral": integral_13co,
        "12CO_Integral": integral_12co,
    }
    df_peak_data = pd.DataFrame([peak_data])

    output_filename = f"{filename_base}_isoXchg_Integral.csv"
    output_path = os.path.join(save_dir, output_filename)
    save_data(df_peak_data, output_path, axis=0)

    print(f"Processed and saved isotopic exchange data for: {file_path}")
