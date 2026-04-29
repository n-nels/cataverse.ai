"""NI USB-6009 analog I/O adapter for hardware-layer actuator control.

This module consolidates legacy NI-DAQ access and actuator mapping into one
class with cached NI device instances.
"""

from __future__ import annotations

import logging

import nidaqmx
from nidaqmx.constants import AcquisitionType

from src.hardware.errors import HardwareMappingError


logger = logging.getLogger(__name__)


class NI_USB6009:
    """NI USB-6009 device helper for analog input/output operations."""

    def __init__(self, device_name: str):
        self.device_name = device_name

    def read_analog_input(self, channel: str) -> float:
        """Read one analog input value from the specified channel."""

        try:
            with nidaqmx.Task() as task:
                task.ai_channels.add_ai_voltage_chan(
                    f"{self.device_name}/{channel}",
                    min_val=0.0,
                    max_val=5.0,
                )
                task.timing.cfg_samp_clk_timing(
                    rate=10000,
                    sample_mode=AcquisitionType.FINITE,
                    samps_per_chan=1,
                )
                analog_value = task.read()
                return float(analog_value)
        except nidaqmx.DaqError as exc:
            logger.error("Failed to read analog input from channel %s: %s", channel, exc)
            return 0.0

    def write_analog_output(self, channel: str, value: float) -> bool:
        """Write one analog output value to the specified channel."""

        try:
            with nidaqmx.Task() as task:
                task.ao_channels.add_ao_voltage_chan(
                    f"{self.device_name}/{channel}",
                    min_val=0.0,
                    max_val=5.0,
                )
                task.write(value)
                return True
        except nidaqmx.DaqError as exc:
            logger.error(
                "Failed to write analog output to channel %s: %s",
                channel,
                exc,
            )
            return False


class AnalogIO:
    """Analog I/O helper that resolves actuator IDs to NI device channels."""

    def __init__(self, device_map: dict[str, tuple[str, str]]) -> None:
        self.device_map = device_map
        self._devices: dict[str, NI_USB6009] = {}

    def _get_device(self, device_name: str) -> NI_USB6009:
        """Return cached NI device instance by device name."""

        if device_name not in self._devices:
            self._devices[device_name] = NI_USB6009(device_name)
        return self._devices[device_name]

    def write(self, actuator_id: str, voltage: float) -> bool:
        """Write voltage to mapped analog output for an actuator ID."""

        device_channel = self.device_map.get(actuator_id)
        if not device_channel:
            raise HardwareMappingError(f"No mapping found for actuator ID: {actuator_id}")

        device_name, channel = device_channel
        device = self._get_device(device_name)
        return device.write_analog_output(channel, voltage)

    def read(self, device_name: str, channel: str) -> float:
        """Read analog input from a specific NI device and channel."""

        device = self._get_device(device_name)
        return device.read_analog_input(channel)
