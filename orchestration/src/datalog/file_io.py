"""Data logging file I/O helpers.

This module provides CSV and markdown writing primitives used by the datalog
layer: directory creation, general-purpose CSV append, actuator/temperature
CSV logging, and markdown parameter sections for experiment READMEs.

Session-bookkeeping functions (experiment ID generation, share-drive copies)
live in ``experiments.session``.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


def create_directory(directory_path: str | Path) -> None:
    """Create directory path if it does not already exist."""

    Path(directory_path).mkdir(parents=True, exist_ok=True)


def log_to_csv(
    file_path: str | Path, headers: list[str], rows: list[list[Any]]
) -> None:
    """General-purpose append-or-create CSV logger."""

    p = Path(file_path)
    mode = "a" if p.exists() else "w"
    with p.open(mode, newline="") as csv_file:
        writer = csv.writer(csv_file)
        if mode == "w":
            writer.writerow(headers)
        writer.writerows(rows)


def log_actuator_state(
    file_path: str | Path,
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
    file_path: str | Path,
    write_temps: list[Any],
    read_temps: list[Any],
    timestamps: list[Any],
) -> None:
    """Log target/read temperature values with timestamps to CSV."""

    headers = ["WriteTemp", "ReadTemp", "DateTime"]
    length = min(len(write_temps), len(read_temps), len(timestamps))
    rows = [[write_temps[i], read_temps[i], timestamps[i]] for i in range(length)]
    log_to_csv(file_path, headers, rows)


def log_experiment_parameters(
    file_path: str | Path, parameters: list[dict[str, Any]]
) -> None:
    """Append experiment parameter sections to a markdown file."""

    p = Path(file_path)
    mode = "a" if p.exists() else "w"
    with p.open(mode) as file:
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
    path_readme: str | Path,
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

    if Path(path_readme).exists():
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
