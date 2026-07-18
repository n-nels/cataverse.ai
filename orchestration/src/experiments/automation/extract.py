"""
Data extraction for PFO-Sec parameter prediction model.

Walks filesystem, parses JSON metadata, caches raw records.
Provides incremental loading with cache persistence.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = Path(__file__).parent / "experiment_cache.json"

class ExperimentRecord(NamedTuple):
    """Container for a single experiment's loaded data."""

    base_name: str
    datetime: datetime
    json_path: Path
    csv_path: Path
    json_data: dict

    def load_csv(self) -> pd.DataFrame:
        """Load CSV data on demand."""
        return pd.read_csv(self.csv_path)


class FilenameParseError(Exception):
    """Raised when filename does not match expected format."""


def _parse_datetime_from_filename(filename: str) -> datetime:
    """Extract datetime from filename pattern YYYYMM_HHMMSS_...

    Raises
    ------
    FilenameParseError
        If the filename does not match the expected pattern.
    """
    match = re.match(r"(\d{8})_(\d{6})", filename)
    if match is None:
        raise FilenameParseError(
            f"Could not parse datetime from filename: {filename}"
        )
    dt_str = match.group(1) + match.group(2)
    return datetime.strptime(dt_str, "%Y%m%d%H%M%S")


def _load_cache(cache_path: Path) -> dict | None:
    """
    Load cache from disk.

    Parameters
    ----------
    cache_path : Path
        Path to cache file.

    Returns
    -------
    dict | None
        Cache data with 'records' and 'last_updated' keys, or None if not found.
    """
    if not cache_path.exists():
        return None

    try:
        with open(cache_path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load cache from %s: %s", cache_path, e)
        return None


def _save_cache(cache_path: Path, records: list[ExperimentRecord]) -> None:
    """
    Save records to cache file.

    Parameters
    ----------
    cache_path : Path
        Path to cache file.
    records : list[ExperimentRecord]
        Records to cache.
    """
    cache_data = {
        "last_updated": datetime.now().isoformat(),
        "records": [
            {
                "base_name": rec.base_name,
                "datetime": rec.datetime.isoformat(),
                "json_path": str(rec.json_path),
                "csv_path": str(rec.csv_path),
                "json_data": rec.json_data,
            }
            for rec in records
        ],
    }

    with open(cache_path, "w") as f:
        json.dump(cache_data, f, indent=2)

    logger.info("Saved %d records to cache: %s", len(records), cache_path)


def _walk_data_root(data_root: Path) -> list[Path]:
    """
    Walk data directory for all *_expParams.json files.

    Parameters
    ----------
    data_root : Path
        Root directory to search.

    Returns
    -------
    list[Path]
        List of JSON file paths found.
    """
    return list(data_root.rglob("*_expParams.json"))


def _filter_new_files(all_paths: list[Path], cached_paths: set[str]) -> list[Path]:
    """
    Return only files not already in cache.

    Parameters
    ----------
    all_paths : list[Path]
        All JSON paths found on filesystem.
    cached_paths : set[str]
        Paths already in cache.

    Returns
    -------
    list[Path]
        New files not in cache.
    """
    return [p for p in all_paths if str(p) not in cached_paths]


def _process_new_files(new_paths: list[Path]) -> list[ExperimentRecord]:
    """
    Process new JSON files into ExperimentRecords.

    Parameters
    ----------
    new_paths : list[Path]
        New JSON file paths to process.

    Returns
    -------
    list[ExperimentRecord]
        Processed records from new files.
    """
    records = []
    skipped_parse = 0
    skipped_has_csv = 0
    skipped_exp_success = 0
    skipped_no_csv = 0

    for json_path in new_paths:
        try:
            dt = _parse_datetime_from_filename(json_path.name)
        except FilenameParseError as e:
            logger.warning(str(e))
            skipped_parse += 1
            continue

        with open(json_path, "r") as f:
            json_data = json.load(f)

        flags = json_data.get("filename_flags", {})

        if flags.get("has_csv") is False:
            skipped_has_csv += 1
            continue

        if flags.get("exp_success") is False:
            skipped_exp_success += 1
            continue

        csv_path = json_path.with_name(
            json_path.name.replace("_expParams.json", "_CarbonylPeakArea.csv")
        )

        if not csv_path.exists():
            skipped_no_csv += 1
            continue

        base_name = json_data.get("base_name")

        records.append(
            ExperimentRecord(
                base_name=base_name,
                datetime=dt,
                json_path=json_path,
                csv_path=csv_path,
                json_data=json_data,
            )
        )

    logger.info(
        "Processed %d new files: %d loaded, "
        "%d skipped (parse), %d skipped (has_csv), "
        "%d skipped (exp_success), %d skipped (no CSV)",
        len(new_paths),
        len(records),
        skipped_parse,
        skipped_has_csv,
        skipped_exp_success,
        skipped_no_csv,
    )

    return records


def _load_cached_records(cache_data: dict) -> list[ExperimentRecord]:
    """
    Convert cached record dicts back to ExperimentRecord objects.

    Parameters
    ----------
    cache_data : dict
        Cache data with 'records' key.

    Returns
    -------
    list[ExperimentRecord]
        Records loaded from cache.
    """
    records = []
    for rec_dict in cache_data.get("records", []):
        records.append(
            ExperimentRecord(
                base_name=rec_dict["base_name"],
                datetime=datetime.fromisoformat(rec_dict["datetime"]),
                json_path=Path(rec_dict["json_path"]),
                csv_path=Path(rec_dict["csv_path"]),
                json_data=rec_dict["json_data"],
            )
        )
    return records


def extract_data(
    data_root: str | Path = r"X:\peakFit",
    cache_path: str | Path | None = None,
    force_refresh: bool = False,
) -> list[ExperimentRecord]:
    """
    Load experiment records with incremental caching.

    Parameters
    ----------
    data_root : str | Path
        Root directory containing experiment folders.
    cache_path : str | Path | None
        Path to cache file. Defaults to module-relative experiment_cache.json.
    force_refresh : bool
        If True, ignore cache and do full walk.

    Returns
    -------
    list[ExperimentRecord]
        Chronologically sorted list of loaded experiment records.

    Raises
    ------
    FileNotFoundError
        If data_root does not exist.
    """
    data_path = Path(data_root)
    if not data_path.exists():
        raise FileNotFoundError(f"Data root not found: {data_path}")

    cache_file = Path(cache_path) if cache_path else DEFAULT_CACHE_PATH

    # Try loading cache
    cached_records: list[ExperimentRecord] = []
    if not force_refresh:
        cache_data = _load_cache(cache_file)
        if cache_data is not None:
            cached_records = _load_cached_records(cache_data)
            logger.info("Loaded %d records from cache", len(cached_records))

    # Walk filesystem for all JSON files
    all_json_paths = _walk_data_root(data_path)

    # Find new files not in cache
    cached_paths = {str(rec.json_path) for rec in cached_records}
    new_paths = _filter_new_files(all_json_paths, cached_paths)

    if new_paths:
        logger.info("Found %d new files to process", len(new_paths))
        new_records = _process_new_files(new_paths)
    else:
        new_records = []
        logger.info("No new files found")

    # Combine and sort
    all_records = cached_records + new_records
    all_records.sort(key=lambda r: r.datetime)

    # Save updated cache
    _save_cache(cache_file, all_records)

    logger.info(
        "Phase 1 complete: %d total filesystem, %d cached, "
        "%d new, %d final",
        len(all_json_paths),
        len(cached_records),
        len(new_records),
        len(all_records),
    )

    return all_records
