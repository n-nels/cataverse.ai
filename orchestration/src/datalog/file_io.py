"""Data logging and experiment file I/O helpers for new datalog layer.

This module consolidates legacy utilities for directory creation, CSV/markdown
logging, experiment ID generation, and share-drive copy operations.
"""

from __future__ import annotations

import csv
import glob
import os
import shutil
import time
import logging
from datetime import datetime
from typing import Any

from src.core.config_loader import PathsConfig, SampleConfig


logger = logging.getLogger(__name__)


def material_prefix(sample: SampleConfig) -> str:
    """Build standard sample folder prefix."""

    return f"{sample.notebook}_{sample.metal}_{sample.support}_"


def create_directory(directory_path: str) -> None:
    """Create directory path if it does not already exist."""

    if not os.path.exists(directory_path):
        os.makedirs(directory_path)


def log_to_csv(file_path: str, headers: list[str], rows: list[list[Any]]) -> None:
    """General-purpose append-or-create CSV logger."""

    mode = "a" if os.path.exists(file_path) else "w"
    with open(file_path, mode, newline="") as csv_file:
        writer = csv.writer(csv_file)
        if mode == "w":
            writer.writerow(headers)
        writer.writerows(rows)


def log_actuator_state(
    file_path: str,
    actuator_id: str,
    act_writes: list[Any],
    pressures: list[Any],
    timestamps: list[Any],
    dithers: list[Any],
) -> None:
    """Log actuator writes/pressures/timestamps/dither values to CSV."""

    headers = ["ID", "DateTime", "ActWrite", "Pressure", "Dither"]
    rows = [
        [actuator_id, timestamps[i], act_writes[i], pressures[i], dithers[i]]
        for i in range(len(act_writes))
    ]
    log_to_csv(file_path, headers, rows)


def log_temperature(
    file_path: str,
    write_temps: list[Any],
    read_temps: list[Any],
    timestamps: list[Any],
) -> None:
    """Log target/read temperature values with timestamps to CSV."""

    headers = ["WriteTemp", "ReadTemp", "DateTime"]
    length = min(len(write_temps), len(read_temps), len(timestamps))
    rows = [[write_temps[i], read_temps[i], timestamps[i]] for i in range(length)]
    log_to_csv(file_path, headers, rows)


def log_experiment_parameters(file_path: str, parameters: list[dict[str, Any]]) -> None:
    """Append experiment parameter sections to a markdown file."""

    mode = "a" if os.path.exists(file_path) else "w"
    with open(file_path, mode) as file:
        for parameter in parameters:
            file.write(f"## {parameter['name']}\n")
            file.write(f"- Description: {parameter['description']}\n")
            if "value" in parameter:
                file.write(f"- Value: {parameter['value']}\n")
            if "subparameters" in parameter:
                for subparam in parameter["subparameters"]:
                    file.write(f"  - **{subparam['name']}**\n")
                    file.write(f"    - Description: {subparam['description']}\n")
                    file.write(f"    - Value: {subparam['value']}\n")
                file.write("\n")


def write_material_parameters(
    path_readme: str,
    notebook: str,
    mass: float,
    metal: str,
    metal_load: float,
    metal_density: float,
    support: str,
    support_sa: float,
    v_tot: float,
) -> None:
    """Write one-time material parameter markdown to README path."""

    if os.path.exists(path_readme):
        return

    parameters = [
        {
            "name": "notebook",
            "description": "Notebook number.",
            "value": notebook,
        },
        {
            "name": "mass",
            "description": "Catalyst mass in grams.",
            "value": mass,
        },
        {
            "name": "metal",
            "description": "Metal identity.",
            "value": metal,
        },
        {
            "name": metal + "_loading",
            "description": "Weight percentage of metal used in the experiment.",
            "value": metal_load,
        },
        {
            "name": metal + "_density",
            "description": "Surface density of metal in inverse nanometers squared.",
            "value": metal_density,
        },
        {
            "name": "support",
            "description": "Support identity.",
            "value": support,
        },
        {
            "name": support + "_SA",
            "description": "Surface area of support in square meters per gram.",
            "value": support_sa,
        },
        {
            "name": "mfldVol",
            "description": "Volume of the manifold in liters",
            "value": v_tot,
        },
    ]

    log_experiment_parameters(path_readme, parameters)


