"""Adsorption experiment protocol using the new architecture layers.

This module provides a v2 adsorption experiment class that coordinates
session metadata, control-layer operations, and hardware access through the
new typed interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any
from typing import cast

from src.control.gas_delivery import GasDelivery
from src.control.spectrometer_control import SpectrometerController
from src.control.temperature_control import TemperatureController
from src.datalog.mass_spec_logger import MassSpecLogger
from src.experiments.session import ExperimentSession
from src.hardware.connections import DeviceManager
from src.core import get_logger


logger = get_logger(__name__)


@dataclass
class AdsorptionExperiment:
    """V2 adsorption experiment orchestrator.

    This class will port legacy adsorption protocol methods to the new
    architecture while preserving operation ordering and timing behavior.
    """

    session: ExperimentSession
    devices: DeviceManager
    gas_controller: GasDelivery
    temp: TemperatureController
    spec: SpectrometerController

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

        # Legacy extrel_sequence('start') behavior: register 1 -> value 2
        success = cast(Any, self.devices.mass_spec).write_register(address=1, value=2)
        if success:
            logger.info("Extrel sequence started")
        else:
            logger.info("Failed to set Extrel sequence")

        ms_logger = MassSpecLogger(
            mass_spec=cast(Any, self.devices.mass_spec),
            path=self._path(cast(str, self.session.path_ms_log)),
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
            time.sleep(60 * 15)
            ms_logger.stop()

            # Legacy extrel_sequence('stop') behavior: register 1 -> value 9
            success = cast(Any, self.devices.mass_spec).write_register(address=1, value=9)
            if success:
                logger.info("Extrel sequence stopped")
            else:
                logger.info("Failed to set Extrel sequence")
            self.gas_controller.valves.close("MassSpec")
            self.gas_controller.valves.open("irCell")

        self.dt, self.p_mfld, p_cell = cast(Any, self.devices.pressure).read()

        if log_params:
            p_mfld_value = cast(float, self.p_mfld)
            p_cell_value = cast(float, p_cell)
            t_cell_value = cast(float, cast(Any, self.devices.temperature).read_temperature())
            self.session.log_pretreatment(
                gas=self.gas,
                p_gas_meas=(p_mfld_value, p_cell_value),
                t_cell=t_cell_value,
                rate=rate,
                duration=duration,
                chiller_state=self.chiller_state,
            )

    @staticmethod
    def _path(value: str) -> "Any":
        from pathlib import Path

        return Path(value)
