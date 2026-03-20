from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.config_loader import (
    ActuatorConfig,
    HardwareConfig,
    KasaConfig,
    NetworkConfig,
    SerialDeviceConfig,
)
from src.hardware.connections import DeviceManager


def _hardware_config_fixture() -> HardwareConfig:
    return HardwareConfig(
        mks=SerialDeviceConfig(port="COM8", baudrate=9600, timeout_s=2.0),
        watlow_ir=SerialDeviceConfig(
            port="COM6",
            baudrate=9600,
            timeout_s=1.0,
            parity="N",
            stopbits=1,
            bytesize=8,
        ),
        extrel_ms=SerialDeviceConfig(
            port="COM5",
            baudrate=9600,
            timeout_s=1.0,
            parity="N",
            stopbits=1,
            bytesize=8,
        ),
        actuator=ActuatorConfig(
            voltage_closed=1.0,
            voltage_open=5.0,
            voltage_max_write=5.0,
            post_write_sleep_s=5.0,
            turbo_pressure_poll_s=2.0,
            turbo_open_max_manifold_torr=0.02,
            mass_spec_open_max_cell_torr=0.1,
            device_map={"H2": ("act3-4", "ao0")},
            reserved_channels=[],
        ),
        network=NetworkConfig(
            opus_ip="130.20.216.127",
            opus_port=5555,
            zmq_receive_timeout_ms=300000,
        ),
        kasa=KasaConfig(
            chiller_id="c",
            variac_id="v",
            variac_id_vsl="vv",
            username="user",
            password="pass",
        ),
    )


def test_device_manager_connect_creates_all_hardware_instances() -> None:
    hardware_config = _hardware_config_fixture()

    with (
        patch("src.hardware.connections.serial.Serial") as serial_cls,
        patch("src.hardware.connections.ModbusClient") as modbus_cls,
        patch("src.hardware.connections.zmq.Context") as zmq_context_cls,
        patch("src.hardware.connections.KasaPower") as kasa_power_cls,
    ):
        serial_conn = MagicMock()
        serial_conn.is_open = True
        serial_conn.port = hardware_config.mks.port
        serial_conn.baudrate = hardware_config.mks.baudrate
        serial_conn.timeout = hardware_config.mks.timeout_s
        serial_cls.return_value = serial_conn

        watlow_modbus = MagicMock()
        watlow_modbus.connect.return_value = True
        extrel_modbus = MagicMock()
        extrel_modbus.connect.return_value = True
        modbus_cls.side_effect = [watlow_modbus, extrel_modbus]

        zmq_context = MagicMock()
        zmq_socket = MagicMock()
        zmq_context.socket.return_value = zmq_socket
        zmq_context_cls.return_value = zmq_context

        manager = DeviceManager(hardware_config)
        manager.connect()

        serial_cls.assert_called_once_with(
            "COM8",
            baudrate=9600,
            timeout=2.0,
        )
        assert modbus_cls.call_count == 2
        watlow_modbus.connect.assert_called_once()
        extrel_modbus.connect.assert_called_once()
        zmq_context.socket.assert_called_once()
        zmq_socket.setsockopt.assert_called_once()
        zmq_socket.connect.assert_called_once_with("tcp://130.20.216.127:5555")

        assert manager.pressure is not None
        assert manager.temperature is not None
        assert manager.mass_spec is not None
        assert manager.analog_io is not None
        assert manager.spectrometer is not None
        assert manager.power is not None

        kasa_power_cls.assert_called_once_with(hardware_config.kasa)


def test_device_manager_disconnect_cleans_up_resources() -> None:
    hardware_config = _hardware_config_fixture()

    with (
        patch("src.hardware.connections.serial.Serial") as serial_cls,
        patch("src.hardware.connections.ModbusClient") as modbus_cls,
        patch("src.hardware.connections.zmq.Context") as zmq_context_cls,
        patch("src.hardware.connections.KasaPower"),
    ):
        serial_conn = MagicMock()
        serial_conn.is_open = True
        serial_conn.port = hardware_config.mks.port
        serial_conn.baudrate = hardware_config.mks.baudrate
        serial_conn.timeout = hardware_config.mks.timeout_s
        serial_cls.return_value = serial_conn

        watlow_modbus = MagicMock()
        watlow_modbus.connect.return_value = True
        extrel_modbus = MagicMock()
        extrel_modbus.connect.return_value = True
        modbus_cls.side_effect = [watlow_modbus, extrel_modbus]

        zmq_context = MagicMock()
        zmq_socket = MagicMock()
        zmq_context.socket.return_value = zmq_socket
        zmq_context_cls.return_value = zmq_context

        manager = DeviceManager(hardware_config)
        manager.connect()
        manager.disconnect()

        serial_conn.close.assert_called_once()
        watlow_modbus.close.assert_called_once()
        extrel_modbus.close.assert_called_once()
        zmq_socket.close.assert_called_once()
        zmq_context.term.assert_called_once()

        assert manager.pressure is None
        assert manager.temperature is None
        assert manager.mass_spec is None
        assert manager.analog_io is None
        assert manager.spectrometer is None
        assert manager.power is None
