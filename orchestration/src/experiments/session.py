"""Experiment session metadata manager for the new architecture."""

from __future__ import annotations

import glob
import json
import os
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.hardware.pressure import MKSPressure
    from src.hardware.mass_spec import ExtrelMassSpec

from src.core.config_loader import PathsConfig, SampleConfig, SystemConstants
from src.datalog.file_io import (
    create_directory,
    log_experiment_parameters,
    write_material_parameters,
)
from src.datalog.pressure_logger import PressureLogger
from src.datalog.mass_spec_logger import MassSpecLogger
from src.core.physics import SystemVolumes


@dataclass
class ExperimentSession:
    """Manage experiment ID creation and experiment metadata persistence."""

    sample: SampleConfig
    volumes: SystemVolumes
    constants: SystemConstants
    paths: PathsConfig
    file_name: str | None = None
    folder_name: str | None = None
    path_readme: str | None = None
    path_exp_params: str | None = None
    path_pressure_log: str | None = None
    path_actuator_log: str | None = None
    path_ms_log: str | None = None
    counter: int = 0
    _material_metadata: dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    _filename_flags: dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    _pretreatments: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)
    _exp_conditions: dict[str, Any] = field(default_factory=dict, init=False, repr=False)

    def new_experiment(
        self,
        name: str | None = None,
        folder_name: str | None = None,
        is_new: bool = False,
        is_reference: bool = False,
        exp_type: str = "adsorption",
        counter: int = 0,
    ) -> tuple[str, str]:
        """Create/resolve experiment IDs and initialize metadata artifacts."""

        self.counter = counter

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
            is_new_arg: bool,
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
                new_folder=is_new_arg,
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
            is_new_arg=is_new,
        )

        base_dir = os.path.join(self.paths.data_directory, self.folder_name)
        create_directory(base_dir)

        self.path_readme = os.path.join(base_dir, f"{self.file_name}_README.md")
        self.path_exp_params = os.path.join(base_dir, f"{self.file_name}_expParams.json")
        self.path_pressure_log = os.path.join(base_dir, f"{self.file_name}_pressureLog.csv")
        self.path_actuator_log = os.path.join(base_dir, f"{self.file_name}_actLog.csv")
        self.path_ms_log = os.path.join(base_dir, f"{self.file_name}_msLog.csv")

        self._initialize_metadata_state(
            is_new=is_new,
            is_reference=is_reference,
            exp_type=exp_type,
        )

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

        if not self._check_line_exists("## is_reference"):
            log_experiment_parameters(
                self.path_readme,
                [
                    {
                        "name": "is_reference",
                        "description": "Whether this is a reference experiment.",
                        "value": is_reference,
                    }
                ],
            )

        if not self._check_line_exists("## is_new_sample"):
            log_experiment_parameters(
                self.path_readme,
                [
                    {
                        "name": "is_new_sample",
                        "description": "Whether this is a new sample.",
                        "value": is_new,
                    }       
                ],
            )

        if self.file_name is None or self.folder_name is None:
            raise RuntimeError("Failed to generate experiment file/folder identifiers")

        self._persist_exp_params_json()
        return self.file_name, self.folder_name

    def _initialize_metadata_state(
        self,
        *,
        is_new: bool,
        is_reference: bool,
        exp_type: str,
    ) -> None:
        self._material_metadata = {
            "notebook": self.sample.notebook,
            "mass_g": self.sample.mass_g,
            "metal": self.sample.metal,
            "metal_loading": self.sample.metal_load_wt_percent,
            "support": self.sample.support,
            "support_sa": self.sample.support_surface_area_m2_g,
            "mfldVol": self.volumes.total,
        }
        self._filename_flags = {
            "exp_type": exp_type,
            "has_csv": False,
            "is_new": is_new,
            "is_reference": is_reference,
            "exp_success": False,
        }
        self._pretreatments = []
        self._exp_conditions = {}

    def _normalize_gas_list(self, gas: Any) -> list[Any]:
        if gas is None:
            return []
        if isinstance(gas, (list, tuple)):
            return list(gas)
        return [gas]

    def _normalize_pressure_meas(
        self,
        p_gas_meas: Any,
    ) -> tuple[float | None, float | None]:
        if isinstance(p_gas_meas, (list, tuple)):
            values = list(p_gas_meas)
        else:
            values = [p_gas_meas]

        while len(values) < 2:
            values.append(None)

        return (values[0], values[1])

    def _normalize_pressure_calc(self, p_gas_calc: Any) -> list[float | None] | None:
        if p_gas_calc is None:
            return None
        if isinstance(p_gas_calc, (list, tuple)):
            return list(p_gas_calc)
        return [p_gas_calc]

    def build_exp_params_payload(self) -> dict[str, Any]:
        """Build the canonical experiment metadata payload."""

        if self.file_name is None:
            raise RuntimeError("new_experiment must be called before build_exp_params_payload")

        timestamp = datetime.strptime(self.file_name[:15], "%Y%m%d_%H%M%S")

        return {
            "base_name": self.file_name,
            "datetime": timestamp.isoformat(),
            "material": deepcopy(self._material_metadata),
            "filename_flags": deepcopy(self._filename_flags),
            "pretreatments": deepcopy(self._pretreatments),
            "exp_conditions": deepcopy(self._exp_conditions),
        }

    def _persist_exp_params_json(self) -> None:
        if not self.path_exp_params:
            raise RuntimeError("new_experiment must be called before persisting expParams")

        payload = self.build_exp_params_payload()
        target = Path(self.path_exp_params)
        temp_target = target.with_suffix(target.suffix + ".tmp")
        with temp_target.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)
            file.write("\n")
        temp_target.replace(target)

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
        p_gas_meas: tuple[float, float] | tuple[float, Any],
        t_cell: float,
        rate: float,
        duration: float,
        p_gas_calc: float | tuple[float | None, ...] | None = None,
        chiller_state: bool | None = None,
    ) -> None:
        """Append one pretreatment block to README metadata."""

        if not self.path_readme:
            raise RuntimeError("new_experiment must be called before log_pretreatment")

        self.counter += 1
        header = f"## pretreatment_{self.counter}"
        if self._check_line_exists(header):
            return

        pressure_meas_mfld, pressure_meas_cell = self._normalize_pressure_meas(p_gas_meas)
        self._pretreatments.append(
            {
                "step_index": self.counter,
                "gas": self._normalize_gas_list(gas),
                "pressure_meas_mfld": pressure_meas_mfld,
                "pressure_meas_cell": pressure_meas_cell,
                "pressure_calc": self._normalize_pressure_calc(p_gas_calc),
                "temp": float(t_cell),
                "rate": float(rate),
                "duration": float(duration),
                "chiller": chiller_state,
            }
        )

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
                        "description": "Measured pressure of gas in Torr (p_mfld, p_cell).",
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
        self._persist_exp_params_json()

    def log_experimental_parameters(
        self,
        gas: str | tuple[str, str],
        p_gas_meas: tuple[float, float] | tuple[float, Any],
        t_cell: float,
        p_gas_calc: float | tuple[float | None, ...] | None,
        chiller_state: bool | None = None,
    ) -> None:
        """Append experiment-gas parameter block to README metadata."""

        if not self.path_readme:
            raise RuntimeError(
                "new_experiment must be called before log_experimental_parameters"
            )

        self.counter = 0
        if self._exp_conditions or self._check_line_exists("## exp_gas"):
            return

        pressure_meas_mfld, pressure_meas_cell = self._normalize_pressure_meas(p_gas_meas)
        self._exp_conditions = {
            "gas": self._normalize_gas_list(gas),
            "pressure_meas_mfld": pressure_meas_mfld,
            "pressure_meas_cell": pressure_meas_cell,
            "pressure_calc": self._normalize_pressure_calc(p_gas_calc),
            "temp": float(t_cell),
            "chiller": chiller_state,
        }

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
        self._persist_exp_params_json()

    def mark_success(self, success: bool = True) -> None:
        """Set/append ``exp_success`` field in README metadata."""

        if not self.path_readme:
            raise RuntimeError("new_experiment must be called before mark_success")

        self._filename_flags["exp_success"] = success

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
            self._persist_exp_params_json()
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

        self._persist_exp_params_json()


    def start_pressure_log(
        self,
        pressure: MKSPressure,
        p_mfld_initial: float,
        p_cell_initial: float,
    ) -> PressureLogger:
        """Construct, start, and return a PressureLogger for this session."""

        pressure_logger = PressureLogger(
            pressure=pressure,
            volumes=self.volumes,
            sample=self.sample,
            constants=self.constants,
            path=self.path_pressure_log,
            p_mfld_initial=p_mfld_initial,
            p_cell_initial=p_cell_initial,
        )
        pressure_logger.start()
        return pressure_logger

    def start_mass_spec_log(
        self,
        mass_spec: ExtrelMassSpec,
        stream_tags: list[str],
    ) -> MassSpecLogger:
        """Construct, start, and return a MassSpecLogger for this session."""

        ms_logger = MassSpecLogger(
            mass_spec=mass_spec,
            path=Path(self.path_ms_log),
            stream_tags=stream_tags,
        )
        ms_logger.start()
        return ms_logger
