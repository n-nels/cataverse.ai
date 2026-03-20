from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, call, patch

import pytest

from src.control.gas_delivery import GasDelivery


def test_deliver_gas_to_manifold_executes_expected_valve_write_sequence() -> None:
    valves = MagicMock()
    valves.write.side_effect = lambda actuator_id, voltage: (actuator_id, float(voltage))

    pressure = MagicMock()
    pressure.read.side_effect = [
        (datetime.now(), 0.0, 0.0),   # initial p_mfld_start
        (datetime.now(), 0.30, 0.0),  # first else-branch read
        (datetime.now(), 1.00, 0.0),  # branch update p_mfld_i
        (datetime.now(), 1.05, 0.0),  # next loop read, causes while-exit on next check
        (datetime.now(), 1.00, 0.0),  # post-shutdown equilibration read
    ]

    gas = GasDelivery(valves=valves, pressure=pressure)

    with patch("src.control.gas_delivery.time.sleep"):
        actuator_id, p_final = gas.deliver_gas_to_manifold(
            filename=None,
            foldername=None,
            id="H2",
            target=1.0,
            openMS=False,
        )

    assert actuator_id == "H2"
    assert p_final == pytest.approx(1.0)

    assert valves.close.call_args_list == [
        call("RoughPump"),
        call("TurboPump"),
        call("irCell"),
    ]

    # Critical sequence: initialize irCell write, staged H2 writes, then close gas valve.
    write_calls = valves.write.call_args_list
    assert [c.args[0] for c in write_calls] == ["irCell", "H2", "H2", "H2", "H2", "H2"]
    assert [c.args[1] for c in write_calls] == pytest.approx([1.0, 1.1, 1.2, 1.16, 1.26, 1.0])

    # Cross-method ordering: startup closes happen before first write.
    assert valves.mock_calls[:4] == [
        call.close("RoughPump"),
        call.close("TurboPump"),
        call.close("irCell"),
        call.write("irCell", 1.0),
    ]


def test_evacuate_cell_uses_roughpump_sequence_then_opens_turbopump() -> None:
    valves = MagicMock()
    valves.write.side_effect = lambda actuator_id, voltage: (actuator_id, float(voltage))

    pressure = MagicMock()
    pressure.read.side_effect = [
        (datetime.now(), 1.00, 0.0),  # initial p_mfld_i
        (datetime.now(), 1.02, 0.0),  # first pressure_diff calc (<=0.05)
        (datetime.now(), 1.00, 0.0),  # pressure_diff > 0 loop: i
        (datetime.now(), 1.00, 0.0),  # pressure_diff > 0 loop: f -> 0.0
    ]

    gas = GasDelivery(valves=valves, pressure=pressure)

    with patch("src.control.gas_delivery.time.sleep"):
        final_id = gas.evacuate_cell("TurboPump")

    assert final_id == "TurboPump"

    # Safety closes happen before opening irCell.
    assert valves.close.call_args_list[:2] == [
        call("TurboPump"),
        call("MassSpec"),
    ]
    assert valves.open.call_args_list == [call("irCell"), call("TurboPump")]

    # Sequence is routed through RoughPump when initial id != RoughPump.
    assert valves.write.call_args_list[0] == call("RoughPump", 1.0)
    assert valves.write.call_args_list[-1] == call("RoughPump", 5.0)

    # Cross-method ordering: final TurboPump open occurs after RoughPump reaches 5.0.
    last_write_index = max(i for i, c in enumerate(valves.mock_calls) if c == call.write("RoughPump", 5.0))
    open_turbo_index = max(i for i, c in enumerate(valves.mock_calls) if c == call.open("TurboPump"))
    assert open_turbo_index > last_write_index
