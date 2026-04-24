from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import src.control.temperature_control as temperature_control_module
from src.core.config_loader import load_config
from src.control.temperature_control import TemperatureController


_CFG = load_config()


def test_watlow_ramp_returns_tuple_and_writes_setpoints() -> None:
    temperature = MagicMock()
    power = MagicMock()

    # initial current_temp + one read during one ramp-loop iteration
    temperature.read_temperature.side_effect = [25.0, 25.0]
    temperature.set_temperature.return_value = True

    controller = TemperatureController(
        temperature=temperature,
        power=power,
        paths=_CFG.paths,
        kasa=_CFG.hardware.kasa,
    )

    with (
        patch("src.control.temperature_control.time.sleep"),
        patch("src.control.temperature_control.log_temperature"),
    ):
        result = controller.watlow(
            filename="run1",
            foldername="f1",
            target_temp=25.1,
            duration=0.0,
            rate=3.0,
            variac_cmd=True,
            update_interval=2,
        )

    assert result == (25.1, 3.0, 0.0)
    # one ramp step from 25.0 to 25.1
    temperature.set_temperature.assert_called_once_with(25.1)


def test_watlow_cooling_path_controls_variac_states() -> None:
    temperature = MagicMock()
    power = MagicMock()

    # initial read, while-loop read, then hold_temp read
    temperature.read_temperature.side_effect = [40.0, 25.0, 25.0]
    temperature.set_temperature.return_value = True

    controller = TemperatureController(
        temperature=temperature,
        power=power,
        paths=_CFG.paths,
        kasa=_CFG.hardware.kasa,
    )

    # stabilize module-global legacy path state for filename=None branch
    temperature_control_module.path_tempLog = "unused.csv"

    with patch("src.control.temperature_control.time.sleep"):
        result = controller.watlow(
            filename=None,
            foldername=None,
            target_temp=20.0,
            duration=0.0,
            rate=0.0,
            variac_cmd=False,
            update_interval=2,
        )

    assert result == (20.0, 0.0, 0.0)
    temperature.set_temperature.assert_called_once_with(20.0)
    # vessel variac off first, then main variac off when threshold is met
    assert power.set_state.call_args_list == [
        call(_CFG.hardware.kasa.variac_id_vsl, False),
        call(_CFG.hardware.kasa.variac_id, False),
    ]


def test_kasa_helpers_delegate_to_power_set_state() -> None:
    temperature = MagicMock()
    power = MagicMock()
    controller = TemperatureController(
        temperature=temperature,
        power=power,
        paths=_CFG.paths,
        kasa=_CFG.hardware.kasa,
    )

    controller.chiller_state(True)
    controller.variac_state(False)
    controller.kasa_plug_state("plug-123", True)

    assert power.set_state.call_args_list == [
        call(_CFG.hardware.kasa.chiller_id, True),
        call(_CFG.hardware.kasa.variac_id, False),
        call("plug-123", True),
    ]
