# src/core/config.py

import yaml
import os
from pathlib import Path

# --- Constants ---
# Determine the project root directory dynamically.
# Assumes this file is at src/core/config.py
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config" / "paths.yaml"
_ANALYSIS_CONFIG_PATH = _PROJECT_ROOT / "config" / "analysis.yaml"

# --- Private State ---
_config = None
_analysis_config = None


# --- Private Functions ---
def _load_config():
    """Loads the YAML configuration file into a global dictionary."""
    global _config
    if _config is None:
        try:
            with open(_CONFIG_PATH, "r") as f:
                _config = yaml.safe_load(f)
        except FileNotFoundError:
            # Handle cases where the config file is missing.
            raise RuntimeError(f"Configuration file not found at: {_CONFIG_PATH}")
        except yaml.YAMLError as e:
            # Handle errors during YAML parsing.
            raise RuntimeError(f"Error parsing YAML configuration: {e}")


def _load_analysis_config():
    """Loads the analysis YAML configuration into a global dictionary."""
    global _analysis_config
    if _analysis_config is None:
        try:
            with open(_ANALYSIS_CONFIG_PATH, "r") as f:
                _analysis_config = yaml.safe_load(f)
        except FileNotFoundError:
            raise RuntimeError(
                f"Analysis configuration file not found at: {_ANALYSIS_CONFIG_PATH}"
            )
        except yaml.YAMLError as e:
            raise RuntimeError(f"Error parsing analysis YAML configuration: {e}")


def _get_value(config_data: dict, key_path: str):
    keys = key_path.split(".")
    value = config_data
    try:
        for key in keys:
            value = value[key]
        return value
    except (TypeError, KeyError):
        raise KeyError(f"Configuration key not found: '{key_path}'")


# --- Public API ---
def get_setting(key_path: str):
    """
    Retrieves a configuration value using a dot-separated key.

    Example: get_setting("opus.server.host") -> "130.20.216.127"
    """
    _load_config()
    return _get_value(_config, key_path)


def get_analysis_setting(key_path: str):
    """
    Retrieves a configuration value from analysis.yaml using a dot-separated key.

    Example: get_analysis_setting("analysis.voight_fit") -> {...}
    """
    _load_analysis_config()
    normalized_key = key_path
    if normalized_key.startswith("analysis."):
        normalized_key = normalized_key.split(".", 1)[1]
    return _get_value(_analysis_config, normalized_key)


def get_path(key_path: str, *args: str) -> str:
    """
    Retrieves a path from config and joins it with any additional parts.

    Example: get_path("data.opus_files", "my_experiment") -> "C:\\Data\\OpusFiles\\my_experiment"
    """
    base_path = get_setting(key_path)
    if not isinstance(base_path, str):
        raise TypeError(f"Path for key '{key_path}' is not a string.")

    # Use os.path.join for OS-agnostic path construction.
    return os.path.join(base_path, *args)
