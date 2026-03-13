"""Configuration and constants for the instrument control system."""

import os
import logging
from pathlib import Path
from typing import Any

import yaml


logger = logging.getLogger(__name__)


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

# ---------------------------------------------------------------------------
# Raw values loaded from YAML files
# ---------------------------------------------------------------------------
_raw_R = _system_physical_constants["R"]  # [L Torr K^-1 mol^-1]
_raw_t_mfld = _system_temperature["t_mfld"]  # [K]

_raw_v_vessel = _system_volumes_l["v_vessel"]  # [L]
_raw_v_valve = _system_volumes_l["v_valve"]  # [L]
_raw_v_cell = _system_volumes_l["v_cell"]  # [L]
_raw_v_m1m2 = _system_volumes_l["v_m1m2"]  # [L]
_raw_v_m1m2m3 = _system_volumes_l["v_m1m2m3"]  # [L]
_raw_v_50tube = _system_volumes_l["v_50tube"]  # [L]
_raw_v_flask = _system_volumes_l["v_flask"]  # [L]

_raw_notebook = _sample["notebook"]
_raw_metal = _sample["metal"]
_raw_support = _sample["support"]
_raw_mass = _sample["mass"]  # [g]
_raw_metal_load = _sample["metal_load"]  # [wt.%]
_raw_support_sa = _sample["support_sa"]  # [m^2/g]

_raw_chiller_id = _kasa_plugs["chiller_id"]
_raw_variac_id = _kasa_plugs["variac_id"]
_raw_variac_id_vsl = _kasa_plugs["variac_id_vsl"]

# Public raw values
R = _raw_R
t_mfld = _raw_t_mfld

v_vessel = _raw_v_vessel
v_valve = _raw_v_valve
v_cell = _raw_v_cell
v_m1m2 = _raw_v_m1m2
v_m1m2m3 = _raw_v_m1m2m3
v_50tube = _raw_v_50tube
v_flask = _raw_v_flask

notebook = _raw_notebook
metal = _raw_metal
support = _raw_support
mass = _raw_mass
metal_load = _raw_metal_load
support_sa = _raw_support_sa

chiller_id = _raw_chiller_id
variac_id = _raw_variac_id
variac_id_vsl = _raw_variac_id_vsl

# ---------------------------------------------------------------------------
# Derived values (computed from raw values)
# ---------------------------------------------------------------------------
# v_m3 [L] = v_m1m2m3 - v_m1m2 - v_valve
v_m3 = v_m1m2m3 - v_m1m2 - v_valve

# v_tot [L] = v_m1m2m3 + v_cell + v_valve + v_50tube
v_tot = v_m1m2m3 + v_cell + v_valve + v_50tube

# metal_density [nm^-2] =
#   (metal_load / 100) * (1 / 106.42) * (6.023e23) * (1 / support_sa) * (1e-9**2)
# where 106.42 is Pd molar mass [g/mol].
metal_density = (metal_load / 100) * (1 / 106.42) * (6.023e23) * (1 / support_sa) * (1e-9**2)
