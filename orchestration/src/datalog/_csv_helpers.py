"""Shared CSV helpers for threaded loggers."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import IO


def open_csv_with_header(
    path: Path, headers: list[str]
) -> tuple[IO[str], csv.writer]:
    """Open *path* for appending; write *headers* if the file is new.

    Returns the open file handle and a ``csv.writer`` bound to it.  The
    caller is responsible for closing the file (typically via a ``with``
    block wrapping the returned handle).
    """

    file_exists = path.exists()
    handle = path.open("a", newline="")
    writer = csv.writer(handle)
    if not file_exists:
        writer.writerow(headers)
    return handle, writer
