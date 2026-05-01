"""Mock device factory for smoke-testing without real hardware.

Used by ``main.py --mock`` to construct a ``DeviceManager``-shaped object
graph that returns canned values for every hardware call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from src.core.config_loader import AppConfig

from src.hardware.connections import DeviceManager


def create_mock_devices(config: AppConfig) -> MagicMock:
    """Return a MagicMock that quacks like a connected DeviceManager."""

    devices = MagicMock(spec=DeviceManager)
    devices.config = config.hardware

    devices.pressure = MagicMock()
    devices.pressure.read.return_value = (MagicMock(), 0.01, 0.01)

    devices.temperature = MagicMock()
    devices.temperature.read_temperature.return_value = 25.0

    devices.mass_spec = MagicMock()
    devices.mass_spec.write_register.return_value = True
    devices.mass_spec.read_registers.return_value = [1, 2]

    devices.analog_io = MagicMock()
    devices.analog_io.write.return_value = None

    devices.spectrometer = MagicMock()
    devices.spectrometer.send.return_value = "OK"
    devices.spectrometer.receive.return_value = "fileid123"

    devices.power = MagicMock()
    devices.power.set_state.return_value = True

    devices.connect.return_value = None
    devices.disconnect.return_value = None

    return devices
