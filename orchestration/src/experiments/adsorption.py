"""Adsorption experiment protocol using the new architecture layers.

This module provides an adsorption experiment class that coordinates
session metadata, control-layer operations, and hardware access through the
new typed interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
import shutil
import threading
import time
import os
import logging
from typing import Any
from typing import cast
from pathlib import Path

from src.control.gas_delivery import GasDelivery
from src.control.mass_spec_control import MassSpecController
from src.control.spectrometer_control import SpectrometerController
from src.control.temperature_control import TemperatureController
from src.datalog.mass_spec_logger import MassSpecLogger
from src.datalog.pressure_logger import PressureLogger
from src.datalog.temperature_logger import TemperatureLogger
from src.experiments.session import ExperimentSession
from src.core.physics import cell_pressure_from_manifold


logger = logging.getLogger(__name__)


@dataclass
class AdsorptionExperiment:
    """Orchestrates the adsorption experiment protocol workflow.

    Coordinates session metadata, gas delivery, temperature control,
    spectrometer operations, and logging while preserving protocol sequencing.
    """

    session: ExperimentSession
    gas_controller: GasDelivery
    temp: TemperatureController
    ftir: SpectrometerController
    mass_spec: MassSpecController

    def __post_init__(self) -> None:
        self.gas: str | tuple[str, str] | None = None
        self.gas_2: str | None = None
        self.p_mfld: float | str | None = None
        self.p_cell_calc: float | tuple[float, float] | None = None
        self.dt: Any = None
        self.chiller_state: bool | None = None

    def acquire_ms_spectra(self) -> MassSpecLogger:
        """Start mass-spec streaming with legacy valve/sequence ordering."""

        self.gas_controller.valves.close("irCell")
        self.gas_controller.valves.open("MassSpec")
        time.sleep(30)

        # Extrel sequence start from config
        success = self.mass_spec.start_sequence()
        if success:
            logger.info("Extrel sequence started")
        else:
            logger.info("Failed to set Extrel sequence")

        ms_logger = MassSpecLogger(
            mass_spec=self.mass_spec.mass_spec_adapter(),
            path=Path(cast(str, self.session.path_ms_log)),
        )
        ms_logger.start()
        time.sleep(60)
        return ms_logger

    def heat_under_evacuation(
        self,
        pump_type: str,
        target_temp: int,
        hold_time: float,
        ramp_rate: int,
        enable_ms_stream: bool = False,
        variac_cmd: bool = True,
        log_params: bool = True,
    ) -> None:
        """Heat cell under evacuation with optional mass-spec stream sequence."""

        if pump_type is not None:
            self.gas = self.gas_controller.evacuate_cell(pump_type)
            if hold_time == 0:
                time.sleep(60)

        ms_logger: MassSpecLogger | None = None
        if enable_ms_stream:
            ms_logger = self.acquire_ms_spectra()

        t_cell, rate, duration = self.temp.watlow(
            self.session.file_name,
            self.session.folder_name,
            target_temp,
            hold_time,
            ramp_rate,
            variac_cmd,
        )

        if enable_ms_stream and ms_logger is not None:
            time.sleep(60 * 15)  # [fix] Should be arg
            ms_logger.stop()

            # Extrel sequence stop from config
            success = self.mass_spec.stop_sequence()
            if success:
                logger.info("Extrel sequence stopped")
            else:
                logger.info("Failed to set Extrel sequence")
            self.gas_controller.valves.close("MassSpec")
            self.gas_controller.valves.open("irCell")

        self.dt, self.p_mfld, p_cell = self.gas_controller.read_pressure()

        if log_params:
            p_mfld_value = cast(float, self.p_mfld)
            p_cell_value = cast(float, p_cell)
            t_cell_value = cast(float, t_cell)
            self.session.log_pretreatment(
                gas=self.gas,
                p_gas_meas=(p_mfld_value, p_cell_value),
                t_cell=t_cell_value,
                rate=rate,
                duration=duration,
                chiller_state=self.chiller_state,
            )

    def cool_cell(
        self, target_temp: int, hold_time: float, variac_cmd: bool, ramp_rate: int = 0
    ) -> None:
        """Cool the cell to a target temperature. The variac_cmd is used to keep the cell on even at target temperature."""
        t_cell, rate, duration = self.temp.watlow(
            self.session.file_name,
            self.session.folder_name,
            target_temp,
            hold_time,
            ramp_rate,
            variac_cmd,
        )
        while True:
            current_temp = self.temp.read_temperature()
            logger.info(
                f"Current temperature: {current_temp}\nTarget temperature: {t_cell}\n"
            )
            try:
                if t_cell + 1 >= current_temp:
                    break
            except TypeError as e:
                logger.info(f"Error occurred while reading temperatures: {e}")
            time.sleep(60)
        self.dt, self.p_mfld, p_cell = self.gas_controller.read_pressure()

    def supply_gas_to_mfld(self, gas: str, target_pressure: float) -> None:
        """Supply gas to the manifold. The target pressure corresponds to the pressure in the total volume of the system."""
        if self.gas_2:
            self.gas_2 = None

        # Calculate target pressure for the manifold based on volume ratios
        val = (
            self.session.volumes.total
            / (self.session.volumes.manifold_m1m2m3 + self.session.volumes.tube_50ml)
            * target_pressure
        )
        self.gas, self.p_mfld = self.gas_controller.deliver_gas_to_manifold(
            self.session.file_name,
            self.session.folder_name,
            id=gas,
            target=val,
            openMS=True,
        )

        self.p_cell_calc = cell_pressure_from_manifold(
            self.p_mfld,
            self.session.volumes.manifold_m1m2m3 + self.session.volumes.tube_50ml,
            self.session.volumes.total,
        )

    def supply_another_gas_to_mfld(self, gas: str, target_pressure: float) -> None:
        """Supply another gas to the manifold. The gas is delivered to the manifold and the pressure is calculated."""
        self.gas_controller.valves.close("v16")
        self.gas_controller.valves.open("TurboPump")
        time.sleep(120)
        self.gas_2, self.p_mfld_2 = self.gas_controller.deliver_gas_to_manifold(
            self.session.file_name,
            self.session.folder_name,
            id=gas,
            target=target_pressure,
            openMS=False,
        )
        self.p_cell_calc = cell_pressure_from_manifold(
            self.p_mfld, self.session.volumes.m3, self.session.volumes.total
        )
        self.p_cell_calc_2 = cell_pressure_from_manifold(
            self.p_mfld_2,
            self.session.volumes.manifold_m1m2 + self.session.volumes.tube_50ml,
            self.session.volumes.total,
        )
        self.gas_controller.valves.open("v16")
        time.sleep(60)

    def supply_gases_to_mfld(
        self, gas: list[str], target_pressure: list[float]
    ) -> None:
        """Supply gases to the manifold. The target pressure corresponds to the pressure in the total volume of the system."""
        # Calculate target pressures for each gas based on volume ratios
        val_1 = (
            (self.session.volumes.total) / self.session.volumes.m3 * target_pressure[0]
        )
        val_2 = (
            (self.session.volumes.total)
            / (self.session.volumes.manifold_m1m2 + self.session.volumes.tube_50ml)
            * target_pressure[1]
        )

        # Supply first gas to manifold
        self.gas, self.p_mfld = self.gas_controller.deliver_gas_to_manifold(
            self.session.file_name,
            self.session.folder_name,
            id=gas[0],
            target=val_1,
            openMS=True,
        )
        self.gas_controller.valves.close("v16")
        self.dt, self.p_mfld, p_cell = self.gas_controller.read_pressure()
        self.p_cell_calc = cell_pressure_from_manifold(
            self.p_mfld, self.session.volumes.m3, self.session.volumes.total
        )

        # Supply second gas to manifold
        self.gas_controller.valves.open("TurboPump")
        time.sleep(300)
        self.gas_2, self.p_mfld_2 = self.gas_controller.deliver_gas_to_manifold(
            self.session.file_name,
            self.session.folder_name,
            id=gas[1],
            target=val_2,
            openMS=True,
        )
        self.p_cell_calc_2 = cell_pressure_from_manifold(
            self.p_mfld_2,
            self.session.volumes.manifold_m1m2 + self.session.volumes.tube_50ml,
            self.session.volumes.total,
        )
        self.gas_controller.valves.open("v16")
        time.sleep(60)

    def acquire_spectra(
        self,
        repeat: list[int],
        delay: list[int],
        all_fileids: bool,
        do_bckg: bool,
        do_fit: bool,
    ) -> None:
        """Acquire spectra from Opus software with threaded acquisition and pressure logging."""

        # Initial Opus acquisition with zero repeat/delay
        self.ftir.opus_vertex80(  # [fix] could use a beter name
            {
                "foldername": self.session.folder_name,
                "filename": self.session.file_name,
                "do_bckg": do_bckg,
                "do_fit": do_fit,
                "reset_fileids": all_fileids,
            }
        )

        # Thread for main Opus acquisition
        opus_thread = threading.Thread(
            target=self.ftir.opus_acquire,
            args=(
                self.session.file_name,
                self.session.folder_name,
                repeat,
                delay,
                all_fileids,
                do_bckg,
                do_fit,
            ),
        )

        # Read initial pressure
        dt, p_mfld_initial, p_cell_initial = self.gas_controller.read_pressure()

        # Thread for admitting gas to cell
        gas_thread = threading.Thread(target=self.gas_controller.cell_open_admit)

        # Start threads
        opus_thread.start()
        gas_thread.start()

        # Wait for gas thread to complete, then short delay
        gas_thread.join()
        time.sleep(20)

        # Read pressure after gas admission
        dt, p_mfld, p_cell = self.gas_controller.read_pressure()

        # Log experimental parameters
        if self.gas_2:
            self.session.log_experimental_parameters(
                gas=(self.gas, self.gas_2),
                p_gas_meas=(p_mfld, p_cell),
                t_cell=self.temp.read_temperature(),
                p_gas_calc=(self.p_cell_calc, getattr(self, "p_cell_calc_2", None)),
                chiller_state=self.chiller_state,
            )
        else:
            self.session.log_experimental_parameters(
                gas=self.gas,
                p_gas_meas=(p_mfld, p_cell),
                t_cell=self.temp.read_temperature(),
                p_gas_calc=self.p_cell_calc,
                chiller_state=self.chiller_state,
            )

        # Start pressure logging
        pressure_logger = self.start_pressure_log(p_mfld_initial, p_cell_initial)

        # Wait for Opus acquisition to complete
        opus_thread.join()
        pressure_logger.stop()

        # Evacuate cell with rough pump
        self.gas_controller.evacuate_cell("RoughPump")

        # Opus Vertex80 for evacuation
        self.ftir.opus_vertex80(
            {
                "end_experiment": True,
                "foldername": self.session.folder_name,
                "filename": self.session.file_name + "_evacuation",
                "do_bckg": False,
                "do_fit": False,
                "reset_fileids": False,
            }
        )

        # Mark experiment as successful
        self.session.mark_success(success=True)
        time.sleep(5)

        # Check if new sample experiment
        self.session.is_new_sample_experiment()
        time.sleep(5)

        # Copy files to share drive
        try:
            # Copy README file
            shutil.copy2(
                self.session.path_readme,
                os.path.join(
                    self.session.paths.share_drive_peak_fit_root,
                    self.session.folder_name,
                    f"{self.session.file_name}_README.md",
                ),
            )
            # Copy pressure log file
            shutil.copy2(
                self.session.path_pressure_log,
                os.path.join(
                    self.session.paths.share_drive_pressure_data_root,
                    self.session.folder_name,
                    f"{self.session.file_name}_pressureLog.csv",
                ),
            )

            # Send readme command to Opus
            self.ftir.opus_vertex80({"readme": True})

        except Exception as e:
            logger.info(f"An error occurred while copying the file: {e}")

    def introduce_pretreatment_gas_to_cell(
        self,
        target_temp: int,
        hold_time: float,
        ramp_rate: int = 0,
        variac_cmd: bool = True,
    ) -> None:
        """Introduce pretreatment gas to the cell and apply temperature ramp/hold."""
        # Deliver gas to cell
        self.gas_controller.deliver_gas_to_cell()

        # Apply temperature ramp/hold using Watlow controller
        t_cell, rate, duration = self.temp.watlow(
            self.session.file_name,
            self.session.folder_name,
            target_temp,
            hold_time,
            ramp_rate,
            variac_cmd,
        )

        # Read pressure after gas delivery and temperature stabilization
        self.dt, self.p_mfld, p_cell = self.gas_controller.read_pressure()

        # Log pretreatment parameters
        if self.gas_2:
            self.session.log_pretreatment(
                gas=(self.gas, self.gas_2),
                p_gas_meas=(self.p_mfld, p_cell),
                t_cell=t_cell,
                rate=rate,
                duration=duration,
                p_gas_calc=(self.p_cell_calc, getattr(self, "p_cell_calc_2", None)),
                chiller_state=self.chiller_state,
            )
        else:
            self.session.log_pretreatment(
                gas=self.gas,
                p_gas_meas=(self.p_mfld, p_cell),
                t_cell=t_cell,
                rate=rate,
                duration=duration,
                p_gas_calc=self.p_cell_calc,
                chiller_state=self.chiller_state,
            )

    def chiller_variac_state(
        self, chiller_cmd: bool, variac_cmd: bool, variac_vsl_cmd: bool
    ) -> None:
        """Set the state of the chiller and variac. The chiller_cmd is used to set the state of the chiller and the variac_cmd is used to set the state of the variac."""
        if chiller_cmd is not None:
            self.chiller_state = chiller_cmd
            self.temp.chiller_state(chiller_cmd)
        if variac_cmd is not None:
            self.temp.variac_state(variac_cmd)
        if variac_vsl_cmd is not None:
            self.temp.kasa_plug_state("variac_id_vsl", variac_vsl_cmd)
        """
        [fix] These are devices controlled by Kasa plugs. Two plugs control the variac and one a chiller.
            We should just use kasa_plug_state.
        """

    def start_pressure_log(
        self, p_mfld_initial: Any, p_cell_initial: Any
    ) -> PressureLogger:
        """Start pressure logging and return the logger handle."""
        log_path = self.session.path_pressure_log
        pressure_logger = PressureLogger(
            pressure=self.gas_controller.pressure_adapter(),
            physics=self.session.volumes,
            path=log_path,
            p_mfld_initial=p_mfld_initial,
            p_cell_initial=p_cell_initial,
            mass_g=self.session.sample.mass_g,
            metal_load_wt_percent=self.session.sample.metal_load_wt_percent,
            metal_molar_mass_g_mol=self.session.sample.metal_molar_mass_g_mol,
            temperature_k=self.gas_controller.temperature_k,
            gas_constant=self.gas_controller.gas_constant,
        )
        pressure_logger.start()

        return pressure_logger

    def start_temperature_log(self) -> TemperatureLogger:
        """Start temperature logging and return the logger handle."""
        log_path = (
            Path(self.session.paths.data_directory)
            / self.session.folder_name
            / f"{self.session.file_name}_tempLog.csv"
        )
        temp_logger = TemperatureLogger(
            temperature=self.temp.temperature_adapter(),
            path=log_path,
            read_interval_s=5,
        )
        temp_logger.start()
        return temp_logger
