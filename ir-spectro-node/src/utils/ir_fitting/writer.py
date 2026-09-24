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


def params_frame(results: list[FileFitResult]) -> pd.DataFrame:
    """Build the output params table from this run's rows only.

    Nothing is carried over from the saved CSV. A file that failed or was
    skipped has no rows, so every row in the output came from this refit's
    model. Column order matches the live schema; ``PdCO_mol`` is not written.
    """
    rows = [row for result in results for row in result.rows]
    if not rows:
        return pd.DataFrame(columns=PARAM_COLUMNS)
    frame = pd.DataFrame(rows, columns=PARAM_COLUMNS)
    frame = frame.sort_values(by=["Peak_Name", "File"], kind="stable")
    return frame.reset_index(drop=True)


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
    measurement.params.to_csv(params_path, index=False)
    paths["params"] = params_path

    baseline_path = output_dir / f"{measurement.file_name}{baseline_suffix()}"
    _wide_frame(measurement.files, "baseline").to_csv(baseline_path, index=False)
    paths["baseline"] = baseline_path

    residual_path = output_dir / f"{measurement.file_name}{residual_suffix()}"
    _wide_frame(measurement.files, "residual").to_csv(residual_path, index=False)
    paths["residual"] = residual_path

    LOGGER.info("Wrote %s", params_path)
    return paths
