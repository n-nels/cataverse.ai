"""High-level orchestration for analysis workflows."""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from lmfit import Parameters

from . import peak_heights
from ..core import config
from .io import import_calibration_data, import_data, load_peak_parameters
from .kinetics_fitting import (
    append_pfo_fit_results,
    calibration_statistics,
)
from .output import (
    compute_baseline_df,
    compute_cumulative_peak_area_df,
    compute_peak_area_with_kinetics_df,
    compute_peak_parameters_df,
    compute_residual_df,
    save_baseline_df,
    save_monomer_max_df,
    save_peak_area_versus_time_df,
    save_peak_parameters_df,
    save_residual_df,
)
from .monomer_max import compute_monomer_max_row
from .spectral_fitting import (
    add_params,
    create_baseline,
    find_fsd_peaks,
    get_peak_list,
    get_shifted_monomer_peaks,
    manually_skip_files,
    peak_analysis,
    resolve_peak_lists,
    resolve_temp_peak,
    resolve_time_delta,
)


@dataclass
class AnalysisPaths:
    """Resolved input/output paths for a subIFG file."""

    folder_name: str
    file_name: str
    file_index: str
    delta_file: str
    save_dir: str
    time_dir: str
    fsd_dir: str
    subifg_log_dir: str
    calibration_dir: str


@dataclass
class AnalysisInputs:
    """Loaded spectral inputs for a subIFG file."""

    arr_subifg_roi: np.ndarray
    arr_fsd_roi: np.ndarray
    subifg_log: pd.DataFrame
    exp_params: pd.DataFrame


@dataclass
class CalibrationMetrics:
    """Calibration data and derived statistics for a run."""

    calibration_peak_area: pd.Series | None
    peak_area_mole_carbonyl_slope: float | np.ndarray | None
    see: float | None


