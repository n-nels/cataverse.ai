"""Result containers for offline IR peak fitting.

These are the in-memory bundles an EDA session works with: the plot modules in
``src/visualizations`` consume them directly, so fitting and plotting need no
round trip through disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class PeakCurve:
    """One fitted Voigt peak and its evaluated curve."""

    peak_name: str
    peak_value: float
    center: float
    amplitude: float
    sigma: float
    gamma: float
    y0: float
    fwhm: float
    peak_area: float
    curve: np.ndarray
    is_new: bool
    """True for peaks added by ``ir_fitting``; False for reconstructed live peaks."""


@dataclass
class FileFitResult:
    """Fit outcome for a single subIFG file (one delta group, one index)."""

    file_key: str
    """``delta{N}.{index}``, e.g. ``delta5.0007`` -- matches the ``File`` column."""

    delta_group: str
    subifg_path: Path
    wavenumbers: np.ndarray
    raw: np.ndarray
    baseline: np.ndarray
    corrected: np.ndarray
    composite: np.ndarray
    """Full-ROI model: reconstructed live peaks plus newly fitted peaks."""

    residual: np.ndarray
    """``composite - corrected``, matching ``spectral_fitting.objective``."""

    curves: list[PeakCurve] = field(default_factory=list)
    new_rows: list[dict] = field(default_factory=list)
    skipped_peaks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    baseline_source: str = "saved"

    @property
    def new_curves(self) -> list[PeakCurve]:
        """Only the curves for peaks this run fitted."""
        return [curve for curve in self.curves if curve.is_new]


@dataclass
class MeasurementFitResult:
    """Fit outcome for one measurement (all subIFG files sharing a base name)."""

    folder_name: str
    file_name: str
    files: list[FileFitResult] = field(default_factory=list)
    merged_params: pd.DataFrame = field(default_factory=pd.DataFrame)
    output_paths: dict[str, Path] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def n_fitted(self) -> int:
        """Number of peak rows this run added."""
        return sum(len(result.new_rows) for result in self.files)

    @property
    def n_skipped(self) -> int:
        """Number of peak/file pairs skipped because rows already existed."""
        return sum(len(result.skipped_peaks) for result in self.files)

    def summary(self) -> str:
        """One-line run summary."""
        return (
            f"{self.file_name}: {len(self.files)} files, "
            f"{self.n_fitted} rows fitted, {self.n_skipped} skipped, "
            f"{len(self.warnings)} warnings"
        )


@dataclass
class BatchFitResult:
    """Fit outcome for a whole dataset folder."""

    folder_name: str
    measurements: list[MeasurementFitResult] = field(default_factory=list)

    def summary(self) -> str:
        """One-line batch summary."""
        fitted = sum(item.n_fitted for item in self.measurements)
        skipped = sum(item.n_skipped for item in self.measurements)
        return (
            f"{self.folder_name}: {len(self.measurements)} measurements, "
            f"{fitted} rows fitted, {skipped} skipped"
        )
