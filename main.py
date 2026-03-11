"""
New main entry point using package structure.

This file demonstrates how to use the refactored instrument control system
with the new package structure. Replace main.py with this file once
the migration is complete.

Usage:
    python main_new.py
"""

import time
from datetime import datetime, timedelta
from typing import List

from src import *

# Initialize devices using package imports
actuators = ActuatorManager(device_map)
serial = SerialDevices()
actuator_control = ActuatorControl(actuators, serial)
opus = NetworkMessaging()
instrument_operations = InstrumentOperations(serial, actuator_control, opus)

# Setup experiment parameters
exp_params = experiment_parameters(
    notebook=notebook, 
    mass=mass, 
    metal=metal, 
    metal_load=metal_load, 
    metal_density=metal_density,
    support=support,
    support_sa=support_sa,
    v_tot=v_tot
)

# Initialize experiment
adsExp = adsorption_experiment(exp_params, serial, actuator_control, instrument_operations)

# Connect to devices
opus.connect(ip="130.20.216.127", port=5555)  # ir spectrometer
serial.connect_mks()  # pressure gauge
serial.connect_watlow_ir()  # temperature controller for IR cell
# serial.connect_extrel()  # mass spectrometer


def run_isotopic_exchange_calibration():

    isoX = isotopic_exchange_calibration(exp_params, serial, actuator_control, instrument_operations)

    # clean surface
    isoX.chiller_variac_state(chiller_cmd= True, variac_cmd=True, variac_vsl_cmd=True)
    isoX.heat_under_evacuation(pumpType='RoughPump', targetTemp=500, holdTime=0.0, rampRate=20)
    isoX.heat_under_evacuation(pumpType='TurboPump', targetTemp=500, holdTime=2.0, rampRate=0)

    # pretreat surface #1
    isoX.supply_gas_to_mfld(gas='O2', targetPressure=5.0)
    isoX.introduce_pretreatment_gas_to_cell(targetTemp=500, holdTime=2)
    isoX.heat_under_evacuation(pumpType='TurboPump', targetTemp=500, holdTime=0.5, rampRate=0)

    ### pretreat surface #2 ###
    isoX.heat_under_evacuation(pumpType='TurboPump', targetTemp=665, holdTime=0.25, rampRate=20)
    isoX.supply_gas_to_mfld(gas='H2O', targetPressure=5.0)
    isoX.introduce_pretreatment_gas_to_cell(targetTemp=665, holdTime=2)
    isoX.heat_under_evacuation(pumpType='TurboPump', targetTemp=665, holdTime=0.5, rampRate=0)

    # adsorb 13CO
    isoX.cool_cell(targetTemp=45, holdTime=0, variac_cmd=False)
    isoX.chiller_variac_state(chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False)
    isoX.supply_gas_to_mfld(gas='13CO', targetPressure=1.0)
    isoX.acquire_spectra(repeat=[10,5,15,30], # 120 is about 60 h ### change back to 60 ###
                        delay=[60,300,600,1800],
                        all_fileids=True,
                        do_bckg=True,
                        do_fit=True)
    isoX.copy_readme()

    # create new instance
    exp_params = experiment_parameters(notebook=notebook, 
                                mass=mass, 
                                metal=metal, 
                                metal_load=metal_load, 
                                metal_density=metal_density,
                                support=support,
                                support_sa=support_sa,
                                v_tot=v_tot
                                )
    exp_params.experiment_id()
    exp_params.material_parameters()
    isoX = isotopic_exchange_calibration(exp_params)

    # clean surface
    isoX.chiller_variac_state(chiller_cmd= True, variac_cmd=True, variac_vsl_cmd=True)
    isoX.heat_under_evacuation(pumpType='RoughPump', targetTemp=500, holdTime=0, rampRate=20)
    isoX.heat_under_evacuation(pumpType='TurboPump', targetTemp=500, holdTime=0.5, rampRate=0)

    ### pretreat surface #1 ###
    isoX.supply_gas_to_mfld(gas='O2', targetPressure=5.0)
    isoX.introduce_pretreatment_gas_to_cell(targetTemp=500, holdTime=2)
    isoX.heat_under_evacuation(pumpType='TurboPump', targetTemp=500, holdTime=0.5, rampRate=0)

    # adsorb 13CO
    isoX.cool_cell(targetTemp=45, holdTime=0, variac_cmd=False)
    isoX.chiller_variac_state(chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False)
    isoX.supply_gas_to_mfld(gas='13CO', targetPressure=1.0)
    isoX.acquire_spectra(repeat=[10,5,15,60], # 120 is about 60 h
                        delay=[60,300,600,1800],
                        all_fileids=True,
                        do_bckg=True,
                        do_fit=True)
    isoX.copy_readme()

    # cool cell for isotopic exchange
    isoX.chiller_variac_state(chiller_cmd=True, variac_cmd=False, variac_vsl_cmd=False)
    isoX.cool_cell(targetTemp=25, holdTime=0, variac_cmd=False)
    isoX.chiller_variac_state(chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False)

    # do isotopic exchange
    isoX.isoX_calib_main(xchgTime=[2,4,6,8,9,10,11,12,14,16], sleepTime=2)
    # isoX.isoX_calib_main(xchgTime=[10,12,13,14,15,16,18,20], sleepTime=2)

    # clean surface
    isoX.chiller_variac_state(chiller_cmd= True, variac_cmd=True, variac_vsl_cmd=True)
    isoX.heat_under_evacuation(pumpType='RoughPump', targetTemp=400, holdTime=0, rampRate=20, expParams=False)
    isoX.heat_under_evacuation(pumpType='TurboPump', targetTemp=400, holdTime=0.25, rampRate=0, expParams=False)
    isoX.cool_cell(targetTemp=25, holdTime=0, variac_cmd=False)
    isoX.chiller_variac_state(chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False)

    # CO calibration for mass spectrometer
    isoX.massSpec_calibration(targets=[2e-10, 4e-10, 6e-10, 1.5e-9, 5e-9])

