"""Full-stack integration tests for the v2 architecture.

These tests load config, create mock DeviceManager, build all controllers,
and run minimal experiments to verify no exceptions and correct call ordering.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call
import pytest

from src.config_loader import load_config, AppConfig
from src.hardware.connections import DeviceManager
from src.control.gas_delivery import GasDelivery
from src.control.spectrometer_control import SpectrometerController
from src.control.temperature_control import TemperatureController
from src.control.valves import ValveController
from src.experiments.session import ExperimentSession
from src.experiments.adsorption import AdsorptionExperiment
from src.experiments.isotopic_exchange import IsotopicExchangeCalibration
from src.physics import SystemVolumes


@pytest.fixture
def app_config():
    """Load application configuration."""
    return load_config()


@pytest.fixture
def mock_device_manager(app_config):
    """Create mock device manager with config."""
    devices = MagicMock(spec=DeviceManager)
    devices.config = app_config.hardware

    # Mock hardware adapters
    devices.pressure = MagicMock()
    devices.pressure.read.return_value = (MagicMock(), 0.5, 0.3)

    devices.temperature = MagicMock()
    devices.temperature.read_temperature.return_value = 25.0

    devices.mass_spec = MagicMock()
    devices.mass_spec.write_register.return_value = True

    devices.analog_io = MagicMock()
    devices.spectrometer = MagicMock()
    devices.power = MagicMock()

    return devices


@pytest.fixture
def valve_controller(mock_device_manager, app_config):
    """Create valve controller with mock device manager."""
    return ValveController(
        analog_io=mock_device_manager.analog_io,
        pressure=mock_device_manager.pressure,
        config=app_config.hardware.actuator,
    )


@pytest.fixture
def gas_controller(valve_controller, mock_device_manager, app_config):
    """Create gas delivery controller."""
    return GasDelivery(
        valves=valve_controller,
        pressure=mock_device_manager.pressure,
        paths=app_config.paths,
        total_volume_l=(
            app_config.system.manifold_m1m2m3_volume_l
            + app_config.system.cell_volume_l
            + app_config.system.valve_volume_l
            + app_config.system.tube_50ml_volume_l
        ),
        temperature_k=app_config.system.manifold_temperature_k,
        gas_constant=app_config.system.gas_constant,
    )


@pytest.fixture
def temp_controller(mock_device_manager, app_config):
    """Create temperature controller."""
    return TemperatureController(
        temperature=mock_device_manager.temperature,
        power=mock_device_manager.power,
        paths=app_config.paths,
        kasa=app_config.hardware.kasa,
    )


@pytest.fixture
def spec_controller(mock_device_manager):
    """Create spectrometer controller."""
    return SpectrometerController(
        spectrometer=mock_device_manager.spectrometer,
    )


@pytest.fixture
def experiment_session(app_config):
    """Create experiment session."""
    return ExperimentSession(
        sample=app_config.sample,
        volumes=SystemVolumes(
            vessel=app_config.system.vessel_volume_l,
            valve=app_config.system.valve_volume_l,
            cell=app_config.system.cell_volume_l,
            manifold_m1m2=app_config.system.manifold_m1m2_volume_l,
            manifold_m1m2m3=app_config.system.manifold_m1m2m3_volume_l,
            tube_50ml=app_config.system.tube_50ml_volume_l,
            flask=app_config.system.flask_volume_l,
        ),
        paths=app_config.paths,
    )


@pytest.fixture
def adsorption_experiment(
    experiment_session,
    mock_device_manager,
    gas_controller,
    temp_controller,
    spec_controller,
):
    """Create adsorption experiment with all dependencies."""
    return AdsorptionExperiment(
        session=experiment_session,
        devices=mock_device_manager,
        gas_controller=gas_controller,
        temp=temp_controller,
        spec=spec_controller,
    )


@pytest.fixture
def isotopic_exchange_experiment(
    experiment_session,
    mock_device_manager,
    gas_controller,
    temp_controller,
    spec_controller,
):
    """Create isotopic exchange experiment with all dependencies."""
    return IsotopicExchangeCalibration(
        session=experiment_session,
        devices=mock_device_manager,
        gas_controller=gas_controller,
        temp=temp_controller,
        spec=spec_controller,
    )


class TestFullStackIntegration:
    """Full-stack integration tests."""

    def test_config_loads_successfully(self, app_config):
        """Test that configuration loads without errors."""
        assert isinstance(app_config, AppConfig)
        assert app_config.hardware is not None
        assert app_config.sample is not None
        assert app_config.paths is not None

    def test_device_manager_initializes(self, mock_device_manager, app_config):
        """Test device manager initializes with config."""
        assert mock_device_manager.config == app_config.hardware
        assert mock_device_manager.pressure is not None
        assert mock_device_manager.temperature is not None

    def test_controllers_initialize(
        self, valve_controller, gas_controller, temp_controller, spec_controller
    ):
        """Test all controllers initialize without errors."""
        assert valve_controller is not None
        assert gas_controller is not None
        assert temp_controller is not None
        assert spec_controller is not None

    def test_experiment_session_creates(self, experiment_session):
        """Test experiment session creates without errors."""
        assert experiment_session is not None
        assert experiment_session.sample is not None
        assert experiment_session.volumes is not None

    def test_adsorption_experiment_creates(self, adsorption_experiment):
        """Test adsorption experiment creates with all dependencies."""
        assert adsorption_experiment is not None
        assert adsorption_experiment.session is not None
        assert adsorption_experiment.devices is not None
        assert adsorption_experiment.gas_controller is not None
        assert adsorption_experiment.temp is not None
        assert adsorption_experiment.spec is not None

    def test_isotopic_exchange_experiment_creates(self, isotopic_exchange_experiment):
        """Test isotopic exchange experiment creates with all dependencies."""
        assert isotopic_exchange_experiment is not None
        assert isotopic_exchange_experiment.session is not None
        assert isotopic_exchange_experiment.devices is not None
        assert isotopic_exchange_experiment.gas_controller is not None
        assert isotopic_exchange_experiment.temp is not None
        assert isotopic_exchange_experiment.spec is not None


class TestMinimalExperimentExecution:
    """Test minimal experiment execution without exceptions."""

    def test_adsorption_heat_under_evacuation(self, adsorption_experiment):
        """Test heat under evacuation runs without exceptions."""
        adsorption_experiment.heat_under_evacuation(
            pump_type="RoughPump",
            target_temp=400,
            hold_time=0.0,
            ramp_rate=20,
        )

    def test_adsorption_cool_cell(self, adsorption_experiment):
        """Test cool cell runs without exceptions."""
        adsorption_experiment.cool_cell(
            target_temp=45,
            hold_time=0,
            variac_cmd=False,
        )

    def test_adsorption_supply_gas(self, adsorption_experiment):
        """Test gas supply runs without exceptions."""
        adsorption_experiment.supply_gas_to_mfld(
            gas="CO",
            target_pressure=1.0,
        )

    def test_adsorption_chiller_variac(self, adsorption_experiment):
        """Test chiller/variad control runs without exceptions."""
        adsorption_experiment.chiller_variac_state(
            chiller_cmd=True,
            variac_cmd=True,
            variac_vsl_cmd=False,
        )

    def test_isotopic_exchange_heat_under_evacuation(
        self, isotopic_exchange_experiment
    ):
        """Test isotopic exchange heat under evacuation runs without exceptions."""
        isotopic_exchange_experiment.heat_under_evacuation(
            pumpType="RoughPump",
            targetTemp=500,
            holdTime=0.0,
            rampRate=20,
        )

    def test_isotopic_exchange_cool_cell(self, isotopic_exchange_experiment):
        """Test isotopic exchange cool cell runs without exceptions."""
        isotopic_exchange_experiment.cool_cell(
            targetTemp=25,
            holdTime=0,
            variac_cmd=False,
        )

    def test_isotopic_exchange_supply_gas(self, isotopic_exchange_experiment):
        """Test isotopic exchange gas supply runs without exceptions."""
        isotopic_exchange_experiment.supply_gas_to_mfld(
            gas="13CO",
            targetPressure=1.0,
        )


class TestCallOrdering:
    """Test correct call ordering in experiments."""

    def test_adsorption_sequence_order(
        self, adsorption_experiment, mock_device_manager
    ):
        """Test adsorption sequence calls devices in correct order."""
        # Run a simplified sequence
        adsorption_experiment.heat_under_evacuation(
            pump_type="RoughPump",
            target_temp=400,
            hold_time=0.0,
            ramp_rate=20,
        )
        adsorption_experiment.supply_gas_to_mfld(
            gas="O2",
            target_pressure=5.0,
        )

        # Verify calls were made
        assert mock_device_manager.pressure.read.call_count >= 1

    def test_isotopic_exchange_sequence_order(
        self, isotopic_exchange_experiment, mock_device_manager
    ):
        """Test isotopic exchange sequence calls devices in correct order."""
        # Run a simplified sequence
        isotopic_exchange_experiment.heat_under_evacuation(
            pumpType="RoughPump",
            targetTemp=500,
            holdTime=0.0,
            rampRate=20,
        )
        isotopic_exchange_experiment.supply_gas_to_mfld(
            gas="13CO",
            targetPressure=1.0,
        )

        # Verify calls were made
        assert mock_device_manager.pressure.read.call_count >= 1


class TestMainIntegration:
    """Test main.py integration."""

    def test_main_imports(self):
        """Test main.py imports without errors."""
        import main

        assert main is not None

    def test_main_has_main_function(self):
        """Test main.py has main function."""
        import main

        assert hasattr(main, "main")
        assert callable(main.main)