def _increment(
    dir_path: str,
    base_folder_name: str,
    folder_name: str | None = None,
    new_folder: bool = False,
) -> tuple[int, int]:
    """Handle folder/file iteration logic for experiment IDs."""

    if os.path.exists(dir_path):
        existing_folders = [
            folder
            for folder in os.listdir(dir_path)
            if folder.startswith(base_folder_name)
        ]
        if folder_name:
            existing_files = glob.glob(f"{os.path.join(dir_path, folder_name)}/*")
            exp_iter = (
                max(
                    [
                        int(os.path.basename(file).split("-")[-1].split("_")[0])
                        for file in existing_files
                        if base_folder_name in file
                    ]
                )
                + 1
            )
            return 0, exp_iter

        if existing_folders:
            if new_folder:
                fld_iter = (
                    max([int(folder.split("_")[-1]) for folder in existing_folders]) + 1
                )
                exp_iter = 0
                return fld_iter, exp_iter
            else:
                fld_iter = max(
                    int(folder.split("_")[-1]) for folder in existing_folders
                )

            last_folder = None
            filtered_folders = [
                folder for folder in existing_folders if base_folder_name in folder
            ]
            if filtered_folders:
                last_folder = filtered_folders[-1]

            if last_folder and os.path.exists(os.path.join(dir_path, last_folder)):
                last_folder_path = os.path.join(dir_path, last_folder)
                existing_files = glob.glob(f"{last_folder_path}/*")
                exp_iter = 0
                if existing_files:
                    exp_iter = (
                        max(
                            [
                                int(os.path.basename(file).split("-")[-1].split("_")[0])
                                for file in existing_files
                                if base_folder_name in file
                            ]
                        )
                        + 1
                    )
                return fld_iter, exp_iter
    return 0, 0


def generate_experiment_id(
    sample: SampleConfig,
    paths: PathsConfig,
    file_name: str,
    folder_name: str,
    new_sample: bool,
) -> tuple[str, str]:
    """Generate experiment file/folder names from current directory state."""

    dir_path = paths.data_directory
    base_folder_name = material_prefix(sample)

    if file_name and folder_name:
        return file_name, folder_name

    elif file_name:
        fld_iter = _increment(dir_path, base_folder_name)[0]
        fld_iter_str = f"{fld_iter:03}"
        folder_name = (
            f"{sample.notebook}_{sample.metal}_{sample.support}_{fld_iter_str}"
        )

    elif folder_name:
        fld_iter_str = folder_name.split("_")[-1]
        exp_iter = _increment(dir_path, base_folder_name, folder_name)[1]
        now = datetime.now()
        formatted_time = now.strftime("%Y%m%d_%H%M%S_")
        exp_iter_str = f"{exp_iter:03}"
        file_name = f"{formatted_time}{sample.metal}_{sample.support}_{fld_iter_str}-{exp_iter_str}"
    else:
        fld_iter, exp_iter = _increment(
            dir_path, base_folder_name, new_folder=new_sample
        )
        now = datetime.now()
        formatted_time = now.strftime("%Y%m%d_%H%M%S_")
        fld_iter_str = f"{fld_iter:03}"
        exp_iter_str = f"{exp_iter:03}"

        file_name = f"{formatted_time}{sample.metal}_{sample.support}_{fld_iter_str}-{exp_iter_str}"
        folder_name = (
            f"{sample.notebook}_{sample.metal}_{sample.support}_{fld_iter_str}"
        )

    return file_name, folder_name


def copy_to_share_drive(
    src_path: str,
    dest_folder: str,
    file_name: str,
    suffix: str,
) -> None:
    """Copy a source file to destination folder with suffixed filename."""

    dest_path = os.path.join(dest_folder, f"{file_name}_{suffix}")
    create_directory(dest_folder)

    try:
        shutil.copy(src_path, dest_path)
        time.sleep(10)
    except IOError as exc:
        logger.error("An error occurred while copying the file: %s", exc)
