"""
New main entry point using the v2 architecture.

This file demonstrates how to use the refactored instrument control system
with the new architecture layers (config, hardware, control, datalog, experiments).

Usage:
    python main_v2.py
"""

import time
from datetime import datetime, timedelta
from typing import List

from src.config_loader import load_config
from src.hardware.connections import DeviceManager
from src.control.gas_delivery import GasDelivery
from src.control.spectrometer_control import SpectrometerController
from src.control.temperature_control import TemperatureController
from src.control.valves import ValveController
from src.experiments.session import ExperimentSession
from src.experiments.adsorption_v2 import AdsorptionExperiment
from src.experiments.isotopic_exchange_v2 import IsotopicExchangeCalibration


def main():
    """Main entry point for the v2 architecture."""
    # Load configuration
    config = load_config()

    # Initialize device manager and connect to hardware
    devices = DeviceManager(config.hardware)
    devices.connect()

    # Initialize control layers
    valves = ValveController(devices.analog_io, config.hardware.actuator)
    gas_controller = GasDelivery(
        valves=valves,
        pressure=devices.pressure,
        temperature=devices.temperature,
        config=config.hardware.actuator,
    )
    temp_controller = TemperatureController(
        temperature=devices.temperature,
        power=devices.power,
        config=config.hardware.kasa,
    )
    spec_controller = SpectrometerController(devices.spectrometer)

    # Initialize experiment session
    session = ExperimentSession(
        sample=config.sample,
        volumes=config.system,
        paths=config.paths,
    )

    # Create experiment instances
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

    # Example: Run a simple adsorption experiment
    def run_adsorption_experiment():
        """Run a simple adsorption experiment."""
        session.new_experiment()

        # Clean surface
        ads_exp.chiller_variac_state(
            chiller_cmd=True, variac_cmd=True, variac_vsl_cmd=True
        )
        ads_exp.heat_under_evacuation(
            pumpType="RoughPump", targetTemp=400, holdTime=0.0, rampRate=20
        )
        ads_exp.heat_under_evacuation(
            pumpType="TurboPump", targetTemp=400, holdTime=2.0, rampRate=0
        )

        # Oxidize surface
        ads_exp.supply_gas_to_mfld(gas="O2", targetPressure=5.0)
        ads_exp.introduce_pretreatment_gas_to_cell(targetTemp=500, holdTime=2)
        ads_exp.heat_under_evacuation(
            pumpType="TurboPump", targetTemp=500, holdTime=0.5, rampRate=0
        )

        # Cool and adsorb
        ads_exp.cool_cell(targetTemp=45, holdTime=0, variac_cmd=False)
        ads_exp.chiller_variac_state(
            chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False
        )
        ads_exp.supply_gas_to_mfld(gas="13CO", targetPressure=1.0)
        ads_exp.acquire_spectra(
            repeat=[10, 5, 15, 30],
            delay=[60, 300, 600, 1800],
            all_fileids=True,
            do_bckg=True,
            do_fit=True,
        )

    # Example: Run isotopic exchange calibration
    def run_isotopic_exchange_calibration():
        """Run isotopic exchange calibration experiment."""
        session.new_experiment()

        # Clean surface
        iso_exp.chiller_variac_state(
            chiller_cmd=True, variac_cmd=True, variac_vsl_cmd=True
        )
        iso_exp.heat_under_evacuation(
            pumpType="RoughPump", targetTemp=500, holdTime=0.0, rampRate=20
        )
        iso_exp.heat_under_evacuation(
            pumpType="TurboPump", targetTemp=500, holdTime=2.0, rampRate=0
        )

        # Pretreat surface
        iso_exp.supply_gas_to_mfld(gas="O2", targetPressure=5.0)
        iso_exp.introduce_pretreatment_gas_to_cell(targetTemp=500, holdTime=2)
        iso_exp.heat_under_evacuation(
            pumpType="TurboPump", targetTemp=500, holdTime=0.5, rampRate=0
        )

        # Adsorb 13CO
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

        # Cool for isotopic exchange
        iso_exp.chiller_variac_state(
            chiller_cmd=True, variac_cmd=False, variac_vsl_cmd=False
        )
        iso_exp.cool_cell(targetTemp=25, holdTime=0, variac_cmd=False)
        iso_exp.chiller_variac_state(
            chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False
        )

        # Run isotopic exchange
        iso_exp.isoX_calib_main(
            xchgTime=[2, 4, 6, 8, 9, 10, 11, 12, 14, 16], sleepTime=2
        )

        # Clean surface
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

        # Mass spec calibration
        iso_exp.massSpec_calibration(targets=[2e-10, 4e-10, 6e-10, 1.5e-9, 5e-9])

    # Run experiments
    try:
        # Uncomment to run experiments:
        # run_adsorption_experiment()
        # run_isotopic_exchange_calibration()
        print("v2 architecture initialized successfully.")
        print("Uncomment experiment functions in main_v2.py to run experiments.")
    finally:
        # Disconnect from hardware
        devices.disconnect()


if __name__ == "__main__":
    main()
