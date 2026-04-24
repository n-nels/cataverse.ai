"""Tests for typed YAML loading in ``src.config_loader``."""

from __future__ import annotations

from pathlib import Path

from src.core.config_loader import (
    DEFAULT_METAL_MOLAR_MASS,
    AppConfig,
    ExtrelDeviceConfig,
    ExtrelRegisterConfig,
    HardwareConfig,
    PathsConfig,
    SampleConfig,
    SystemConstants,
    load_config,
)
from src.core.physics import SystemVolumes


def test_load_config_returns_typed_app_config_from_repo_yaml() -> None:
    cfg = load_config()

    assert isinstance(cfg, AppConfig)
    assert isinstance(cfg.system, SystemConstants)
    assert isinstance(cfg.hardware, HardwareConfig)
    assert isinstance(cfg.sample, SampleConfig)
    assert isinstance(cfg.paths, PathsConfig)


def test_load_config_values_match_repo_yaml() -> None:
    cfg = load_config()

    assert cfg.system.gas_constant == 62.363577
    assert cfg.system.manifold_temperature_k == 298
    assert cfg.system.manifold_m1m2m3_volume_l == 0.11116

    assert cfg.hardware.mks.port == "COM8"
    assert cfg.hardware.network.opus_ip == "130.20.216.127"
    assert cfg.hardware.network.opus_port == 5555
    assert cfg.hardware.actuator.voltage_open == 5.0
    assert cfg.hardware.actuator.device_map["H2"] == ("act3-4", "ao0")

    assert cfg.sample.notebook == "nn1120-3"
    assert cfg.sample.metal == "pd"
    assert cfg.sample.metal_molar_mass_g_mol == 106.42

    assert cfg.paths.data_directory == "C:\\Data"
    assert cfg.paths.share_drive_peak_fit_root == "X:\\peakFit"


def test_load_config_uses_default_metal_molar_mass_when_missing(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    (config_dir / "system.yaml").write_text(
        """
physical_constants:
  R: 62.363577
temperature:
  t_mfld: 298
volumes_l:
  v_vessel: 0.0119913
  v_valve: 0.000152
  v_cell: 0.03381
  v_m1m2: 0.078862
  v_m1m2m3: 0.11116
  v_50tube: 0.05643
  v_flask: 1.004
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (config_dir / "devices.yaml").write_text(
        """
serial:
  mks:
    port: COM8
    baudrate: 9600
    timeout_s: 2
  watlow_ir:
    port: COM6
    baudrate: 9600
    parity: N
    stopbits: 1
    bytesize: 8
    timeout_s: 1
  extrel_ms:
    port: COM5
    baudrate: 9600
    parity: N
    stopbits: 1
    bytesize: 8
    timeout_s: 1
network:
  opus:
    ip: 130.20.216.127
    port: 5555
  zmq:
    receive_timeout_ms: 300000
kasa_plugs:
  chiller_id: c1
  variac_id: v1
  variac_id_vsl: v2
actuators:
  voltages:
    closed: 1.0
    open: 5.0
    max_write: 5.0
  timing_s:
    post_write_sleep: 5
    turbo_pressure_poll: 2
  safety_limits_torr:
    turbo_open_max_manifold: 0.02
    mass_spec_open_max_cell: 0.1
  device_map:
    H2: [act3-4, ao0]
  reserved_channels:
    - [act9-10, ao1]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (config_dir / "sample.yaml").write_text(
        """
sample:
  notebook: nn1120-3
  metal: pd
  support: ceo2
  mass: 0.0164
  metal_load: 0.04983
  support_sa: 54
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (config_dir / "paths.yaml").write_text(
        """
paths:
  data_directory: 'C:\\Data'
  autonomous_parameters_directory: 'C:\\Users\\labuser\\instrument_control\\catalysis_autolab\\data'
  share_drive:
    peak_fit_root: 'X:\\peakFit'
    pressure_data_root: 'X:\\pressureData'
    ms_calibrations_root: 'X:\\ms_calibrations'
""".strip()
        + "\n",
        encoding="utf-8",
    )

    cfg = load_config(config_dir=config_dir)
    assert cfg.sample.metal_molar_mass_g_mol == DEFAULT_METAL_MOLAR_MASS


def test_system_volumes_from_loaded_config_match_core_config_derived_values() -> None:
    cfg = load_config()

    volumes = SystemVolumes(
        vessel=cfg.system.vessel_volume_l,
        valve=cfg.system.valve_volume_l,
        cell=cfg.system.cell_volume_l,
        manifold_m1m2=cfg.system.manifold_m1m2_volume_l,
        manifold_m1m2m3=cfg.system.manifold_m1m2m3_volume_l,
        tube_50ml=cfg.system.tube_50ml_volume_l,
        flask=cfg.system.flask_volume_l,
    )

    expected_v_m3 = (
        cfg.system.manifold_m1m2m3_volume_l
        - cfg.system.manifold_m1m2_volume_l
        - cfg.system.valve_volume_l
    )
    expected_v_tot = (
        cfg.system.manifold_m1m2m3_volume_l
        + cfg.system.cell_volume_l
        + cfg.system.valve_volume_l
        + cfg.system.tube_50ml_volume_l
    )

    assert volumes.m3 == expected_v_m3
    assert volumes.total == expected_v_tot
