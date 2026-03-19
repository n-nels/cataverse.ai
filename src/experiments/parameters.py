"""Experiment parameter persistence and metadata helpers."""

import csv
import glob
import os
import re
from typing import Any, Optional

from ..core import get_logger
from ..core.config import (
    autonomous_parameters_directory,
    data_directory,
    share_drive_peak_fit_root,
)
from ..utils.data_logging import (
    create_directory,
    expID,
    log_experiment_parameters,
    materParams,
)


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


class experiment_parameters:
    """Experiment metadata helper for README and parameter logging."""

    def __init__(
        self,
        notebook: str,
        mass: float,
        metal: str,
        metal_load: float,
        metal_density: float,
        support: str,
        support_sa: float,
        v_tot: float,
    ) -> None:
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
        self.path_ms_log = None

    def experiment_id(
        self,
        file_name: Optional[str] = None,
        folder_name: Optional[str] = None,
        new_sample: bool = False,
        counter: int = 0,
    ) -> None:
        self.file_name, self.folder_name = expID(file_name, folder_name, new_sample)
        base_dir = os.path.join(data_directory, self.folder_name)
        create_directory(base_dir)
        self.path_readme = os.path.join(base_dir, f"{self.file_name}_README.md")
        self.path_pressure_log = os.path.join(base_dir, f"{self.file_name}_pressureLog.csv")
        self.path_ms_log = os.path.join(base_dir, f"{self.file_name}_msLog.csv")
        self.counter = counter

    def material_parameters(self) -> None:
        materParams(
            path_readme=self.path_readme,
            notebook=self.notebook,
            mass=self.mass,
            metal=self.metal,
            metal_load=self.metal_load,
            metal_density=self.metal_density,
            support=self.support,
            support_sa=self.support_sa,
            v_tot=self.v_tot,
        )

        self.experiment_success(False)

    def check_line_exists(self) -> bool:
        if os.path.exists(self.path_readme):
            with open(self.path_readme, "r") as file:
                for line in file:
                    if line.strip() == f"## pretreatment_{self.counter}":
                        return True
                    if (line.strip() == "## exp_gas") and self.counter == 0:
                        return True

        return False

    def pretreatment_parameters(
        self,
        gas: str,
        p_gas_meas: tuple[float, float],
        t_cell: float,
        rate: int,
        duration: float,
        p_gas_calc: float = None,
        chiller_state: bool = None,
    ) -> None:
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

    def experimental_parameters(
        self,
        gas: str,
        p_gas_meas: tuple[float, float],
        t_cell: float,
        p_gas_calc: float,
        chiller_state: bool = None,
    ) -> None:
        self.counter = 0
        if self.check_line_exists():
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

    def experiment_success(self, success: bool) -> None:
        if self.check_line_exists():
            return
        parameters = [
            {
                "name": "exp_success",
                "description": "Success status of the experiment.",
                "value": success,
            }
        ]
        log_experiment_parameters(self.path_readme, parameters)

    def update_experiment_success(self, success: bool) -> None:
        if not os.path.exists(self.path_readme):
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

    def check_exp_success(self, readme_path: str) -> bool:
        try:
            if not os.path.exists(readme_path):
                return False

            with open(readme_path, "r", encoding="utf-8") as file:
                content = file.read()

            pattern = r"##\s*exp_success.*?-\s*Value:\s*(True|true)"
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)

            return match is not None

        except Exception as e:
            print(f"Error reading README file: {e}")
            return False

    def import_experimental_parameters(self, csvfile: str) -> Optional[dict]:
        """Imports experimental parameters from a CSV file for autonomous experiments."""

        def clean_gas_string(val):
            if isinstance(val, str):
                match = re.match(r"\(([^,]+),\)", val)
                if match:
                    return match.group(1)
            return val

        path = os.path.join(autonomous_parameters_directory, csvfile)

        with open(path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                experiment_dict = {k: clean_gas_string(v) for k, v in row.items()}
                return experiment_dict
        return None

    def is_reference_experiment(self, val: bool) -> None:
        parameters = [
            {
                "name": "is_reference",
                "description": "Whether this is a reference experiment.",
                "value": val,
            },
        ]
        log_experiment_parameters(self.path_readme, parameters)

    def is_new_sample_experiment(self) -> None:
        directory_path = os.path.join(share_drive_peak_fit_root, self.folder_name)
        carbonyl_files = glob.glob(os.path.join(directory_path, "*_CarbonylPeakArea.csv"))

        if len(carbonyl_files) != 1:
            is_new_sample = False
        else:
            is_new_sample = self.check_exp_success(self.path_readme)

        parameters = [
            {
                "name": "is_new_sample",
                "description": "Whether this is a new sample.",
                "value": is_new_sample,
            },
        ]

        log_experiment_parameters(self.path_readme, parameters)