def clean_surface(evac_temp: int, evac_time: float, enable_ms: bool = False, chiller: bool = True) -> None:
    """A procedure for removing surface adsorbates under evacuation
    Args:
        evac_temp (int): Temperature of evacuation in C
        evac_time (float): Hold time in hours
        enable_ms (bool): Whether to enable mass spectrometer streaming during the procedure
        chiller (bool): Whether to use the chiller and variac for cooling
    """
    adsExp.chiller_variac_state(chiller_cmd=chiller, variac_cmd=True, variac_vsl_cmd=True)
    adsExp.heat_under_evacuation(pumpType='RoughPump', targetTemp=evac_temp, holdTime=0.0, rampRate=20, enable_ms_stream=enable_ms)
    adsExp.heat_under_evacuation(pumpType='TurboPump', targetTemp=evac_temp, holdTime=evac_time, rampRate=0)

def oxidize_surface(pressure: float, temp: int, time: float, evac_temp: int, evac_time: float) -> None:
    """A procedure for oxidizing the surface in O2. The pressure corresponds to the total volume. After
    oxidation, the cell is evacuated to remove O2.
    Args:
        pressure (float): Pressure of O2 in Torr
        temp (int): Temperature of evacuation in C
        time (float): Hold time in hours
        evac_temp (int): Temperature of evacuation in C. If None, the temperature is set to temp.
        evac_time (float): Hold time in hours for evacuation after oxidation
    """

    if serial.readTemp_ir() > temp + 3:
        adsExp.cool_cell(targetTemp=temp, holdTime=0, rampRate=0, variac_cmd=True)
    elif serial.readTemp_ir() < temp - 3:
        adsExp.heat_under_evacuation(pumpType='TurboPump', targetTemp=temp, holdTime=0.0, rampRate=20, expParams=False)
    
    adsExp.supply_gas_to_mfld(gas='O2', targetPressure=pressure)
    adsExp.introduce_pretreatment_gas_to_cell(targetTemp=temp, holdTime=time)
    
    if evac_temp is None:
        evac_temp = temp

    if serial.readTemp_ir() > evac_temp + 3:
        adsExp.cool_cell(targetTemp=evac_temp, holdTime=0, rampRate=0, variac_cmd=True)
        adsExp.heat_under_evacuation(pumpType='TurboPump', targetTemp=evac_temp, holdTime=evac_time, rampRate=0, variac_cmd=False)
    elif serial.readTemp_ir() < evac_temp - 3:
        adsExp.heat_under_evacuation(pumpType='TurboPump', targetTemp=evac_temp, holdTime=0.0, rampRate=20, expParams=False)
        adsExp.heat_under_evacuation(pumpType='TurboPump', targetTemp=evac_temp, holdTime=evac_time, rampRate=0)
    else:
        adsExp.heat_under_evacuation(pumpType='TurboPump', targetTemp=evac_temp, holdTime=evac_time, rampRate=0)

