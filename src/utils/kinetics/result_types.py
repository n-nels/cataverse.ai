"""Result container types for kinetics API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class FitRunResult:
    path: Path
    model: str | None
    mode: str | None
    n_rows_input: int
    n_rows_fit: int
    output_path: Path | None
    metrics_summary: dict[str, float]
    warnings: list[str]
    fit_params: pd.DataFrame


@dataclass
class BatchFitResult:
    dataset_folder: Path
    n_files_found: int
    n_files_success: int
    n_files_failed: int
    outputs: list[Path]
    failures: dict[str, str]
