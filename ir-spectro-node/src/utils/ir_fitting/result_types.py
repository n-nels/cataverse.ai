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


def _matches(file_key: str, delta_group: str, pattern: str) -> bool:
    """Return True if ``pattern`` selects this file.

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
                _matches(result.file_key, result.delta_group, pattern)
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
                _matches(result.file_key, result.delta_group, pattern)
                for pattern in patterns
            )
        ]

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
class BaselineTrace:
    """One baseline variant evaluated on one subIFG file."""

    label: str
    settings: dict
    window: tuple[float, float]
    wavenumbers: np.ndarray
    raw: np.ndarray
    baseline: np.ndarray

    degenerate: bool = False
    """``std_distribution`` found no baseline points -- the curve is not real."""

    moved_pct_of_range: float = 0.0
    """How far this baseline sits from the reference variant's.

    Percentage of the reference's signal range over the region the two share.
    It says the baseline *moved*, not that moving it was an improvement -- no
    quality score is available here (see ``spec.md`` section 14.8).
    """

    compared_over: tuple[float, float] | None = None
    """``(high, low)`` region :attr:`moved_pct_of_range` was measured over.

    Not always the full window: variants with different windows are compared on
    their overlap, and the number is uninterpretable without knowing which.
    """

    @property
    def corrected(self) -> np.ndarray:
        """Baseline-subtracted signal."""
        return self.raw - self.baseline

    @property
    def is_reference(self) -> bool:
        """True for the variant everything else is measured against."""
        return self.compared_over is None


@dataclass
class FileBaselineComparison:
    """Every baseline variant evaluated on one subIFG file."""

    file_key: str
    delta_group: str
    subifg_path: Path
    verdict: str = ""
    """``"bad"`` / ``"good"`` / ``""`` -- an eye judgement, not a measurement."""

    traces: list[BaselineTrace] = field(default_factory=list)

    @property
    def reference(self) -> BaselineTrace | None:
        """The first variant, which the others are compared against."""
        return self.traces[0] if self.traces else None


@dataclass
class BaselineComparison:
    """A baseline experiment across one or more subIFG files."""

    folder_name: str
    run_name: str
    files: list[FileBaselineComparison] = field(default_factory=list)
    table: pd.DataFrame = field(default_factory=pd.DataFrame)
    figure_paths: list[Path] = field(default_factory=list)
    table_path: Path | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def n_degenerate(self) -> int:
        """Number of (file, variant) pairs that produced no real baseline."""
        return sum(
            1 for item in self.files for trace in item.traces if trace.degenerate
        )

    def summary(self) -> str:
        """One-line run summary."""
        n_variants = len(self.files[0].traces) if self.files else 0
        return (
            f"{self.run_name}: {len(self.files)} files x {n_variants} variants, "
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
        skipped = sum(item.n_skipped for item in self.measurements)
        return (
            f"{self.folder_name}: {len(self.measurements)} measurements, "
            f"{fitted} rows fitted, {skipped} skipped"
        )
