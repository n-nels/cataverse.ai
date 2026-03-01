#!/usr/bin/env python3
"""Simple CLI wrapper around the peak fitting workflow."""

from pathlib import Path
import os
import sys

SRC_PATH = Path(__file__).resolve().parent.parent
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from src.analysis.main import DataAnalysisRunner


class KineticFit:

    def __init__(
        self,
        input_path: str,
        output_path: str,
    ) -> None:
        self.input_path = input_path
        self.output_path = output_path
        self.runner = DataAnalysisRunner()

    def run(self) -> None:
        """Convert *PeakFitParams.csv into *CarbonylPeakArea.csv outputs.

        Workflow:
        - Read a *_CarbonylPeakFitParams.csv file.
        - Compute cumulative peak areas (monomer/cluster sums included).
        - Append kinetics fits (PFO + biexponential).
        - Write *_CarbonylPeakArea.csv output.
        """
        from src.analysis.output import compute_cumulative_peak_area_df
        from src.analysis.spectral_fitting import get_shifted_monomer_peaks
        from src.core import config
        import pandas as pd

        df = pd.read_csv(self.input_path)
        settings = config.get_analysis_setting("analysis.voigt_fit")
        sum_peaks = [f"Peak_{peak}" for peak in get_shifted_monomer_peaks(settings)]
        df_cumulative = compute_cumulative_peak_area_df(df, sum_peaks)

        df_with_kinetics = self.runner.run_kinetics_fit(df_cumulative)
        if df_with_kinetics is None:
            raise SystemExit("No data returned from kinetics fit.")
        df_with_kinetics.to_csv(self.output_path, index=False)
        print(f"Saved: {self.output_path}")

    @staticmethod
    def run_main(subifg_file_path: str) -> None:
        """Run the full analysis workflow for a subIFG file."""
        runner = DataAnalysisRunner()
        runner.run_main(subifg_file_path)


if __name__ == "__main__":
    kinetic_fit = KineticFit(
        input_path=r"X:\peakFit\20260223_215629_pd_ceo2_003-119_CarbonylPeakFitParams.csv",
        output_path=r"X:\peakFit\20260223_215629_pd_ceo2_003-119_CarbonylPeakArea_new.csv",
    )
    kinetic_fit.run()
