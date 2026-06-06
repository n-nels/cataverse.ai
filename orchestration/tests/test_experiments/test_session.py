from __future__ import annotations

import json
from pathlib import Path
import re

from src.core.config_loader import PathsConfig, SampleConfig, SystemConstants
from src.experiments.session import ExperimentSession
from src.core.physics import SystemVolumes


def _sample_config() -> SampleConfig:
    return SampleConfig(
        notebook="nn1120-3",
        metal="pd",
        support="ceo2",
        mass_g=0.0164,
        metal_load_wt_percent=0.04983,
        support_surface_area_m2_g=54.0,
        metal_molar_mass_g_mol=106.42,
    )


def _system_volumes() -> SystemVolumes:
    return SystemVolumes(
        vessel=0.0119913,
        valve=0.000152,
        cell=0.03381,
        manifold_m1m2=0.078862,
        manifold_m1m2m3=0.11116,
        tube_50ml=0.05643,
        flask=1.004,
        gauge_max_pressure_torr=15.0,
    )


def _system_constants() -> SystemConstants:
    return SystemConstants(
        gas_constant=62.363577,
        manifold_temperature_k=298.0,
        vessel_volume_l=0.0119913,
        valve_volume_l=0.000152,
        cell_volume_l=0.03381,
        manifold_m1m2_volume_l=0.078862,
        manifold_m1m2m3_volume_l=0.11116,
        tube_50ml_volume_l=0.05643,
        flask_volume_l=1.004,
        gauge_max_pressure_torr=15.0,
    )


def _paths_config(tmp_path: Path) -> PathsConfig:
    return PathsConfig(
        data_directory=str(tmp_path / "data"),
        autonomous_parameters_directory=str(tmp_path / "autonomous"),
        share_drive_peak_fit_root=str(tmp_path / "share_peak_fit"),
        share_drive_pressure_data_root=str(tmp_path / "share_pressure"),
        share_drive_ms_calibrations_root=str(tmp_path / "share_ms"),
    )


def test_new_experiment_creates_directory_and_json(tmp_path: Path) -> None:
    session = ExperimentSession(
        sample=_sample_config(),
        volumes=_system_volumes(),
        constants=_system_constants(),
        paths=_paths_config(tmp_path),
    )

    file_name, folder_name = session.new_experiment(name=None, is_new=False)

    assert file_name
    assert folder_name
    assert re.match(r"^\d{8}_\d{6}_pd_ceo2_\d{3}-\d{3}$", file_name)
    assert re.match(r"^nn1120-3_pd_ceo2_\d{3}$", folder_name)

    data_root = Path(tmp_path / "data")
    assert (data_root / folder_name).exists()

    assert session.path_exp_params == str((data_root / folder_name / f"{file_name}_expParams.json"))
    assert Path(session.path_exp_params).exists()
    assert session.path_pressure_log == str((data_root / folder_name / f"{file_name}_pressureLog.csv"))
    assert session.path_ms_log == str((data_root / folder_name / f"{file_name}_msLog.csv"))

    payload = json.loads(Path(session.path_exp_params).read_text(encoding="utf-8"))
    assert payload["base_name"] == file_name
    assert payload["filename_flags"]["exp_success"] is False
    assert payload["filename_flags"]["has_csv"] is False
    assert payload["filename_flags"]["is_new"] is False
    assert payload["filename_flags"]["is_reference"] is False
    assert payload["pretreatments"] == []
    assert payload["exp_conditions"] == {}

    # second experiment in same sample should increment experiment index, same folder index
    file_name_2, folder_name_2 = session.new_experiment(name=None, is_new=False)
    assert folder_name_2.endswith("_000")
    assert file_name_2.endswith("_000-001")

    # new sample should increment folder index
    file_name_3, folder_name_3 = session.new_experiment(name=None, is_new=True)
    assert folder_name_3.endswith("_001")
    assert file_name_3.endswith("_001-000")


