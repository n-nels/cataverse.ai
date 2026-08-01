"""
K-nearest neighbors model for PFO-Sec parameter prediction.

Supports two strategies:

- **shared** (default): a single ``KNeighborsRegressor`` trained on 2D
  ``y``. Neighbor lookup is shared across all targets via scikit-learn's
  native multi-output support.

- **separate**: one ``KNeighborsRegressor`` per target via
  ``MultiOutputRegressor``. Each target gets its own regressor.

Uses the same Box-Cox target transforms as the other models for fair
comparison and standardizes features before distance-based prediction.
"""

import logging

import pandas as pd
from sklearn.metrics import root_mean_squared_error, r2_score
from sklearn.multioutput import MultiOutputRegressor
from sklearn.neighbors import KNeighborsRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from model import (
    ModelConfig,
    TrainedModel,
    apply_target_transforms,
    fit_boxcox_lambdas,
    inverse_target_transforms,
    register_default_config,
    register_model,
)

logger = logging.getLogger(__name__)

# KNN default config: brand-new baseline. KNN uses sklearn's own estimator
# defaults and ignores the shared tree/boosting fields in ModelConfig.
KNN_DEFAULT = ModelConfig()
register_default_config("knn", KNN_DEFAULT)


def _train_shared(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
) -> Pipeline:
    """Train one shared multi-output ``KNeighborsRegressor``."""
    model = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            ("regressor", KNeighborsRegressor(n_jobs=-1)),
        ]
    )
    model.fit(X_train, y_train.values)
    return model


def _train_separate(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
) -> Pipeline:
    """Train one ``KNeighborsRegressor`` per target."""
    model = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "regressor",
                MultiOutputRegressor(KNeighborsRegressor(n_jobs=-1), n_jobs=-1),
            ),
        ]
    )
    model.fit(X_train, y_train.values)
    return model


@register_model("knn")
def train_knn(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    X_val: pd.DataFrame,
    y_val: pd.DataFrame,
    config: ModelConfig | None = None,
    strategy: str = "shared",
) -> TrainedModel:
    """Train a multi-output KNN model for all targets."""
    if config is None:
        config = KNN_DEFAULT

    target_names = list(y_train.columns)

    lambdas = fit_boxcox_lambdas(y_train)
    y_train_tfm = apply_target_transforms(y_train, lambdas)
    y_val_tfm = apply_target_transforms(y_val, lambdas)

    logger.info(
        "Training KNN (strategy=%s) on %d targets (Box-Cox lambdas: %s)",
        strategy,
        y_train.shape[1],
        {k: f"{v:.3f}" for k, v in lambdas.items()},
    )

    if strategy == "shared":
        model = _train_shared(X_train, y_train_tfm)
    elif strategy == "separate":
        model = _train_separate(X_train, y_train_tfm)
    else:
        raise ValueError(f"Unknown strategy: {strategy!r}. Choose 'shared' or 'separate'.")

    y_pred_tfm = model.predict(X_val)
    y_pred = inverse_target_transforms(y_pred_tfm, target_names, lambdas)
    y_val_orig = y_val.values

    all_metrics = {}
    for i, target_name in enumerate(target_names):
        rmse = float(root_mean_squared_error(y_val_orig[:, i], y_pred[:, i]))
        r2 = float(r2_score(y_val_orig[:, i], y_pred[:, i]))
        all_metrics[target_name] = {"rmse": rmse, "r2": r2}
        logger.info("%s - RMSE: %.6f, R²: %.4f", target_name, rmse, r2)

    avg_rmse = sum(m["rmse"] for m in all_metrics.values()) / len(all_metrics)
    avg_r2 = sum(m["r2"] for m in all_metrics.values()) / len(all_metrics)
    logger.info("Aggregate - Avg RMSE: %.6f, Avg R²: %.4f", avg_rmse, avg_r2)

    return TrainedModel(
        model=model,
        config=config,
        target_names=target_names,
        metrics=all_metrics,
        lambdas=lambdas,
    )
