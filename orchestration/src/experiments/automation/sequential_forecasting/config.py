"""Shared sequential forecasting run configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .data.contract import DEFAULT_TIME_TOLERANCE_S, TARGET_COLUMNS


DEFAULT_DATA_ROOT = r"X:\peakFit"
DEFAULT_EXCLUDE_FOLDERS = ("test", "nn1120-4_pd_ceo2_000")
DEFAULT_ARTIFACT_DIR = (
    Path(__file__).parent.parent / "artifacts" / "sequential_forecasting"
)
DEFAULT_MODEL_PATH = Path(__file__).parent.parent / "models" / "random_forest.joblib"
DEFAULT_ODE_FIT_MODE = "secondary_pfo"
DEFAULT_ODE_TIMEOUT_SECONDS = 0.1
DEFAULT_MINIMUM_FIT_POINTS = 4


@dataclass(frozen=True)
class RunConfig:
    """Reproducibility configuration for sequential data preparation."""

    data_root: str = DEFAULT_DATA_ROOT
    exclude_folders: tuple[str, ...] = DEFAULT_EXCLUDE_FOLDERS
    artifact_dir: str = str(DEFAULT_ARTIFACT_DIR)
    model_path: str = str(DEFAULT_MODEL_PATH)
    minimum_fit_points: int = DEFAULT_MINIMUM_FIT_POINTS
    cutoff_policy: str = "every flattened monomer observation through final time"
    time_tolerance_s: float = DEFAULT_TIME_TOLERANCE_S
    split_seed: int = 42
    train_ratio: float = 0.8
    val_ratio: float = 0.2
    target_order: tuple[str, ...] = TARGET_COLUMNS
    oof_folds: int = 5
    ode_fit_mode: str = DEFAULT_ODE_FIT_MODE
    ode_timeout_seconds: float = DEFAULT_ODE_TIMEOUT_SECONDS
    ode_initial_guess: tuple[float, ...] | None = None
    ode_prior_fit_carry_forward: bool = False
