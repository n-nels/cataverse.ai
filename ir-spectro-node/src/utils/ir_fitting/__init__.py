"""Offline IR peak-fitting package for EDA and reprocessing.

Wraps ``src/analysis/spectral_fitting.py`` rather than duplicating it. Never
invoked by the live server path and never writes into source data -- output goes
to a ``_test`` subfolder. See ``spec.md`` for the design.
"""

from src.utils.ir_fitting.api import (
    fit_file,
    fit_folder,
    load_measurement,
    subifg_dir,
)

__all__ = [
    "fit_file",
    "fit_folder",
    "load_measurement",
    "subifg_dir",
]