def pretreat_adsorbate(adsorbate: str, pressure: float, temp: int, time: float, evac_temp: int, evac_time: float) -> None:
    """A procedure for introducing an adsorbate during pretreatment. The pressure corresponds to the total volume.
    Args:
        adsorbate (str): The gas introduced
        pressure (float): Pressure of gas in Torr
        temp (int): Temperature of adsorption in C
        time (float): Hold time in hours
        evac_time (float): Hold time in hours for evacuation after pretreatment
    """
    if serial.readTemp_ir() > temp + 3:
        adsExp.cool_cell(targetTemp=temp, holdTime=0, rampRate=0, variac_cmd=True)
    elif serial.readTemp_ir() < temp - 3:
        adsExp.heat_under_evacuation(pumpType='TurboPump', targetTemp=temp, holdTime=0.0, rampRate=20, expParams=False)

    adsExp.supply_gas_to_mfld(gas=adsorbate, targetPressure=pressure)
    adsExp.introduce_pretreatment_gas_to_cell(targetTemp=temp, holdTime=time)

    if evac_temp is None:
        evac_temp = temp

    if serial.readTemp_ir() > evac_temp + 3:
        adsExp.cool_cell(targetTemp=evac_temp, holdTime=0, rampRate=0, variac_cmd=True)
        adsExp.heat_under_evacuation(pumpType='TurboPump', targetTemp=evac_temp, holdTime=evac_time, rampRate=0, variac_cmd=False)
    elif serial.readTemp_ir() < evac_temp - 3:
        adsExp.heat_under_evacuation(pumpType='TurboPump', targetTemp=evac_temp, holdTime=0.0, rampRate=20, expParams=False)
        adsExp.heat_under_evacuation(pumpType='TurboPump', targetTemp=evac_temp, holdTime=evac_time, rampRate=0)
    else:
        adsExp.heat_under_evacuation(pumpType='TurboPump', targetTemp=evac_temp, holdTime=evac_time, rampRate=0)

def pretreat_coadsorbates(adsorbates: List[str], pressures: List[float], temp: int, time: float, evac_temp: int,evac_time: float) -> None:
    """A procedure for introducing two adsorbates during pretreatment. The pressure corresponds to the total volume.
    The pressure of gas[0] cannot exceed 1.6 Torr. The pressure of gas[1] cannot exceed 9 Torr.
    Args:
        adsorbates (List[str]): The gases introduced
        pressures (List[float]): The pressures of the gases in Torr
        temp (int): Temperature of adsorption in C
        time (float): Hold time in hours
    """

    if serial.readTemp_ir() > temp + 3:
        adsExp.cool_cell(targetTemp=temp, holdTime=0, rampRate=0, variac_cmd=True)
    elif serial.readTemp_ir() < temp - 3:
        adsExp.heat_under_evacuation(pumpType='TurboPump', targetTemp=temp, holdTime=0.0, rampRate=20, expParams=False)

    adsExp.supply_gases_to_mfld(gas=adsorbates, targetPressure=pressures)
    adsExp.introduce_pretreatment_gas_to_cell(targetTemp=temp, holdTime=time)

    if evac_temp is None:
        evac_temp = temp

    if serial.readTemp_ir() > evac_temp + 3:
        adsExp.cool_cell(targetTemp=evac_temp, holdTime=0, rampRate=0, variac_cmd=True)
        adsExp.heat_under_evacuation(pumpType='TurboPump', targetTemp=evac_temp, holdTime=evac_time, rampRate=0, variac_cmd=False)
    elif serial.readTemp_ir() < evac_temp - 3:
        adsExp.heat_under_evacuation(pumpType='TurboPump', targetTemp=evac_temp, holdTime=0.0, rampRate=20, expParams=False)
        adsExp.heat_under_evacuation(pumpType='TurboPump', targetTemp=evac_temp, holdTime=evac_time, rampRate=0)
    else:
        adsExp.heat_under_evacuation(pumpType='TurboPump', targetTemp=evac_temp, holdTime=evac_time, rampRate=0)

