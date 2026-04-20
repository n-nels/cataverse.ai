"""Shared pytest fixtures for new architecture tests.

These fixtures are intentionally hardware-free. Hardware/library boundaries are
represented by mocks so test suites can run without physical instruments.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.config_loader import (
    ActuatorConfig,
    HardwareConfig,
    KasaConfig,
    NetworkConfig,
    SampleConfig,
    SerialDeviceConfig,
)
from src.physics import SystemVolumes


@pytest.fixture
def mock_serial_conn() -> MagicMock:
    """Mock serial connection object (pyserial boundary)."""

    return MagicMock(name="mock_serial_conn")


@pytest.fixture
def mock_modbus_client() -> MagicMock:
    """Mock modbus client object (pymodbus boundary)."""

    return MagicMock(name="mock_modbus_client")


@pytest.fixture
def mock_nidaqmx_task() -> MagicMock:
    """Mock nidaqmx task object (NI DAQ boundary)."""

    return MagicMock(name="mock_nidaqmx_task")


@pytest.fixture
def mock_zmq_socket() -> MagicMock:
    """Mock ZeroMQ socket object (pyzmq boundary)."""

    return MagicMock(name="mock_zmq_socket")


@pytest.fixture
def sample_config() -> SampleConfig:
    """Representative typed sample config for tests."""

    return SampleConfig(
        notebook="nn1120-3",
        metal="pd",
        support="ceo2",
        mass_g=0.0164,
        metal_load_wt_percent=0.04983,
        support_surface_area_m2_g=54.0,
        metal_molar_mass_g_mol=106.42,
    )


@pytest.fixture
def hardware_config() -> HardwareConfig:
    """Representative typed hardware config for tests."""

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
            device_map={
                "v16": ("act1-2", "ao0"),
                "RoughPump": ("act1-2", "ao1"),
                "H2": ("act3-4", "ao0"),
                "H2O": ("act3-4", "ao1"),
                "MassSpec": ("act5-6", "ao0"),
                "13CO": ("act5-6", "ao1"),
                "irCell": ("act7-8", "ao0"),
                "O2": ("act7-8", "ao1"),
                "TurboPump": ("act9-10", "ao0"),
            },
            reserved_channels=[
                ("act9-10", "ao1"),
                ("act11-12", "ao0"),
                ("act11-12", "ao1"),
                ("act13-14", "ao0"),
                ("act13-14", "ao1"),
            ],
        ),
        network=NetworkConfig(
            opus_ip="130.20.216.127",
            opus_port=5555,
            zmq_receive_timeout_ms=300000,
        ),
        kasa=KasaConfig(
            chiller_id="80068F39DE57BDF8D6EA6F2AB145251E223AF901",
            variac_id="80068C02EA20EFE6A7149420FAA20DB5223A54AA",
            variac_id_vsl="8006CF042D478C8A62FE5B07A53B29B8223A2135",
        ),
    )


@pytest.fixture
def system_volumes() -> SystemVolumes:
    """Representative calibrated volume set for calculations."""

    return SystemVolumes(
        vessel=0.0119913,
        valve=0.000152,
        cell=0.03381,
        manifold_m1m2=0.078862,
        manifold_m1m2m3=0.11116,
        tube_50ml=0.05643,
        flask=1.004,
    )
