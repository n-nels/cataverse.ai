"""Integration tests for adsorption experiment.

These tests mock all hardware and verify the correct order of control calls
and logging start/stops for the adsorption experiment protocol.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call
import pytest

from src.experiments.adsorption import AdsorptionExperiment
from src.experiments.session import ExperimentSession


@pytest.fixture
def mock_devices():
    """Create mock device manager."""
    devices = MagicMock()
    devices.pressure.read.return_value = (MagicMock(), 0.5, 0.3)
    devices.temperature.read_temperature.return_value = 25.0
    devices.mass_spec.write_register.return_value = True
    devices.config.extrel_ms.registers.sequence_start_address = 1
    devices.config.extrel_ms.registers.sequence_start_value = 2
    devices.config.extrel_ms.registers.sequence_stop_address = 1
    devices.config.extrel_ms.registers.sequence_stop_value = 9
    return devices


@pytest.fixture
def mock_gas_controller():
    """Create mock gas delivery controller."""
    gas_controller = MagicMock()
    gas_controller.evacuate_cell.return_value = "RoughPump"
    gas_controller.deliver_gas_to_manifold.return_value = ("CO", 1.0)
    gas_controller.pressure.read.return_value = (MagicMock(), 0.5, 0.3)
    gas_controller.temperature.read_temperature.return_value = 25.0
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
    session.path_ms_log = "/tmp/test_ms.csv"
    session.path_readme = "/tmp/test_readme.md"
    session.sample.mass_g = 0.01
    session.sample.metal_load_wt_percent = 5.0
    session.sample.metal_molar_mass_g_mol = 106.42
    session.volumes.total = 0.5
    return session


@pytest.fixture
def adsorption_experiment(
    mock_session,
    mock_devices,
    mock_gas_controller,
    mock_temp_controller,
    mock_spec_controller,
):
    """Create adsorption experiment instance with mocked dependencies."""
    return AdsorptionExperiment(
        session=mock_session,
        devices=mock_devices,
        gas_controller=mock_gas_controller,
        temp=mock_temp_controller,
        spec=mock_spec_controller,
    )


class TestAdsorptionExperiment:
    """Test adsorption experiment methods."""

    def test_acquire_ms_spectra(
        self, adsorption_experiment, mock_gas_controller, mock_devices
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
            mock_devices.mass_spec.write_register.assert_called_with(address=1, value=2)

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
        mock_gas_controller.pressure.read.assert_called()

    def test_cool_cell(
        self, adsorption_experiment, mock_temp_controller, mock_gas_controller
    ):
        """Test cool cell sequence."""
        mock_gas_controller.temperature.read_temperature.side_effect = [100, 50, 26, 25]

        adsorption_experiment.cool_cell(
            target_temp=25,
            hold_time=0,
            variac_cmd=False,
        )

        # Verify Watlow called
        mock_temp_controller.watlow.assert_called_once()

        # Verify temperature readings
        assert mock_gas_controller.temperature.read_temperature.call_count >= 1

    def test_supply_gas_to_mfld(self, adsorption_experiment, mock_gas_controller):
        """Test gas supply to manifold."""
        adsorption_experiment.supply_gas_to_mfld(gas="CO", target_pressure=1.0)

        # Verify gas delivery called
        mock_gas_controller.deliver_gas_to_manifold.assert_called_once()

    def test_supply_another_gas_to_mfld(
        self, adsorption_experiment, mock_gas_controller
    ):
        """Test second gas supply to manifold."""
        adsorption_experiment.supply_another_gas_to_mfld(
            gas="13CO", target_pressure=1.0
        )

        # Verify valve sequence
        mock_gas_controller.valves.close.assert_called_with("v16")
        mock_gas_controller.valves.open.assert_any_call("TurboPump")

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
        mock_gas_controller.pressure.read.assert_called()

    def test_introduce_pretreatment_gas_to_cell(
        self, adsorption_experiment, mock_gas_controller, mock_temp_controller
    ):
        """Test pretreatment gas introduction."""
        adsorption_experiment.introduce_pretreatment_gas_to_cell(
            target_temp=500,
            hold_time=2.0,
        )

        # Verify gas delivery to cell
        mock_gas_controller.deliver_gas_to_cell.assert_called_once()

        # Verify Watlow called
        mock_temp_controller.watlow.assert_called_once()

    def test_chiller_variac_state(self, adsorption_experiment, mock_temp_controller):
        """Test chiller and variac state control."""
        adsorption_experiment.chiller_variac_state(
            chiller_cmd=True,
            variac_cmd=True,
            variac_vsl_cmd=False,
        )

        # Verify Kasa plug states set
        assert mock_temp_controller.kasa_plug_state.call_count >= 2

    def test_start_pressure_log(self, adsorption_experiment, mock_gas_controller):
        """Test pressure logging thread start."""
        pressure_logger = adsorption_experiment.start_pressure_log(0.5, 0.3)

        # Verify logger returned
        assert pressure_logger is not None

    def test_start_temperature_log(self, adsorption_experiment, mock_gas_controller):
        """Test temperature logging thread start."""
        thread, stop_event = adsorption_experiment.start_temperature_log()

        # Verify thread returned
        assert thread is not None
        assert stop_event is not None


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
        adsorption_experiment.introduce_pretreatment_gas_to_cell(
            target_temp=500, hold_time=2
        )
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
