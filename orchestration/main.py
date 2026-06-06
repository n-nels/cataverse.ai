"""
Main entry point for CataVerse instrument control.

Architecture:
    src/experiments/setup.py  — Instruments dataclass + initialize()
    api/                      — high-level scientist-facing experiment classes
    main.py                   — CLI + experiment recipes composed from api/ verbs

Usage:
    python main.py adsorption            # Run adsorption with real hardware
    python main.py isotopic              # Run isotopic exchange with real hardware
    python main.py adsorption-ref        # Run adsorption reference with real hardware
    python main.py --mock adsorption     # Run adsorption with mock hardware
"""

import argparse

from src.datalog import get_logger, configure_logging
from src.experiments.setup import initialize, Instruments
from api.adsorption import Adsorption


logger = get_logger(__name__)


def run_isotopic_exchange_calibration(inst: Instruments):
    # TODO: define api/isotopic_exchange.py and rewrite this recipe
    from src.experiments.isotopic_exchange import IsotopicExchangeCalibration

    iso = IsotopicExchangeCalibration(
        session=inst.session,
        gas_controller=inst.gas,
        temp=inst.temp,
        ftir=inst.ftir,
        mass_spec=inst.ms,
        pressure=inst.devices.pressure,
    )

    inst.session.new_experiment(is_reference=False)
    success = False
    try:
        iso.chiller_variac_state(chiller_cmd=True, variac_cmd=True, variac_vsl_cmd=True)
        iso.heat_under_evacuation(pump_type="RoughPump", target_temp=500, hold_time=0.0, ramp_rate=20)
        iso.heat_under_evacuation(pump_type="TurboPump", target_temp=500, hold_time=2.0, ramp_rate=0)
        iso.supply_gas_to_mfld(gas="O2", target_pressure=5.0)
        iso.introduce_pretreatment_gas_to_cell(target_temp=500, hold_time=2)
        iso.heat_under_evacuation(pump_type="TurboPump", target_temp=500, hold_time=0.5, ramp_rate=0)
        iso.cool_cell(target_temp=45, hold_time=0, variac_cmd=False)
        iso.chiller_variac_state(chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False)
        iso.supply_gas_to_mfld(gas="13CO", target_pressure=1.0)
        iso.acquire_spectra(
            repeat=[10, 5, 15, 60], delay=[60, 300, 600, 1800],
            all_fileids=True, do_bckg=True, do_fit=True,
        )
        iso.copy_readme()
        iso.chiller_variac_state(chiller_cmd=True, variac_cmd=False, variac_vsl_cmd=False)
        iso.cool_cell(target_temp=25, hold_time=0, variac_cmd=False)
        iso.chiller_variac_state(chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False)
        iso.isoX_calib_main(xchg_time=[2, 4, 6, 8, 9, 10, 11, 12, 14, 16], sleep_time=2)
        iso.chiller_variac_state(chiller_cmd=True, variac_cmd=True, variac_vsl_cmd=True)
        iso.heat_under_evacuation(pump_type="RoughPump", target_temp=400, hold_time=0, ramp_rate=20, exp_params=False)
        iso.heat_under_evacuation(pump_type="TurboPump", target_temp=400, hold_time=0.25, ramp_rate=0, exp_params=False)
        iso.cool_cell(target_temp=25, hold_time=0, variac_cmd=False)
        iso.chiller_variac_state(chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False)
        iso.massSpec_calibration(targets=[2e-10, 4e-10, 6e-10, 1.5e-9, 5e-9])
        success = True
    finally:
        iso.finalize(success=success)

def run_adsorption_experiment(inst: Instruments):
    """[pressure_limits_torr]-{single:8.3, dual:[1.6, 6.7]}"""
    
    ads = Adsorption(inst)
    inst.session.new_experiment(is_new=False)
    success = False
    
    try:
        ads.clean_surface(evac_temp=450,
                          evac_time=1,
                          enable_ms=False,
                          chiller=False)
        
        ads.oxidize_surface(pressure=5.5,
                            temp=550,
                            time=2.5,
                            evac_temp=450,
                            evac_time=0.5)
        
        # ads.pretreat_adsorbate(adsorbate="H2",
        #                        pressure=7.0,
        #                        temp=350,
        #                        time=1,
        #                        evac_temp=250,
        #                        evac_time=0.5)
        
        ads.monitor_adsorption(adsorbate="13CO",
                               pressure=0.84,
                               temp=45,
                               repeat=[10, 5, 15, 150],
                               delay=[60, 300, 600, 1800])
        success = True
    
    finally:
        ads.finalize(success=success)

def run_adsorption_reference(inst: Instruments):
    """[pressure_limits_torr]-{single:8.3, dual:[1.6, 6.7]}"""
    
    ads = Adsorption(inst)
    inst.session.new_experiment(is_new=False, is_reference=True)
    success = False
    
    try:
        ads.clean_surface(evac_temp=450,
                          evac_time=2.0,
                          enable_ms=False,
                          chiller=False)
        
        ads.oxidize_surface(pressure=5.0,
                            temp=450,
                            time=2.0,
                            evac_temp=450,
                            evac_time=0.5)
                
        ads.monitor_adsorption(adsorbate="13CO",
                               pressure=0.84,
                               temp=45,
                               repeat=[10, 5, 15, 150],
                               delay=[60, 300, 600, 1800])
        success = True
    
    finally:
        ads.finalize(success=success)

def main():
    configure_logging()

    parser = argparse.ArgumentParser(description="CataVerse instrument control")
    parser.add_argument("--mock", action="store_true", help="Use mock hardware for testing")
    parser.add_argument("experiment", choices=EXPERIMENTS.keys(),
                        help="Experiment to run")
    args = parser.parse_args()

    inst = initialize(mock=args.mock)
    try:
        EXPERIMENTS[args.experiment](inst)
    finally:
        if not inst.mock:
            inst.devices.disconnect()


if __name__ == "__main__":
    EXPERIMENTS = {
        "adsorption": run_adsorption_experiment,
        "adsorption-ref": run_adsorption_reference,
        "isotopic": run_isotopic_exchange_calibration,
    }
    main()