def monitor_adsorption(adsorbate: str,
                       pressure: float,
                       temp: int,
                       repeat: List[int] = [10,5,15,60],
                       delay: List[int] = [60,300,600,1800],
                       all_fileids: bool = True,
                       do_bckg: bool = True,
                       do_fit: bool = True) -> None:
    """A procedure for monitoring the adsorption of a gas in the IR cell. The pressure corresponds to the total volume.
    Args:
        adsorbate (str): The gas introduced
        temp (int): Temperature of adsorption in C
        pressure (float): Pressure of gas in Torr
        repeat (List[int]): Number of times to repeat acquisition at each delay time. The length of this list should match the length of delay.
        delay (List[int]): Delay times in seconds between acquisitions. The length of this list should match the length of repeat.
        all_fileids (bool): Reset file ID counter for each acquisition if True.
        do_bckg (bool): Whether to acquire a background spectrum before adsorption
        do_fit (bool): Whether to perform peak fitting after acquisition
    """
    adsExp.cool_cell(targetTemp=temp, holdTime=0, variac_cmd=False)
    adsExp.chiller_variac_state(chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False)
    adsExp.supply_gas_to_mfld(gas=adsorbate, targetPressure=pressure)
    adsExp.acquire_spectra(repeat=repeat, # 115 is about 60 h
                        delay=delay,
                        all_fileids=all_fileids,
                        do_bckg=do_bckg,
                        do_fit=do_fit)
    
def monitor_coadsorption(adsorbate_1: str, adsorbate_2: str, temp: int, pressure_1: float, pressure_2: float) -> None:
        """A procedure for monitoring the coadsorption of two gases in the IR cell. The pressure corresponds to volume of manifold less IR cell.
        Args:
            adsorbate_1 (str): The first gas introduced
            adsorbate_2 (str): The second gas introduced
            temp (int): Temperature of adsorption in C
            pressure_1 (float): Pressure of first gas in Torr
            pressure_2 (float): Pressure of second gas in Torr
        """
        adsExp.cool_cell(targetTemp=temp, holdTime=0, variac_cmd=False)
        adsExp.chiller_variac_state(chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False)
        adsExp.supply_gas_to_mfld(gas=adsorbate_1, targetPressure=pressure_1)
        adsExp.supply_another_gas_to_mfld(gas=adsorbate_2, targetPressure=pressure_2)
        # adsExp.supply_gas_to_mfld(gas='13CO', targetPressure=(v_m1m2m3+v_50tube)/v_m3)
        # adsExp.supply_another_gas_to_mfld(gas='CO2', targetPressure=(5*(v_m1m2m3+v_50tube))/(v_m1m2+v_50tube))
        adsExp.acquire_spectra(repeat=[10,5,15,60], # 115 is about 60 h
                            delay=[60,300,600,1800],
                            all_fileids=True,
                            do_bckg=True,
                            do_fit=True)
    
def measure_leak_rate(temp: int, duration: float) -> None:
    """A procedure for measuring the leak rate of the system.
    Args:
        temp (int): Temperature of the IR cell in C
        duration (float): Duration of the measurement in hours
    Returns:
        None
    """

    now = datetime.now().strftime("%Y%m%d_%H%M%S")

    exp_params.experiment_id(file_name=f"{now}_leakRate", folder_name="leak_rates")
    exp_params.material_parameters()

    # clean_surface(evac_temp=450, evac_time=1.0)
    # oxidize_surface(pressure=5, temp=450, time=1.0, evac_temp=450, evac_time=0.5)
    # adsExp.cool_cell(targetTemp=temp, holdTime=0, variac_cmd=False)
    # adsExp.chiller_variac_state(chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False)

    adsExp.instrument_operations.actuator_control.actuator_close('TurboPump')
    pressure_thread, stop_pressure_log = adsExp.start_pressure_log(0.0007, 0.002)
    temperature_thread, stop_temperature_log = adsExp.start_temperature_log()

    wait = datetime.now() + timedelta(hours=duration)
    print(f"Measuring leak rate for {duration} hours at {temp} C.\n"
          f"Finished at {datetime.now() + timedelta(hours=duration)}")

    time.sleep(duration * 3600)

    stop_pressure_log.set()
    stop_temperature_log.set()
    pressure_thread.join()
    temperature_thread.join()