class DataAnalysisRunner:
    """Orchestrates spectral fit, kinetics fit, and peak height analysis."""

    def __init__(
        self,
        config_module: Any = config,
        analysis_key: str = "analysis.voigt_fit",
    ) -> None:
        """Initialize the runner with analysis configuration."""
        self.config = config_module
        self.analysis_key = analysis_key
        self.voigt_settings = self.config.get_analysis_setting(self.analysis_key)
        self.paths: AnalysisPaths | None = None
        self.inputs: AnalysisInputs | None = None
        self.calibration: CalibrationMetrics | None = None

    def _resolve_paths(self, file_path: str) -> AnalysisPaths:
        """Resolve input/output paths for a subIFG file."""
        folder_name = os.path.basename(os.path.dirname(file_path))
        file_name = "_".join(os.path.basename(file_path).split("_")[:-1])
        file_index = file_path.split(".")[-1]
        delta_file = file_path.split("_")[-1].split(".")[0]

        save_dir = self.config.get_path("data.peak_fit", folder_name)
        time_dir = self.config.get_path(
            "utility.subtract_ifg.read_params_output", folder_name, f"{file_name}.txt"
        )
        fsd_dir = self.config.get_path(
            "utility.subtract_ifg.fsd_output", folder_name, f"{file_name}.{file_index}"
        )
        subifg_log_dir = self.config.get_path(
            "utility.subtract_ifg.read_params_output",
            folder_name,
            f"{file_name}_subIFGfiles.txt",
        )
        calibration_dir = self.config.get_path(
            "calibration.root", folder_name, "CalibrationData"
        )

        self.paths = AnalysisPaths(
            folder_name=folder_name,
            file_name=file_name,
            file_index=file_index,
            delta_file=delta_file,
            save_dir=save_dir,
            time_dir=time_dir,
            fsd_dir=fsd_dir,
            subifg_log_dir=subifg_log_dir,
            calibration_dir=calibration_dir,
        )
        return self.paths

    def _load_inputs(
        self,
        file_path: str,
    ) -> AnalysisInputs:
        """Load subIFG, FSD, log, and experiment parameters."""
        if self.paths is None:
            raise ValueError("Input paths must be resolved before loading data.")
        imported = import_data(
            file_path,
            self.paths.fsd_dir,
            self.paths.subifg_log_dir,
            self.paths.time_dir,
        )
        self.inputs = AnalysisInputs(
            arr_subifg_roi=imported.arr_subifg_roi,
            arr_fsd_roi=imported.arr_fsd_roi,
            subifg_log=imported.subifg_log,
            exp_params=imported.exp_params,
        )
        return self.inputs

    def _load_calibration(
        self,
        folder_name: str,
        calibration_dir: str,
    ) -> CalibrationMetrics:
        """Load calibration data and derive conversion statistics."""
        calibration_result = import_calibration_data(folder_name, calibration_dir)
        if calibration_result is None:
            print("Calibration data is missing.")
            calibration_peak_area = None
            calibration_moles = None
            peak_area_mole_carbonyl_slope = None
            see = None
        else:
            calibration_peak_area = calibration_result.peak_area
            calibration_moles = calibration_result.moles
            peak_area_mole_carbonyl_slope = (
                calibration_result.peak_area_mole_carbonyl_slope
            )
            pcov = calibration_result.pcov
            see, _ = calibration_statistics(
                calibration_peak_area,
                calibration_moles,
                peak_area_mole_carbonyl_slope,
                pcov,
            )

        self.calibration = CalibrationMetrics(
            calibration_peak_area=calibration_peak_area,
            peak_area_mole_carbonyl_slope=peak_area_mole_carbonyl_slope,
            see=see,
        )
        return self.calibration

    def run_spectral_fit(self, file_path: str) -> str | None:
        """Fit a Voigt profile to the carbonyl peak in subIFG data."""
        peak_list_core = get_peak_list(self.voigt_settings)
        if not peak_list_core:
            print(f"No peak list configured for {file_path}")
            return None

        paths = self._resolve_paths(file_path)

        if manually_skip_files(paths.delta_file, paths.file_index):
            return None

        try:
            inputs = self._load_inputs(file_path)
        except Exception as e:
            print(f"Error importing data for {file_path}: {e}")
            return None

        calibration = self._load_calibration(paths.folder_name, paths.calibration_dir)

        fsd_peak_indices = find_fsd_peaks(
            inputs.arr_fsd_roi,
            self.voigt_settings.get("baseline", {}),
            self.voigt_settings.get("find_peaks", {}).get("fsd", {}),
        )

        wavenumbers = inputs.arr_subifg_roi[:, 0]
        intensity = inputs.arr_subifg_roi[:, 1]
        temp_peak = resolve_temp_peak(fsd_peak_indices)
        peak_fit_records = []
        fit_params = Parameters()

        baseline_corrected, baseline_std_distribution = create_baseline(
            intensity, self.voigt_settings.get("baseline", {})
        )

        peak_list = resolve_peak_lists(peak_list_core, fsd_peak_indices)

        for i, peak in enumerate(peak_list):
            peak_name = peak_list_core[i]
            add_params(
                fit_params,
                peak,
                peak_name,
                paths.file_index,
                temp_peak,
                self.voigt_settings,
            )

        time_delta = resolve_time_delta(file_path, inputs.subifg_log, inputs.exp_params)

        # === COMPUTE PHASE: Pure computation, no file I/O ===
        analysis_result = peak_analysis(
            file_path,
            wavenumbers,
            inputs.arr_subifg_roi,
            baseline_corrected,
            peak_list_core,
            peak_list,
            paths.delta_file,
            fit_params,
            self.voigt_settings,
            time_delta,
        )

        # Compute output DataFrames
        df_fit_peaks = compute_peak_parameters_df(
            [record.to_dict() for record in analysis_result.peak_fit_records],
            calibration.calibration_peak_area,
            calibration.peak_area_mole_carbonyl_slope,
            calibration.see,
        )
        df_residual = compute_residual_df(
            file_path, inputs.arr_subifg_roi, analysis_result.residual
        )
        df_baseline = compute_baseline_df(
            file_path, inputs.arr_subifg_roi, baseline_std_distribution
        )

        # === I/O PHASE: Save computed results to files ===
        params_path = save_peak_parameters_df(
            df_fit_peaks,
            paths.file_name,
            paths.save_dir,
        )
        df_fit_peaks_history = load_peak_parameters(params_path)
        if df_fit_peaks_history is None:
            df_fit_peaks_history = df_fit_peaks
        df_cumulative_areas = compute_cumulative_peak_area_df(
            df_fit_peaks_history,
            [f"Peak_{peak}" for peak in get_shifted_monomer_peaks(self.voigt_settings)],
        )
        df_peak_area_output = compute_peak_area_with_kinetics_df(df_cumulative_areas)
        peak_area_path = save_peak_area_versus_time_df(
            df_peak_area_output,
            paths.file_name,
            paths.save_dir,
        )
        save_residual_df(
            df_residual,
            paths.file_name,
            paths.save_dir,
        )
        save_baseline_df(
            df_baseline,
            paths.file_name,
            paths.save_dir,
        )

        lg_refl_path = Path(
            self.config.get_path(
                "utility.subtract_ifg.lg_refl_output",
                paths.folder_name,
                f"{paths.file_name}.{paths.file_index}",
            )
        )
        if lg_refl_path.exists():
            df_monomer_max = compute_monomer_max_row(file_path=lg_refl_path)
            if not df_monomer_max.empty:
                save_monomer_max_df(
                    df_monomer_max,
                    paths.file_name,
                    paths.save_dir,
                )

        return peak_area_path

    def run_kinetics_fit(
        self,
        cumulative_peak_area: str | pd.DataFrame | None,
    ) -> pd.DataFrame | None:
        """Run kinetics fitting on cumulative peak area outputs."""
        if cumulative_peak_area is None:
            return None
        if isinstance(cumulative_peak_area, str):
            df_cumulative_peak_area = load_peak_parameters(cumulative_peak_area)
        else:
            df_cumulative_peak_area = cumulative_peak_area
        if df_cumulative_peak_area is None or df_cumulative_peak_area.empty:
            return df_cumulative_peak_area
        df_with_pfo = append_pfo_fit_results(df_cumulative_peak_area)
        return df_with_pfo

    def run_spectral_peak_heights(self, file_path: str) -> None:
        """Run peak height analysis for a subIFG file."""
        analyzer = peak_heights.PeakHeightsAnalyzer()
        analyzer.run(file_path)

    def run_main(self, file_path: str) -> None:
        """Run spectral fit, kinetics fit, and peak heights in order."""
        peak_area_path = self.run_spectral_fit(file_path)
        self.run_kinetics_fit(peak_area_path)
        self.run_spectral_peak_heights(file_path)


if __name__ == "__main__":
    # test
    file_directory = r"C:\Data\OpusConvert_subIFG_lgRfl\nn1120-3_pd_ceo2_003"
    name = r"20260203_102014_pd_ceo2_003-109"

    runner = DataAnalysisRunner()

    for file_name in os.listdir(file_directory):
        if name in file_name:
            file_path = os.path.join(file_directory, file_name)
            if os.path.isfile(file_path):
                try:
                    print(f"Processing {file_path}...")
                    runner.run_main(file_path)
                except Exception as e:
                    print(e)
