"""Integration tests for adsorption experiment.

These tests mock all hardware and verify the correct order of control calls
and logging start/stops for the adsorption experiment protocol.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call
import pytest

from src.control.mass_spec_control import MassSpecController
from src.experiments.adsorption import AdsorptionExperiment
from src.experiments.session import ExperimentSession


@pytest.fixture
def mock_mass_spec_adapter():
    """Create mock Extrel hardware adapter."""
    adapter = MagicMock()
    adapter.write_register.return_value = True
    return adapter


@pytest.fixture
def mock_extrel_registers():
    """Create mock Extrel register config."""
    registers = MagicMock()
    registers.sequence_start_address = 1
    registers.sequence_start_value = 2
    registers.sequence_stop_address = 1
    registers.sequence_stop_value = 9
    return registers


@pytest.fixture
def mock_mass_spec_controller(mock_mass_spec_adapter, mock_extrel_registers):
    """Create mass-spec controller with mocked dependencies."""
    return MassSpecController(
        mass_spec=mock_mass_spec_adapter,
        registers=mock_extrel_registers,
    )


@pytest.fixture
def mock_gas_controller():
    """Create mock gas delivery controller."""
    gas_controller = MagicMock()
    gas_controller.evacuate_cell.return_value = "RoughPump"
    gas_controller.deliver_gas_to_manifold.return_value = ("CO", 1.0)
    gas_controller.read_pressure.return_value = (MagicMock(), 0.5, 0.3)
    return gas_controller


@pytest.fixture
def mock_temp_controller():
    """Create mock temperature controller."""
    temp = MagicMock()
    temp.watlow.return_value = (500, 20, 2.0)
    return temp


@pytest.fixture
def mock_spec_controller():
    """Create mock spectrometer controller."""
    spec = MagicMock()
    spec.opus_acquire.return_value = None
    spec.opus_vertex80.return_value = "fileid123"
    return spec


@pytest.fixture
def mock_session():
    """Create mock experiment session."""
    session = MagicMock(spec=ExperimentSession)
    session.file_name = "test_experiment"
    session.folder_name = "test_folder"
    session.path_pressure_log = "/tmp/test_pressure.csv"
    session.path_actuator_log = "/tmp/test_act.csv"
    session.path_ms_log = "/tmp/test_ms.csv"
    session.path_readme = "/tmp/test_readme.md"
    session.paths.data_directory = "/tmp"
    session.paths.share_drive_peak_fit_root = "/tmp"
    session.paths.share_drive_pressure_data_root = "/tmp"
    session.sample.mass_g = 0.01
    session.sample.metal_load_wt_percent = 5.0
    session.sample.metal_molar_mass_g_mol = 106.42
    session.volumes.total = 0.5
    return session


@pytest.fixture
def adsorption_experiment(
    mock_session,
    mock_mass_spec_controller,
    mock_gas_controller,
    mock_temp_controller,
    mock_spec_controller,
):
    """Create adsorption experiment instance with mocked dependencies."""
    return AdsorptionExperiment(
        session=mock_session,
        gas_controller=mock_gas_controller,
        temp=mock_temp_controller,
        ftir=mock_spec_controller,
        ms=mock_mass_spec_controller,
    )


class TestAdsorptionExperiment:
    """Test adsorption experiment methods."""

    def test_acquire_ms_spectra(
        self, adsorption_experiment, mock_gas_controller, mock_mass_spec_adapter
    ):
        """Test MS spectra acquisition sequence."""
        with patch("src.experiments.adsorption.MassSpecLogger") as mock_logger_class:
            mock_logger = MagicMock()
            mock_logger_class.return_value = mock_logger

            result = adsorption_experiment.acquire_ms_spectra()

            # Verify valve sequence
            mock_gas_controller.valves.close.assert_called_with("irCell")
            mock_gas_controller.valves.open.assert_called_with("MassSpec")

            # Verify Extrel sequence start
            mock_mass_spec_adapter.write_register.assert_called_with(address=1, value=2)

            # Verify MS logger started
            mock_logger.start.assert_called_once()

            assert result == mock_logger

    def test_heat_under_evacuation(
        self, adsorption_experiment, mock_gas_controller, mock_temp_controller
    ):
        """Test heat under evacuation sequence."""
        adsorption_experiment.heat_under_evacuation(
            pump_type="RoughPump",
            target_temp=500,
            hold_time=2.0,
            ramp_rate=20,
        )

        # Verify evacuation called
        mock_gas_controller.evacuate_cell.assert_called_with("RoughPump")

        # Verify Watlow called
        mock_temp_controller.watlow.assert_called_once()

        # Verify pressure read
        mock_gas_controller.read_pressure.assert_called()

    def test_cool_cell(
        self, adsorption_experiment, mock_temp_controller, mock_gas_controller
    ):
        """Test cool cell sequence."""
        mock_temp_controller.read_temperature.side_effect = [100, 50, 26, 25]

        adsorption_experiment.cool_cell(
            target_temp=25,
            hold_time=0,
            variac_cmd=False,
        )

        # Verify Watlow called
        mock_temp_controller.watlow.assert_called_once()

        # Verify temperature readings
        assert mock_temp_controller.read_temperature.call_count >= 1

    def test_supply_gas_to_mfld(self, adsorption_experiment, mock_gas_controller):
        """Test gas supply to manifold."""
        adsorption_experiment.supply_gas_to_mfld(gas="CO", target_pressure=1.0)

        # Verify gas delivery called
        mock_gas_controller.deliver_gas_to_manifold.assert_called_once()

    def test_acquire_spectra(
        self, adsorption_experiment, mock_spec_controller, mock_gas_controller
    ):
        """Test spectra acquisition sequence."""
        adsorption_experiment.acquire_spectra(
            repeat=[10, 5],
            delay=[60, 300],
            all_fileids=True,
            do_bckg=True,
            do_fit=True,
        )

        # Verify OPUS acquire called
        mock_spec_controller.opus_acquire.assert_called()

        # Verify pressure logging started
        mock_gas_controller.read_pressure.assert_called()

    def test_deliver_gas_to_cell(
        self, adsorption_experiment, mock_gas_controller
    ):
        """Test gas delivery to cell."""
        adsorption_experiment.deliver_gas_to_cell()

        # Verify gas delivery to cell
        mock_gas_controller.deliver_gas_to_cell.assert_called_once()
        mock_gas_controller.read_pressure.assert_called()

    def test_chiller_variac_state(self, adsorption_experiment, mock_temp_controller):
        """Test chiller and variac state control."""
        adsorption_experiment.chiller_variac_state(
            chiller_cmd=True,
            variac_cmd=True,
            variac_vsl_cmd=False,
        )

        # Verify Kasa plug states set via set_plug_state
        assert mock_temp_controller.set_plug_state.call_count == 3
        mock_temp_controller.set_plug_state.assert_any_call(
            mock_temp_controller.kasa.chiller_id, True
        )
        mock_temp_controller.set_plug_state.assert_any_call(
            mock_temp_controller.kasa.variac_id, True
        )
        mock_temp_controller.set_plug_state.assert_any_call(
            mock_temp_controller.kasa.variac_id_vsl, False
        )

    def test_start_pressure_log(self, adsorption_experiment, mock_gas_controller):
        """Test pressure logging thread start."""
        pressure_logger = adsorption_experiment.start_pressure_log(0.5, 0.3)

        # Verify logger returned
        assert pressure_logger is not None


class TestAdsorptionExperimentSequence:
    """Test adsorption experiment call sequences."""

    def test_full_adsorption_sequence(
        self,
        adsorption_experiment,
        mock_gas_controller,
        mock_temp_controller,
        mock_spec_controller,
    ):
        """Test a simplified full adsorption sequence."""
        # Clean surface
        adsorption_experiment.chiller_variac_state(
            chiller_cmd=True, variac_cmd=True, variac_vsl_cmd=True
        )
        adsorption_experiment.heat_under_evacuation(
            pump_type="RoughPump", target_temp=400, hold_time=0.0, ramp_rate=20
        )
        adsorption_experiment.heat_under_evacuation(
            pump_type="TurboPump", target_temp=400, hold_time=2.0, ramp_rate=0
        )

        # Oxidize surface
        adsorption_experiment.supply_gas_to_mfld(gas="O2", target_pressure=5.0)
        adsorption_experiment.deliver_gas_to_cell()
        adsorption_experiment.heat_cell(target_temp=500, hold_time=2, ramp_rate=0)
        adsorption_experiment._log_pretreatment(500, 0, 2, log_gas_calc=True)
        adsorption_experiment.heat_under_evacuation(
            pump_type="TurboPump", target_temp=500, hold_time=0.5, ramp_rate=0
        )

        # Cool and adsorb
        adsorption_experiment.cool_cell(target_temp=45, hold_time=0, variac_cmd=False)
        adsorption_experiment.chiller_variac_state(
            chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False
        )
        adsorption_experiment.supply_gas_to_mfld(gas="13CO", target_pressure=1.0)

        # Verify key calls were made
        assert mock_gas_controller.evacuate_cell.call_count >= 2
        assert mock_gas_controller.deliver_gas_to_manifold.call_count >= 2
        assert mock_temp_controller.watlow.call_count >= 2
