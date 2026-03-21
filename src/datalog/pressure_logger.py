"""Threaded pressure logger for manifold/cell pressure monitoring.

Ports legacy pressure CSV logging behavior from instrument operations into a
reusable start/stop class with a daemon worker thread.
"""

from __future__ import annotations

import csv
import logging
import threading
import time
from pathlib import Path
from typing import cast

from src.core.config import R, t_mfld
from src.hardware.pressure import MKSPressure
from src.physics import SystemVolumes, amount_adsorbed


logger = logging.getLogger(__name__)


class PressureLogger:
    """Write periodic pressure-derived metrics to CSV in a background thread."""

    def __init__(
        self,
        pressure: MKSPressure,
        physics: SystemVolumes,
        path: Path,
        p_mfld_initial: float,
        p_cell_initial: float,
        mass_g: float,
        metal_load_wt_percent: float,
        metal_molar_mass_g_mol: float = 106.42,
        temperature_k: float = t_mfld,
        read_interval_s: int = 5,
    ) -> None:
        self.pressure = pressure
        self.physics = physics
        self.path = path
        self.p_mfld_initial = p_mfld_initial
        self.p_cell_initial = p_cell_initial
        self.mass_g = mass_g
        self.metal_load_wt_percent = metal_load_wt_percent
        self.metal_molar_mass_g_mol = metal_molar_mass_g_mol
        self.temperature_k = temperature_k
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

        file_exists = self.path.exists()
        source_volume_l = self.physics.manifold_m1m2m3 + self.physics.tube_50ml
        total_volume_l = self.physics.total

        n_initial = (self.p_mfld_initial * source_volume_l) / (R * self.temperature_k)  # mol
        p_initial = (
            (self.p_mfld_initial * source_volume_l)
            + (self.p_cell_initial * self.physics.cell)
        ) / total_volume_l
        pd_umol_g = (
            (self.metal_load_wt_percent / 100)
            * (1 / self.metal_molar_mass_g_mol)
            * 1e6
        )

        t0 = None
        with self.path.open("a", newline="") as file:
            writer = csv.writer(file)
            if not file_exists:
                writer.writerow(
                    [
                        "timestamp",
                        "p_mfld",
                        "p_cell",
                        "relative_time_s",
                        "amount_adsorbed_umol/g",
                        "apparent_conversion",
                        "apparent_coverage",
                    ]
                )

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
                        p_mfld_value = cast(float, p_mfld)
                        relative_time_s = (dt - t0).total_seconds() if t0 else None

                        # Preserve legacy formula while centralizing adsorption math in physics.py.
                        n_adsorbed_initial = (p_initial * total_volume_l) / (
                            R * self.temperature_k
                        )
                        amount_adsorbed_umol_g = amount_adsorbed(
                            n_initial_mol=n_adsorbed_initial,
                            pressure_equilibrium_torr=p_mfld_value,
                            total_volume_l=total_volume_l,
                            temperature_k=self.temperature_k,
                            mass_g=self.mass_g,
                            gas_constant=R,
                        )

                        n_current = p_mfld_value * total_volume_l / (R * self.temperature_k)
                        apparent_conversion = (n_initial - n_current) / n_initial * 100
                        apparent_coverage = amount_adsorbed_umol_g / pd_umol_g
                    else:
                        relative_time_s = None
                        amount_adsorbed_umol_g = None
                        apparent_conversion = None
                        apparent_coverage = None

                    writer.writerow(
                        [
                            dt,
                            p_mfld,
                            p_cell,
                            relative_time_s,
                            amount_adsorbed_umol_g,
                            apparent_conversion,
                            apparent_coverage,
                        ]
                    )
                    file.flush()
                    time.sleep(self.read_interval_s)
            except KeyboardInterrupt:
                logger.info("Pressure logging stopped.")
