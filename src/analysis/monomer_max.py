"""Compute monomer maximum peak data for a single lgRefl file."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd

SRC_PATH = Path(__file__).resolve().parent.parent.parent
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from src.core import config
from src.analysis.spectral_fitting import get_shifted_monomer_peaks

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MonomerMaxRow:
    """Monomer max results for a single lgRefl file."""

    file_name: str
    max_monomer_peak: float
    peak_bin: int
    time_total_s: float
    time_total_fraction: float


def _add_milliseconds(time_string: str) -> str:
    """Ensure time string includes microseconds."""
    if "." in time_string:
        if time_string.endswith("."):
            return time_string + "000000"
        return time_string
    return f"{time_string}.000000"


def load_experiment_params(time_file: Path) -> pd.DataFrame | None:
    """Load experiment parameters and parse DateTime/iterator."""
    if not time_file.exists():
        LOGGER.warning("Time parameter file not found: %s", time_file)
        return None

    try:
        exp_params = pd.read_csv(
            time_file,
            header=None,
            names=["file_directory", "Date", "Time", "pka", "nss"],
        )
    except Exception as exc:
        LOGGER.warning("Failed to read time parameter file %s: %s", time_file, exc)
        return None

    if exp_params.empty:
        LOGGER.warning("Time parameter file is empty: %s", time_file)
        return None

    exp_params["file_directory"] = exp_params["file_directory"].apply(
        lambda x: str(x).split()[0].strip("\"'")
    )
    exp_params["iterator"] = exp_params["file_directory"].apply(
        lambda x: str(x).split(".")[-1]
    )

    time_strings = exp_params["Time"].astype(str).str.strip()
    time_strings = time_strings.apply(_add_milliseconds)
    exp_params["Time"] = time_strings

    date_strings = exp_params["Date"].astype(str)
    datetime_primary = pd.to_datetime(
        date_strings + " " + time_strings,
        format=" %Y-%m-%d %H:%M:%S.%f",
        errors="coerce",
    )
    datetime_trimmed = pd.to_datetime(
        date_strings.str.strip() + " " + time_strings,
        format="%Y-%m-%d %H:%M:%S.%f",
        errors="coerce",
    )
    datetime_no_micro = pd.to_datetime(
        date_strings.str.strip() + " " + time_strings,
        format="%Y-%m-%d %H:%M:%S",
        errors="coerce",
    )

    exp_params["DateTime"] = datetime_primary.fillna(datetime_trimmed).fillna(
        datetime_no_micro
    )

    if bool(exp_params["DateTime"].isna().any()):
        bad_rows = exp_params[exp_params["DateTime"].isna()].index.tolist()
        LOGGER.warning(
            "Failed to parse DateTime from %s; problematic rows: %s",
            time_file,
            bad_rows,
        )

    return exp_params


def read_lgrefl_file(file_path: Path) -> pd.DataFrame | None:
    """Read lgRefl data file."""
    try:
        df = pd.read_csv(file_path, header=None, names=["wavenumber", "lgrefl"])
        return df
    except Exception as exc:
        LOGGER.debug("Failed to read %s: %s", file_path, exc)
        return None


def find_monomer_max_in_file(
    df: pd.DataFrame, *, peak_min: float, peak_max: float
) -> float | None:
    """Find maximum monomer peak in a single lgRefl file."""
    if df is None or df.empty:
        return None

    wavenum_col = df.columns[0]
    absorb_col = df.columns[1]
    monomer_mask = (df[wavenum_col] >= peak_min) & (df[wavenum_col] <= peak_max)
    monomer_data = df[monomer_mask]

    if monomer_data.empty:
        return None

    absorb_values = np.asarray(monomer_data[absorb_col])
    max_idx = int(np.argmax(absorb_values))
    wavenum_values = np.asarray(monomer_data[wavenum_col])
    max_peak = wavenum_values[max_idx]

    return float(max_peak)


def _build_time_lookup(exp_params: pd.DataFrame) -> dict[str, pd.Timestamp]:  # type: ignore[return-value]
    exp_params = exp_params[pd.notna(exp_params["DateTime"])].copy()  # type: ignore[assignment]
    time_lookup: dict[str, pd.Timestamp] = {}
    for _, row in exp_params.iterrows():
        iterator = str(row["iterator"])
        time_lookup[iterator] = cast(pd.Timestamp, row["DateTime"])
    return time_lookup


def _compute_time_integrals(
    exp_params: pd.DataFrame,
    max_peaks: list[tuple[str, float]],
) -> dict[str, tuple[float, int, float, float]]:
    """Compute cumulative and total time per peak bin by iterator.

    Returns a mapping of iterator -> (time_total_s, peak_bin,
    max_monomer_peak, time_total_fraction).
    """
    time_lookup = _build_time_lookup(exp_params)
    records = []
    for iterator, max_peak in max_peaks:
        file_time = time_lookup.get(iterator)
        if file_time is None or bool(pd.isna(file_time)):
            continue
        records.append((iterator, max_peak, file_time))

    if not records:
        return {}

    records = sorted(records, key=lambda item: item[2])
    total_by_peak: dict[int, float] = {}
    delta_by_iterator: dict[str, tuple[int, float, float]] = {}
    previous_time = None

    for iterator, max_peak, file_time in records:
        if previous_time is None:
            time_delta_s = 0.0
        else:
            time_delta_s = float((file_time - previous_time).total_seconds())
        peak_bin = int(round(max_peak))
        total_by_peak[peak_bin] = total_by_peak.get(peak_bin, 0.0) + time_delta_s
        delta_by_iterator[iterator] = (peak_bin, max_peak, time_delta_s)
        previous_time = file_time

    total_experiment_time = sum(total_by_peak.values())
    cumulative_by_peak: dict[int, float] = {}
    results: dict[str, tuple[float, int, float, float]] = {}
    for iterator, max_peak, _ in records:
        peak_bin, max_peak, time_delta_s = delta_by_iterator[iterator]
        cumulative_by_peak[peak_bin] = (
            cumulative_by_peak.get(peak_bin, 0.0) + time_delta_s
        )
        time_total_s = total_by_peak[peak_bin]
        if total_experiment_time > 0.0:
            time_total_fraction = time_total_s / total_experiment_time
        else:
            time_total_fraction = 0.0
        results[iterator] = (
            time_total_s,
            peak_bin,
            max_peak,
            time_total_fraction,
        )

    return results


def compute_monomer_max_row(
    *,
    file_path: Path,
    peak_min: float | None = None,
    peak_max: float | None = None,
) -> pd.DataFrame:
    """Compute monomer max for a folder based on an lgRefl file path.

    Returns all rows for the folder (for the whole-run time_total_fraction).

    Args:
        file_path: Path to an lgRefl file (used to determine folder/stem)
        peak_min: Minimum wavenumber for monomer peak search
        peak_max: Maximum wavenumber for monomer peak search
    """
    folder_name = file_path.parent.name
    stem = file_path.stem

    if peak_min is None or peak_max is None:
        voigt_settings = config.get_analysis_setting("voigt_fit")
        monomer_peaks = get_shifted_monomer_peaks(voigt_settings)
        if not monomer_peaks:
            LOGGER.warning("No monomer peaks configured for monomer max.")
            return pd.DataFrame()
        derived_min = float(min(monomer_peaks))
        derived_max = float(max(monomer_peaks))
        peak_min = float(peak_min) if peak_min is not None else derived_min
        peak_max = float(peak_max) if peak_max is not None else derived_max

    time_file = Path(
        config.get_path(
            "utility.subtract_ifg.read_params_output", folder_name, f"{stem}.txt"
        )
    )
    exp_params = load_experiment_params(time_file)
    if exp_params is None or exp_params.empty:
        return pd.DataFrame()

    max_peaks: list[tuple[str, float]] = []
    for match in exp_params["iterator"].dropna().astype(str).unique().tolist():
        candidate = file_path.with_suffix(f".{match}")
        if not candidate.exists():
            continue
        df = read_lgrefl_file(candidate)
        if df is None:
            continue
        max_peak = find_monomer_max_in_file(df, peak_min=peak_min, peak_max=peak_max)
        if max_peak is None:
            continue
        max_peaks.append((match, max_peak))

    time_summary = _compute_time_integrals(exp_params, max_peaks)

    # Return all rows for this stem/folder (for full rebuild)
    all_rows = []
    for iter_name, values in time_summary.items():
        time_total_s, peak_bin, max_peak_val, time_total_fraction = values
        row = MonomerMaxRow(
            file_name=f"{stem}.{iter_name}",
            max_monomer_peak=max_peak_val,
            peak_bin=peak_bin,
            time_total_s=time_total_s,
            time_total_fraction=time_total_fraction,
        )
        all_rows.append(row.__dict__)

    if not all_rows:
        return pd.DataFrame()

    df_all = pd.DataFrame(all_rows)

    return df_all


def compute_and_save_monomer_max(
    folder_name: str,
    stem: str | None = None,
    save_dir: str | None = None,
    peak_min: float | None = None,
    peak_max: float | None = None,
) -> pd.DataFrame:
    """Compute monomer max for all files in a folder and save to CSV (overwrites).

    Args:
        folder_name: The folder name (e.g., nn1120-3_pd_ceo2_004)
        stem: Optional stem name. If not provided, will process all stems in folder.
        save_dir: Optional save directory. If not provided, uses config path.
        peak_min: Optional minimum wavenumber for monomer peak search
        peak_max: Optional maximum wavenumber for monomer peak search
    """
    if save_dir is None:
        save_dir = config.get_path("data.peak_fit", folder_name)

    # Find the lgRefl folder
    folder_path = Path(config.get_path("data.lg_refl", folder_name))
    if not folder_path.exists():
        LOGGER.warning("Folder not found: %s", folder_path)
        return pd.DataFrame()

    # Get list of stems to process
    if stem is not None:
        stems_to_process = [stem]
    else:
        # Auto-detect all stems from existing files (exclude isoX)
        lg_files = list(folder_path.glob("*.*"))
        stems_to_process = set()
        for f in lg_files:
            # Skip isoX files
            if "isoX" in f.name:
                continue
            if f.suffix.lstrip(".").isdigit():
                stems_to_process.add(f.stem)

        if not stems_to_process:
            LOGGER.warning("No lgRefl files found in %s", folder_path)
            return pd.DataFrame()

        stems_to_process = sorted(stems_to_process)
        LOGGER.debug("Processing %d stems: %s", len(stems_to_process), stems_to_process)

    # Process each stem and combine results
    all_dfs = []
    for stem in stems_to_process:
        lg_files = list(folder_path.glob(f"{stem}.*"))
        if not lg_files:
            LOGGER.warning("No lgRefl files found for stem %s in %s", stem, folder_name)
            continue

        # Compute all rows for this stem
        df_stem = compute_monomer_max_row(
            file_path=lg_files[0],
            peak_min=peak_min,
            peak_max=peak_max,
        )

        if not df_stem.empty:
            all_dfs.append(df_stem)

    if not all_dfs:
        LOGGER.warning("No data computed for any stem in %s", folder_name)
        return pd.DataFrame()

    # Combine all stems into one DataFrame
    df_all = pd.concat(all_dfs, ignore_index=True)

    if df_all.empty:
        return df_all

    # Overwrite the CSV (not append)
    filename = f"{folder_name}_monomerMax.csv"
    path = os.path.join(save_dir, filename)
    df_all.to_csv(path, index=False)
    LOGGER.debug("Saved monomer max to %s", path)

    return df_all


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # Example: run for a specific folder (stem is auto-detected)
    FOLDER_NAME = "nn1120-3_pd_ceo2_004"

    df = compute_and_save_monomer_max(FOLDER_NAME)
