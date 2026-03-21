"""Threaded temperature logger for IR temperature monitoring.

Ports legacy temperature CSV logging behavior into a reusable start/stop class
with a daemon worker thread.
"""

from __future__ import annotations

import csv
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from src.hardware.temperature import WatlowTemperature


logger = logging.getLogger(__name__)


class TemperatureLogger:
    """Write periodic temperature readings to CSV in a background thread."""

    def __init__(
        self,
        temperature: WatlowTemperature,
        path: Path,
        read_interval_s: int = 5,
    ) -> None:
        self.temperature = temperature
        self.path = path
        self.read_interval_s = read_interval_s

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start temperature logging daemon thread if not already running."""

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
        """Worker loop that appends timestamp/temperature rows to CSV."""

        file_exists = self.path.exists()
        with self.path.open("a", newline="") as file:
            writer = csv.writer(file)
            if not file_exists:
                writer.writerow(["timestamp", "temperature"])

            try:
                while not self._stop.is_set():
                    try:
                        dt = datetime.now()
                        temp = self.temperature.read_temperature()
                    except Exception as exc:
                        logger.error("Error reading temperature: %s", exc)
                        dt, temp = datetime.now(), None

                    writer.writerow([dt, temp])
                    file.flush()
                    time.sleep(self.read_interval_s)
            except KeyboardInterrupt:
                logger.info("Temperature logging stopped.")