def test_log_pretreatment_and_experimental_parameters_write_json(tmp_path: Path) -> None:
    session = ExperimentSession(
        sample=_sample_config(),
        volumes=_system_volumes(),
        constants=_system_constants(),
        paths=_paths_config(tmp_path),
    )
    session.new_experiment(name=None, is_new=False)

    session.log_pretreatment(
        gas="H2",
        p_gas_meas=(1.0, 0.1),
        t_cell=25.0,
        rate=5,
        duration=1.0,
        p_gas_calc=0.95,
        chiller_state=True,
    )
    session.log_experimental_parameters(
        gas="CO",
        p_gas_meas=(0.5, 0.1),
        t_cell=35.0,
        p_gas_calc=0.48,
        chiller_state=False,
    )

    payload = session.build_exp_params_payload()
    assert payload["pretreatments"] == [
        {
            "step_index": 1,
            "gas": ["H2"],
            "pressure_meas_mfld": 1.0,
            "pressure_meas_cell": 0.1,
            "pressure_calc": [0.95],
            "temp": 25.0,
            "rate": 5.0,
            "duration": 1.0,
            "chiller": True,
        }
    ]
    assert payload["exp_conditions"] == {
        "gas": ["CO"],
        "pressure_meas_mfld": 0.5,
        "pressure_meas_cell": 0.1,
        "pressure_calc": [0.48],
        "temp": 35.0,
        "chiller": False,
    }
    assert "exp_conditions.pressure_meas_g1" not in json.dumps(payload)

    # log_experimental_parameters should be idempotent on repeat
    session.log_experimental_parameters(
        gas="CO",
        p_gas_meas=(0.5, 0.1),
        t_cell=35.0,
        p_gas_calc=0.48,
        chiller_state=False,
    )
    payload_after_repeat = session.build_exp_params_payload()
    assert payload_after_repeat["exp_conditions"] == payload["exp_conditions"]


def test_mark_success_updates_json(tmp_path: Path) -> None:
    session = ExperimentSession(
        sample=_sample_config(),
        volumes=_system_volumes(),
        constants=_system_constants(),
        paths=_paths_config(tmp_path),
    )
    session.new_experiment(name=None, is_new=False)

    # Verify initial state is False
    payload = json.loads(Path(session.path_exp_params).read_text(encoding="utf-8"))
    assert payload["filename_flags"]["exp_success"] is False

    session.mark_success(True)

    payload = json.loads(Path(session.path_exp_params).read_text(encoding="utf-8"))
    assert payload["filename_flags"]["exp_success"] is True


def test_build_exp_params_payload_pressure_normalization(tmp_path: Path) -> None:
    sample = SampleConfig(
        notebook="nn1120-3",
        metal="pd",
        support="ceo2",
        mass_g=0.0164,
        metal_load_wt_percent=0.04983,
        support_surface_area_m2_g=54.0,
        metal_molar_mass_g_mol=106.42,
    )
    session = ExperimentSession(
        sample=sample,
        volumes=_system_volumes(),
        constants=_system_constants(),
        paths=_paths_config(tmp_path),
    )
    session.new_experiment(name=None, is_new=False)

    session.log_pretreatment(
        gas=("O2", "H2O"),
        p_gas_meas=(3.092, None),
        t_cell=698.9,
        rate=0,
        duration=1,
        p_gas_calc=(2.98, None),
        chiller_state=True,
    )

    payload = session.build_exp_params_payload()

    assert payload["pretreatments"] == [
        {
            "step_index": 1,
            "gas": ["O2", "H2O"],
            "pressure_meas_mfld": 3.092,
            "pressure_meas_cell": None,
            "pressure_calc": [2.98, None],
            "temp": 698.9,
            "rate": 0.0,
            "duration": 1.0,
            "chiller": True,
        }
    ]
    assert payload["filename_flags"]["has_csv"] is False
    assert payload["filename_flags"]["exp_success"] is False
