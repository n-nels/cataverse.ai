"""Experiment session metadata manager for the new architecture.

This module provides a typed session object that replaces legacy
``experiment_parameters`` while preserving output structure and README content
format through datalog file I/O helpers.
"""

from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.core.config_loader import PathsConfig, SampleConfig
from src.datalog.file_io import (
    create_directory,
    log_experiment_parameters,
    write_material_parameters,
)
from src.core.physics import SystemVolumes


@dataclass
class ExperimentSession:
    """Manage experiment ID creation and README parameter logging."""

    sample: SampleConfig
    volumes: SystemVolumes
    paths: PathsConfig
    file_name: str | None = None
    folder_name: str | None = None
    path_readme: str | None = None
    path_pressure_log: str | None = None
    path_ms_log: str | None = None
    counter: int = 0

    def new_experiment(
        self,
        name: str | None = None,
        folder_name: str | None = None,
        new_sample: bool = False,
    ) -> tuple[str, str]:
        """Create/resolve experiment IDs and initialize README/material metadata."""

        self.counter = 0

        def increment(
            dir_path: str,
            base_folder_name: str,
            folder_name_arg: str | None = None,
            new_folder: bool = False,
        ) -> tuple[int, int]:
            if os.path.exists(dir_path):
                existing_folders = [
                    folder
                    for folder in os.listdir(dir_path)
                    if folder.startswith(base_folder_name)
                ]
                if folder_name_arg:
                    existing_files = glob.glob(f"{os.path.join(dir_path, folder_name_arg)}/*")
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
                            max([int(folder.split("_")[-1]) for folder in existing_folders])
                            + 1
                        )
                        exp_iter = 0
                        return fld_iter, exp_iter
                    else:
                        fld_iter = max(
                            int(folder.split("_")[-1]) for folder in existing_folders
                        )

                    last_folder = None
                    filtered_folders = [
                        folder
                        for folder in existing_folders
                        if base_folder_name in folder
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

        def experiment_id(
            file_name: str | None,
            folder_name_arg: str | None,
            new_sample_arg: bool,
        ) -> tuple[str, str]:
            dir_path = self.paths.data_directory
            base_folder_name = (
                f"{self.sample.notebook}_{self.sample.metal}_{self.sample.support}_"
            )

            if file_name and folder_name_arg:
                return file_name, folder_name_arg

            elif file_name:
                fld_iter = increment(dir_path, base_folder_name)[0]
                fld_iter_str = f"{fld_iter:03}"
                folder = (
                    f"{self.sample.notebook}_{self.sample.metal}_{self.sample.support}_{fld_iter_str}"
                )
                return file_name, folder

            elif folder_name_arg:
                fld_iter_str = folder_name_arg.split("_")[-1]
                exp_iter = increment(dir_path, base_folder_name, folder_name_arg)[1]
                now = datetime.now()
                formatted_time = now.strftime("%Y%m%d_%H%M%S_")
                exp_iter_str = f"{exp_iter:03}"
                file_value = (
                    f"{formatted_time}{self.sample.metal}_{self.sample.support}_{fld_iter_str}-{exp_iter_str}"
                )
                return file_value, folder_name_arg

            fld_iter, exp_iter = increment(
                dir_path,
                base_folder_name,
                new_folder=new_sample_arg,
            )
            now = datetime.now()
            formatted_time = now.strftime("%Y%m%d_%H%M%S_")
            fld_iter_str = f"{fld_iter:03}"
            exp_iter_str = f"{exp_iter:03}"

            file_value = (
                f"{formatted_time}{self.sample.metal}_{self.sample.support}_{fld_iter_str}-{exp_iter_str}"
            )
            folder_value = (
                f"{self.sample.notebook}_{self.sample.metal}_{self.sample.support}_{fld_iter_str}"
            )
            return file_value, folder_value

        self.file_name, self.folder_name = experiment_id(
            file_name=name,
            folder_name_arg=folder_name,
            new_sample_arg=new_sample,
        )

        base_dir = os.path.join(self.paths.data_directory, self.folder_name)
        create_directory(base_dir)

        self.path_readme = os.path.join(base_dir, f"{self.file_name}_README.md")
        self.path_pressure_log = os.path.join(base_dir, f"{self.file_name}_pressureLog.csv")
        self.path_actuator_log = os.path.join(base_dir, f"{self.file_name}_actLog.csv")
        self.path_ms_log = os.path.join(base_dir, f"{self.file_name}_msLog.csv")

        metal_density = (
            (self.sample.metal_load_wt_percent / 100)
            * (1 / self.sample.metal_molar_mass_g_mol)
            * (6.023e23)
            * (1 / self.sample.support_surface_area_m2_g)
            * (1e-9**2)
        )

        write_material_parameters(
            path_readme=self.path_readme,
            notebook=self.sample.notebook,
            mass=self.sample.mass_g,
            metal=self.sample.metal,
            metal_load=self.sample.metal_load_wt_percent,
            metal_density=metal_density,
            support=self.sample.support,
            support_sa=self.sample.support_surface_area_m2_g,
            v_tot=self.volumes.total,
        )
        if not self._check_line_exists("## exp_success"):
            log_experiment_parameters(
                self.path_readme,
                [
                    {
                        "name": "exp_success",
                        "description": "Success status of the experiment.",
                        "value": False,
                    }
                ],
            )

        if self.file_name is None or self.folder_name is None:
            raise RuntimeError("Failed to generate experiment file/folder identifiers")
        return self.file_name, self.folder_name

    def _check_line_exists(self, header: str) -> bool:
        if not self.path_readme or not os.path.exists(self.path_readme):
            return False

        with open(self.path_readme, "r") as file:
            for line in file:
                if line.strip() == header:
                    return True
        return False

    def log_pretreatment(
        self,
        gas: Any,
        p_gas_meas: tuple[float, float],
        t_cell: float,
        rate: float,
        duration: float,
        p_gas_calc: float | None = None,
        chiller_state: bool | None = None,
    ) -> None:
        """Append one pretreatment block to README metadata."""

        if not self.path_readme:
            raise RuntimeError("new_experiment must be called before log_pretreatment")

        self.counter += 1
        header = f"## pretreatment_{self.counter}"
        if self._check_line_exists(header):
            return

        parameters = [
            {
                "name": f"pretreatment_{self.counter}",
                "description": "Parameters for pretreatment steps...",
                "subparameters": [
                    {
                        "name": f"pre_gas_{self.counter}",
                        "description": "Gas identity",
                        "value": gas,
                    },
                    {
                        "name": f"pre_pressure_meas_{self.counter}",
                        "description": "Measured pressure of gas in Torr.",
                        "value": p_gas_meas,
                    },
                    {
                        "name": f"pre_pressure_calc_{self.counter}",
                        "description": "Calculated pressure of gas in Torr.",
                        "value": p_gas_calc,
                    },
                    {
                        "name": f"pre_temp_{self.counter}",
                        "description": "Temperature of cell in Celsius.",
                        "value": t_cell,
                    },
                    {
                        "name": f"pre_rate_{self.counter}",
                        "description": "Heating rate in Celsius per minute",
                        "value": rate,
                    },
                    {
                        "name": f"pre_duration_{self.counter}",
                        "description": "Duration of pretreatment step in hours.",
                        "value": duration,
                    },
                    {
                        "name": f"pre_chiller_{self.counter}",
                        "description": "Chiller state during pretreatment.",
                        "value": chiller_state,
                    },
                ],
            }
        ]

        log_experiment_parameters(self.path_readme, parameters)

    def log_experimental_parameters(
        self,
        gas: str,
        p_gas_meas: tuple[float, float],
        t_cell: float,
        p_gas_calc: float,
        chiller_state: bool | None = None,
    ) -> None:
        """Append experiment-gas parameter block to README metadata."""

        if not self.path_readme:
            raise RuntimeError(
                "new_experiment must be called before log_experimental_parameters"
            )

        self.counter = 0
        if self._check_line_exists("## exp_gas"):
            return

        parameters = [
            {"name": "exp_gas", "description": "Gas identity.", "value": gas},
            {
                "name": "exp_pressure_meas",
                "description": "Pressure of gas in Torr as (p_mfld, p_cell).",
                "value": p_gas_meas,
            },
            {
                "name": "exp_pressure_calc",
                "description": "Pressure of gas in Torr.",
                "value": p_gas_calc,
            },
            {
                "name": "exp_temp",
                "description": "Temperature of cell in Celsius.",
                "value": t_cell,
            },
            {
                "name": "exp_chiller",
                "description": "Chiller state during pretreatment.",
                "value": chiller_state,
            },
        ]

        log_experiment_parameters(self.path_readme, parameters)

    def mark_success(self, success: bool = True) -> None:
        """Set/append ``exp_success`` field in README metadata."""

        if not self.path_readme:
            raise RuntimeError("new_experiment must be called before mark_success")

        if not self._check_line_exists("## exp_success"):
            log_experiment_parameters(
                self.path_readme,
                [
                    {
                        "name": "exp_success",
                        "description": "Success status of the experiment.",
                        "value": success,
                    }
                ],
            )
            return

        with open(self.path_readme, "r") as file:
            lines = file.readlines()

        with open(self.path_readme, "w") as file:
            found_header = False

            for line in lines:
                if line.strip().startswith("## exp_success"):
                    found_header = True
                    file.write(line)
                    continue

                if found_header and line.strip().startswith("- Value:"):
                    file.write(f"- Value: {str(success)}\n")
                    found_header = False
                    continue

                file.write(line)

    def is_new_sample_experiment(self) -> None: # [fix] this seems fragile!
        """Append ``is_new_sample`` metadata field using legacy share-drive rule."""

        if not self.path_readme or not self.folder_name:
            return

        directory_path = os.path.join(self.paths.share_drive_peak_fit_root, self.folder_name)
        carbonyl_files = glob.glob(os.path.join(directory_path, "*_CarbonylPeakArea.csv"))

        if len(carbonyl_files) != 1:
            is_new_sample = False
        else:
            with open(self.path_readme, "r", encoding="utf-8") as file:
                content = file.read()

            pattern = r"##\s*exp_success.*?-\s*Value:\s*(True|true)"
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            is_new_sample = match is not None

        log_experiment_parameters(
            self.path_readme,
            [
                {
                    "name": "is_new_sample",
                    "description": "Whether this is a new sample.",
                    "value": is_new_sample,
                }
            ],
        )
