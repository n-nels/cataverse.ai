"""
This script is used to manage data logs by creating directorys and writing to .csv files
"""
import os
import csv
import glob
import shutil
import time
from datetime import datetime
from typing import List, Any, Dict
from ..core.config import (notebook, metal, support)

def create_directory(directory_path: str) -> None:
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)

def log_to_csv(file_path: str, headers: List[str], rows: List[List[Any]]) -> None:
    """
    General-purpose function to log data to a CSV file.
    Args:
        file_path: Path to the CSV file.
        headers: List of column headers.
        rows: List of rows (each row is a list of values).
    Returns:
        None
    """
    mode = 'a' if os.path.exists(file_path) else 'w'
    with open(file_path, mode, newline='') as csv_file:
        writer = csv.writer(csv_file)
        if mode == 'w':
            writer.writerow(headers)
        writer.writerows(rows)
    return None

def log_actuator_state(file_path: str, actuator_id: str,
                       act_writes: List[Any], pressures: List[Any],
                       timestamps: List[Any], dithers: List[Any]) -> None:
    """
    Log actuator states to a CSV file.
    Args:
        file_path: Path to the CSV file.
        actuator_id: ID of the actuator.
        act_writes: List of actuator write values.
        pressures: List of pressure readings.
        timestamps: List of timestamps.
        dithers: List of dither values.
    Returns:
        None
    """

    headers = ["ID", "DateTime", "ActWrite", "Pressure", "Dither"]
    rows = [
        [actuator_id, timestamps[i], act_writes[i], pressures[i], dithers[i]]
        for i in range(len(act_writes))
    ]
    log_to_csv(file_path, headers, rows)
    return None

def log_temperature(file_path: str, write_temps: List[Any],
                    read_temps: List[Any], timestamps: List[Any]) -> None:
    """
    Log temperature data to a CSV file.
    Args:
        file_path: Path to the CSV file.
        write_temps: List of target temperatures.
        read_temps: List of actual temperatures.
        timestamps: List of timestamps.
    Returns:
        None
    """

    headers = ["WriteTemp", "ReadTemp", "DateTime"]
    length = min(len(write_temps), len(read_temps), len(timestamps))
    rows = [
        [write_temps[i], read_temps[i], timestamps[i]]
        for i in range(length)
    ]
    log_to_csv(file_path, headers, rows)
    return None

def log_experiment_parameters(file_path: str, parameters: List[Dict[str, Any]]) -> None:
    """
    Log experiment parameters to a markdown file.
    Args:
        file_path: Path to the markdown file.
        parameters: List of dictionaries containing parameter details.
    Returns:
        None
    """
    mode = 'a' if os.path.exists(file_path) else 'w'
    with open(file_path, mode) as file:
        for parameter in parameters:
            file.write(f"## {parameter['name']}\n")
            file.write(f"- Description: {parameter['description']}\n")
            if 'value' in parameter:
                file.write(f"- Value: {parameter['value']}\n")
            if 'subparameters' in parameter:
                for subparam in parameter['subparameters']:
                    file.write(f"  - **{subparam['name']}**\n")
                    file.write(f"    - Description: {subparam['description']}\n")
                    file.write(f"    - Value: {subparam['value']}\n")
                file.write("\n")
    return None

def materParams(path_readme: str, notebook: str,
                mass: float, metal: str,
                metal_load: float, metal_density: float,
                support: str, support_sa: float, v_tot: float) -> None:
    """
    Log material parameters to a markdown file.
    Args:
        path_readme: Path to the markdown file.
        notebook: Notebook number.
        mass: Catalyst mass in grams.
        metal: Metal identity.
        metal_load: Weight percentage of metal used in the experiment.
        metal_density: Surface density of metal in inverse nanometers squared.
        support: Support identity.
        support_sa: Surface area of support in square meters per gram.
        v_tot: Volume of the manifold in liters.
        is_new_sample: Whether this is a new sample.
    Returns:
        None
    """
    if os.path.exists(path_readme):
        return
    parameters = [
    {
        "name": "notebook",
        "description": "Notebook number.",
        "value": notebook
    },
    {
        "name": "mass",
        "description": "Catalyst mass in grams.",
        "value": mass
    },
    {
        "name": "metal",
        "description": "Metal identity.",
        "value": metal
    },
    {
        "name": metal + "_loading",
        "description": "Weight percentage of metal used in the experiment.",
        "value": metal_load
    },
    {
        "name": metal + "_density",
        "description": "Surface density of metal in inverse nanometers squared.",
        "value": metal_density
    },
    {
        "name": "support",
        "description": "Support identity.",
        "value": support
    },
    {
        "name": support + "_SA",
        "description": "Surface area of support in square meters per gram.",
        "value": support_sa
    },
    {
        "name": "mfldVol",
        "description": "Volume of the manifold in liters",
        "value": v_tot
    },
    ]

    log_experiment_parameters(path_readme, parameters)
    return None

