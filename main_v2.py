"""
New main entry point using the v2 architecture.

This file demonstrates how to use the refactored instrument control system
with the new architecture layers (config, hardware, control, datalog, experiments).

Usage:
    python main_v2.py              # Run with real hardware
    python main_v2.py --mock       # Run with mock hardware (for testing/debugging)
    python main_v2.py --mock --adsorption  # Run adsorption experiment with mocks
    python main_v2.py --mock --isotopic    # Run isotopic exchange with mocks
"""

import argparse
import time
from datetime import datetime, timedelta
from typing import List
from unittest.mock import MagicMock

from src.config_loader import load_config
from src.hardware.connections import DeviceManager
from src.control.gas_delivery import GasDelivery
from src.control.spectrometer_control import SpectrometerController
from src.control.temperature_control import TemperatureController
from src.control.valves import ValveController
from src.physics import SystemVolumes
from src.experiments.session import ExperimentSession
from src.experiments.adsorption_v2 import AdsorptionExperiment
from src.experiments.isotopic_exchange_v2 import IsotopicExchangeCalibration


def create_mock_devices(config):
    """Create mock device manager for testing without hardware."""
    devices = MagicMock(spec=DeviceManager)
    devices.config = config.hardware

    # Mock hardware adapters with convenient return values
    devices.pressure = MagicMock()
    devices.pressure.read.return_value = (
        MagicMock(),
        0.01,
        0.01,
    )  # (timestamp, p_mfld, p_cell)

    devices.temperature = MagicMock()
    devices.temperature.read_temperature.return_value = 25.0  # °C

    devices.mass_spec = MagicMock()
    devices.mass_spec.write_register.return_value = True
    devices.mass_spec.read_registers.return_value = [1, 2]  # Mock register values

    devices.analog_io = MagicMock()
    devices.analog_io.write.return_value = None  # Valve writes succeed

    devices.spectrometer = MagicMock()
    devices.spectrometer.send.return_value = "OK"
    devices.spectrometer.receive.return_value = "fileid123"

    devices.power = MagicMock()
    devices.power.set_state.return_value = True

    # Mock connect/disconnect
    devices.connect.return_value = None
    devices.disconnect.return_value = None

    return devices


def create_real_devices(config):
    """Create real device manager for hardware."""
    devices = DeviceManager(config.hardware)
    devices.connect()
    return devices


def main():
    """Main entry point for the v2 architecture."""
    parser = argparse.ArgumentParser(description="CataVerse v2 Architecture")
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

    # Load configuration
    config = load_config()

    # Initialize device manager (real or mock)
    if args.mock:
        print("Running in MOCK mode - no real hardware required")
        devices = create_mock_devices(config)
    else:
        print("Running with REAL hardware")
        devices = create_real_devices(config)

    # Initialize control layers
    valves = ValveController(devices.analog_io, devices.pressure)
    gas_controller = GasDelivery(valves=valves, pressure=devices.pressure)
    temp_controller = TemperatureController(temperature=devices.temperature, power=devices.power)
    spec_controller = SpectrometerController(devices.spectrometer)

    # Initialize experiment session
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
        print("Starting adsorption experiment...")
        session.new_experiment()

        # Clean surface
        print("Cleaning surface...")
        ads_exp.chiller_variac_state(
            chiller_cmd=True, variac_cmd=True, variac_vsl_cmd=True
        )
        ads_exp.heat_under_evacuation(
            pump_type="RoughPump", target_temp=25, hold_time=0.0, ramp_rate=20
        )
        ads_exp.heat_under_evacuation(
            pump_type="TurboPump", target_temp=25, hold_time=0.0, ramp_rate=0
        )

        # Oxidize surface
        print("Oxidizing surface...")
        # ads_exp.supply_gas_to_mfld(gas="O2", target_pressure=5.0)
        ads_exp.introduce_pretreatment_gas_to_cell(target_temp=25, hold_time=0)
        ads_exp.heat_under_evacuation(
            pump_type="TurboPump", target_temp=25, hold_time=0.0, ramp_rate=0
        )

        # Cool and adsorb
        print("Adsorbing 13CO...")
        ads_exp.cool_cell(target_temp=45, hold_time=0, variac_cmd=False)
        ads_exp.chiller_variac_state(
            chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False
        )
        # ads_exp.supply_gas_to_mfld(gas="13CO", target_pressure=1.0)
        ads_exp.acquire_spectra(
            repeat=[0],
            delay=[0],
            all_fileids=True,
            do_bckg=True,
            do_fit=True,
        )
        print("Adsorption experiment completed!")

    # Example: Run isotopic exchange calibration
    def run_isotopic_exchange_calibration():
        """Run isotopic exchange calibration experiment."""
        print("Starting isotopic exchange calibration...")
        session.new_experiment()

        # Clean surface
        print("Cleaning surface...")
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
        print("Pretreating surface...")
        iso_exp.supply_gas_to_mfld(gas="O2", targetPressure=5.0)
        iso_exp.introduce_pretreatment_gas_to_cell(targetTemp=500, holdTime=2)
        iso_exp.heat_under_evacuation(
            pumpType="TurboPump", targetTemp=500, holdTime=0.5, rampRate=0
        )

        # Adsorb 13CO
        print("Adsorbing 13CO...")
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
        print("Cooling for isotopic exchange...")
        iso_exp.chiller_variac_state(
            chiller_cmd=True, variac_cmd=False, variac_vsl_cmd=False
        )
        iso_exp.cool_cell(targetTemp=25, holdTime=0, variac_cmd=False)
        iso_exp.chiller_variac_state(
            chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False
        )

        # Run isotopic exchange
        print("Running isotopic exchange...")
        iso_exp.isoX_calib_main(
            xchgTime=[2, 4, 6, 8, 9, 10, 11, 12, 14, 16], sleepTime=2
        )

        # Clean surface
        print("Final cleaning...")
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
        print("Running mass spec calibration...")
        iso_exp.massSpec_calibration(targets=[2e-10, 4e-10, 6e-10, 1.5e-9, 5e-9])
        print("Isotopic exchange calibration completed!")

    # Run experiments based on arguments
    try:
        if args.adsorption:
            run_adsorption_experiment()
        elif args.isotopic:
            run_isotopic_exchange_calibration()
        else:
            print("v2 architecture initialized successfully.")
            print("Use --adsorption or --isotopic to run experiments.")
            print("Use --mock to run without hardware.")
    finally:
        # Disconnect from hardware
        if not args.mock:
            devices.disconnect()


if __name__ == "__main__":
    main()
