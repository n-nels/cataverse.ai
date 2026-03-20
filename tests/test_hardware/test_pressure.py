from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch
from typing import cast

from src.hardware.pressure import MKSPressure, PressureReading


def test_read_returns_pressure_reading_on_valid_response() -> None:
    conn = MagicMock()
    conn.is_open = True
    conn.readline.return_value = b"1.23 4.56\n"

    pressure = MKSPressure(conn)
    reading = pressure.read()

    assert isinstance(reading, PressureReading)
    assert isinstance(reading.timestamp, datetime)
    assert reading.manifold == 1.23
    assert reading.cell == 4.56
    conn.write.assert_called_once()


def test_read_attempts_reconnect_after_write_error() -> None:
    conn = MagicMock()
    conn.is_open = True
    conn.port = "COM8"
    conn.baudrate = 9600
    conn.timeout = 2
    conn.write.side_effect = [Exception("boom"), None]
    conn.readline.return_value = b"2.0 3.0\n"

    reconnected_conn = MagicMock()
    reconnected_conn.is_open = True
    reconnected_conn.port = "COM8"
    reconnected_conn.baudrate = 9600
    reconnected_conn.timeout = 2
    reconnected_conn.write.return_value = None
    reconnected_conn.readline.return_value = b"2.0 3.0\n"

    pressure = MKSPressure(conn)
    serial_cls_mock = MagicMock(return_value=reconnected_conn)
    pressure._serial_cls = cast(type, serial_cls_mock)

    with patch("src.hardware.pressure.time.sleep") as sleep_mock:
        reading = pressure.read()

    assert reading.manifold == 2.0
    assert reading.cell == 3.0
    serial_cls_mock.assert_called_once_with("COM8", baudrate=9600, timeout=2)
    reconnected_conn.write.assert_called_once()
    sleep_mock.assert_any_call(2)


def test_disconnect_closes_open_connection() -> None:
    conn = MagicMock()
    conn.is_open = True
    pressure = MKSPressure(conn)

    pressure.disconnect()

    conn.close.assert_called_once()
