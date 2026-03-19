"""Adsorption experiment protocol implementation."""

import csv
import os
import shutil
import threading
import time
from datetime import datetime, timedelta
from typing import Any, List

from ..core import get_logger
from ..core.config import (
    R,
    chiller_id,
    data_directory,
    share_drive_ms_calibrations_root,
    share_drive_peak_fit_root,
    share_drive_pressure_data_root,
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
from .parameters import experiment_parameters
from ..utils.data_logging import copy_to_share_drive


logger = get_logger(__name__)


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


class adsorption_experiment():
    def __init__(self, expParams: Any, serial: Any, actuator_control: Any, instrument_operations: Any) -> None:
        self.expParams = expParams
        self.serial = serial
        self.actuator_control = actuator_control
        self.instrument_operations = instrument_operations
        self.gas = None
        self.gas_2 = None
        self.p_mfld = None
        self.p_cell_calc = None
        self.dt = None
        self.chiller_state = None

    def heat_under_evacuation(self, pumpType: str, targetTemp: int, holdTime: float, rampRate: int,
                              enable_ms_stream: bool=False, variac_cmd: bool=True, expParams: bool=True) -> None:
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

        if enable_ms_stream:
            ms_thread, stop_ms = self.acquire_ms_spectra()

        t_cell, rate, duration = self.instrument_operations.Watlow(self.expParams.file_name,
                                        self.expParams.folder_name,
                                        targetTemp,
                                        holdTime,
                                        rampRate,
                                        variac_cmd)
        if enable_ms_stream:
            time.sleep(60*15)
            print()
            stop_ms.set()
            ms_thread.join()
            self.instrument_operations.extrel_sequence('stop')
            self.actuator_control.actuator_close('MassSpec')
            self.actuator_control.actuator_open('irCell')

        self.dt, self.p_mfld, p_cell = self.serial.read_pressure()
        if expParams:
            self.expParams.pretreatment_parameters(gas=self.gas, p_gas_meas=(self.p_mfld, p_cell),
                                                    t_cell=self.serial.readTemp_ir(), rate=rate, duration=duration,
                                                    chiller_state=self.chiller_state)
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
        t_cell, rate, duration = self.instrument_operations.Watlow(self.expParams.file_name,
                                        self.expParams.folder_name,
                                        targetTemp,
                                        holdTime,
                                        rampRate,
                                        variac_cmd)
        while True:
            current_temp = self.serial.readTemp_ir()
            print(f"Current temperature: {current_temp}\nTarget temperature: {t_cell}\n")
            try:
                if t_cell + 1 >= current_temp:
                    break
            except TypeError as e:
                print(f"Error occurred while reading temperatures: {e}")
            time.sleep(60)
        dt, self.p_mfld, p_cell = self.serial.read_pressure()
        return None

    def supply_gas_to_mfld(self, gas: str, targetPressure: float) -> None:
        """
        Supplies gas to the manifold. The target pressure corresponds to the pressure in the total volume of
        the system. The pressure should not exceed 7.5 Torr
        Args:
            gas (str): Gas identity.
            targetPressure (float): Target pressure in Torr.
        """
        if self.gas_2:
            self.gas_2 = None
        val = (v_tot)/(v_m1m2m3+v_50tube) * targetPressure
        self.gas, self.p_mfld = self.instrument_operations.deliver_gas_to_mfld(self.expParams.file_name,
                                                    self.expParams.folder_name,
                                                    id=gas,
                                                    target=val,
                                                    openMS=True)
        self.p_cell_calc = self.instrument_operations.calc_pressure(self.p_mfld, v_m1m2m3+v_50tube)
        return None

    def supply_another_gas_to_mfld(self, gas: str, targetPressure: float) -> None:
        """
        Supplies another gas to the manifold. The gas is delivered to the manifold and the pressure is calculated.
        Args:
            gas (str): Gas identity.
            targetPressure (float): Target pressure in Torr.
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

    def supply_gases_to_mfld(self, gas: List[str], targetPressure: List[float]) -> None:
        """
        Supplies gas to the manifold. The target pressure corresponds to the pressure in the total volume of
        the system. The pressure of gas[0] cannot exceed 2.2 Torr. The pressure of gas[1] cannot exceed 9 Torr.
        Args:
            gas (str): Gas identity.
            targetPressure (float): Target pressure in Torr.
        """
        val_1 = (v_tot)/v_m3 * targetPressure[0]
        val_2 = (v_tot)/(v_m1m2+v_50tube) * targetPressure[1]

        # supply first gas to manifold
        self.gas, self.p_mfld = self.instrument_operations.deliver_gas_to_mfld(self.expParams.file_name,
                                                    self.expParams.folder_name,
                                                    id=gas[0],
                                                    target=val_1,
                                                    openMS=True)
        self.actuator_control.actuator_close('v16')
        dt, self.p_mfld, p_cell = self.serial.read_pressure()
        self.p_cell_calc = self.instrument_operations.calc_pressure(self.p_mfld, v_m3)

        # supply second gas to manifold
        self.actuator_control.actuator_open('TurboPump')
        time.sleep(300)
        self.gas_2, self.p_mfld_2 = self.instrument_operations.deliver_gas_to_mfld(self.expParams.file_name,
                                            self.expParams.folder_name,
                                            id=gas[1],
                                            target=val_2,
                                            openMS=True)
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
        self.instrument_operations.opusAcquire(
                    self.expParams.file_name,
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
        dt, p_mfld_initial, p_cell_initial = self.serial.read_pressure()
        gas_thread = threading.Thread(target=self.instrument_operations.cell_open_admit)

        opus_thread.start()
        gas_thread.start()

        gas_thread.join()
        time.sleep(20)
        dt, p_mfld, p_cell = self.serial.read_pressure()
        if self.gas_2:
            self.expParams.experimental_parameters(gas=(self.gas, self.gas_2), p_gas_meas=(p_mfld, p_cell),
                                                   t_cell=self.serial.readTemp_ir(), p_gas_calc=(self.p_cell_calc,self.p_cell_calc_2),
                                                   chiller_state=self.chiller_state)
        else:
            self.expParams.experimental_parameters(gas=self.gas, p_gas_meas=(p_mfld, p_cell),
                                               t_cell=self.serial.readTemp_ir(), p_gas_calc=self.p_cell_calc,
                                               chiller_state=self.chiller_state)

        pressure_thread, stop_pressure_log = self.start_pressure_log(p_mfld_initial, p_cell_initial)

        opus_thread.join()
        stop_pressure_log.set()
        pressure_thread.join()

        self.instrument_operations.evacuate_cell('RoughPump')
        self.instrument_operations.OpusVertex80(message = {
                        'end_experiment': True,
                        'foldername': self.expParams.folder_name,
                        'filename': self.expParams.file_name + "_evacuation",
                        'do_bckg': False,
                        'do_fit': False,
                        'reset_fileids': False # opus waits 10 minutes; need to fix reconnecting socket logic
                    })

        self.expParams.update_experiment_success(success=True)
        time.sleep(5)
        self.expParams.is_new_sample_experiment()
        time.sleep(5)
        try:
            copy_to_share_drive(src_path=self.expParams.path_readme,
                                dest_folder=os.path.join(share_drive_peak_fit_root, self.expParams.folder_name),
                                file_name=self.expParams.file_name,
                                suffix="README.md")
            copy_to_share_drive(src_path=self.expParams.path_pressure_log,
                                dest_folder=os.path.join(share_drive_pressure_data_root, self.expParams.folder_name),
                                file_name=self.expParams.file_name,
                                suffix="pressureLog.csv")

            self.instrument_operations.OpusVertex80({'readme': True})

        except Exception as e:
            print(f"An error occurred while copying the file: {e}")

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
                                                   p_gas_calc=(self.p_cell_calc,self.p_cell_calc_2),
                                                   chiller_state=self.chiller_state)
        else:
            self.expParams.pretreatment_parameters(gas=self.gas, p_gas_meas=(self.p_mfld, p_cell),
                                                t_cell=self.serial.readTemp_ir(), rate=rate, duration=duration, p_gas_calc=self.p_cell_calc,
                                                chiller_state=self.chiller_state)
        return None

    def chiller_variac_state(self, chiller_cmd: bool, variac_cmd: bool, variac_vsl_cmd: bool) -> None:
        """
        Sets the state of the chiller and variac. The chiller_cmd is used to set the state of the chiller and
        the variac_cmd is used to set the state of the variac.
        Args:
            chiller_cmd (bool): Whether to turn on the chiller. Can be None to skip.
            variac_cmd (bool): Whether to turn on the variac. Can be None to skip.
            variac_vsl_cmd (bool): Whether to turn on the variac for the VSL. Can be None to skip.
        Returns:
            None
        """
        if chiller_cmd is not None:
            self.chiller_state = chiller_cmd
            self.instrument_operations.kasaPlug_state(chiller_id, chiller_cmd)
            # self.instrument_operations.chiller_state(chiller_cmd)
        if variac_cmd is not None:
            self.instrument_operations.kasaPlug_state(variac_id, variac_cmd)
            # self.instrument_operations.variac_state(variac_cmd)
        if variac_vsl_cmd is not None:
            self.instrument_operations.kasaPlug_state(variac_id_vsl, variac_vsl_cmd)
            # self.instrument_operations.variac_state(variac_vsl_cmd)
        return None

    def start_pressure_log(self, p_mfld_initial: Any, p_cell_initial: Any) -> tuple[threading.Thread, threading.Event]:
        """
        Starts the pressure logging thread and returns the thread and stop event.
        Returns:
            (threading.Thread, threading.Event): The pressure logging thread and stop event.
        """
        stop_pressure_log = threading.Event()
        log_path = self.expParams.path_pressure_log
        pressure_thread = threading.Thread(
            target=self.instrument_operations.pressure_log,
            args=(log_path, stop_pressure_log, p_mfld_initial, p_cell_initial)
        )
        pressure_thread.start()
        return pressure_thread, stop_pressure_log

    def start_temperature_log(self) -> tuple[threading.Thread, threading.Event]:
        """
        Starts the temperature logging thread and returns the thread and stop event.
        Returns:
            (threading.Thread, threading.Event): The temperature logging thread and stop event.
        """
        stop_temp_log = threading.Event()
        log_path = os.path.join(
            data_directory,
            self.expParams.folder_name,
            f"{self.expParams.file_name}_tempLog.csv",
        )
        temp_thread = threading.Thread(
            target=self.instrument_operations.temperature_log,
            args=(log_path, stop_temp_log)
        )
        temp_thread.start()
        return temp_thread, stop_temp_log

    def acquire_ms_spectra(self) -> tuple[threading.Thread, threading.Event]:
        """
        Acquires spectra from the Mass Spectrometer software. The spectra are acquired in a separate thread.
        Returns:
            (threading.Thread, threading.Event): The mass spectrometer logging thread and stop event.
        """
        self.actuator_control.actuator_close('irCell')
        self.actuator_control.actuator_open('MassSpec')
        time.sleep(30)

        self.instrument_operations.extrel_sequence('start')
        stop_ms_log = threading.Event()
        log_path = self.expParams.path_ms_log
        ms_thread = threading.Thread(
            target=self.instrument_operations.extrel_stream,
            args=(log_path, stop_ms_log)
        )
        ms_thread.start()
        time.sleep(60)
        return ms_thread, stop_ms_log
