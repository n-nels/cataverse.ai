"""Offline IR peak-fitting package for EDA and reprocessing.

Wraps ``src/analysis/spectral_fitting.py`` rather than duplicating it. Never
invoked by the live server path and never writes into source data -- output goes
to a ``_test`` subfolder. See ``spec.md`` for the design.
"""

from src.utils.ir_fitting.api import (
    baseline_experiment_dir,
    fit_file,
    fit_folder,
    load_measurement,
    measurement_names,
    resolve_folder,
    run_baseline,
    subifg_dir,
    subifg_files,
)
from src.utils.ir_fitting.baseline import (
    DEFAULT_FILES,
    DEFAULT_WINDOW,
    BaselineVariant,
)

__all__ = [
    "DEFAULT_FILES",
    "DEFAULT_WINDOW",
    "BaselineVariant",
    "baseline_experiment_dir",
    "fit_file",
    "fit_folder",
    "load_measurement",
    "measurement_names",
    "resolve_folder",
    "run_baseline",
    "subifg_dir",
    "subifg_files",
]
