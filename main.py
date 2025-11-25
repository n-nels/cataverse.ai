

from ni_usb6009_devices import ActuatorManager, device_map
from serial_devices import SerialDevices
from network_messaging import NetworkMessaging
from actuator_control import ActuatorControl
from instrument_operations import InstrumentOperations
from experiment_protocols import experiment_parameters, isotopic_exchange_calibration, adsorption_experiment
from config import (v_tot, notebook, metal, support, mass, metal_load, support_sa, metal_density)
from typing import List
from datetime import datetime
import time
import numpy as np

actuators = ActuatorManager(device_map)
serial = SerialDevices()
actuator_control = ActuatorControl(actuators, serial)
opus = NetworkMessaging()
instrument_operations = InstrumentOperations(serial, actuator_control, opus)
exp_params = experiment_parameters(notebook=notebook, 
                            mass=mass, 
                            metal=metal, 
                            metal_load=metal_load, 
                            metal_density=metal_density,
                            support=support,
                            support_sa=support_sa,
                            v_tot=v_tot
                            )
adsExp = adsorption_experiment(exp_params, serial, actuator_control, instrument_operations)

opus.connect(ip="130.20.216.127", port=5555) # spectrometer
serial.connect_mks() # pressure gauge
serial.connect_watlow_ir() # temperature controller for IR cell


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

def clean_surface(evac_temp: int, evac_time: float, chiller: bool = True) -> None:
    """A procedure for removing surface adsorbates under evacuation
    Args:
        evac_temp (int): Temperature of evacuation in C
        evac_time (float): Hold time in hours
        chiller (bool): Whether to use the chiller and variac for cooling
    """
    adsExp.chiller_variac_state(chiller_cmd=chiller, variac_cmd=True, variac_vsl_cmd=True)
    adsExp.heat_under_evacuation(pumpType='RoughPump', targetTemp=evac_temp, holdTime=0.0, rampRate=20)
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

def monitor_adsorption(adsorbate: str, pressure: float, temp: int) -> None:
    """A procedure for monitoring the adsorption of a gas in the IR cell. The pressure corresponds to the total volume.
    Args:
        adsorbate (str): The gas introduced
        temp (int): Temperature of adsorption in C
        pressure (float): Pressure of gas in Torr
    """
    adsExp.cool_cell(targetTemp=temp, holdTime=0, variac_cmd=False)
    adsExp.chiller_variac_state(chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False)
    adsExp.supply_gas_to_mfld(gas=adsorbate, targetPressure=pressure)
    adsExp.acquire_spectra(repeat=[10,5,15,60], # 115 is about 60 h
                        delay=[60,300,600,1800],
                        all_fileids=True,
                        do_bckg=True,
                        do_fit=True)

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
    # exp_params.experiment_id('20250713_102624_leakRate', folder_name='leak_rates')
    exp_params.material_parameters()

    clean_surface(evac_temp=450, evac_time=1.0)
    oxidize_surface(pressure=5, temp=450, time=2.0, evac_temp=450, evac_time=0.5)
    adsExp.cool_cell(targetTemp=temp, holdTime=0, variac_cmd=False)
    adsExp.chiller_variac_state(chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False)

    adsExp.instrument_operations.actuator_control.actuator_close('TurboPump')
    pressure_thread, stop_pressure_log = adsExp.start_pressure_log()
    temperature_thread, stop_temperature_log = adsExp.start_temperature_log()

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
        clean_surface(evac_temp=450,
                      evac_time=1,
                      chiller=False)

        oxidize_surface(pressure=5, 
                        temp=450, 
                        time=1,
                        evac_temp=450,
                        evac_time=0.5)

        # pretreat_adsorbate(adsorbate='H2O',
        #                    pressure=5,
        #                    temp=450,
        #                    time=1,
        #                    evac_temp=450,
        #                    evac_time=0.5)

        pretreat_coadsorbates(adsorbates=['O2', 'H2O'],
                              pressures=[0.5, 5.0], # max of [1.6, 6.7] Torr, respectively. Need to error handle in function
                              temp=450,
                              time=1,
                              evac_temp=450,
                              evac_time=0.5)
        
        monitor_adsorption(adsorbate='13CO', pressure=0.84, temp=45)

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
                    chiller=False)

        oxidize_surface(pressure=5,
                        temp=450,
                        time=2.0,
                        evac_temp=450,
                        evac_time=0.5)

        monitor_adsorption(adsorbate='13CO', pressure=0.84, temp=45)

    def troubleshooting():
        """A procedure for troubleshooting the system."""

        # actuator_control.actuator_open('irCell')
        # actuator_control.actuator_close('CO2')
        # actuator_control.actuator_write('RoughPump', 1.48)
        actuator_control.actuator_close_all()

        # isoX=isotopic_exchange_calibration()
        # isoX.massSpec_calibration(targets=[1e-9])

        # opusAcquire(filename='test', foldername='test', repeat=[5], delay=[60],
        #             all_fileids=True, do_bckg=False, do_fit=True)
        # time.sleep(5)
        # opusAcquire(filename='test', foldername='test', repeat=[2], delay=[60],
        #             all_fileids=True, do_bckg=False, do_fit=False)
        # repeat = [10, 5, 15, 110] # number of times to repeat
        # delay = [60, 300, 600, 1800] # delay (s) between repeats



"""scripts for running experiments"""
# run_isotopic_exchange_calibration()
run_adsorption_experiment_manual()
# run_reference_experiment()
# run_adsorption_experiment_autonomous("selected_experiments_20250731.csv")
# measure_leak_rate(temp=45, duration=24)

"""manual physical control of the system"""
# actuator_control.actuator_close_all(device_map=device_map)
# actuator_control.actuator_open('v16')
# time.sleep(5)
# actuator_control.actuator_close('irCell')
# time.sleep(5)
# actuator_control.actuator_open('RoughPump')
# troubleshooting()


"""manual data logging"""
# exp_params.experiment_id('20251020_144255_pd_ceo2_003-045')
# pressure_thread, stop_pressure_log = adsExp.start_pressure_log()
# time.sleep(24*3600)
# stop_pressure_log.set()
# pressure_thread.join()

# expParams = exp_params.import_experimental_parameters("selected_experiments_20250731.csv")
# print(expParams)

"""To Do List
- Use Ar to determine effective temperature when cell is 45 C and manifold is at room temperature. This can
be done by measuring the pressure when cell is at 45 C and 25 C. The difference in pressure can be used to
determine the effective temperature of the manifold. This can be done by using the ideal gas law
- Use Ar to determine leak rate of the system. This can be done by measuring the pressure increase over time
- From the leak rate experiment, the rate of water adsorption can be determined. This can be done by doing
TPD as a function of leak test time. The amount of water adsorbed can be determined by integrating the TPD.
It is probably better to do this with the empty cell and then compare to the sample. This will help determine
the temeperature needed to remove all water from the material.
- The same method can be used to count the number of hydroxyls following water adsorption and evacuation.
- Need to add the chiller on/off functionality when heating above reference temperature.
- Need to add the second variac control to the script.
- Need to add argument to check line to make more robust.
"""