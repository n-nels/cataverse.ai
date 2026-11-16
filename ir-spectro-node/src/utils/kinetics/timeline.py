"""Per-spectrum time axis for one measurement, independent of which fits exist.

Cumulative ``Time (s)`` is a running sum of ``Time_Delta (s)`` over a delta
group. Taking ``Time_Delta`` from params rows (as live and the refit both do)
means a spectrum with no row -- a failed fit, or one live never recorded --
silently drops its time step and shifts every later time in that group. The
timeline instead lists every subIFG spectrum and derives its ``Time_Delta``
from the subIFG log + exp params, with the same ``resolve_time_delta`` live uses.

Spectra are every ``_delta`` entry in the subIFG log (plus any extra file on
disk): the log is the record of every subtraction performed, even when a file
is no longer on disk. As in the refit (``src/utils/ir_fitting``), ``isoX``
files are excluded and ``manually_skip_files`` is applied.
"""

from __future__ import annotations

import contextlib
import io
import logging
from pathlib import Path

import pandas as pd

from src.analysis.spectral_fitting import resolve_time_delta
from src.core import config
from src.utils.ir_fitting.api import ISO_X_MARKER, resolve_folder
from src.utils.ir_fitting.runner import file_key_for, split_file_key
from src.utils.ir_fitting.voigt import manually_skip_files

LOGGER = logging.getLogger(__name__)

TIMELINE_COLUMNS = ["File", "Delta_Group", "Time_Delta (s)"]


def _read_params_path(folder_name: str, file_name: str) -> Path:
    return Path(
        config.get_path(
            "utility.subtract_ifg.read_params_output", folder_name, file_name
        )
    )


def load_subifg_log(path: Path) -> pd.DataFrame:
    """Parse ``<measurement>_subIFGfiles.txt``.

    Copy of the log parsing in ``src/analysis/io.py::import_data``, which only
    loads it together with a subIFG and FSD file.
    """
    log = pd.read_csv(path, header=None, names=["sample_name", "sample", "background"])
    log["sample_name"] = (
        log["sample_name"].str.replace(r"[\'\(\)]", "", regex=True).str.strip()
    )
    for column in ("sample", "background"):
        log[column] = (
            log[column].str.extract(r"([^\s\'\"]+)").replace(r"\\\\", r"\\", regex=True)
        )
    return log


def load_exp_params(path: Path) -> pd.DataFrame:
    """Parse ``<measurement>.txt``. Copy of ``src/analysis/io.py::import_data``."""
    exp = pd.read_csv(
        path, header=None, names=["file_directory", "Date", "Time", "PKA", "NSS"]
    )
    exp["file_directory"] = exp["file_directory"].apply(
        lambda x: x.split()[0].strip("\"'")
    )
    exp["Time"] = exp["Time"].str.strip()
    exp["Time"] = exp["Time"].apply(lambda t: t if "." in t else t + ".000000")
    exp["datetime"] = pd.to_datetime(
        exp["Date"] + " " + exp["Time"],
        format=" %Y-%m-%d %H:%M:%S.%f",
        errors="coerce",
    )
    exp["datetime"] = exp["datetime"].fillna(
        pd.to_datetime(exp["Time"], format="%H:%M:%S.", errors="coerce")
    )
    return exp


def build_timeline(folder: str, measurement: str) -> pd.DataFrame:
    """One row per fit-eligible subIFG spectrum of ``measurement``.

    Args:
        folder: Dataset name (e.g. ``nn1120-3_pd_ceo2_004``).
        measurement: Measurement base name (e.g. ``20260304_145524_pd_ceo2_004-000``).

    Returns:
        ``File``, ``Delta_Group``, ``Time_Delta (s)``, sorted by delta group
        then file index. ``Time_Delta`` is NaN (with a warning) when the log or
        exp params cannot resolve it -- never silently 0.
    """
    subifg_dir = resolve_folder(folder)
    log = load_subifg_log(_read_params_path(folder, f"{measurement}_subIFGfiles.txt"))
    exp = load_exp_params(_read_params_path(folder, f"{measurement}.txt"))

    # The log is the record of every subtraction performed, so it -- not the
    # files currently on disk -- defines the spectra. A logged file missing
    # from disk still took time.
    names = {
        str(name)
        for name in log["sample_name"]
        if str(name).startswith(f"{measurement}_delta")
    }
    names |= {
        item.name
        for item in subifg_dir.glob(f"{measurement}_delta*.*")
        if item.is_file()
    }
    paths = sorted(
        subifg_dir / name for name in names if "_delta" in name and ISO_X_MARKER not in name
    )
    if not paths:
        raise FileNotFoundError(f"No subIFG spectra for {measurement} in log or {subifg_dir}")

    rows = []
    for item in paths:
        if not item.exists():
            LOGGER.info("%s: %s is logged but not on disk", measurement, item.name)
        file_key = file_key_for(item)
        delta_group, file_index = split_file_key(file_key)
        if manually_skip_files(delta_group, file_index):
            continue
        # resolve_time_delta prints and returns 0 on failure; a real 0 is
        # impossible (sample and background are different scans).
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            time_delta = resolve_time_delta(str(item), log, exp)
        if not time_delta:
            LOGGER.warning(
                "%s %s: no time delta (%s)",
                measurement,
                file_key,
                captured.getvalue().strip() or "resolved to 0",
            )
            time_delta = float("nan")
        rows.append((file_key, delta_group, int(file_index), float(time_delta)))

    df = pd.DataFrame(rows, columns=["File", "Delta_Group", "_index", "Time_Delta (s)"])
    df["_group_n"] = df["Delta_Group"].str.removeprefix("delta").astype(int)
    df = df.sort_values(["_group_n", "_index"]).reset_index(drop=True)
    return df[TIMELINE_COLUMNS]
