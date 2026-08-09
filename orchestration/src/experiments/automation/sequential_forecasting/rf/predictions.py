"""Held-out RF prediction export for sequential inputs."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold

from model import TrainedModel, inverse_target_transforms
from models.random_forest import train_random_forest
from load import DatasetSplit


def _predict(model: TrainedModel, features: pd.DataFrame) -> np.ndarray:
    """Predict in original target units."""
    transformed = model.model.predict(features)
    return inverse_target_transforms(transformed, model.target_names, model.lambdas)


def _oof_predictions(
    model: TrainedModel,
    X_train_val: pd.DataFrame,
    y_train_val: pd.DataFrame,
    *,
    folds: int,
    seed: int,
) -> pd.DataFrame:
    """Generate fold-held-out predictions for train and validation records."""
    if folds < 2 or folds > len(X_train_val):
        raise ValueError("oof_folds must be between 2 and the training-record count")
    splitter = KFold(n_splits=folds, shuffle=True, random_state=seed)
    rows: list[dict[str, object]] = []
    for fold, (fit_indices, holdout_indices) in enumerate(
        splitter.split(X_train_val), start=1
    ):
        fold_model = train_random_forest(
            X_train_val.iloc[fit_indices],
            y_train_val.iloc[fit_indices],
            X_train_val.iloc[holdout_indices],
            y_train_val.iloc[holdout_indices],
            config=model.config,
            strategy="separate",
        )
        predictions = _predict(fold_model, X_train_val.iloc[holdout_indices])
        for row_index, values in zip(holdout_indices, predictions, strict=True):
            row: dict[str, object] = {
                "base_name": str(X_train_val.index[row_index]),
                "prediction_provenance": "out_of_fold",
                "fold_id": fold,
                "training_experiment_count": len(fit_indices),
            }
            row.update(
                {
                    name: float(value)
                    for name, value in zip(model.target_names, values, strict=True)
                }
            )
            rows.append(row)
    return pd.DataFrame(rows).sort_values("base_name").reset_index(drop=True)


def export_predictions(
    model: TrainedModel,
    splits: DatasetSplit,
    *,
    folds: int,
    seed: int,
) -> pd.DataFrame:
    """Export held-out train/validation and held-out test RF predictions."""
    train_val_X = pd.concat([splits.X_train, splits.X_val])
    train_val_y = pd.concat([splits.y_train, splits.y_val])
    predictions = _oof_predictions(
        model,
        train_val_X,
        train_val_y,
        folds=folds,
        seed=seed,
    )
    test_values = _predict(model, splits.X_test)
    test_rows: list[dict[str, object]] = []
    for base_name, values in zip(splits.X_test.index, test_values, strict=True):
        row: dict[str, object] = {
            "base_name": str(base_name),
            "prediction_provenance": "held_out_test",
            "fold_id": None,
            "training_experiment_count": len(splits.X_train),
        }
        row.update(
            {
                name: float(value)
                for name, value in zip(model.target_names, values, strict=True)
            }
        )
        test_rows.append(row)
    return pd.concat([predictions, pd.DataFrame(test_rows)], ignore_index=True).sort_values(
        "base_name"
    ).reset_index(drop=True)