if __name__ == "__main__":
    
    def run_adsorption_experiment_manual():

        exp_params.experiment_id()
        exp_params.material_parameters()
        exp_params.is_reference_experiment(False)

        # sequence of operations
        # clean_surface(evac_temp=400,
        #               evac_time=2,
        #               enable_ms=False,
        #               chiller=False)

        # oxidize_surface(pressure=5, 
        #                 temp=500,
        #                 time=2,
        #                 evac_temp=400,
        #                 evac_time=0.5)

        # pretreat_adsorbate(adsorbate='H2O',
        #                    pressure=5,
        #                    temp=550,
        #                    time=1,
        #                    evac_temp=550,
        #                    evac_time=0.5)

        # pretreat_coadsorbates(adsorbates=['H2O', 'O2'],
        #                       pressures=[1.2, 4.2], # max of [1.6, 6.7] Torr, respectively. Need to error handle in function
        #                       temp=650,
        #                       time=1,
        #                       evac_temp=650,
        #                       evac_time=0.5)
        
        monitor_adsorption(adsorbate='13CO',
                           pressure=0.84,
                           temp=45)
                        #    repeat=[10,5,15,135])

    def run_adsorption_experiment_autonomous(selected_experiment):

        exp_params.experiment_id(new_sample=True)
        exp_params.material_parameters()
        exp_params.is_reference_experiment(False)

        expParams = exp_params.import_experimental_parameters(selected_experiment)

        # sequence of operations
        clean_surface(evac_temp=float(expParams['pre_temp_2']),
                    evac_time=float(expParams['pre_duration_2']),
                    chiller=False)

        oxidize_surface(pressure=float(expParams['pre_pressure_calc_3_1']),
                        temp=float(expParams['pre_temp_3']),
                        time=float(expParams['pre_duration_3']),
                        evac_temp=float(expParams['pre_temp_4']), # None
                        evac_time=float(expParams['pre_duration_4'])) # 0.5

        if expParams['pre_gas_5_1'] != '' and expParams['pre_gas_5_2'] == '':
            pretreat_adsorbate(adsorbate=expParams['pre_gas_5_1'], # O2?
                            pressure=float(expParams['pre_pressure_calc_5_1']),
                            temp=int(expParams['pre_temp_5']),
                            time=float(expParams['pre_duration_5']),
                            evac_temp=None,
                            evac_time=0.5) #float(expParams['pre_duration_6'])) # 0, Need hardcoded value

        if expParams['pre_gas_5_1'] != '' and expParams['pre_gas_5_2'] != '':
            pretreat_coadsorbates(adsorbates=[expParams['pre_gas_5_1'], expParams['pre_gas_5_2']],
                                pressures=[float(expParams['pre_pressure_calc_5_1']), float(expParams['pre_pressure_calc_5_2'])],
                                temp=int(expParams['pre_temp_5']),
                                time=float(expParams['pre_duration_5']),
                                evac_temp=None, #int(expParams['pre_temp_6']), #0, need None
                                evac_time=0.5) #float(expParams['pre_duration_6'])) # 0, Need hardcoded value
        
        monitor_adsorption(adsorbate='13CO', pressure=0.84, temp=45)

    def run_reference_experiment():

        exp_params.experiment_id()
        exp_params.material_parameters()
        exp_params.is_reference_experiment(True)

        # sequence of operations
        clean_surface(evac_temp=450,
                    evac_time=2,
                    enable_ms=False,
                    chiller=False)

        oxidize_surface(pressure=5,
                        temp=450,
                        time=2.0,
                        evac_temp=450,
                        evac_time=0.5)

        monitor_adsorption(adsorbate='13CO',
                           pressure=0.84,
                           temp=45)
                        #    repeat=[10,5,15,135])

    def troubleshooting():

        """A procedure for troubleshooting the system."""
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        exp_params.experiment_id(file_name=f"{now}_test", folder_name="_test")

        # actuator_control.actuator_open('irCell')
        # actuator_control.actuator_close('CO2')
        # actuator_control.actuator_write('RoughPump', 1.48)
        # actuator_control.actuator_close_all()

        # isoX=isotopic_exchange_calibration()
        # isoX.massSpec_calibration(targets=[1e-9])

        # opusAcquire(filename='test', foldername='test', repeat=[5], delay=[60],
        #             all_fileids=True, do_bckg=False, do_fit=True)
        # time.sleep(5)
        adsExp.acquire_spectra(repeat=[10], delay=[60],
                    all_fileids=True, do_bckg=False, do_fit=True)
        # repeat = [10, 5, 15, 110] # number of times to repeat
        # delay = [60, 300, 600, 1800] # delay (s) between repeats

    for i in range(8):
        run_reference_experiment()
    # run_reference_experiment()
    # run_adsorption_experiment_manual()
    # run_reference_experiment()
    # measure_leak_rate(temp=45, duration=16)
    # troubleshooting()


    """
    Start-up procedure needed for new sample.
    """