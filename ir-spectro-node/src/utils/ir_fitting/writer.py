"""Output writing for offline IR peak fitting.

Never writes into the source folder: the live pipeline re-reads
``*_CarbonylPeakFitParams.csv`` as fit history, so overwriting it in place
corrupts the dataset. Output always lands in a subfolder (``_test`` by default),
following the same rule as ``src/utils/kinetics/utils.py::resolve_output_dir``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

path = Path(__file__).resolve().parents[3]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.core import config
from src.utils.ir_fitting.result_types import FileFitResult, MeasurementFitResult
from src.utils.ir_fitting.runner import PARAM_COLUMNS, WAVENUMBER_COLUMN

LOGGER = logging.getLogger(__name__)


def params_suffix() -> str:
    """Return the fit-params filename suffix from config."""
    return str(config.get_setting("filenames.carbonyl_fit.params_suffix"))


def baseline_suffix() -> str:
    """Return the baseline filename suffix from config."""
    return str(config.get_setting("filenames.carbonyl_fit.baseline_suffix"))


def residual_suffix() -> str:
    """Return the residual filename suffix from config."""
    return str(config.get_setting("filenames.carbonyl_fit.residual_suffix"))


def peak_fit_dir(folder_name: str) -> Path:
    """Return the dataset's peak-fit output folder."""
    return Path(config.get_path("data.peak_fit", folder_name))


