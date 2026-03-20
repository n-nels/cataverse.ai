from __future__ import annotations

import struct
from unittest.mock import MagicMock, patch

import pytest

from src.hardware.temperature import WatlowTemperature


def _regs_from_fahrenheit(value_f: float) -> list[int]:
    packed = struct.pack(">f", value_f)
    hi, lo = struct.unpack(">HH", packed)
    return [lo, hi]


def test_read_temperature_returns_celsius() -> None:
    client = MagicMock()
    rr = MagicMock()
    rr.isError.return_value = False
    rr.registers = _regs_from_fahrenheit(212.0)
    client.read_holding_registers.return_value = rr

    watlow = WatlowTemperature(client)
    value = watlow.read_temperature()

    assert value == 100.0


def test_set_temperature_writes_registers() -> None:
    client = MagicMock()
    wr = MagicMock()
    wr.isError.return_value = False
    client.write_registers.return_value = wr

    watlow = WatlowTemperature(client)
    ok = watlow.set_temperature(100.0)

    assert ok is True
    expected_hi, expected_lo = struct.unpack(">HH", struct.pack(">f", 212.0))
    client.write_registers.assert_called_once_with(
        address=2160,
        values=[expected_lo, expected_hi],
    )


def test_read_temperature_returns_none_on_modbus_error() -> None:
    client = MagicMock()
    rr = MagicMock()
    rr.isError.return_value = True
    client.read_holding_registers.return_value = rr

    watlow = WatlowTemperature(client)

    assert watlow.read_temperature() is None


def test_read_temperature_malfunction_path_calls_exit() -> None:
    client = MagicMock()

    rr_bad_temp = MagicMock()
    rr_bad_temp.isError.return_value = False
    rr_bad_temp.registers = _regs_from_fahrenheit(-1000.0)

    rr_error_code = MagicMock()
    rr_error_code.isError.return_value = False
    rr_error_code.registers = [9999, 0]

    rr_setpoint = MagicMock()
    rr_setpoint.isError.return_value = False
    rr_setpoint.registers = _regs_from_fahrenheit(77.0)

    client.read_holding_registers.side_effect = [rr_bad_temp, rr_error_code, rr_setpoint]

    watlow = WatlowTemperature(client)
    with patch("src.hardware.temperature.sys.exit", side_effect=SystemExit):
        with pytest.raises(SystemExit):
            watlow.read_temperature()

    client.write_registers.assert_called_once()


def test_read_temperature_returns_none_when_client_missing() -> None:
    watlow = WatlowTemperature(None)
    assert watlow.read_temperature() is None
