"""Threaded pressure logger for manifold/cell pressure monitoring.

Ports legacy pressure CSV logging behavior from instrument operations into a
reusable start/stop class with a daemon worker thread.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from src.hardware.pressure import MKSPressure
from src.core.config_loader import SampleConfig, SystemConstants
from src.core.physics import (
    SystemVolumes,
    compute_pressure_metrics,
)
from src.datalog._csv_helpers import open_csv_with_header


logger = logging.getLogger(__name__)


class PressureLogger:
    """Write periodic pressure-derived metrics to CSV in a background thread."""

    def __init__(
        self,
        pressure: MKSPressure,
        volumes: SystemVolumes,
        sample: SampleConfig,
        constants: SystemConstants,
        path: Path,
        p_mfld_initial: float,
        p_cell_initial: float,
        read_interval_s: float = 5,
    ) -> None:
        self.pressure = pressure
        self.volumes = volumes
        self.sample = sample
        self.constants = constants
        self.path = Path(path)
        self.p_mfld_initial = p_mfld_initial
        self.p_cell_initial = p_cell_initial
        self.read_interval_s = read_interval_s

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start pressure logging daemon thread if not already running."""

        if self._thread is not None and self._thread.is_alive():
            return

        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal logging thread to stop and wait for thread exit."""

        self._stop.set()
        if self._thread is not None:
            self._thread.join()

    def _run(self) -> None:
        """Worker loop that appends pressure and derived metrics to CSV."""

        source_volume_l = self.volumes.source_m1m2m3
        total_volume_l = self.volumes.total
        cell_volume_l = self.volumes.cell
        gas_constant = self.constants.gas_constant
        temperature_k = self.constants.manifold_temperature_k

        t0 = None
        _HEADERS = [
            "timestamp",
            "p_mfld",
            "p_cell",
            "relative_time_s",
            "amount_adsorbed_umol/g",
            "apparent_conversion",
            "apparent_coverage",
        ]
        file, writer = open_csv_with_header(self.path, _HEADERS)
        with file:

            try:
                while not self._stop.is_set():
                    try:
                        dt, p_mfld, p_cell = self.pressure.read()
                    except Exception as exc:
                        logger.error("Error reading pressure: %s", exc)
                        dt, p_mfld, p_cell = None, None, None

                    if t0 is None and dt is not None:
                        t0 = dt

                    if p_mfld is not None and dt is not None:
                        metrics = compute_pressure_metrics(
                            p_mfld=p_mfld,
                            dt=dt,
                            t0=t0,
                            p_mfld_initial=self.p_mfld_initial,
                            p_cell_initial=self.p_cell_initial,
                            source_volume_l=source_volume_l,
                            total_volume_l=total_volume_l,
                            cell_volume_l=cell_volume_l,
                            mass_g=self.sample.mass_g,
                            metal_load_wt_percent=self.sample.metal_load_wt_percent,
                            metal_molar_mass_g_mol=self.sample.metal_molar_mass_g_mol,
                            temperature_k=temperature_k,
                            gas_constant=gas_constant,
                        )
                        writer.writerow(
                            [
                                dt,
                                p_mfld,
                                p_cell,
                                metrics.relative_time_s,
                                metrics.amount_adsorbed_umol_per_g,
                                metrics.apparent_conversion,
                                metrics.apparent_coverage,
                            ]
                        )
                    else:
                        writer.writerow([dt, p_mfld, p_cell, None, None, None, None])

                    file.flush()
                    time.sleep(self.read_interval_s)
            except KeyboardInterrupt:
                logger.info("Pressure logging stopped.")
