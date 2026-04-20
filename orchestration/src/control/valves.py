"""Behavior-frozen valve and actuator control for the new control layer.

This module ports legacy actuator sequencing with identical safety checks,
branching, and timing, while delegating writes/reads to hardware-layer adapters.
"""

from __future__ import annotations

import logging
import sys
import time

from src.config_loader import ActuatorConfig
from src.hardware.analog_io import AnalogIO
from src.hardware.pressure import MKSPressure


logger = logging.getLogger(__name__)


class ValveController:
    """Behavior-frozen valve controller using hardware-layer adapters."""

    def __init__(
        self, analog_io: AnalogIO, pressure: MKSPressure, config: ActuatorConfig
    ) -> None:
        self.analog_io = analog_io
        self.pressure = pressure
        self.config = config

    def write(self, actuator_id: str, voltage: float) -> tuple[str, float]:
        """Write raw voltage to one actuator channel."""

        if voltage > self.config.voltage_max_write:
            self.analog_io.write(actuator_id, self.config.voltage_closed)
            # TODO: consider custom exception
            sys.exit("Gas bulb empty")

        self.analog_io.write(actuator_id, voltage)
        return actuator_id, round(float(voltage), 2)

    def close(self, actuator_id: str) -> tuple[str, float]:
        """Close one actuator and apply post-write delay."""

        voltage = self.config.voltage_closed
        actuator_id, write_value = self.write(actuator_id, voltage)
        self._log_write(actuator_id, write_value)
        time.sleep(self.config.post_write_sleep_s)
        return actuator_id, float(voltage)

    def close_all(self, device_map: dict[str, tuple[str, str]]) -> None:
        """Close all actuators listed in device map iteration order."""

        logger.info("Closing all actuators...")
        for actuator_id in device_map:
            self.close(actuator_id)
        logger.info("All actuators closed.")
        return None

    def open(self, actuator_id: str) -> tuple[str, float]:
        """Open one actuator with behavior-frozen safety checks."""

        safety_checks = {
            "TurboPump": self.safe_turbo_open,
            "MassSpec": self.safe_mass_spec_open,
        }

        if actuator_id in safety_checks:
            safety_checks[actuator_id]()

        voltage = self.config.voltage_open
        actuator_id, write_value = self.write(actuator_id, voltage)
        self._log_write(actuator_id, write_value)
        time.sleep(self.config.post_write_sleep_s)
        return actuator_id, float(voltage)

    def safe_turbo_open(self) -> None:
        """Run safety sequence before opening TurboPump."""

        dt, p_mfld, p_cell = self.pressure.read()
        if p_mfld > self.config.turbo_open_max_manifold_torr:
            self.open("RoughPump")

            while p_mfld > self.config.turbo_open_max_manifold_torr:
                time.sleep(self.config.turbo_pressure_poll_s)
                dt, p_mfld, p_cell = self.pressure.read()
                logger.info("Manifold pressure is %s", p_mfld)

            self.close("RoughPump")
        else:
            self.close("RoughPump")
        return None

    def safe_mass_spec_open(self) -> None:
        """Run safety sequence before opening MassSpec."""

        self.close("irCell")
        dt, p_mfld, p_cell = self.pressure.read()
        if p_cell > self.config.mass_spec_open_max_cell_torr:
            # TODO: consider custom exception
            sys.exit("Pressure of cell above limit to open safely")
        return None

    def _log_write(self, actuator_id: str, value: float) -> None:
        """Log actuator write id/value with timestamp."""

        logger.info("%s write value is %s", actuator_id, value)
