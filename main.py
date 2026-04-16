"""
Main entry point for CataVerse instrument control.

This file demonstrates how to run the instrument control system
across its architecture layers (config, hardware, control, datalog, experiments).

Usage:
    python main.py              # Run with real hardware
    python main.py --mock       # Run with mock hardware (for testing/debugging)
    python main.py --mock --adsorption  # Run adsorption experiment with mocks
    python main.py --mock --isotopic    # Run isotopic exchange with mocks
"""

import argparse
from unittest.mock import MagicMock

from src.config_loader import load_config
from src.datalog import get_logger, configure_logging
from src.physics import SystemVolumes
from src.experiments.session import ExperimentSession
from src.hardware.connections import DeviceManager
from src.control.spectrometer_control import SpectrometerController
from src.control.temperature_control import TemperatureController
from src.control.valves import ValveController
from src.control.gas_delivery import GasDelivery
from src.experiments.adsorption import AdsorptionExperiment
from src.experiments.isotopic_exchange import IsotopicExchangeCalibration



logger = get_logger(__name__)


def create_mock_devices(config):
    """Create mock device manager for testing without hardware."""
    devices = MagicMock(spec=DeviceManager)
    devices.config = config.hardware

    devices.pressure = MagicMock()
    devices.pressure.read.return_value = (MagicMock(), 0.01, 0.01)

    devices.temperature = MagicMock()
    devices.temperature.read_temperature.return_value = 25.0

    devices.mass_spec = MagicMock()
    devices.mass_spec.write_register.return_value = True
    devices.mass_spec.read_registers.return_value = [1, 2]

    devices.analog_io = MagicMock()
    devices.analog_io.write.return_value = None

    devices.spectrometer = MagicMock()
    devices.spectrometer.send.return_value = "OK"
    devices.spectrometer.receive.return_value = "fileid123"

    devices.power = MagicMock()
    devices.power.set_state.return_value = True

    devices.connect.return_value = None
    devices.disconnect.return_value = None

    return devices


def create_real_devices(config):
    """Create real device manager for hardware."""
    devices = DeviceManager(config.hardware)
    devices.connect()
    return devices