def resolve_output_dir(source_dir: Path, output_folder_name: str) -> Path:
    """Resolve and create the output directory under ``source_dir``.

    Rejects any name that would resolve back to the source folder or escape it:
    ``""`` and ``"."`` both collapse to the parent under ``Path.__truediv__``,
    and an absolute right-hand side discards the left side entirely.
    """
    if not isinstance(output_folder_name, str) or not output_folder_name.strip():
        raise ValueError(
            "output_folder must be a non-empty subfolder name (e.g. '_test'); "
            f"got {output_folder_name!r}. Writing into the source folder would "
            "overwrite the input params CSV that the live pipeline reads back "
            "as fit history."
        )
    name = output_folder_name.strip()
    if Path(name).is_absolute() or name in {".", ".."} or ".." in Path(name).parts:
        raise ValueError(
            f"output_folder must be a relative subfolder name; got {name!r}."
        )
    output_dir = (source_dir / name).resolve()
    if (
        output_dir == source_dir.resolve()
        or source_dir.resolve() not in output_dir.parents
    ):
        raise ValueError(
            f"output_folder {name!r} does not resolve to a subfolder of {source_dir}."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def load_measurement_params(folder_name: str, file_name: str) -> pd.DataFrame:
    """Load a measurement's existing ``*_CarbonylPeakFitParams.csv``."""
    csv_path = peak_fit_dir(folder_name) / f"{file_name}{params_suffix()}"
    if not csv_path.exists():
        LOGGER.warning("No existing params CSV at %s", csv_path)
        return pd.DataFrame(columns=PARAM_COLUMNS)
    return pd.read_csv(csv_path)


def load_saved_baseline(folder_name: str, file_name: str) -> pd.DataFrame | None:
    """Load a measurement's existing ``*_CarbonylFitBaseline.csv``, if present."""
    csv_path = peak_fit_dir(folder_name) / f"{file_name}{baseline_suffix()}"
    if not csv_path.exists():
        LOGGER.warning("No saved baseline CSV at %s", csv_path)
        return None
    return pd.read_csv(csv_path)


def merge_params(
    df_existing: pd.DataFrame,
    results: list[FileFitResult],
    *,
    on_existing: str = "skip",
    append_only: bool = True,
) -> pd.DataFrame:
    """Merge newly fitted rows into the existing params table.

    Column order and names match the live schema exactly, so the output is
    readable by the existing plotting and kinetics code unchanged. Columns the
    live path adds when calibration is available (``PdCO_mol``,
    ``PdCO_mol_stderr``) are preserved on existing rows and left empty on new
    ones -- the calibration slope is derived in the carbonyl region and is not
    justified at 1775-1795.

    A row is replaced rather than added when this run refitted it: either
    ``on_existing="overwrite"``, or ``append_only=False``. The second case
    matters -- a full refit produces a row for *every* peak, so keeping the
    saved rows as well would duplicate every ``(File, Peak_Name)`` pair and feed
    doubled history to ``compute_cumulative_peak_area_df``. ``on_existing`` asks
    what to do when *appending* and has no meaning in a full refit.
    """
    new_rows = [row for result in results for row in result.new_rows]
    df_new = (
        pd.DataFrame(new_rows, columns=PARAM_COLUMNS) if new_rows else pd.DataFrame()
    )

    df_kept = df_existing
    if not df_existing.empty and not df_new.empty:
        if append_only:
            # Appending replaces only the exact rows this run refitted.
            replaced = set(zip(df_new["File"], df_new["Peak_Name"]))
            mask = [
                (file_key, peak) not in replaced
                for file_key, peak in zip(df_existing["File"], df_existing["Peak_Name"])
            ]
        else:
            # A full refit replaces every row for every file it touched, not
            # just the (File, Peak_Name) pairs it happens to reproduce. The peak
            # list has churned between datasets -- nn1120-2_pd_ceo2_000 holds
            # peaks the current list dropped -- and keeping such a row would mix
            # one model's output with another's in the same file, so the peak
            # curves no longer sum to the composite. Files the run did not touch
            # (e.g. skipped by manually_skip_files) keep their rows untouched.
            refitted_files = set(df_new["File"])
            mask = [file_key not in refitted_files for file_key in df_existing["File"]]
        df_kept = df_existing.loc[mask]

    if df_new.empty:
        merged = df_kept.copy()
    elif df_kept.empty:
        merged = df_new
    else:
        merged = pd.concat([df_kept, df_new], axis=0, ignore_index=True)

    if merged.empty:
        return merged

    # Preserve any extra live columns (e.g. PdCO_mol) after the standard ones.
    ordered = [col for col in PARAM_COLUMNS if col in merged.columns]
    extras = [col for col in merged.columns if col not in PARAM_COLUMNS]
    merged = merged[ordered + extras]

    if "Peak_Name" in merged.columns and "File" in merged.columns:
        merged = merged.sort_values(by=["Peak_Name", "File"], kind="stable")
    return merged.reset_index(drop=True)


def _wide_frame(
    results: list[FileFitResult],
    attribute: str,
) -> pd.DataFrame:
    """Build a wide ``Wavenumber (cm-1)`` + one-column-per-file table."""
    if not results:
        return pd.DataFrame()
    frame = pd.DataFrame({WAVENUMBER_COLUMN: results[0].wavenumbers})
    for result in results:
        frame[result.file_key] = getattr(result, attribute)
    return frame


def write_measurement(
    measurement: MeasurementFitResult,
    *,
    output_folder: str = "_test",
) -> dict[str, Path]:
    """Write params, baseline and residual CSVs for one measurement."""
    output_dir = resolve_output_dir(
        peak_fit_dir(measurement.folder_name), output_folder
    )
    paths: dict[str, Path] = {}

    params_path = output_dir / f"{measurement.file_name}{params_suffix()}"
    measurement.merged_params.to_csv(params_path, index=False)
    paths["params"] = params_path

    baseline_path = output_dir / f"{measurement.file_name}{baseline_suffix()}"
    _wide_frame(measurement.files, "baseline").to_csv(baseline_path, index=False)
    paths["baseline"] = baseline_path

    residual_path = output_dir / f"{measurement.file_name}{residual_suffix()}"
    _wide_frame(measurement.files, "residual").to_csv(residual_path, index=False)
    paths["residual"] = residual_path

    LOGGER.info("Wrote %s", params_path)
    return paths
