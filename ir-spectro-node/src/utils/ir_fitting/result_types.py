"""Result containers for offline IR peak fitting.

These are the in-memory bundles an EDA session works with: the plot modules in
``src/visualizations`` consume them directly, so fitting and plotting need no
round trip through disk.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path

import numpy as np
import pandas as pd

LOGGER = logging.getLogger(__name__)


def matches_file_key(file_key: str, delta_group: str, pattern: str) -> bool:
    """Return True if ``pattern`` selects this file.

    The single file-selection vocabulary for the package: both
    :meth:`MeasurementFitResult.select` (the plotting path) and
    ``api.subifg_files`` (the baseline path) go through here, so
    ``["delta10"]`` means the same thing in both.

    A pattern is one of:

    - an exact file key, ``"delta5.0007"``
    - a whole delta group, ``"delta5"`` -- every index in it
    - a glob against the file key, ``"delta5.00*"``

    A bare group name never collides with a file key, since file keys always
    carry a ``.index`` suffix.
    """
    if pattern == file_key or pattern == delta_group:
        return True
    return fnmatchcase(file_key, pattern)


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
    """True when the saved fit had no row for this peak in this file (a peak the
    refit added); False for refitted existing peaks and reconstructed saved ones."""


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
    """Full-ROI model: the sum of every curve in ``curves``."""

    residual: np.ndarray
    """``composite - corrected``, matching ``spectral_fitting.objective``."""

    curves: list[PeakCurve] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    """Params-CSV rows this refit produced, one per peak. Empty when loaded."""

    warnings: list[str] = field(default_factory=list)
    baseline_source: str = "saved"
    n_seeded: int = 0
    """Peaks that started from their saved fit rather than their rule."""

    n_clipped: int = 0
    """Seed values clipped into their rule bounds."""

    n_nudged: int = 0
    """Seed values moved off a bound so the optimizer can move them."""

    nfev: int = 0
    """Objective evaluations the optimizer used; 0 when nothing was fitted."""

    fit_success: bool = True
    """lmfit's ``success``; False when ``leastsq`` hit its evaluation cap."""

    @property
    def new_curves(self) -> list[PeakCurve]:
        """Only the curves for peaks the saved fit did not have."""
        return [curve for curve in self.curves if curve.is_new]


@dataclass
class MeasurementFitResult:
    """Fit outcome for one measurement (all subIFG files sharing a base name)."""

    folder_name: str
    file_name: str
    files: list[FileFitResult] = field(default_factory=list)
    params: pd.DataFrame = field(default_factory=pd.DataFrame)
    """This run's output rows (live schema); only refitted files appear."""

    output_paths: dict[str, Path] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def select(self, file_keys: list[str] | None = None) -> list[FileFitResult]:
        """Return the files matching ``file_keys``, in measurement order.

        Each entry may be an exact file key (``"delta5.0007"``), a whole delta
        group (``"delta5"`` -- every index in it), or a glob against the file key
        (``"delta5.00*"``). ``None`` returns every file.

        Results are deduplicated, so overlapping entries such as
        ``["delta5", "delta5.0007"]`` plot each file once.

        A pattern matching nothing is logged rather than silently ignored -- a
        typo would otherwise just produce no output.
        """
        if file_keys is None:
            return list(self.files)
        if isinstance(file_keys, str):
            raise TypeError(
                "file_keys must be a list of patterns, not a string; "
                f"pass [{file_keys!r}] instead."
            )

        patterns = list(file_keys)
        unmatched = [
            pattern
            for pattern in patterns
            if not any(
                matches_file_key(result.file_key, result.delta_group, pattern)
                for result in self.files
            )
        ]
        if unmatched:
            LOGGER.warning(
                "%s: no files matched %s. Available delta groups: %s",
                self.file_name,
                unmatched,
                sorted({result.delta_group for result in self.files}),
            )

        # Iterate self.files once so order is preserved and duplicates collapse.
        return [
            result
            for result in self.files
            if any(
                matches_file_key(result.file_key, result.delta_group, pattern)
                for pattern in patterns
            )
        ]

    @property
    def n_fitted(self) -> int:
        """Number of peak rows this run produced."""
        return sum(len(result.rows) for result in self.files)

    @property
    def n_clipped(self) -> int:
        """Seed values clipped into their bounds, across every file."""
        return sum(result.n_clipped for result in self.files)

    def summary(self) -> str:
        """One-line run summary."""
        return (
            f"{self.file_name}: {len(self.files)} files, "
            f"{self.n_fitted} rows fitted, {self.n_clipped} seeds clipped, "
            f"{len(self.warnings)} warnings"
        )


@dataclass
class FileBaseline:
    """One baseline recipe evaluated on one subIFG file."""

    file_key: str
    delta_group: str
    subifg_path: Path
    wavenumbers: np.ndarray
    raw: np.ndarray
    baseline: np.ndarray
    degenerate: bool = False
    """``std_distribution`` found no baseline points -- the curve is not real."""

    anchors_applied: tuple[float, ...] = ()
    lower_anchors_applied: tuple[float, ...] = ()
    split_applied: float | None = None

    @property
    def corrected(self) -> np.ndarray:
        """Baseline-subtracted signal."""
        return self.raw - self.baseline


@dataclass
class BaselineRun:
    """One baseline recipe run across one or more subIFG files."""

    folder_name: str
    run_name: str
    label: str
    files: list[FileBaseline] = field(default_factory=list)
    figure_paths: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def n_degenerate(self) -> int:
        """Number of files that produced no real baseline."""
        return sum(1 for item in self.files if item.degenerate)

    def summary(self) -> str:
        """One-line run summary."""
        return (
            f"{self.run_name}: {len(self.files)} files, "
            f"{len(self.figure_paths)} figures, "
            f"{self.n_degenerate} degenerate baselines"
        )


@dataclass
class BatchFitResult:
    """Fit outcome for a whole dataset folder."""

    folder_name: str
    measurements: list[MeasurementFitResult] = field(default_factory=list)

    def summary(self) -> str:
        """One-line batch summary."""
        fitted = sum(item.n_fitted for item in self.measurements)
        return (
            f"{self.folder_name}: {len(self.measurements)} measurements, "
            f"{fitted} rows fitted"
        )
