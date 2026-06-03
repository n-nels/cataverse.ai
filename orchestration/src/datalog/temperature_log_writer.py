"""CSV writer for temperature ramp/hold logs.

Replaces the module-level ``dir_tempLog`` / ``path_tempLog`` globals and the
inline CSV writes that were scattered across ``TemperatureController.watlow()``.

The writer is constructed once per ``watlow()`` invocation and passed into the
ramp, cool, and hold helpers.  When ``filename`` is ``None`` all write methods
are silent no-ops, which eliminates the uninitialised-global bug that existed
in the legacy code.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime

from src.datalog.file_io import create_directory, log_to_csv


logger = logging.getLogger(__name__)


class TemperatureLogWriter:
    """Owns path construction, directory creation, and CSV row appending for
    temperature logs produced during a single ``watlow()`` call.

    Parameters
    ----------
    data_directory:
        Root data directory (``PathsConfig.data_directory``).
    filename:
        Experiment file stem, or ``None`` to disable logging.
    foldername:
        Subfolder name under *data_directory*.
    """

    _HEADERS = ["WriteTemp", "ReadTemp", "DateTime"]

    def __init__(
        self,
        data_directory: str,
        filename: str | None,
        foldername: str | None,
    ) -> None:
        if filename is None:
            self._file_path: str | None = None
            return

        directory = os.path.join(data_directory, str(foldername))
        create_directory(directory)
        self._file_path = os.path.join(directory, f"{filename}_tempLog.csv")

    @property
    def enabled(self) -> bool:
        """Return ``True`` when a valid file path is configured."""
        return self._file_path is not None

    def append_row(
        self,
        setpoint: float,
        actual: float,
        timestamp: datetime | None = None,
    ) -> None:
        """Append a single temperature row to the CSV.

        Used for both ramp-phase and hold-phase temperature logging.
        """
        if self._file_path is None:
            return

        if timestamp is None:
            timestamp = datetime.now()

        log_to_csv(self._file_path, self._HEADERS, [[setpoint, actual, timestamp]])
