"""Configuration and constants for the instrument control system."""

import os
from pathlib import Path
from typing import Any

import yaml
from .logging import get_logger


logger = get_logger(__name__)


def _load_yaml(file_path: Path) -> dict[str, Any]:
    logger.debug("Loading YAML config: %s", file_path)
    with file_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    return data if data is not None else {}


def _resolve_config_dir() -> Path:
    env_config_dir = os.getenv("CATAVERSE_CONFIG_DIR")
    if env_config_dir:
        config_dir = Path(env_config_dir)
    else:
        repo_root = Path(__file__).resolve().parents[2]
        config_dir = repo_root / "config"

    if not config_dir.exists():
        raise FileNotFoundError(f"Configuration directory not found: {config_dir}")

    return config_dir


def _require(data: dict[str, Any], key: str, file_name: str) -> Any:
    if key not in data:
        raise KeyError(f"Missing required key '{key}' in {file_name}")
    return data[key]


CONFIG_DIR = _resolve_config_dir()

_system_config = _load_yaml(CONFIG_DIR / "system.yaml")
_sample_config = _load_yaml(CONFIG_DIR / "sample.yaml")
_devices_config = _load_yaml(CONFIG_DIR / "devices.yaml")
_paths_config = _load_yaml(CONFIG_DIR / "paths.yaml")

_system_physical_constants = _require(_system_config, "physical_constants", "system.yaml")
_system_temperature = _require(_system_config, "temperature", "system.yaml")
_system_volumes_l = _require(_system_config, "volumes_l", "system.yaml")

_sample = _require(_sample_config, "sample", "sample.yaml")
_kasa_plugs = _require(_devices_config, "kasa_plugs", "devices.yaml")
_paths = _require(_paths_config, "paths", "paths.yaml")
_share_drive_paths = _require(_paths, "share_drive", "paths.yaml")
_serial_config = _require(_devices_config, "serial", "devices.yaml")
_actuators_config = _require(_devices_config, "actuators", "devices.yaml")
_serial_mks = _require(_serial_config, "mks", "devices.yaml")
_serial_watlow_ir = _require(_serial_config, "watlow_ir", "devices.yaml")
_serial_extrel_ms = _require(_serial_config, "extrel_ms", "devices.yaml")
_actuator_device_map = _require(_actuators_config, "device_map", "devices.yaml")
_actuator_voltages = _require(_actuators_config, "voltages", "devices.yaml")
_actuator_timing_s = _require(_actuators_config, "timing_s", "devices.yaml")
_actuator_safety_limits_torr = _require(
    _actuators_config, "safety_limits_torr", "devices.yaml"
)
_network_config = _require(_devices_config, "network", "devices.yaml")
_network_opus = _require(_network_config, "opus", "devices.yaml")
_network_zmq = _require(_network_config, "zmq", "devices.yaml")

# ---------------------------------------------------------------------------
# Values loaded from YAML files
# ---------------------------------------------------------------------------
R = _system_physical_constants["R"]  # [L Torr K^-1 mol^-1]
t_mfld = _system_temperature["t_mfld"]  # [K]

v_vessel = _system_volumes_l["v_vessel"]  # [L]
v_valve = _system_volumes_l["v_valve"]  # [L]
v_cell = _system_volumes_l["v_cell"]  # [L]
v_m1m2 = _system_volumes_l["v_m1m2"]  # [L]
v_m1m2m3 = _system_volumes_l["v_m1m2m3"]  # [L]
v_50tube = _system_volumes_l["v_50tube"]  # [L]
v_flask = _system_volumes_l["v_flask"]  # [L]

notebook = _sample["notebook"]
metal = _sample["metal"]
support = _sample["support"]
mass = _sample["mass"]  # [g]
metal_load = _sample["metal_load"]  # [wt.%]
support_sa = _sample["support_sa"]  # [m^2/g]

chiller_id = _kasa_plugs["chiller_id"]
variac_id = _kasa_plugs["variac_id"]
variac_id_vsl = _kasa_plugs["variac_id_vsl"]

mks_serial_port = _serial_mks["port"]
mks_serial_baudrate = _serial_mks["baudrate"]
mks_serial_timeout_s = _serial_mks["timeout_s"]

watlow_ir_port = _serial_watlow_ir["port"]
watlow_ir_baudrate = _serial_watlow_ir["baudrate"]
watlow_ir_parity = _serial_watlow_ir["parity"]
watlow_ir_stopbits = _serial_watlow_ir["stopbits"]
watlow_ir_bytesize = _serial_watlow_ir["bytesize"]
watlow_ir_timeout_s = _serial_watlow_ir["timeout_s"]

extrel_ms_port = _serial_extrel_ms["port"]
extrel_ms_baudrate = _serial_extrel_ms["baudrate"]
extrel_ms_parity = _serial_extrel_ms["parity"]
extrel_ms_stopbits = _serial_extrel_ms["stopbits"]
extrel_ms_bytesize = _serial_extrel_ms["bytesize"]
extrel_ms_timeout_s = _serial_extrel_ms["timeout_s"]

ni_usb6009_device_map = {
    actuator_id: tuple(device_channel)
    for actuator_id, device_channel in _actuator_device_map.items()
}

actuator_voltage_closed = _actuator_voltages["closed"]
actuator_voltage_open = _actuator_voltages["open"]
actuator_voltage_max_write = _actuator_voltages["max_write"]
actuator_post_write_sleep_s = _actuator_timing_s["post_write_sleep"]
actuator_turbo_pressure_poll_s = _actuator_timing_s["turbo_pressure_poll"]
actuator_turbo_open_max_manifold_torr = _actuator_safety_limits_torr[
    "turbo_open_max_manifold"
]
actuator_mass_spec_open_max_cell_torr = _actuator_safety_limits_torr[
    "mass_spec_open_max_cell"
]

opus_default_ip = _network_opus["ip"]
opus_default_port = _network_opus["port"]
zmq_receive_timeout_ms = _network_zmq["receive_timeout_ms"]

data_directory = _paths["data_directory"]
autonomous_parameters_directory = _paths["autonomous_parameters_directory"]
share_drive_peak_fit_root = _share_drive_paths["peak_fit_root"]
share_drive_pressure_data_root = _share_drive_paths["pressure_data_root"]
share_drive_ms_calibrations_root = _share_drive_paths["ms_calibrations_root"]

# ---------------------------------------------------------------------------
# Derived values (computed from loaded values)
# ---------------------------------------------------------------------------
# v_m3 [L] = v_m1m2m3 - v_m1m2 - v_valve
v_m3 = v_m1m2m3 - v_m1m2 - v_valve

# v_tot [L] = v_m1m2m3 + v_cell + v_valve + v_50tube
v_tot = v_m1m2m3 + v_cell + v_valve + v_50tube

# metal_density [nm^-2] =
#   (metal_load / 100) * (1 / 106.42) * (6.023e23) * (1 / support_sa) * (1e-9**2)
# where 106.42 is Pd molar mass [g/mol].
metal_density = (metal_load / 100) * (1 / 106.42) * (6.023e23) * (1 / support_sa) * (1e-9**2)
