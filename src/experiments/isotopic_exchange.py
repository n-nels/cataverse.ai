
"""Defines classes for experiment categories"""

import csv
import logging
import os
import shutil
import sys
import threading
import time
from datetime import datetime, timedelta
from typing import Any, List

from ..core.config import (
    R,
    chiller_id,
    data_directory,
    share_drive_ms_calibrations_root,
    share_drive_peak_fit_root,
    t_mfld,
    v_50tube,
    v_cell,
    v_m1m2,
    v_m1m2m3,
    v_m3,
    v_tot,
    variac_id,
    variac_id_vsl,
)


logger = logging.getLogger(__name__)

if not logger.handlers:
    _stream_handler = logging.StreamHandler(sys.stdout)
    _stream_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_stream_handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def print(*args: Any, **kwargs: Any) -> None:
    """Module-local print compatibility routed to logging."""

    sep = kwargs.get("sep", " ")
    if sep is None:
        sep = " "
    end = kwargs.get("end", "\n")
    if end is None:
        end = "\n"
    message = sep.join(str(arg) for arg in args)
    if end != "\n":
        message = f"{message}{end}"
    logger.info(message)


class isotopic_exchange_calibration(): # need to update from changes in adsExp
    """
    This class is used to run the isotopic exchange calibration experiment. It uses the methods from the
    experiment_parameters class to log the parameters of the experiment.
    """
    def __init__(self, expParams: Any, serial: Any, actuator_control: Any, instrument_operations: Any) -> None:
        self.expParams = expParams
        self.serial = serial
        self.actuator_control = actuator_control
        self.instrument_operations = instrument_operations
        self.gas = None
        self.gas_2 = None
        self.p_mfld = None
        self.p_cell_calc = None
        self.filename = None # for isoX naming convention
        self.dt = None
    
    def isoX_calib_main(self, xchgTime: List[int], sleepTime: int) -> None:
        """
        Main function to run the isotopic exchange calibration experiment.
        Args:
            xchgTime (List[int]): List of exchange times in minutes.
            sleepTime (int): Sleep time between experiments in hours.
        Returns:
            None
        """
        for i in range(len(xchgTime)):
            self.filename = self.expParams.file_name + '_isoX_' + str(i)
            self.foldername = self.expParams.folder_name

            self.instrument_operations.evacuate_cell('TurboPump')
            self.actuator_control.actuator_open('MassSpec')
            time.sleep(120)
            self.gas, self.p_mfld = self.instrument_operations.deliver_gas_to_mfld(
                                                        filename=self.filename,
                                                        foldername=self.foldername,
                                                        id='CO',
                                                        target=1.0,
                                                        openMS=True)
            now = time.time()
            opus_thread = threading.Thread(target=self.instrument_operations.opusAcquire, args=(
                                                            self.filename,
                                                            self.foldername,
                                                            [1], # repeat
                                                            [0], # delay
                                                            True, # all fileids
                                                            False, # do_bckg
                                                            True # do_fit
                                                            ))
            gas_thread = threading.Thread(target=self.instrument_operations.cell_open_admit)
            """gas delivery is 2 min 49 s (best case), open cell is 2 min 11 s"""

            opus_thread.start()
            gas_thread.start()

            gas_thread.join()
            self.actuator_control.actuator_close('irCell')
            self.actuator_control.actuator_open('TurboPump')
            opus_thread.join()

            wait = (xchgTime[i]*60) - (time.time() - now)
            print(f"MS open at {datetime.now() + timedelta(seconds=wait)}")
            time.sleep(wait) if wait > 0 else None

            ms_thread = threading.Thread(target=self.instrument_operations.MassSpec_open_calibration)
            ms_thread.start()

            while True:
                dt, p_mfld, p_cell_i = self.serial.read_pressure()
                time.sleep(10)
                dt, p_mfld, p_cell_f = self.serial.read_pressure()
                try:
                    if abs(p_cell_f - p_cell_i) > 0.005:
                        break
                except Exception as e:
                    print(e)

            while True:
                dt, p_mfld, p_cell_i = self.serial.read_pressure()
                time.sleep(6)
                dt, p_mfld, p_cell_f = self.serial.read_pressure()
                print(f"p_cell_f: {p_cell_f}, p_cell_i: {p_cell_i}")
                if abs(p_cell_f - p_cell_i) <= 0.00015:
                    break

            self.instrument_operations.opusAcquire(filename=self.filename,
                        foldername=self.foldername,
                        repeat=[1],
                        delay=[0],
                        all_fileids=False,
                        do_bckg=False,
                        do_fit=True)
            ms_thread.join()

            if i != len(xchgTime) - 1:
                self.gas, self.p_mfld = self.instrument_operations.deliver_gas_to_mfld(filename=self.filename,
                                                            foldername=self.foldername,
                                                            id='13CO',
                                                            target=1.0,
                                                            openMS=True)
                self.instrument_operations.deliver_gas_to_cell()

            print(f"Finished experiment {i+1} of {len(xchgTime)} with exchange time of {xchgTime[i]}")

            if i == len(xchgTime) - 1:
                continue
            else:
                print(f"Next experiment at {datetime.now() + timedelta(seconds=3600 * sleepTime)}")
                time.sleep(3600*sleepTime)
        return None

    def heat_under_evacuation(self, pumpType: str, targetTemp: int, holdTime: float, rampRate: int,
                              variac_cmd: bool=True, expParams: bool=True) -> None:
        """
        Heats the cell under evacuation. The pumpType is the type of pump used to evacuate the cell.
        Args:
            pumpType (str): Type of pump used to evacuate the cell. Can be None to skip evacuation and heat.
            targetTemp (int): Target temperature in Celsius.
            holdTime (float): Hold time in hours.
            rampRate (int): Ramp rate in Celsius per minute.
            variac_cmd (bool): Whether to keep the variac on even at target temperature.
            expParams (bool): Whether to log the experimental parameters.
        Returns:
            None
        """
        if pumpType != None:
            self.gas = self.instrument_operations.evacuate_cell(pumpType)
            if holdTime == 0:
                time.sleep(60)
        t_cell, rate, duration = self.instrument_operations.Watlow(
                                        self.expParams.file_name,
                                        self.expParams.folder_name,
                                        targetTemp,
                                        holdTime,
                                        rampRate,
                                        variac_cmd)
        self.dt, self.p_mfld, p_cell = self.serial.read_pressure()
        if expParams:
            self.expParams.pretreatment_parameters(gas=self.gas, p_gas_meas=(self.p_mfld, p_cell),
                                                    t_cell=self.serial.readTemp_ir(), rate=rate, duration=duration)
        return None

    def cool_cell(self, targetTemp: int, holdTime: float, variac_cmd: bool, rampRate: int=0) -> None:
        """
        Cools the cell to a target temperature. The variac_cmd is used to keep the cell on even at target temperature. 
        Args:
            targetTemp (int): Target temperature in Celsius.
            holdTime (float): Hold time in hours.
            variac_cmd (bool): Whether to keep the variac on even at target temperature.
            rampRate (int): Ramp rate in Celsius per minute. Defaults to 0.
        Returns:
            None
        """
        t_cell, rate, duration = self.instrument_operations.Watlow(
                                        self.expParams.file_name,
                                        self.expParams.folder_name,
                                        targetTemp,
                                        holdTime,
                                        rampRate,
                                        variac_cmd)
        while True:
            current_temp = self.serial.readTemp_ir()
            print(f"Current temperature: {current_temp}\nTarget temperature: {t_cell}\n")
            if t_cell + 1 >= current_temp:
                break
            time.sleep(60)
        dt, self.p_mfld, p_cell = self.serial.read_pressure()
        return None

    def supply_gas_to_mfld(self, gas: str, targetPressure: float) -> None:
        """
        Supplies gas to the manifold. The gas is delivered to the manifold and the pressure is calculated.
        Args:
            gas (str): Gas identity.
            targetPressure (float): Target pressure in Torr.
        Returns:
            None
        """
        self.gas, self.p_mfld = self.instrument_operations.deliver_gas_to_mfld(
                                                    self.expParams.file_name,
                                                    self.expParams.folder_name,
                                                    id=gas,
                                                    target=targetPressure,
                                                    openMS=True)
        self.p_cell_calc = self.instrument_operations.calc_pressure(self.p_mfld, v_m1m2m3+v_50tube)
        return None

    def supply_another_gas_to_mfld(self, gas: str, targetPressure: float) -> None:
        """
        Supplies another gas to the manifold. The gas is delivered to the manifold and the pressure is calculated.
        Args:
            gas (str): Gas identity.
            targetPressure (float): Target pressure in Torr.
        Returns:
            None
        """
        self.actuator_control.actuator_close('v16')
        self.actuator_control.actuator_open('TurboPump')
        time.sleep(120)
        self.gas_2, self.p_mfld_2 = self.instrument_operations.deliver_gas_to_mfld(self.expParams.file_name,
                                            self.expParams.folder_name,
                                            id=gas,
                                            target=targetPressure,
                                            openMS=False)
        self.p_cell_calc = self.instrument_operations.calc_pressure(self.p_mfld, v_m3)
        self.p_cell_calc_2 = self.instrument_operations.calc_pressure(self.p_mfld_2, v_m1m2+v_50tube)
        self.actuator_control.actuator_open('v16')
        time.sleep(60)
        return None

    def acquire_spectra(self, repeat: List[int], delay: List[int], all_fileids: bool, do_bckg: bool, do_fit: bool) -> None:
        """
        Acquires spectra from the Opus software. The spectra are acquired in a separate thread.
        Args:
            repeat (List[int]): List of repeat values for the spectra acquisition.
            delay (List[int]): List of delay values for the spectra acquisition.
            all_fileids (bool): Whether to reset spectral processing.
            do_bckg (bool): Whether to acquire background spectra.
            do_fit (bool): Whether to fit the spectra.
        Returns:
            None
        """
        self.instrument_operations.opusAcquire(self.expParams.file_name,
                    self.expParams.folder_name,
                    repeat=[0],
                    delay=[0],
                    all_fileids=all_fileids,
                    do_bckg=do_bckg,
                    do_fit=do_fit
                    )  
        opus_thread = threading.Thread(target=self.instrument_operations.opusAcquire, args=(
                                                            self.expParams.file_name,
                                                            self.expParams.folder_name,
                                                            repeat,
                                                            delay,
                                                            False, # all fileids
                                                            False, # do_bckg
                                                            do_fit # do_fit
                                        ))                                                 
        gas_thread = threading.Thread(target=self.instrument_operations.cell_open_admit)

        opus_thread.start()
        gas_thread.start()
        gas_thread.join()
        time.sleep(20)

        dt, p_mfld, p_cell = self.serial.read_pressure()
        if self.gas_2:
            self.expParams.experimental_parameters(gas=(self.gas, self.gas_2), p_gas_meas=(p_mfld, p_cell),
                                                   t_cell=self.serial.readTemp_ir(), p_gas_calc=(self.p_cell_calc,self.p_cell_calc_2))
        else:
            self.expParams.experimental_parameters(gas=self.gas, p_gas_meas=(p_mfld, p_cell),
                                               t_cell=self.serial.readTemp_ir(), p_gas_calc=self.p_cell_calc)
        
        stop_pressure_log = threading.Event()
        pressure_thread = threading.Thread(
            target=self.instrument_operations.pressure_log,
            args=(self.expParams.path_pressure_log, stop_pressure_log, p_mfld, p_cell),
        )
        pressure_thread.start()
        
        opus_thread.join()
        stop_pressure_log.set()
        pressure_thread.join()
        return None

    def introduce_pretreatment_gas_to_cell(self, targetTemp: int, holdTime: float, rampRate: int=0, variac_cmd: bool=True) -> None:
        """
        Introduces the pretreatment gas to the cell. The gas is delivered to the cell and the pressure is calculated.
        Args:
            targetTemp (int): Target temperature in Celsius.
            holdTime (float): Hold time in hours.
            rampRate (int): Ramp rate in Celsius per minute. Defaults to 0.
            variac_cmd (bool): Whether to keep the variac on even at target temperature.
        Returns:
            None
        """
        self.instrument_operations.deliver_gas_to_cell()
        t_cell, rate, duration = self.instrument_operations.Watlow(self.expParams.file_name,
                                self.expParams.folder_name,
                                targetTemp,
                                holdTime,
                                rampRate,
                                variac_cmd)
        self.dt, self.p_mfld, p_cell = self.serial.read_pressure()
        if self.gas_2:
            self.expParams.pretreatment_parameters(gas=(self.gas, self.gas_2), p_gas_meas=(self.p_mfld, p_cell),
                                                   t_cell=self.serial.readTemp_ir(), rate=rate, duration=duration,
                                                   p_gas_calc=(self.p_cell_calc,self.p_cell_calc_2))
        else:
            self.expParams.pretreatment_parameters(gas=self.gas, p_gas_meas=(self.p_mfld, p_cell),
                                                t_cell=self.serial.readTemp_ir(), rate=rate, duration=duration, p_gas_calc=self.p_cell_calc)
        return None

    def chiller_variac_state(self, chiller_cmd: bool, variac_cmd: bool, variac_vsl_cmd: bool) -> None:
        """
        Sets the state of the chiller and variac. The chiller_cmd is used to set the state of the chiller and
        the variac_cmd is used to set the state of the variac.
        Args:
            chiller_cmd (bool): Whether to turn on the chiller.
            variac_cmd (bool): Whether to turn on the variac.
        Returns:
            None    
        """
        # self.instrument_operations.chiller_state(chiller_cmd)
        # self.instrument_operations.variac_state(variac_cmd)
        self.instrument_operations.kasaPlug_state(chiller_id, chiller_cmd)
        self.instrument_operations.kasaPlug_state(variac_id, variac_cmd)
        self.instrument_operations.kasaPlug_state(variac_id_vsl, variac_vsl_cmd)
        return None

    def copy_readme(self) -> None:
        """
        Copies the README.md file to the peakFit folder. The file is copied to the path specified in the config.py file.
        Args:
            None
        Returns:
            None
        """
        path_copy = os.path.join(
            share_drive_peak_fit_root,
            self.expParams.folder_name,
            self.expParams.file_name + "_README.md",
        )

        try:
            shutil.copy(self.expParams.path_readme, path_copy)
            time.sleep(10)
            self.instrument_operations.OpusVertex80({'readme': True})
        except IOError as e:
            print(f"An error occurred while copying the file: {e}")

    def massSpec_calibration(self, targets: list) -> None:
        """
        This function runs the mass spectrometer calibration experiment. It uses the methods from the
        experiment_parameters class to log the parameters of the experiment.
        Args:
            targets (list): List of target moles for the calibration.
        Returns:
            None
        """
        def calculate_number_of_dilutions(target, dilution_factor, initial_moles):
            """Calculate how many dilutions are required to reach the target moles."""
            n_dilutions = 0
            while initial_moles > (target +(target * 0.25)):
                initial_moles *= dilution_factor
                n_dilutions += 1
            return n_dilutions

        filename = f"{self.expParams.file_name}_msCalib_moles.csv"
        file_path = os.path.join(data_directory, self.expParams.folder_name, filename)
        
        dilution_factor = v_m3 / (v_m1m2m3 + v_50tube)
        minimum_mfld_moles = 3*(v_m1m2m3+v_50tube)/(R*t_mfld) # 3 Torr minimum
        i = 0

        # collect calibration data    
        for target in targets:

            self.actuator_control.actuator_open('MassSpec') # cell closes here
            self.actuator_control.actuator_open('TurboPump')
            print(f"Sleep until {datetime.now() +timedelta(seconds=300)}")
            time.sleep(300)

            final_mfld_moles = target / (v_cell / v_tot)
            n_dilutions = calculate_number_of_dilutions(final_mfld_moles, dilution_factor, minimum_mfld_moles)

            initial_mfld_moles = final_mfld_moles
            for _ in range(n_dilutions):
                initial_mfld_moles /= dilution_factor  # Reverse the effects of dilution
    
            p_mfld_calc = (initial_mfld_moles * R * t_mfld) / (v_m1m2m3 + v_50tube)
            id, p_mfld = self.instrument_operations.deliver_gas_to_mfld(filename=None, foldername=None, id='13CO', target=p_mfld_calc)
            moles = p_mfld*(v_m1m2m3+v_50tube)/(R*t_mfld)

            j = 0
            while True:
                moles = moles * dilution_factor
                self.actuator_control.actuator_close('v16')
                time.sleep(5)
                self.actuator_control.actuator_open('TurboPump')
                print(f"Sleep until {datetime.now() + timedelta(seconds=300)}")
                time.sleep(300)
                self.actuator_control.actuator_close('TurboPump')
                time.sleep(5)
                self.actuator_control.actuator_open('v16')
                time.sleep(60)

                expected_final_dilution = moles * dilution_factor
                expected_final_moles = expected_final_dilution * v_cell / v_tot
                if abs(expected_final_moles - target) < target * 0.25:
                    print(f"Target mole value of {expected_final_moles:.4e} reached. Target moles is {target}. Execute final dilution.")
                    break
                print(f"Dilution {j+1}:")
                print(f"Expected calibration moles is {expected_final_moles:.4e}. Target moles is {target} Diluting again...")
                j += 1

            # final dilution
            self.actuator_control.actuator_close('v16')
            time.sleep(5)
            self.actuator_control.actuator_open('TurboPump')
            print(f"Sleep until {datetime.now() + timedelta(seconds=300)}")
            time.sleep(300)
            self.actuator_control.actuator_close('TurboPump')
            id, p_mfld = self.instrument_operations.deliver_gas_to_mfld(filename=None, foldername=None,
                                             id='CO', target=(v_m1m2m3+v_50tube)/(v_m1m2+v_50tube))
            self.actuator_control.actuator_open('v16')
            moles = moles*dilution_factor
            time.sleep(60)

            # introduce gas to cell
            self.instrument_operations.cell_open_admit()
            self.actuator_control.actuator_close('irCell')
            time.sleep(5)
            self.actuator_control.actuator_open('RoughPump')
            moles = moles*v_cell/v_tot
            print(f"final moles = {moles:.4e}. Target moles = {target:.2e}")

            if os.path.exists(file_path):
                with open(file_path, mode='a', newline='') as file:
                    writer = csv.writer(file)
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    name = f"{self.expParams.file_name}_msCalib_{i}.csv"
                    writer.writerow([name, timestamp, moles])
            else:
                with open(file_path, mode='w', newline='') as file:
                    writer = csv.writer(file)
                    headers = ['Filename', 'Timestamp', '13CO_Moles']
                    writer.writerow(headers)
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    name = f"{self.expParams.file_name}_msCalib_{i}.csv"
                    writer.writerow([name, timestamp, moles])

            self.instrument_operations.MassSpec_open_calibration()
            print(f"Finished calibration {i+1} of {len(targets)}")
            i += 1
        
        i = 0
        for _ in range(2):
            self.gas, self.p_mfld = self.instrument_operations.deliver_gas_to_mfld(filename=None, foldername=None, id='CO', target=1.0)
            self.instrument_operations.deliver_gas_to_cell()
            self.actuator_control.actuator_close('irCell')
            self.actuator_control.actuator_open('TurboPump')
            time.sleep(10)
            moles = 0

            with open(file_path, mode='a', newline='') as file:
                writer = csv.writer(file)
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                name = f"{self.expParams.file_name}_msCalib_{i}.csv"
                writer.writerow([name, timestamp, moles])

            self.instrument_operations.MassSpec_open_calibration()
            print(f"Finished calibration {i+1} of {len(range(2))}")
            i += 1

        path_copy = os.path.join(
            share_drive_ms_calibrations_root,
            self.expParams.folder_name,
            filename,
        )
        try:
            shutil.copy(file_path, path_copy)
        except IOError as e:
            print(f"An error occurred while copying the file: {e}")
        return None
