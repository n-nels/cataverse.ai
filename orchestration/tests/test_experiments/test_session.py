from __future__ import annotations

from pathlib import Path
import re

from src.core.config_loader import PathsConfig, SampleConfig
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
    )


def _paths_config(tmp_path: Path) -> PathsConfig:
    return PathsConfig(
        data_directory=str(tmp_path / "data"),
        autonomous_parameters_directory=str(tmp_path / "autonomous"),
        share_drive_peak_fit_root=str(tmp_path / "share_peak_fit"),
        share_drive_pressure_data_root=str(tmp_path / "share_pressure"),
        share_drive_ms_calibrations_root=str(tmp_path / "share_ms"),
    )


def test_new_experiment_creates_directory_and_readme(tmp_path: Path) -> None:
    session = ExperimentSession(
        sample=_sample_config(),
        volumes=_system_volumes(),
        paths=_paths_config(tmp_path),
    )

    file_name, folder_name = session.new_experiment(name=None, new_sample=False)

    assert file_name
    assert folder_name
    assert re.match(r"^\d{8}_\d{6}_pd_ceo2_\d{3}-\d{3}$", file_name)
    assert re.match(r"^nn1120-3_pd_ceo2_\d{3}$", folder_name)

    data_root = Path(tmp_path / "data")
    assert (data_root / folder_name).exists()

    assert session.path_readme is not None
    assert Path(session.path_readme).exists()
    assert Path(session.path_readme).parent.name == folder_name
    assert session.path_pressure_log == str((data_root / folder_name / f"{file_name}_pressureLog.csv"))
    assert session.path_ms_log == str((data_root / folder_name / f"{file_name}_msLog.csv"))

    content = Path(session.path_readme).read_text(encoding="utf-8")
    assert "## notebook" in content
    assert "## exp_success" in content
    assert "- Value: False" in content

    # second experiment in same sample should increment experiment index, same folder index
    file_name_2, folder_name_2 = session.new_experiment(name=None, new_sample=False)
    assert folder_name_2.endswith("_000")
    assert file_name_2.endswith("_000-001")

    # new sample should increment folder index
    file_name_3, folder_name_3 = session.new_experiment(name=None, new_sample=True)
    assert folder_name_3.endswith("_001")
    assert file_name_3.endswith("_001-000")


def test_log_pretreatment_and_experimental_parameters_append_to_readme(tmp_path: Path) -> None:
    session = ExperimentSession(
        sample=_sample_config(),
        volumes=_system_volumes(),
        paths=_paths_config(tmp_path),
    )
    session.new_experiment(name=None, new_sample=False)

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

    assert session.path_readme is not None
    content = Path(session.path_readme).read_text(encoding="utf-8")
    assert "## pretreatment_1" in content
    assert "## exp_gas" in content
    assert "- Value: CO" in content
    assert "## exp_pressure_meas" in content
    assert "## exp_pressure_calc" in content
    assert "## exp_temp" in content

    # log_experimental_parameters should be idempotent on repeat
    session.log_experimental_parameters(
        gas="CO",
        p_gas_meas=(0.5, 0.1),
        t_cell=35.0,
        p_gas_calc=0.48,
        chiller_state=False,
    )
    content_after_repeat = Path(session.path_readme).read_text(encoding="utf-8")
    assert content_after_repeat.count("## exp_gas") == 1


def test_mark_success_updates_existing_success_value(tmp_path: Path) -> None:
    session = ExperimentSession(
        sample=_sample_config(),
        volumes=_system_volumes(),
        paths=_paths_config(tmp_path),
    )
    session.new_experiment(name=None, new_sample=False)

    session.mark_success(True)

    assert session.path_readme is not None
    content = Path(session.path_readme).read_text(encoding="utf-8")
    assert content.count("## exp_success") == 1
    assert "- Value: True" in content
    assert "- Value: False" not in content
