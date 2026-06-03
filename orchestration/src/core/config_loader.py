"""Typed YAML configuration loader for the new architecture.

This module reads configuration from ``config/*.yaml`` and exposes a strongly-typed
``AppConfig`` object for the new hardware/control/datalog packages.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv




@dataclass(frozen=True)
class SystemConstants:
    """Physical constants, temperatures, and calibrated volumes."""

    gas_constant: float
    manifold_temperature_k: float
    vessel_volume_l: float
    valve_volume_l: float
    cell_volume_l: float
    manifold_m1m2_volume_l: float
    manifold_m1m2m3_volume_l: float
    tube_50ml_volume_l: float
    flask_volume_l: float
    gauge_max_pressure_torr: float


@dataclass(frozen=True)
class SerialDeviceConfig:
    """Connection settings for one serial device."""

    port: str
    baudrate: int
    timeout_s: float
    parity: str | None = None
    stopbits: int | None = None
    bytesize: int | None = None


@dataclass(frozen=True)
class ExtrelRegisterConfig:
    """Extrel mass spectrometer register addresses and values."""

    sequence_start_address: int = 1
    sequence_start_value: int = 2
    sequence_stop_address: int = 1
    sequence_stop_value: int = 9


@dataclass(frozen=True)
class ExtrelDeviceConfig:
    """Extrel mass spectrometer device configuration."""

    serial: SerialDeviceConfig
    registers: ExtrelRegisterConfig
    stream_tags: list[str]


@dataclass(frozen=True)
class ActuatorConfig:
    """Actuator voltage/timing/safety settings and channel mapping."""

    voltage_closed: float
    voltage_open: float
    voltage_max_write: float
    post_write_sleep_s: float
    turbo_pressure_poll_s: float
    turbo_open_max_manifold_torr: float
    mass_spec_open_max_cell_torr: float
    actuator_map: dict[str, tuple[str, str]]
    reserved_channels: list[tuple[str, str]]


@dataclass(frozen=True)
class NetworkConfig:
    """Network settings for OPUS and ZMQ communication."""

    opus_ip: str
    opus_port: int
    zmq_receive_timeout_ms: int


@dataclass(frozen=True)
class KasaConfig:
    """Kasa smart-plug device identifiers and optional credentials."""

    chiller_id: str
    variac_id: str
    variac_id_vsl: str
    username: str | None = None
    password: str | None = None


@dataclass(frozen=True)
class HardwareConfig:
    """All hardware-related configuration for devices and communication."""

    mks: SerialDeviceConfig
    watlow_ir: SerialDeviceConfig
    extrel_ms: ExtrelDeviceConfig
    actuator: ActuatorConfig
    network: NetworkConfig
    kasa: KasaConfig


@dataclass(frozen=True)
class SampleConfig:
    """Catalyst/sample descriptors used by experiment workflows."""

    notebook: str
    metal: str
    support: str
    mass_g: float
    metal_load_wt_percent: float
    support_surface_area_m2_g: float
    metal_molar_mass_g_mol: float


@dataclass(frozen=True)
class PathsConfig:
    """Filesystem paths for data output, runtime, and shared-drive copies."""

    data_directory: str
    autonomous_parameters_directory: str
    share_drive_peak_fit_root: str
    share_drive_pressure_data_root: str
    share_drive_ms_calibrations_root: str


@dataclass(frozen=True)
class AppConfig:
    """Top-level container for all configuration groups."""

    system: SystemConstants
    hardware: HardwareConfig
    sample: SampleConfig
    paths: PathsConfig


def _load_yaml(file_path: Path) -> dict[str, Any]:
    with file_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if data is None:
        raise ValueError(f"YAML file is empty: {file_path}")
    if not isinstance(data, dict):
        raise TypeError(f"Expected mapping at root of YAML file: {file_path}")
    return data


def _require(data: dict[str, Any], key: str, file_name: str) -> Any:
    if key not in data:
        raise KeyError(f"Missing required key '{key}' in {file_name}")
    return data[key]


def _resolve_config_dir(config_dir: Path | None) -> Path:
    """Resolve the configuration directory."""
    
    if config_dir is not None:
        resolved = config_dir
    else:
        env_config_dir = os.getenv("CATAVERSE_CONFIG_DIR")
        if env_config_dir:
            resolved = Path(env_config_dir)
        else:
            raise FileNotFoundError(
                "Configuration directory not specified. "
                "Either pass config_dir explicitly or set the "
                "CATAVERSE_CONFIG_DIR environment variable in your .env file."
            )

    if not resolved.exists():
        raise FileNotFoundError(f"Configuration directory not found: {resolved}")
    if not resolved.is_dir():
        raise NotADirectoryError(f"Configuration path is not a directory: {resolved}")

    return resolved


def _to_channel_tuple(value: Any, context: str) -> tuple[str, str]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(
            f"Expected 2-item channel mapping for {context}, got: {value!r}"
        )
    left, right = value
    if not isinstance(left, str) or not isinstance(right, str):
        raise TypeError(
            f"Expected string channel entries for {context}, got: {value!r}"
        )
    return (left, right)


def _build_system_constants(data: dict[str, Any]) -> SystemConstants:
    """Build ``SystemConstants`` from the parsed ``system.yaml`` data."""
    physical_constants = _require(data, "physical_constants", "system.yaml")
    temperature = _require(data, "temperature", "system.yaml")
    volumes_l = _require(data, "volumes_l", "system.yaml")
    pressure_gauge = _require(data, "pressure_gauge", "system.yaml")

    return SystemConstants(
        gas_constant=physical_constants["R"],
        manifold_temperature_k=temperature["t_mfld"],
        vessel_volume_l=volumes_l["v_vessel"],
        valve_volume_l=volumes_l["v_valve"],
        cell_volume_l=volumes_l["v_cell"],
        manifold_m1m2_volume_l=volumes_l["v_m1m2"],
        manifold_m1m2m3_volume_l=volumes_l["v_m1m2m3"],
        tube_50ml_volume_l=volumes_l["v_50tube"],
        flask_volume_l=volumes_l["v_flask"],
        gauge_max_pressure_torr=pressure_gauge["max_pressure_torr"],
    )


def _build_hardware_config(data: dict[str, Any]) -> HardwareConfig:
    """Build ``HardwareConfig`` from the parsed ``devices.yaml`` data."""
    serial = _require(data, "serial", "devices.yaml")
    mks_serial = _require(serial, "mks", "devices.yaml")
    watlow_ir_serial = _require(serial, "watlow_ir", "devices.yaml")
    extrel_ms_serial = _require(serial, "extrel_ms", "devices.yaml")

    actuators = _require(data, "actuators", "devices.yaml")
    voltages = _require(actuators, "voltages", "devices.yaml")
    timing_s = _require(actuators, "timing_s", "devices.yaml")
    safety_limits_torr = _require(actuators, "safety_limits_torr", "devices.yaml")
    actuator_map = _require(actuators, "actuator_map", "devices.yaml")
    reserved_channels = actuators.get("reserved_channels", [])

    network = _require(data, "network", "devices.yaml")
    opus = _require(network, "opus", "devices.yaml")
    zmq = _require(network, "zmq", "devices.yaml")

    kasa_plugs = _require(data, "kasa_plugs", "devices.yaml")

    return HardwareConfig(
        mks=SerialDeviceConfig(
            port=mks_serial["port"],
            baudrate=mks_serial["baudrate"],
            timeout_s=mks_serial["timeout_s"],
        ),
        watlow_ir=SerialDeviceConfig(
            port=watlow_ir_serial["port"],
            baudrate=watlow_ir_serial["baudrate"],
            timeout_s=watlow_ir_serial["timeout_s"],
            parity=watlow_ir_serial.get("parity"),
            stopbits=watlow_ir_serial.get("stopbits"),
            bytesize=watlow_ir_serial.get("bytesize"),
        ),
        extrel_ms=ExtrelDeviceConfig(
            serial=SerialDeviceConfig(
                port=extrel_ms_serial["port"],
                baudrate=extrel_ms_serial["baudrate"],
                timeout_s=extrel_ms_serial["timeout_s"],
                parity=extrel_ms_serial.get("parity"),
                stopbits=extrel_ms_serial.get("stopbits"),
                bytesize=extrel_ms_serial.get("bytesize"),
            ),
            registers=ExtrelRegisterConfig(
                **{
                    k: v
                    for k, v in {
                        "sequence_start_address": extrel_ms_serial.get(
                            "registers", {}
                        )
                        .get("sequence_start", {})
                        .get("address"),
                        "sequence_start_value": extrel_ms_serial.get(
                            "registers", {}
                        )
                        .get("sequence_start", {})
                        .get("value"),
                        "sequence_stop_address": extrel_ms_serial.get(
                            "registers", {}
                        )
                        .get("sequence_stop", {})
                        .get("address"),
                        "sequence_stop_value": extrel_ms_serial.get(
                            "registers", {}
                        )
                        .get("sequence_stop", {})
                        .get("value"),
                    }.items()
                    if v is not None
                }
            ),
            stream_tags=extrel_ms_serial.get(
                "stream_tags", ["V1_I_28", "V1_I_29", "V1_I_44", "V1_I_45"]
            ),
        ),
        actuator=ActuatorConfig(
            voltage_closed=voltages["closed"],
            voltage_open=voltages["open"],
            voltage_max_write=voltages["max_write"],
            post_write_sleep_s=timing_s["post_write_sleep"],
            turbo_pressure_poll_s=timing_s["turbo_pressure_poll"],
            turbo_open_max_manifold_torr=safety_limits_torr["turbo_open_max_manifold"],
            mass_spec_open_max_cell_torr=safety_limits_torr["mass_spec_open_max_cell"],
            actuator_map={
                actuator_id: _to_channel_tuple(
                    device_channel, f"actuators.device_map.{actuator_id}"
                )
                for actuator_id, device_channel in actuator_map.items()
            },
            reserved_channels=[
                _to_channel_tuple(channel, f"actuators.reserved_channels[{index}]")
                for index, channel in enumerate(reserved_channels)
            ],
        ),
        network=NetworkConfig(
            opus_ip=opus["ip"],
            opus_port=opus["port"],
            zmq_receive_timeout_ms=zmq["receive_timeout_ms"],
        ),
        kasa=KasaConfig(
            chiller_id=kasa_plugs["chiller_id"],
            variac_id=kasa_plugs["variac_id"],
            variac_id_vsl=kasa_plugs["variac_id_vsl"],
        ),
    )


def _build_sample_config(data: dict[str, Any]) -> SampleConfig:
    """Build ``SampleConfig`` from the parsed ``sample.yaml`` data."""
    sample = _require(data, "sample", "sample.yaml")

    kwargs: dict[str, Any] = {
        "notebook": sample["notebook"],
        "metal": sample["metal"],
        "support": sample["support"],
        "mass_g": sample["mass"],
        "metal_load_wt_percent": sample["metal_load"],
        "support_surface_area_m2_g": sample["support_sa"],
    }
    kwargs["metal_molar_mass_g_mol"] = _require(
        sample, "metal_molar_mass", "sample.yaml"
    )
    return SampleConfig(**kwargs)


def _build_paths_config(data: dict[str, Any]) -> PathsConfig:
    """Build ``PathsConfig`` from the parsed ``paths.yaml`` data."""
    paths = _require(data, "paths", "paths.yaml")
    share_drive = _require(paths, "share_drive", "paths.yaml")

    kwargs: dict[str, Any] = {
        "data_directory": paths["data_directory"],
        "autonomous_parameters_directory": paths["autonomous_parameters_directory"],
        "share_drive_peak_fit_root": share_drive["peak_fit_root"],
        "share_drive_pressure_data_root": share_drive["pressure_data_root"],
        "share_drive_ms_calibrations_root": share_drive["ms_calibrations_root"],
    }
    return PathsConfig(**kwargs)


def load_config(config_dir: Path | None = None) -> AppConfig:
    """Load all YAML config files into a typed ``AppConfig`` container.

    Calls ``load_dotenv()`` to ensure environment variables (e.g.
    ``CATAVERSE_CONFIG_DIR``) are available before resolving paths.
    """

    load_dotenv()

    resolved_dir = _resolve_config_dir(config_dir)

    system_yaml = _load_yaml(resolved_dir / "system.yaml")
    devices_yaml = _load_yaml(resolved_dir / "devices.yaml")
    sample_yaml = _load_yaml(resolved_dir / "sample.yaml")
    paths_yaml = _load_yaml(resolved_dir / "paths.yaml")

    return AppConfig(
        system=_build_system_constants(system_yaml),
        hardware=_build_hardware_config(devices_yaml),
        sample=_build_sample_config(sample_yaml),
        paths=_build_paths_config(paths_yaml),
    )
