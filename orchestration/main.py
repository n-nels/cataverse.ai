"""
Main entry point for CataVerse instrument control.

This file demonstrates how to run the instrument control system
across its architecture layers (config, hardware, control, datalog, experiments).

Usage:
    python main.py --adsorption          # Run adsorption with real hardware
    python main.py --isotopic            # Run isotopic exchange with real hardware
    python main.py --mock --adsorption   # Run adsorption with mock hardware
    python main.py --mock --isotopic     # Run isotopic exchange with mock hardware
"""

import argparse

from src.core.config_loader import load_config
from src.datalog import get_logger, configure_logging
from src.core.physics import SystemVolumes
from src.experiments.session import ExperimentSession
from src.hardware.connections import DeviceManager
from src.hardware.mocks import create_mock_devices
from src.control.spectrometer_control import SpectrometerController
from src.control.mass_spec_control import MassSpecController
from src.control.temperature_control import TemperatureController
from src.control.valves import ValveController
from src.control.gas_delivery import GasDelivery
from src.experiments.adsorption import AdsorptionExperiment


logger = get_logger(__name__)


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
    experiment = parser.add_mutually_exclusive_group(required=True)
    experiment.add_argument(
        "--adsorption", action="store_true", help="Run adsorption experiment"
    )
    experiment.add_argument(
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
    volumes = SystemVolumes(
        vessel=config.system.vessel_volume_l,
        valve=config.system.valve_volume_l,
        cell=config.system.cell_volume_l,
        manifold_m1m2=config.system.manifold_m1m2_volume_l,
        manifold_m1m2m3=config.system.manifold_m1m2m3_volume_l,
        tube_50ml=config.system.tube_50ml_volume_l,
        flask=config.system.flask_volume_l,
    )

    gas_controller = GasDelivery(
        valves=valves,
        pressure=devices.pressure,
        total_volume_l=volumes.total,
        temperature_k=config.system.manifold_temperature_k,
        gas_constant=config.system.gas_constant,
    )
    temp_controller = TemperatureController(
        temperature=devices.temperature,
        power=devices.power,
        paths=config.paths,
        kasa=config.hardware.kasa,
    )
    ftir_controller = SpectrometerController(devices.spectrometer)

    ms_controller = MassSpecController(
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

    def run_adsorption_experiment():
        ads_exp = AdsorptionExperiment(
            session=session,
            gas_controller=gas_controller,
            temp=temp_controller,
            ftir=ftir_controller,
            ms=ms_controller,
            pressure=devices.pressure,
            temperature=devices.temperature,
        )
        logger.info("Starting adsorption experiment...")
        session.new_experiment()
        success = False
        try:
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
            # ads_exp.supply_gas_to_mfld(gas="O2", target_pressure=5.0)
            ads_exp.introduce_pretreatment_gas_to_cell(target_temp=25, hold_time=0)
            ads_exp.heat_under_evacuation(
                pump_type="TurboPump", target_temp=25, hold_time=0.0, ramp_rate=0
            )
            logger.info("Adsorbing 13CO...")
            ads_exp.cool_cell(target_temp=25, hold_time=0, variac_cmd=False)
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
            success = True
            logger.info("Adsorption experiment completed!")
        finally:
            ads_exp.finalize(success=success)

    def run_isotopic_exchange_calibration():
        from src.experiments.isotopic_exchange import IsotopicExchangeCalibration

        iso_exp = IsotopicExchangeCalibration(
            session=session,
            gas_controller=gas_controller,
            temp=temp_controller,
            ftir=ftir_controller,
            mass_spec=ms_controller,
            pressure=devices.pressure,
        )
        logger.info("Starting isotopic exchange calibration...")
        session.new_experiment()
        logger.info("Cleaning surface...")
        iso_exp.chiller_variac_state(
            chiller_cmd=True, variac_cmd=True, variac_vsl_cmd=True
        )
        iso_exp.heat_under_evacuation(
            pump_type="RoughPump", target_temp=500, hold_time=0.0, ramp_rate=20
        )
        iso_exp.heat_under_evacuation(
            pump_type="TurboPump", target_temp=500, hold_time=2.0, ramp_rate=0
        )
        logger.info("Pretreating surface...")
        iso_exp.supply_gas_to_mfld(gas="O2", target_pressure=5.0)
        iso_exp.introduce_pretreatment_gas_to_cell(target_temp=500, hold_time=2)
        iso_exp.heat_under_evacuation(
            pump_type="TurboPump", target_temp=500, hold_time=0.5, ramp_rate=0
        )
        logger.info("Adsorbing 13CO...")
        iso_exp.cool_cell(target_temp=45, hold_time=0, variac_cmd=False)
        iso_exp.chiller_variac_state(
            chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False
        )
        iso_exp.supply_gas_to_mfld(gas="13CO", target_pressure=1.0)
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
        iso_exp.cool_cell(target_temp=25, hold_time=0, variac_cmd=False)
        iso_exp.chiller_variac_state(
            chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False
        )
        logger.info("Running isotopic exchange...")
        iso_exp.isoX_calib_main(
            xchg_time=[2, 4, 6, 8, 9, 10, 11, 12, 14, 16], sleep_time=2
        )
        logger.info("Final cleaning...")
        iso_exp.chiller_variac_state(
            chiller_cmd=True, variac_cmd=True, variac_vsl_cmd=True
        )
        iso_exp.heat_under_evacuation(
            pump_type="RoughPump",
            target_temp=400,
            hold_time=0,
            ramp_rate=20,
            exp_params=False,
        )
        iso_exp.heat_under_evacuation(
            pump_type="TurboPump",
            target_temp=400,
            hold_time=0.25,
            ramp_rate=0,
            exp_params=False,
        )
        iso_exp.cool_cell(target_temp=25, hold_time=0, variac_cmd=False)
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
    finally:
        if not args.mock:
            devices.disconnect()


if __name__ == "__main__":
    main()
