"""Adsorption experiment protocol using the new architecture layers.

This module provides an adsorption experiment class that coordinates
session metadata, control-layer operations, and hardware access through
typed interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import shutil
import threading
import time
import os
import logging
from typing import Any

from src.control.gas_delivery import GasDelivery
from src.control.mass_spec_control import MassSpecController
from src.control.spectrometer_control import SpectrometerController
from src.control.temperature_control import TemperatureController
from src.hardware.pressure import MKSPressure
from src.hardware.temperature import WatlowTemperature
from src.datalog.mass_spec_logger import MassSpecLogger
from src.datalog.pressure_logger import PressureLogger
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
    ms: MassSpecController
    pressure: MKSPressure
    temperature: WatlowTemperature

    # Runtime state — set by protocol methods during experiment execution.
    gas: str | tuple[str, str] | None = field(default=None)
    gas_2: str | None = field(default=None)
    p_mfld: float | None = field(default=None)
    p_cell_calc: float | tuple[float, float] | None = field(default=None)
    dt: Any = field(default=None)
    chiller_state: bool | None = field(default=None)
    p_mfld_2: float | None = field(default=None)
    p_cell_calc_2: float | None = field(default=None)

    def acquire_ms_spectra(self) -> MassSpecLogger:
        """Start mass-spec streaming with legacy valve/sequence ordering."""

        self.gas_controller.valves.close("irCell")
        self.gas_controller.valves.open("MassSpec")
        time.sleep(30)

        # Extrel sequence start from config
        success = self.ms.start_sequence()
        if success:
            logger.info("Extrel sequence started")
        else:
            logger.info("Failed to set Extrel sequence")

        ms_logger = self.session.start_mass_spec_log(
            mass_spec=self.ms.mass_spec_adapter(),
            stream_tags=self.ms.stream_tags,
        )
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

        t_cell, rate, duration = self.heat_cell(
            target_temp, hold_time, ramp_rate, variac_cmd
        )

        if enable_ms_stream and ms_logger is not None:
            time.sleep(60 * 15)  # [fix] Should be arg
            ms_logger.stop()

            # Extrel sequence stop from config
            success = self.ms.stop_sequence()
            if success:
                logger.info("Extrel sequence stopped")
            else:
                logger.info("Failed to set Extrel sequence")
            self.gas_controller.valves.close("MassSpec")
            self.gas_controller.valves.open("irCell")

        self.dt, self.p_mfld, p_cell = self.gas_controller.read_pressure()

        if log_params:
            self._log_pretreatment(
                t_cell, rate, duration, p_cell=p_cell, log_gas_calc=False
            )

    def cool_cell(
        self, target_temp: int, hold_time: float, variac_cmd: bool, ramp_rate: int = 0
    ) -> None:
        """Cool the cell to a target temperature. The variac_cmd is used to keep the cell on even at target temperature."""
        t_cell, rate, duration = self.heat_cell(
            target_temp, hold_time, ramp_rate, variac_cmd
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

    def heat_cell(
        self,
        target_temp: int,
        hold_time: float,
        ramp_rate: int = 20,
        variac_cmd: bool = True,
    ) -> tuple[float, float, float]:
        """Heat or cool the cell to target temperature with optional ramp and hold.

        Temperature-only operation. Does not change valve states or deliver gas.
        The caller is responsible for ensuring appropriate pump/vacuum state.

        Returns:
            Tuple of (target_temp, ramp_rate, hold_duration) as stored by the controller.
        """
        t_cell, rate, duration = self.temp.watlow(
            self.session.file_name,
            self.session.folder_name,
            target_temp,
            hold_time,
            ramp_rate,
            variac_cmd,
        )
        return t_cell, rate, duration

    def supply_gas_to_mfld(self, gas: str, target_pressure: float) -> None:
        """Supply gas to the manifold. The target pressure corresponds to the pressure in the total volume of the system."""
        limit = self.session.volumes.max_target_pressure
        if target_pressure > limit:
            raise ValueError(
                f"Target pressure {target_pressure:.2f} Torr exceeds gauge-derived "
                f"limit of {limit:.2f} Torr for single-gas delivery."
            )

        if self.gas_2:
            self.gas_2 = None

        # Calculate target pressure for the manifold based on volume ratios
        val = (
            self.session.volumes.total
            / (self.session.volumes.source_m1m2m3)
            * target_pressure
        )
        self.gas, self.p_mfld = self.gas_controller.deliver_gas_to_manifold(
            self.session.path_actuator_log,
            id=gas,
            target=val,
            openMS=True,
        )

        self.p_cell_calc = cell_pressure_from_manifold(
            self.p_mfld,
            self.session.volumes.source_m1m2m3,
            self.session.volumes.total,
        )

    def supply_gases_to_mfld(
        self, gas: list[str], target_pressure: list[float]
    ) -> None:
        """Supply gases to the manifold. The target pressure corresponds to the pressure in the total volume of the system."""
        limits = self.session.volumes.max_target_pressure_dual
        for i, (p, lim) in enumerate(zip(target_pressure, limits)):
            if p > lim:
                raise ValueError(
                    f"Target pressure for gas {gas[i]} ({p:.2f} Torr) exceeds "
                    f"gauge-derived limit of {lim:.2f} Torr."
                )

        # Calculate target pressures for each gas based on volume ratios
        val_1 = (
            (self.session.volumes.total) / self.session.volumes.m3 * target_pressure[0]
        )
        val_2 = (
            (self.session.volumes.total)
            / (self.session.volumes.source_m1m2)
            * target_pressure[1]
        )

        # Supply first gas to manifold
        self.gas, self.p_mfld = self.gas_controller.deliver_gas_to_manifold(
            self.session.path_actuator_log,
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
            self.session.path_actuator_log,
            id=gas[1],
            target=val_2,
            openMS=True,
        )
        self.p_cell_calc_2 = cell_pressure_from_manifold(
            self.p_mfld_2,
            self.session.volumes.source_m1m2,
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
        self.ftir.send_opus_request(
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
                False,  # reset_fileids handled in initial request
                False,  # do_bckg handled in initial request
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
        self.ftir.send_opus_request(
            {
                "end_experiment": True,
                "foldername": self.session.folder_name,
                "filename": self.session.file_name + "_evacuation",
                "do_bckg": False,
                "do_fit": False,
                "reset_fileids": False,
            }
        )

    def finalize(self, success: bool) -> None:
        """End-of-experiment cleanup: mark success, copy JSON/pressure files, notify OPUS.

        Safe to call multiple times — ``mark_success`` and share-drive copies
        are idempotent (copy overwrites, success field is rewritten).
        Must be called after ``pressure_logger.stop()`` so the CSV is not
        held open during the copy on Windows.
        """

        self.session.mark_success(success=success)
        time.sleep(5)

        try:
            shutil.copy2(
                self.session.path_exp_params,
                os.path.join(
                    self.session.paths.share_drive_peak_fit_root,
                    self.session.folder_name,
                    f"{self.session.file_name}_expParams.json",
                ),
            )
            shutil.copy2(
                self.session.path_pressure_log,
                os.path.join(
                    self.session.paths.share_drive_pressure_data_root,
                    self.session.folder_name,
                    f"{self.session.file_name}_pressureLog.csv",
                ),
            )

        except Exception as e:
            logger.info(f"An error occurred while copying the file: {e}")

    def deliver_gas_to_cell(self) -> None:
        """Open irCell to admit manifold gas into the cell."""
        self.gas_controller.deliver_gas_to_cell()
        self.dt, self.p_mfld, _p_cell = self.gas_controller.read_pressure()

    def _log_pretreatment(
        self,
        t_cell: float,
        rate: float,
        duration: float,
        *,
        p_cell: float | None = None,
        log_gas_calc: bool = False,
    ) -> None:
        """Log pretreatment parameters from current instance state.

        Args:
            t_cell: Target temperature (°C).
            rate: Ramp rate (°C/min).
            duration: Hold duration (hours).
            p_cell: Measured cell pressure.
            log_gas_calc: If True, include calculated cell pressure in the log
                (only meaningful when gas has been supplied to the cell).
        """
        gas: Any = (self.gas, self.gas_2) if self.gas_2 else self.gas  # type: ignore[assignment]

        p_gas_calc: Any = None
        if log_gas_calc:
            if self.gas_2:
                p_gas_calc = (self.p_cell_calc, self.p_cell_calc_2)  # type: ignore[assignment]
            elif self.p_cell_calc is not None:
                p_gas_calc = self.p_cell_calc

        self.session.log_pretreatment(
            gas=gas,
            p_gas_meas=(self.p_mfld, p_cell),
            t_cell=t_cell,
            rate=rate,
            duration=duration,
            p_gas_calc=p_gas_calc,
            chiller_state=self.chiller_state,
        )

    def chiller_variac_state(
        self, chiller_cmd: bool, variac_cmd: bool, variac_vsl_cmd: bool
    ) -> None:
        """Set the state of the chiller and variac smart plugs."""
        self.chiller_state = chiller_cmd
        self.temp.set_heating_elements(chiller_cmd, variac_cmd, variac_vsl_cmd)

    def start_pressure_log(
        self, p_mfld_initial: Any, p_cell_initial: Any
    ) -> PressureLogger:
        """Start pressure logging and return the logger handle."""
        return self.session.start_pressure_log(
            pressure=self.pressure,
            p_mfld_initial=p_mfld_initial,
            p_cell_initial=p_cell_initial,
        )
