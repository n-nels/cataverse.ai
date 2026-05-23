"""
Experiment initialization — wires config, devices, controllers, and session.

Usage:
    from src.experiments.setup import initialize

    inst = initialize(mock=True)
    # inst.gas, inst.temp, inst.ftir, inst.ms, inst.session are ready to use
"""

from dataclasses import dataclass

from src.core.config_loader import load_config
from src.core.physics import SystemVolumes
from src.datalog import get_logger
from src.experiments.session import ExperimentSession
from src.hardware.connections import DeviceManager
from src.hardware.mocks import create_mock_devices
from src.control.spectrometer_control import SpectrometerController
from src.control.mass_spec_control import MassSpecController
from src.control.temperature_control import TemperatureController
from src.control.valves import ValveController
from src.control.gas_delivery import GasDelivery


logger = get_logger(__name__)


@dataclass
class Instruments:
    """All wired controllers and session, ready for experiment use."""

    devices: DeviceManager
    gas: GasDelivery
    temp: TemperatureController
    ftir: SpectrometerController
    ms: MassSpecController
    session: ExperimentSession
    mock: bool = False


def initialize(mock: bool = False) -> Instruments:
    """
    Wire up config, devices, and controllers.

    Call this once at program start. Returns an Instruments bundle containing
    everything needed to run any experiment protocol.
    """
    config = load_config()

    if mock:
        logger.info("Running in MOCK mode - no real hardware required")
        devices = create_mock_devices(config)
    else:
        logger.info("Running with REAL hardware")
        devices = DeviceManager(config.hardware)
        devices.connect()

    valves = ValveController(
        devices.analog_io, devices.pressure, config.hardware.actuator
    )
    volumes = SystemVolumes(
        vessel=config.system.vessel_volume_l,
        valve=config.system.valve_volume_l,
        cell=config.system.cell_volume_l,
        manifold_m1m2=config.system.manifold_m1m2_volume_l,
        manifold_m1m2m3=config.system.manifold_m1m2m3_volume_l,
        tube_50ml=config.system.tube_50ml_volume_l,
        flask=config.system.flask_volume_l,
        gauge_max_pressure_torr=config.system.gauge_max_pressure_torr,
    )

    gas = GasDelivery(
        valves=valves,
        pressure=devices.pressure,
        total_volume_l=volumes.total,
        temperature_k=config.system.manifold_temperature_k,
        gas_constant=config.system.gas_constant,
    )
    temp = TemperatureController(
        temperature=devices.temperature,
        power=devices.power,
        paths=config.paths,
        kasa=config.hardware.kasa,
    )
    ftir = SpectrometerController(devices.spectrometer)
    ms = MassSpecController(
        mass_spec=devices.mass_spec,
        registers=config.hardware.extrel_ms.registers,
        stream_tags=config.hardware.extrel_ms.stream_tags,
    )

    session = ExperimentSession(
        sample=config.sample,
        volumes=volumes,
        constants=config.system,
        paths=config.paths,
    )

    return Instruments(
        devices=devices,
        gas=gas,
        temp=temp,
        ftir=ftir,
        ms=ms,
        session=session,
        mock=mock,
    )
