
"""Defines classes for experiment categories"""

import os, time, threading, shutil, csv, re, glob
from datetime import datetime, timedelta
from typing import Optional, List
from data_logging import log_experiment_parameters, materParams, create_directory, expID, copy_to_share_drive
from config import (R, t_mfld, v_cell, v_m1m2, v_m1m2m3, v_50tube, v_m3, v_tot, chiller_id, variac_id, variac_id_vsl)


class experiment_parameters:
    """
    This class is used to log the parameters of the experiment. It creates a README.md file
    in the folder where the experiment is being run. The parameters are logged in a structured
    format, which can be easily read by the user. The class also has methods to check if a line
    already exists in the README.md file, and to add new parameters to the file.
    """
    def __init__(self, notebook: str, mass: float, metal: str, metal_load: float, metal_density: float, support: str,
                 support_sa: float, v_tot: float):
        
        self.notebook = notebook
        self.mass = mass
        self.metal = metal
        self.metal_load = metal_load
        self.metal_density = metal_density
        self.support = support
        self.support_sa = support_sa
        self.v_tot = v_tot
        self.counter = 0
        self.file_name = None
        self.folder_name = None
        self.path_readme = None
        self.path_pressure_log = None

    def experiment_id(self, file_name: Optional[str]=None, folder_name: Optional[str]=None,
                      new_sample: bool=False, counter: int=0) -> None:
        """
        Generates an experiment ID and sets up the necessary directories and files.
        Args:
            file_name (Optional[str]): Name of the experiment file. Defaults to None.
            folder_name (Optional[str]): Name of the experiment folder. Defaults to None.
            new_sample (bool): Whether this is a new sample. Defaults to False.
            counter (int): Counter to start the README script at a specific step count. Defaults to 0.
        Returns:
            None
        """
        self.file_name, self.folder_name = expID(file_name, folder_name, new_sample)
        create_directory(f"C://Data//{self.folder_name}")
        self.path_readme = f"C://Data//{self.folder_name}//{self.file_name}_README.md"
        self.path_pressure_log = f"C://Data//{self.folder_name}//{self.file_name}_pressureLog.csv"
        self.counter=counter
        
    def material_parameters(self) -> None: 
        """
        Logs the material parameters of the experiment in the README.md file.
        Args:
            None
        Returns:
            None
        """
        materParams(
            path_readme = self.path_readme,
            notebook=self.notebook,
            mass=self.mass,
            metal=self.metal,
            metal_load=self.metal_load,
            metal_density=self.metal_density,
            support=self.support,
            support_sa=self.support_sa,
            v_tot=self.v_tot
        )

        self.experiment_success(False)

    def check_line_exists(self) -> bool:
        """
        Checks if a specific line exists in the README.md file.
        Args:
            None
        Returns:
            bool: True if the line exists, False otherwise.
        """
        if os.path.exists(self.path_readme):
            with open(self.path_readme, 'r') as file:
                for line in file:
                    if line.strip() == f"## pretreatment_{self.counter}":
                        return True
                    if (line.strip() == f"## exp_gas") and self.counter == 0:
                        return True
                    
        return False

    def pretreatment_parameters(self, gas: str, p_gas_meas: tuple[float, float], t_cell: float,
                                rate: int, duration: float, p_gas_calc: float=None, chiller_state: bool=None) -> None:
        """
        Logs the pretreatment parameters of the experiment in the README.md file.
        Args:
            gas (str): Gas identity.
            p_gas_meas (tuple[float, float]): Measured pressure of gas in Torr.
            t_cell (float): Temperature of cell in Celsius.
            rate (int): Heating rate in Celsius per minute.
            duration (float): Duration of pretreatment step in hours.
            p_gas_calc (float): Calculated pressure of gas in Torr. Defaults to None.
            chiller_state (bool): State of the chiller during pretreatment. Defaults to None.
        Returns:
            None
        """
        self.counter += 1
        if self.check_line_exists():
            return

        parameters = [
            {
                "name": f"pretreatment_{self.counter}",
                "description": "Parameters for pretreatment steps...",
                "subparameters": [
                    {
                        "name": f"pre_gas_{self.counter}",
                        "description": "Gas identity",
                        "value": gas
                    },
                    {
                        "name": f"pre_pressure_meas_{self.counter}",
                        "description": "Measured pressure of gas in Torr.",
                        "value": p_gas_meas
                    },
                    {
                        "name": f"pre_pressure_calc_{self.counter}",
                        "description": "Calculated pressure of gas in Torr.",
                        "value": p_gas_calc
                    },
                    {
                        "name": f"pre_temp_{self.counter}",
                        "description": "Temperature of cell in Celsius.",
                        "value": t_cell
                    },
                    {
                        "name": f"pre_rate_{self.counter}",
                        "description": "Heating rate in Celsius per minute",
                        "value": rate
                    },
                    {
                        "name": f"pre_duration_{self.counter}",
                        "description": "Duration of pretreatment step in hours.",
                        "value": duration
                    },
                                        {
                        "name": f"pre_chiller_{self.counter}",
                        "description": "Chiller state during pretreatment.",
                        "value": chiller_state
                    },
                ]
            }
        ]
        
        log_experiment_parameters(self.path_readme, parameters)

    def experimental_parameters(self, gas: str, p_gas_meas: tuple[float, float], t_cell: float,
                                p_gas_calc: float, chiller_state: bool=None) -> None:
        """
        Logs the experimental parameters of the experiment in the README.md file.
        Args:
            gas (str): Gas identity.
            p_gas_meas (tuple[float, float]): Measured pressure of gas in Torr.
            t_cell (float): Temperature of cell in Celsius.
            p_gas_calc (float): Calculated pressure of gas in Torr.
        Returns:
            None
        """
        self.counter = 0
        if self.check_line_exists():
            return
        parameters = [
            {
                "name": "exp_gas",
                "description": "Gas identity.",
                "value": gas
            },
            {
                "name": "exp_pressure_meas",
                "description": "Pressure of gas in Torr as (p_mfld, p_cell).",
                "value": p_gas_meas
            },
            {
                "name": "exp_pressure_calc",
                "description": "Pressure of gas in Torr.",
                "value": p_gas_calc
            },
            {
                "name": "exp_temp",
                "description": "Temperature of cell in Celsius.",
                "value": t_cell
            },
            {
                "name": "exp_chiller",
                "description": "Chiller state during pretreatment.",
                "value": chiller_state
            }
            ]

        log_experiment_parameters(self.path_readme, parameters)

    def experiment_success(self, success: bool) -> None:
        """
        Logs the success status of the experiment in the README.md file.
        Args:
            success (bool): Success status of the experiment.
        Returns:
            None
        """
        if self.check_line_exists():
            return
        parameters = [
            {
                "name": "exp_success",
                "description": "Success status of the experiment.",
                "value": success
            }
        ]
        log_experiment_parameters(self.path_readme, parameters)
        # self.is_new_sample_experiment(success)

    def update_experiment_success(self, success: bool) -> None:
        """
        Updates the 'exp_success' value in the README.md file.
        Args:
            success (bool): The new success value to set.
        Returns:
            None
        """
        if not os.path.exists(self.path_readme):
            return

        with open(self.path_readme, 'r') as file:
            lines = file.readlines()

        with open(self.path_readme, 'w') as file:
            found_header = False  # Flag to track if we're in the `## exp_success` section

            for line in lines:
                if line.strip().startswith("## exp_success"):
                    found_header = True
                    file.write(line)  # Write the header line back unchanged
                    continue

                if found_header and line.strip().startswith("- Value:"):
                    file.write(f"- Value: {str(success)}\n")
                    found_header = False
                    continue

                # Write all other lines unchanged
                file.write(line)

    def check_exp_success(self, readme_path: str) -> bool:
        """Check if exp_success is True in the README file."""
        try:
            if not os.path.exists(readme_path):
                return False
                
            with open(readme_path, 'r', encoding='utf-8') as file:
                content = file.read()
                
            # Look for the exp_success section and extract its value
            # This regex looks for "- Value:" followed by optional whitespace and "True"
            # after finding "## exp_success" section
            pattern = r'##\s*exp_success.*?-\s*Value:\s*(True|true)'
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            
            return match is not None
            
        except Exception as e:
            print(f"Error reading README file: {e}")
            return False

    def import_experimental_parameters(self, csvfile) -> dict:
        """Imports experimental parameters from a CSV file for autonomous experiments."""
        
        def clean_gas_string(val):
            # Matches strings like '(O2,)', '(CO2,)', etc.
            if isinstance(val, str):
                match = re.match(r"\(([^,]+),\)", val)
                if match:
                    return match.group(1)
            return val

        path = f"C://Users//labuser//instrument_control//catalysis_autolab//data//{csvfile}"

        with open(path, newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                experiment_dict = {k: clean_gas_string(v) for k, v in row.items()}
                return experiment_dict
        return None

    def is_reference_experiment(self, val: bool) -> None:
        """Logs the experiment as a reference experiment."""
        parameters = [
            {
                "name": "is_reference",
                "description": "Whether this is a reference experiment.",
                "value": val
            },
         ]
        # need a check line here. need to change check_line_exists to check for any line
        log_experiment_parameters(self.path_readme, parameters)

    def is_new_sample_experiment(self) -> None:
        """Checks if the experiment is a new sample experiment."""
        
        directory_path = f"X:\\peakFit\\{self.folder_name}\\"
        carbonyl_files = glob.glob(os.path.join(directory_path, "*_CarbonylPeakArea.csv"))
        
        if len(carbonyl_files) != 1:
            is_new_sample = False
        else:
            is_new_sample = self.check_exp_success(self.path_readme)

        parameters = [
            {
                "name": "is_new_sample",
                "description": "Whether this is a new sample.",
                "value": is_new_sample
            },
        ]
        
        log_experiment_parameters(self.path_readme, parameters)

class isotopic_exchange_calibration(): # need to update from changes in adsExp
    """
    This class is used to run the isotopic exchange calibration experiment. It uses the methods from the
    experiment_parameters class to log the parameters of the experiment.
    """
    def __init__(self, expParams, serial, actuator_control, instrument_operations):
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
        pressure_thread = threading.Thread(target=self.instrument_operations.pressure_log, args=(f"C://Data//{self.expParams.folder_name}//{ \
            self.expParams.file_name}_pressureLog.csv", stop_pressure_log))
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
        path_copy = "X:\\peakFit\\" + self.expParams.folder_name + '\\' + \
            self.expParams.file_name + "_README.md"

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
        file_path = f"C:\\Data\\{self.expParams.folder_name}\\{filename}"
        
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

        path_copy = f"X:/ms_calibrations/{self.expParams.folder_name}/{filename}"
        try:
            shutil.copy(file_path, path_copy)
        except IOError as e:
            print(f"An error occurred while copying the file: {e}")
        return None

class adsorption_experiment():
    def __init__(self, expParams, serial, actuator_control, instrument_operations):
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
        t_cell, rate, duration = self.instrument_operations.Watlow(self.expParams.file_name,
                                        self.expParams.folder_name,
                                        targetTemp,
                                        holdTime,
                                        rampRate,
                                        variac_cmd)
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

        self.expParams.update_experiment_success(success=True)
        time.sleep(5)
        self.expParams.is_new_sample_experiment()
        time.sleep(5)
        try:
            copy_to_share_drive(src_path=self.expParams.path_readme,
                                dest_folder=f"X:\\peakFit\\{self.expParams.folder_name}",
                                file_name=self.expParams.file_name,
                                suffix="README.md")            
            copy_to_share_drive(src_path=self.expParams.path_pressure_log,
                                dest_folder=f"X:\\pressureData\\{self.expParams.folder_name}",
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

    def start_pressure_log(self, p_mfld_initial, p_cell_initial):
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
    
    def start_temperature_log(self):
        """
        Starts the temperature logging thread and returns the thread and stop event.
        Returns:
            (threading.Thread, threading.Event): The temperature logging thread and stop event.
        """
        stop_temp_log = threading.Event()
        log_path = f"C://Data//{self.expParams.folder_name}//{self.expParams.file_name}_tempLog.csv"
        temp_thread = threading.Thread(
            target=self.instrument_operations.temperature_log,
            args=(log_path, stop_temp_log)
        )
        temp_thread.start()
        return temp_thread, stop_temp_log