def increment(dir_path: str, base_folder_name: str, folder_name: str = None, new_folder: bool = False) -> tuple[int, int]:
    """
    Handles folder and file iteration logic for experiment IDs.
    Args:
        dir_path (str): Base directory path.
        base_folder_name (str): Base name for folders.
        folder_name (str, optional): Specific folder name to check. Defaults to None.
        new_folder (bool, optional): Whether to create a new folder. Defaults to False.
    Returns:
        tuple: (fld_iter, exp_iter) where fld_iter is the folder iteration and exp_iter is the experiment iteration.
    """
    if os.path.exists(dir_path):
        # List directories matching the base_folder_name pattern
        existing_folders = [folder for folder in os.listdir(dir_path) if folder.startswith(base_folder_name)]
        if folder_name:
            existing_files = glob.glob(f"{os.path.join(dir_path, folder_name)}/*")
            exp_iter = (
                max(
                    [
                        int(os.path.basename(file).split('-')[-1].split('_')[0])
                        for file in existing_files if base_folder_name in file
                    ]
                ) + 1
            )
            return 0, exp_iter

        if existing_folders:  # Send message to clear path_OpusFiles
            if new_folder:
                # OpusVertex80({'path_OpusFiles': True})
                fld_iter = (
                    max([int(folder.split('_')[-1]) for folder in existing_folders]) + 1
                )
                exp_iter = 0
                return fld_iter, exp_iter
            else:
                fld_iter = max(int(folder.split('_')[-1]) for folder in existing_folders)

            # Find last folder with the base_folder_name pattern
            last_folder = None
            filtered_folders = [folder for folder in existing_folders if base_folder_name in folder]
            if filtered_folders:
                last_folder = filtered_folders[-1]

            if last_folder and os.path.exists(os.path.join(dir_path, last_folder)):
                last_folder_path = os.path.join(dir_path, last_folder)
                existing_files = glob.glob(f"{last_folder_path}/*")
                exp_iter = 0
                if existing_files:
                    exp_iter = max(
                        [
                            int(os.path.basename(file).split('-')[-1].split('_')[0])
                            for file in existing_files if base_folder_name in file
                        ]
                    ) + 1
                return fld_iter, exp_iter
    return 0, 0

def expID(file_name: str, folder_name: str, new_sample: bool)-> tuple[str, str]:
    """
    Generates experiment file and folder names based on the current state of the directory.
    Args:
        file_name (str): Name of the experiment file.
        folder_name (str): Name of the experiment folder.
        new_sample (bool): Whether to create a new folder.
    Returns:
        tuple: (file_name, folder_name)
    """
    dir_path = "C:\\Data"
    base_folder_name = f"{notebook}_{metal}_{support}_"

    if file_name and folder_name:
        return file_name, folder_name

    elif file_name:
        fld_iter = increment(dir_path, base_folder_name)[0]
        fld_iter_str = f"{fld_iter:03}"
        folder_name = f"{notebook}_{metal}_{support}_{fld_iter_str}"

    elif folder_name:
        fld_iter_str = folder_name.split('_')[-1]
        exp_iter = increment(dir_path, base_folder_name, folder_name)[1]
        now = datetime.now()
        formatted_time = now.strftime("%Y%m%d_%H%M%S_")
        exp_iter_str = f"{exp_iter:03}"
        file_name = f"{formatted_time}{metal}_{support}_{fld_iter_str}-{exp_iter_str}"
    else:
        fld_iter, exp_iter = increment(dir_path, base_folder_name, new_folder=new_sample)
        now = datetime.now()
        formatted_time = now.strftime("%Y%m%d_%H%M%S_")
        fld_iter_str = f"{fld_iter:03}"
        exp_iter_str = f"{exp_iter:03}"

        file_name = f"{formatted_time}{metal}_{support}_{fld_iter_str}-{exp_iter_str}"
        folder_name = f"{notebook}_{metal}_{support}_{fld_iter_str}"

    return file_name, folder_name

def copy_to_share_drive(src_path: str, dest_folder: str, file_name: str, suffix: str) -> None:
    """
    Copies the file to the destination folder.
    Args:
        src_path (str): Source path of the file.
        dest_folder (str): Destination folder (e.g., 'X:\\peakFit\\{folder_name}').
        file_name (str): Name of the experiment file (without extension).
        suffix (str): Suffix to append to the file name with extension.
    Returns:
        None
    """
    # dest_path = os.path.join(dest_folder, f"{file_name}_README.md")
    dest_path = os.path.join(dest_folder, f"{file_name}_{suffix}")
    create_directory(dest_folder)

    try:
        shutil.copy(src_path, dest_path)
        time.sleep(10)
    except IOError as e:
        print(f"An error occurred while copying the file: {e}")
