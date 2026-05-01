"""Threaded mass-spectrometer logger for Extrel streaming signals.

Ports legacy Extrel stream CSV logging behavior into a reusable start/stop
class with a daemon worker thread.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from src.hardware.mass_spec import ExtrelMassSpec
from src.datalog._csv_helpers import open_csv_with_header


logger = logging.getLogger(__name__)


class MassSpecLogger:
    """Write periodic Extrel values to CSV in a background thread."""

    def __init__(
        self,
        mass_spec: ExtrelMassSpec,
        path: Path,
        stream_tags: list[str],
        start_address: int = 2,
        read_interval_s: float = 1.2,
        unit: int = 1,
    ) -> None:
        self.mass_spec = mass_spec
        self.path = path
        self.stream_tags = stream_tags
        self.start_address = start_address
        self.read_interval_s = read_interval_s
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

        tags = self.stream_tags

        csvfile, writer = open_csv_with_header(self.path, ["timestamp"] + tags)
        with csvfile:

            try:
                while not self._stop.is_set():
                    try:
                        regs = self.mass_spec.read_registers(
                            address=self.start_address,
                            count=2 * len(tags),
                            unit=self.unit,
                        )
                    except Exception as exc:
                        logger.error("Error reading from Extrel: %s", exc)
                        regs = None

                    if regs is None:
                        logger.error("read error: failed to read from Extrel")
                    else:
                        vals = [
                            self.mass_spec.decode_ieee754_cdab(
                                regs[2 * i], regs[2 * i + 1]
                            )
                            for i in range(len(tags))
                        ]

                        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                        writer.writerow([ts] + vals)
                        csvfile.flush()

                    time.sleep(self.read_interval_s)
            except KeyboardInterrupt:
                logger.info("Mass-spec logging stopped.")
