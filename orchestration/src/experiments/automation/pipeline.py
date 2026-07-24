"""
Reusable training pipeline for PFO-Sec parameter prediction.

Extracts the build -> split -> train -> evaluate flow so that both the
``train.py`` CLI and the autonomous experiment harness can call the same
functions without duplicating dataset assembly, Box-Cox transforms, splitting,
or metric calculation.

This module must NOT reimplement logic that lives in ``load`` or ``model``.
It only composes those existing functions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

import models  # noqa: F401 — trigger model registration
from load import Dataset, DatasetSplit, build_dataset, load_dataset, save_dataset, split_dataset
from model import MODEL_REGISTRY, ModelConfig, TrainedModel, evaluate_baseline, evaluate_on_test

logger = logging.getLogger(__name__)

DEFAULT_OUTPUTS_DIR = Path(__file__).parent / "outputs"


def prepare_dataset(
    data_dir: str | Path | None = None,
    build_fresh: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return the feature/target matrices.

    Parameters
    ----------
    data_dir : str | Path | None
        Directory containing ``X.parquet`` / ``y.parquet``. If ``build_fresh``
        is False and ``data_dir`` is given (or defaults to the package
        ``outputs/`` dir), the cached dataset is loaded. If ``build_fresh``
        is True, the full extraction pipeline runs from ``data_dir`` (which
        then acts as the raw ``data_root`` for :func:`build_dataset`).
    """
    if build_fresh:
        dataset = build_dataset(data_root=str(data_dir) if data_dir else None)
        return dataset.X, dataset.y

    out_dir = Path(data_dir) if data_dir else DEFAULT_OUTPUTS_DIR
    return load_dataset(out_dir)


def prepare_splits(
    X: pd.DataFrame,
    y: pd.DataFrame,
) -> DatasetSplit:
    """Split a dataset using the canonical split logic (seed 42)."""
    return split_dataset(X, y)


def train_model(
    splits: DatasetSplit,
    model_name: str,
    config: ModelConfig | None = None,
    strategy: str = "shared",
) -> TrainedModel:
    """Train a registered model on the given splits."""
    if model_name not in MODEL_REGISTRY:
        raise KeyError(
            f"Unknown model {model_name!r}. Registered: {sorted(MODEL_REGISTRY)}"
        )
    trainer = MODEL_REGISTRY[model_name]
    return trainer(
        splits.X_train, splits.y_train,
        splits.X_val, splits.y_val,
        config,
        strategy=strategy,
    )


def validation_metrics(trained_model: TrainedModel) -> dict[str, dict[str, float]]:
    """Per-target validation metrics from a trained model.

    ``TrainedModel.metrics`` is populated by the trainer against the validation
    set, so this simply returns it. Exposed as a function so callers do not
    reach into the named tuple directly.
    """
    return trained_model.metrics


def validation_avg_rmse(trained_model: TrainedModel) -> float:
    """Primary optimization metric: mean per-target validation RMSE."""
    metrics = trained_model.metrics
    return sum(m["rmse"] for m in metrics.values()) / len(metrics)


def validation_avg_r2(trained_model: TrainedModel) -> float:
    return sum(m["r2"] for m in trained_model.metrics.values()) / len(trained_model.metrics)


def test_metrics(trained_model: TrainedModel, splits: DatasetSplit) -> dict:
    """Evaluate a trained model on the held-out test set."""
    return evaluate_on_test(trained_model, splits.X_test, splits.y_test)


def reference_baseline(splits: DatasetSplit) -> dict:
    """Mean-prediction reference baseline (sanity check, not the keep anchor)."""
    return evaluate_baseline(splits.y_train, splits.y_test)