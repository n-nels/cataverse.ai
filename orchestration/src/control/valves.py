"""Behavior-frozen valve and actuator control for the new control layer.

This module ports legacy actuator sequencing with identical safety checks,
branching, and timing, while delegating writes/reads to hardware-layer adapters.
"""

from __future__ import annotations

import logging
import time

from src.core.config_loader import ActuatorConfig
from src.control.errors import SafetyLimitExceeded
from src.hardware.analog_io import AnalogIO
from src.hardware.pressure import MKSPressure


logger = logging.getLogger(__name__)


class ValveController:
    """Behavior-frozen valve controller using hardware-layer adapters.

    Concurrency
    -----------
    No method on this class is thread-safe.  ``write``, ``dither``, and
    ``close_all`` share the ``AnalogIO`` NI-DAQmx session and the
    ``MKSPressure`` serial connection.  Concurrent calls from multiple threads
    will produce undefined hardware behaviour.  Callers must serialise access
    externally.
    """

    def __init__(
        self, analog_io: AnalogIO, pressure: MKSPressure, config: ActuatorConfig
    ) -> None:
        self.analog_io = analog_io
        self.pressure = pressure
        self.config = config

    def write(self, actuator_id: str, voltage: float) -> tuple[str, float]:
        """Write raw voltage to one actuator channel.

        Raises:
            SafetyLimitExceeded: If *voltage* exceeds ``voltage_max_write``
                (gas bulb empty). The actuator is closed before raising.
            HardwareMappingError: If *actuator_id* is not in the actuator map.
        """

        if voltage > self.config.voltage_max_write:
            self.analog_io.write(actuator_id, self.config.voltage_closed)
            raise SafetyLimitExceeded(
                f"Gas bulb empty: {actuator_id} voltage {voltage} exceeds "
                f"max write {self.config.voltage_max_write}",
                actuator_id=actuator_id,
                measured=voltage,
                limit=self.config.voltage_max_write,
            )

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
        """Run safety sequence before opening MassSpec.

        Raises:
            SafetyLimitExceeded: If cell pressure exceeds the configured
                safe-open limit.
        """

        self.close("irCell")
        dt, p_mfld, p_cell = self.pressure.read()
        if p_cell > self.config.mass_spec_open_max_cell_torr:
            raise SafetyLimitExceeded(
                f"Cell pressure {p_cell} Torr exceeds safe limit "
                f"{self.config.mass_spec_open_max_cell_torr} Torr to open MassSpec",
                actuator_id="MassSpec",
                measured=p_cell,
                limit=self.config.mass_spec_open_max_cell_torr,
            )
        return None

    def _log_write(self, actuator_id: str, value: float) -> None:
        """Log actuator write id/value with timestamp."""

        logger.info("%s write value is %s", actuator_id, value)
