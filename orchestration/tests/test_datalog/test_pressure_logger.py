from __future__ import annotations

import csv
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from src.datalog.pressure_logger import PressureLogger
from src.core.config_loader import SampleConfig, SystemConstants
from src.core.physics import SystemVolumes


def _read_csv_rows(path: Path) -> list[list[str]]:
    with path.open("r", newline="") as f:
        return list(csv.reader(f))


def test_pressure_logger_writes_csv_and_starts_stops_cleanly(tmp_path: Path) -> None:
    log_path = tmp_path / "pressure_log.csv"

    pressure = MagicMock()
    pressure.read.side_effect = [
        (datetime.now(), 1.00, 0.10),
        (datetime.now(), 0.98, 0.10),
        (datetime.now(), 0.97, 0.10),
    ]

    volumes = SystemVolumes(
        vessel=0.0119913,
        valve=0.000152,
        cell=0.03381,
        manifold_m1m2=0.078862,
        manifold_m1m2m3=0.11116,
        tube_50ml=0.05643,
        flask=1.004,
    )

    sample = SampleConfig(
        notebook="NB001",
        metal="Pd",
        support="Al2O3",
        mass_g=0.0164,
        metal_load_wt_percent=0.04983,
        support_surface_area_m2_g=100.0,
    )

    constants = SystemConstants(
        gas_constant=62.363577,
        manifold_temperature_k=298.15,
        vessel_volume_l=0.0119913,
        valve_volume_l=0.000152,
        cell_volume_l=0.03381,
        manifold_m1m2_volume_l=0.078862,
        manifold_m1m2m3_volume_l=0.11116,
        tube_50ml_volume_l=0.05643,
        flask_volume_l=1.004,
    )

    logger = PressureLogger(
        pressure=pressure,
        volumes=volumes,
        sample=sample,
        constants=constants,
        path=log_path,
        p_mfld_initial=1.0,
        p_cell_initial=0.0,
        read_interval_s=0.01,
    )

    logger.start()
    while pressure.read.call_count < 3:
        time.sleep(0.005)

    assert logger._thread is not None
    assert logger._thread.is_alive()

    logger.stop()
    assert logger._thread is not None
    assert not logger._thread.is_alive()

    assert log_path.exists()
    rows = _read_csv_rows(log_path)
    assert rows[0] == [
        "timestamp",
        "p_mfld",
        "p_cell",
        "relative_time_s",
        "amount_adsorbed_umol/g",
        "apparent_conversion",
        "apparent_coverage",
    ]
    assert len(rows) >= 2
    assert pressure.read.call_count >= 3

    first_data_row = rows[1]
    assert len(first_data_row) == 7
    assert first_data_row[1] == "1.0"
    assert first_data_row[2] == "0.1"