def main():
    """Main entry point for CataVerse instrument control."""
    configure_logging()
    parser = argparse.ArgumentParser(description="CataVerse instrument control")
    parser.add_argument(
        "--mock", action="store_true", help="Use mock hardware for testing"
    )
    parser.add_argument(
        "--adsorption", action="store_true", help="Run adsorption experiment"
    )
    parser.add_argument(
        "--isotopic", action="store_true", help="Run isotopic exchange experiment"
    )
    args = parser.parse_args()

    config = load_config()

    if args.mock:
        logger.info("Running in MOCK mode - no real hardware required")
        devices = create_mock_devices(config)
    else:
        logger.info("Running with REAL hardware")
        devices = create_real_devices(config)

    valves = ValveController(
        devices.analog_io, devices.pressure, config.hardware.actuator
    )
    gas_controller = GasDelivery(
        valves=valves,
        pressure=devices.pressure,
        paths=config.paths,
        total_volume_l=(
            config.system.manifold_m1m2m3_volume_l
            + config.system.cell_volume_l
            + config.system.valve_volume_l
            + config.system.tube_50ml_volume_l
        ),
        temperature_k=config.system.manifold_temperature_k,
        gas_constant=config.system.gas_constant,
    )
    temp_controller = TemperatureController(
        temperature=devices.temperature,
        power=devices.power,
        paths=config.paths,
        kasa=config.hardware.kasa,
    )
    spec_controller = SpectrometerController(devices.spectrometer)

    session = ExperimentSession(
        sample=config.sample,
        volumes=SystemVolumes(
            vessel=config.system.vessel_volume_l,
            valve=config.system.valve_volume_l,
            cell=config.system.cell_volume_l,
            manifold_m1m2=config.system.manifold_m1m2_volume_l,
            manifold_m1m2m3=config.system.manifold_m1m2m3_volume_l,
            tube_50ml=config.system.tube_50ml_volume_l,
            flask=config.system.flask_volume_l,
        ),
        paths=config.paths,
    )

    ads_exp = AdsorptionExperiment(
        session=session,
        devices=devices,
        gas_controller=gas_controller,
        temp=temp_controller,
        spec=spec_controller,
    )

    iso_exp = IsotopicExchangeCalibration(
        session=session,
        devices=devices,
        gas_controller=gas_controller,
        temp=temp_controller,
        spec=spec_controller,
    )

    def run_adsorption_experiment():
        logger.info("Starting adsorption experiment...")
        session.new_experiment()
        logger.info("Cleaning surface...")
        ads_exp.chiller_variac_state(
            chiller_cmd=True, variac_cmd=True, variac_vsl_cmd=True
        )
        ads_exp.heat_under_evacuation(
            pump_type="RoughPump", target_temp=25, hold_time=0.0, ramp_rate=20
        )
        ads_exp.heat_under_evacuation(
            pump_type="TurboPump", target_temp=25, hold_time=0.0, ramp_rate=0
        )
        logger.info("Oxidizing surface...")
        ads_exp.introduce_pretreatment_gas_to_cell(target_temp=25, hold_time=0)
        ads_exp.heat_under_evacuation(
            pump_type="TurboPump", target_temp=25, hold_time=0.0, ramp_rate=0
        )
        logger.info("Adsorbing 13CO...")
        ads_exp.cool_cell(target_temp=45, hold_time=0, variac_cmd=False)
        ads_exp.chiller_variac_state(
            chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False
        )
        ads_exp.acquire_spectra(
            repeat=[0],
            delay=[0],
            all_fileids=True,
            do_bckg=True,
            do_fit=True,
        )
        logger.info("Adsorption experiment completed!")

    def run_isotopic_exchange_calibration():
        logger.info("Starting isotopic exchange calibration...")
        session.new_experiment()
        logger.info("Cleaning surface...")
        iso_exp.chiller_variac_state(
            chiller_cmd=True, variac_cmd=True, variac_vsl_cmd=True
        )
        iso_exp.heat_under_evacuation(
            pumpType="RoughPump", targetTemp=500, holdTime=0.0, rampRate=20
        )
        iso_exp.heat_under_evacuation(
            pumpType="TurboPump", targetTemp=500, holdTime=2.0, rampRate=0
        )
        logger.info("Pretreating surface...")
        iso_exp.supply_gas_to_mfld(gas="O2", targetPressure=5.0)
        iso_exp.introduce_pretreatment_gas_to_cell(targetTemp=500, holdTime=2)
        iso_exp.heat_under_evacuation(
            pumpType="TurboPump", targetTemp=500, holdTime=0.5, rampRate=0
        )
        logger.info("Adsorbing 13CO...")
        iso_exp.cool_cell(targetTemp=45, holdTime=0, variac_cmd=False)
        iso_exp.chiller_variac_state(
            chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False
        )
        iso_exp.supply_gas_to_mfld(gas="13CO", targetPressure=1.0)
        iso_exp.acquire_spectra(
            repeat=[10, 5, 15, 60],
            delay=[60, 300, 600, 1800],
            all_fileids=True,
            do_bckg=True,
            do_fit=True,
        )
        iso_exp.copy_readme()
        logger.info("Cooling for isotopic exchange...")
        iso_exp.chiller_variac_state(
            chiller_cmd=True, variac_cmd=False, variac_vsl_cmd=False
        )
        iso_exp.cool_cell(targetTemp=25, holdTime=0, variac_cmd=False)
        iso_exp.chiller_variac_state(
            chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False
        )
        logger.info("Running isotopic exchange...")
        iso_exp.isoX_calib_main(
            xchgTime=[2, 4, 6, 8, 9, 10, 11, 12, 14, 16], sleepTime=2
        )
        logger.info("Final cleaning...")
        iso_exp.chiller_variac_state(
            chiller_cmd=True, variac_cmd=True, variac_vsl_cmd=True
        )
        iso_exp.heat_under_evacuation(
            pumpType="RoughPump",
            targetTemp=400,
            holdTime=0,
            rampRate=20,
            expParams=False,
        )
        iso_exp.heat_under_evacuation(
            pumpType="TurboPump",
            targetTemp=400,
            holdTime=0.25,
            rampRate=0,
            expParams=False,
        )
        iso_exp.cool_cell(targetTemp=25, holdTime=0, variac_cmd=False)
        iso_exp.chiller_variac_state(
            chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False
        )
        logger.info("Running mass spec calibration...")
        iso_exp.massSpec_calibration(targets=[2e-10, 4e-10, 6e-10, 1.5e-9, 5e-9])
        logger.info("Isotopic exchange calibration completed!")

    try:
        if args.adsorption:
            run_adsorption_experiment()
        elif args.isotopic:
            run_isotopic_exchange_calibration()
        else:
            logger.info("Use --adsorption or --isotopic to run experiments.")
            logger.info("Use --mock to run without hardware.")
    finally:
        if not args.mock:
            devices.disconnect()


if __name__ == "__main__":
    main()
