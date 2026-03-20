from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, call, patch

import pytest

from src.control.valves import ValveController
from src.core.config import (
    actuator_mass_spec_open_max_cell_torr,
    actuator_post_write_sleep_s,
    actuator_turbo_open_max_manifold_torr,
    actuator_turbo_pressure_poll_s,
    actuator_voltage_closed,
    actuator_voltage_max_write,
    actuator_voltage_open,
)


def test_open_calls_analog_write_with_open_voltage_then_sleeps() -> None:
    analog_io = MagicMock()
    pressure = MagicMock()
    valves = ValveController(analog_io=analog_io, pressure=pressure)

    ordered_events: list[str] = []

    def write_side_effect(*args, **kwargs):
        ordered_events.append("write")
        return True

    def sleep_side_effect(*args, **kwargs):
        ordered_events.append("sleep")

    analog_io.write.side_effect = write_side_effect

    with patch("src.control.valves.time.sleep", side_effect=sleep_side_effect) as sleep_mock:
        actuator_id, voltage = valves.open("H2")

    assert actuator_id == "H2"
    assert voltage == actuator_voltage_open
    analog_io.write.assert_called_once_with("H2", actuator_voltage_open)
    sleep_mock.assert_called_once_with(actuator_post_write_sleep_s)
    assert ordered_events == ["write", "sleep"]


def test_safe_turbo_open_roughs_until_pressure_below_limit_then_closes() -> None:
    analog_io = MagicMock()
    pressure = MagicMock()
    pressure.read.side_effect = [
        (datetime.now(), actuator_turbo_open_max_manifold_torr + 0.1, 0.0),
        (datetime.now(), actuator_turbo_open_max_manifold_torr + 0.05, 0.0),
        (datetime.now(), actuator_turbo_open_max_manifold_torr - 0.001, 0.0),
    ]
    valves = ValveController(analog_io=analog_io, pressure=pressure)

    with patch("src.control.valves.time.sleep") as sleep_mock:
        valves.safe_turbo_open()

    assert analog_io.write.call_args_list == [
        call("RoughPump", actuator_voltage_open),
        call("RoughPump", actuator_voltage_closed),
    ]
    assert pressure.read.call_count == 3
    poll_sleep_calls = [
        c for c in sleep_mock.call_args_list if c == call(actuator_turbo_pressure_poll_s)
    ]
    assert len(poll_sleep_calls) == 2


def test_safe_mass_spec_open_exits_when_cell_pressure_above_limit() -> None:
    analog_io = MagicMock()
    pressure = MagicMock()
    pressure.read.return_value = (
        datetime.now(),
        0.0,
        actuator_mass_spec_open_max_cell_torr + 0.01,
    )
    valves = ValveController(analog_io=analog_io, pressure=pressure)

    with patch("src.control.valves.time.sleep"):
        with pytest.raises(SystemExit, match="Pressure of cell above limit to open safely"):
            valves.safe_mass_spec_open()

    analog_io.write.assert_called_once_with("irCell", actuator_voltage_closed)


def test_write_over_max_voltage_closes_then_exits() -> None:
    analog_io = MagicMock()
    pressure = MagicMock()
    valves = ValveController(analog_io=analog_io, pressure=pressure)

    with pytest.raises(SystemExit, match="Gas bulb empty"):
        valves.write("H2", actuator_voltage_max_write + 0.01)

    analog_io.write.assert_called_once_with("H2", actuator_voltage_closed)
