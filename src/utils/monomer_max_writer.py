"""Find monomer maximum from lgRefl data for each file within a dataset.

Phase 1.3.3 - Analyzes lgRefl spectral data to find the maximum monomer peak
height for each file/timepoint in a dataset.

Data Source: C:/Data/OpusConvert_lgRfl/<folder>/
File Pattern: <YYYYMMDD_HHMMSS>_<material>_<material-iterator>_<exp-no>.<extension-iterator>
Example: 20260214_170244_pd_ceo2_003-116.0000
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import NamedTuple, cast

import numpy as np
import pandas as pd

LOGGER = logging.getLogger(__name__)

# Data paths
LGREFL_ROOT = Path("C:/Data/OpusConvert_lgRfl")
READ_PARAMS_ROOT = Path("C:/Data/OpusReadParams")
OUTPUT_ROOT = Path("C:/Data/peakFit/")

# Monomer peak region (13CO shifted peaks, cm^-1). Put in analsysis.yaml
MONOMER_PEAK_MIN = 2093.0
MONOMER_PEAK_MAX = 2125.0


class MonomerMaxResult(NamedTuple):
    """Result container for monomer maximum analysis."""

    file_name: str
    time_s: float
    time_total_s: float
    time_total_fraction: float
    peak_bin: int
    max_monomer_peak: float


class ExperimentRecord(NamedTuple):
    """Per-file record for a single experiment stem."""

    file_path: Path
    max_peak: float
    time: pd.Timestamp


class ExperimentDeltaRecord(NamedTuple):
    """Per-file record with time deltas for an experiment."""

    file_path: Path
    max_peak: float
    peak_rounded: int
    time: pd.Timestamp
    time_delta_s: float


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
        LOGGER.warning(f"Time parameter file not found: {time_file}")
        return None

    try:
        exp_params = pd.read_csv(
            time_file,
            header=None,
            names=["file_directory", "Date", "Time", "pka", "nss"],
        )
    except Exception as exc:
        LOGGER.warning(f"Failed to read time parameter file {time_file}: {exc}")
        return None

    if exp_params.empty:
        LOGGER.warning(f"Time parameter file is empty: {time_file}")
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
            f"Failed to parse DateTime from {time_file}; problematic rows: {bad_rows}"
        )

    return exp_params


def read_lgrefl_file(file_path: Path) -> pd.DataFrame | None:
    """Read lgRefl data file."""
    try:
        df = pd.read_csv(file_path, header=None, names=["wavenumber", "lgrefl"])
        return df

    except Exception as exc:
        LOGGER.debug(f"Failed to read {file_path}: {exc}")
        return None


def find_monomer_max_in_file(df: pd.DataFrame) -> float | None:
    """Find maximum monomer peak in a single lgRefl file.

    Returns:
        Tuple of (peak_wavenumber, peak_height, n_peaks_found, all_peak_wavenumbers)
        or None if no monomer peaks found
    """
    if df is None or df.empty:
        return None

    wavenum_col = df.columns[0]
    absorb_col = df.columns[1]

    # Filter to monomer region
    monomer_mask = (df[wavenum_col] >= MONOMER_PEAK_MIN) & (
        df[wavenum_col] <= MONOMER_PEAK_MAX
    )
    monomer_data = df[monomer_mask]

    if monomer_data.empty:
        return None

    absorb_values = np.asarray(monomer_data[absorb_col])
    max_idx = int(np.argmax(absorb_values))
    wavenum_values = np.asarray(monomer_data[wavenum_col])
    max_peak = wavenum_values[max_idx]

    return float(max_peak)


def process_dataset_folder(folder_path: Path) -> list[MonomerMaxResult]:
    """Process all lgRefl files in a dataset folder."""
    results: list[MonomerMaxResult] = []

    # Find all lgRefl files
    lgrefl_files = sorted(folder_path.glob("*.*"))
    grouped_files: dict[str, list[Path]] = {}

    for file_path in lgrefl_files:
        if "isoX" in file_path.name:
            continue
        grouped_files.setdefault(file_path.stem, []).append(file_path)

    # Get folder name
    try:
        folder_name = str(folder_path.relative_to(LGREFL_ROOT))
    except ValueError:
        folder_name = folder_path.name

    for experiment_name, file_paths in grouped_files.items():
        time_file = READ_PARAMS_ROOT / folder_name / f"{experiment_name}.txt"
        exp_params = load_experiment_params(time_file)
        if exp_params is None or exp_params.empty:
            continue

        exp_params = exp_params[pd.notna(exp_params["DateTime"])]
        time_lookup = {
            str(row["iterator"]): row["DateTime"] for _, row in exp_params.iterrows()
        }
        experiment_records: list[ExperimentRecord] = []

        for file_path in file_paths:
            df = read_lgrefl_file(file_path)
            if df is None:
                continue

            max_peak = find_monomer_max_in_file(df)
            if max_peak is None:
                continue

            iterator = file_path.suffix.lstrip(".")
            file_time = time_lookup.get(iterator)
            if file_time is None or bool(pd.isna(file_time)):
                LOGGER.warning(
                    f"Missing DateTime for iterator {iterator} in {time_file}"
                )
                continue

            file_time = cast(pd.Timestamp, file_time)

            experiment_records.append(
                ExperimentRecord(
                    file_path=file_path,
                    max_peak=max_peak,
                    time=file_time,
                )
            )

        if not experiment_records:
            continue

        experiment_records = sorted(experiment_records, key=lambda r: r.time)
        delta_records: list[ExperimentDeltaRecord] = []
        total_by_peak: dict[int, float] = {}
        previous_time = None

        for record in experiment_records:
            current_time = record.time
            if previous_time is None:
                time_delta_s = 0.0
            else:
                time_delta_s = float((current_time - previous_time).total_seconds())

            peak_rounded = int(round(record.max_peak))
            total_by_peak[peak_rounded] = (
                total_by_peak.get(peak_rounded, 0.0) + time_delta_s
            )
            delta_records.append(
                ExperimentDeltaRecord(
                    file_path=record.file_path,
                    max_peak=record.max_peak,
                    peak_rounded=peak_rounded,
                    time=record.time,
                    time_delta_s=time_delta_s,
                )
            )
            previous_time = current_time

        cumulative_by_peak: dict[int, float] = {}
        total_experiment_time = sum(total_by_peak.values())
        for record in delta_records:
            cumulative_by_peak[record.peak_rounded] = (
                cumulative_by_peak.get(record.peak_rounded, 0.0) + record.time_delta_s
            )

            time_total = total_by_peak[record.peak_rounded]
            if total_experiment_time > 0.0:
                time_total_fraction = time_total / total_experiment_time
            else:
                time_total_fraction = 0.0
            result = MonomerMaxResult(
                file_name=record.file_path.name,
                time_s=cumulative_by_peak[record.peak_rounded],
                time_total_s=time_total,
                time_total_fraction=time_total_fraction,
                peak_bin=record.peak_rounded,
                max_monomer_peak=record.max_peak,
            )
            results.append(result)

    return results


def save_results(results: list[MonomerMaxResult], output_path: Path) -> None:
    """Save results to CSV."""
    if not results:
        LOGGER.warning("No results to save")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(results)
    df = df[
        [
            "file_name",
            "time_s",
            "max_monomer_peak",
            "peak_bin",
            "time_total_s",
            "time_total_fraction",
        ]
    ]
    df.to_csv(output_path, index=False)

    LOGGER.info(f"Saved {len(results)} results to {output_path}")


def main():
    """Main execution."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    if not LGREFL_ROOT.exists():
        LOGGER.error(f"lgRefl root not found: {LGREFL_ROOT}")
        return

    # Find all dataset folders (exclude arxiv folders)
    dataset_folders = [
        d
        for d in LGREFL_ROOT.iterdir()
        if d.is_dir()
        and "arxiv" not in d.name.lower()
        and "archive" not in d.name.lower()
        and "_test" not in d.name.lower()
    ]

    if not dataset_folders:
        LOGGER.warning(f"No dataset folders found in {LGREFL_ROOT}")
        return

    all_results: list[MonomerMaxResult] = []

    for folder in dataset_folders:
        results = process_dataset_folder(folder)
        all_results.extend(results)

        # Save per-folder results
        if results:
            folder_output = OUTPUT_ROOT / folder.name / f"{folder.name}_monomerMax.csv"
            save_results(results, folder_output)

    # Save combined results
    if all_results:
        combined_output = OUTPUT_ROOT / "all_monomerMax.csv"
        save_results(all_results, combined_output)
    else:
        LOGGER.warning("No results generated")


if __name__ == "__main__":
    main()
