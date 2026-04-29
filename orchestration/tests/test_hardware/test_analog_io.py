from __future__ import annotations

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from src.hardware.analog_io import AnalogIO


def test_write_uses_mapping_and_cached_device_instances() -> None:
    with patch("src.hardware.analog_io.NI_USB6009") as device_cls:
        fake_device = MagicMock()
        fake_device.write_analog_output.return_value = True
        device_cls.return_value = fake_device

        aio = AnalogIO({"H2": ("dev1", "ao0")})
        assert aio.write("H2", 5.0) is True
        assert aio.write("H2", 1.0) is True

        device_cls.assert_called_once_with("dev1")
        assert fake_device.write_analog_output.call_count == 2


def test_write_raises_for_unknown_mapping() -> None:
    from src.hardware.errors import HardwareMappingError

    aio = AnalogIO({})
    with pytest.raises(HardwareMappingError):
        aio.write("unknown", 1.0)


def test_read_delegates_to_device() -> None:
    aio = AnalogIO({})
    fake_device = MagicMock()
    fake_device.read_analog_input.return_value = 1.23
    aio._get_device = MagicMock(return_value=fake_device)

    value = aio.read("dev1", "ai0")

    assert value == 1.23
    fake_device.read_analog_input.assert_called_once_with("ai0")
