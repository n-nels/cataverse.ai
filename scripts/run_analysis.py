#!/usr/bin/env python3
"""Simple CLI wrapper around the peak fitting workflow."""

import os
import sys
from pathlib import Path
import pandas as pd

SRC_PATH = Path(__file__).resolve().parent.parent
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from src.analysis.output import compute_cumulative_peak_area_df
from src.analysis.spectral_fitting import get_shifted_monomer_peaks
from src.core import config
from src.analysis.main import DataAnalysisRunner


class KineticFit:
    def __init__(
        self,
        input_path: str = None,
        output_path: str = None,
    ) -> None:
        self.input_path = input_path
        self.output_path = output_path
        self.runner = DataAnalysisRunner()

    def run_kinetics_fit(self) -> None:
        """Convert *PeakFitParams.csv into *CarbonylPeakArea.csv outputs.

        Workflow:
        - Read a *_CarbonylPeakFitParams.csv file.
        - Compute cumulative peak areas (monomer/cluster sums included).
        - Append kinetics fits (PFO + biexponential).
        - Write *_CarbonylPeakArea.csv output.
        """

        # df = pd.read_csv(self.input_path)
        # settings = config.get_analysis_setting("analysis.voigt_fit")
        # sum_peaks = [f"Peak_{peak}" for peak in get_shifted_monomer_peaks(settings)]
        # df_cumulative = compute_cumulative_peak_area_df(df, sum_peaks)

        df_with_kinetics = self.runner.run_kinetics_fit(self.input_path)
        if df_with_kinetics is None:
            raise SystemExit("No data returned from kinetics fit.")
        df_with_kinetics.to_csv(self.output_path, index=False)
        print(f"Saved: {self.output_path}")

    def run_voigt_fit(self, subifg_file_path: str) -> str | None:
        """Run Voigt profile fitting on a subIFG file (no PFO/secondary kinetics)."""
        return self.runner.run_spectral_fit(subifg_file_path, run_kinetics=False)

    def run_peak_heights(self, subifg_file_path: str) -> None:
        """Run peak height extraction on a subIFG file."""
        self.runner.run_spectral_peak_heights(subifg_file_path)

    @staticmethod
    def run_main(subifg_file_path: str) -> None:
        """Run the full analysis workflow for a subIFG file."""
        runner = DataAnalysisRunner()
        runner.run_main(subifg_file_path)


if __name__ == "__main__":

    # file_directory = r"C:\Data\OpusConvert_subIFG_lgRfl\nn1120-3_pd_ceo2_004"
    # name = r"20260329_032106_pd_ceo2_004-010"

    # kinetic_fit = KineticFit()

    # for file_name in os.listdir(file_directory):
    #     if name in file_name:
    #         file_path = os.path.join(file_directory, file_name)
    #         if os.path.isfile(file_path):
    #             try:
    #                 print(f"Processing {file_path}...")
    #                 kinetic_fit.run_voigt_fit(file_path)
    #             except Exception as e:
    #                 print(e)

# ---------------------------------------------------------------------------------------------------

    # kinetic_fit = KineticFit(
    #     input_path=r"C:\Data\peakFit\nn1120-3_pd_ceo2_004\20260322_125032_pd_ceo2_004-009_CarbonylPeakArea.csv",
    #     output_path=r"C:\Data\peakFit\nn1120-3_pd_ceo2_004\20260322_125032_pd_ceo2_004-009_CarbonylPeakArea_new.csv",
    # )
    # kinetic_fit.run_kinetics_fit() # batch entry point for kinetics fit (PFO + biexponential)

# ---------------------------------------------------------------------------------------------------

    # file_directory = r"C:\Data\OpusConvert_subIFG_lgRfl\nn1120-3_pd_ceo2_004"
    # name = r"20260329_032106_pd_ceo2_004-010"

    # for file_name in os.listdir(file_directory):
    #     if name in file_name:
    #         file_path = os.path.join(file_directory, file_name)
    #         if os.path.isfile(file_path):
    #             try:
    #                 print(f"Processing {file_path}...")
    #                 KineticFit.run_main(file_path)
    #             except Exception as e:
    #                 print(e)

# ---------------------------------------------------------------------------------------------------

    file_directory = r"C:\Data\OpusConvert_subIFG_lgRfl\nn1120-3_pd_ceo2_004"
    name = r"20260329_032106_pd_ceo2_004-010"

    kinetics = KineticFit()

    for file_name in os.listdir(file_directory):
        if name in file_name:
            file_path = os.path.join(file_directory, file_name)
            if os.path.isfile(file_path):
                try:
                    print(f"Processing {file_path}...")
                    kinetics.run_peak_heights(file_path)
                except Exception as e:
                    print(e)