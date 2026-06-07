"""Data logging file I/O helpers.

This module provides CSV writing primitives used by the datalog
layer: directory creation, general-purpose CSV append, actuator/temperature
CSV logging.

Session-bookkeeping functions (experiment ID generation, metadata persistence)
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



