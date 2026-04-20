"""Threaded mass-spectrometer logger for Extrel streaming signals.

Ports legacy Extrel stream CSV logging behavior into a reusable start/stop
class with a daemon worker thread.
"""

from __future__ import annotations

import csv
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from src.hardware.mass_spec import ExtrelMassSpec


logger = logging.getLogger(__name__)


class MassSpecLogger:
    """Write periodic Extrel values to CSV in a background thread."""

    def __init__(
        self,
        mass_spec: ExtrelMassSpec,
        path: Path,
        start_address: int = 2,
        poll_interval_s: float = 1.2,
        unit: int = 1,
    ) -> None:
        self.mass_spec = mass_spec
        self.path = path
        self.start_address = start_address
        self.poll_interval_s = poll_interval_s
        self.unit = unit

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start mass-spec logging daemon thread if not already running."""

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
        """Worker loop that appends decoded Extrel values to CSV."""

        tags = ["V1_I_28", "V1_I_29", "V1_I_44", "V1_I_45"]
        file_exists = self.path.exists()

        with self.path.open("a", newline="") as csvfile:
            writer = csv.writer(csvfile)
            if not file_exists:
                writer.writerow(["timestamp"] + tags)

            while not self._stop.is_set():
                regs = self.mass_spec.read_registers(
                    address=self.start_address,
                    count=8,
                    unit=self.unit,
                )

                if regs is None:
                    logger.info("read error: failed to read from Extrel")
                else:
                    vals = [
                        self.mass_spec.decode_ieee754_cdab(regs[0], regs[1]),
                        self.mass_spec.decode_ieee754_cdab(regs[2], regs[3]),
                        self.mass_spec.decode_ieee754_cdab(regs[4], regs[5]),
                        self.mass_spec.decode_ieee754_cdab(regs[6], regs[7]),
                    ]

                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    writer.writerow([ts] + vals)
                    csvfile.flush()

                time.sleep(self.poll_interval_s)
