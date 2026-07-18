"""
LightGBM model for PFO-Sec parameter prediction.

Supports two strategies:

- **shared** (default): native LightGBM multi-output regression with
  ``lgb.train()``, ``objective="regression"``, ``num_class=6``. Tree
  splits are shared across all targets. Supports early stopping.

- **separate**: one ``LGBMRegressor`` per target via
  ``MultiOutputRegressor``. Each target gets its own set of trees.
  Does not support early stopping.
"""

import logging
import re

import lightgbm as lgb
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.multioutput import MultiOutputRegressor
from sklearn.preprocessing import StandardScaler

from model import (
    LOG_TRANSFORM_TARGETS,
    ModelConfig,
    TrainedModel,
    fit_boxcox_lambdas,
    apply_target_transforms,
    inverse_target_transforms,
    register_model,
)
from sklearn.metrics import root_mean_squared_error, r2_score

logger = logging.getLogger(__name__)


def _sanitize_feature_names(columns: list[str]) -> list[str]:
    """
    Sanitize feature names for LightGBM.

    Removes characters that LightGBM doesn't support in feature names.
    """
    return [re.sub(r"[^\w\.\-]", "_", col) for col in columns]


def _sanitize_xy(
    X_train: pd.DataFrame,
    X_val: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sanitize feature names and return copies."""
    clean_names = _sanitize_feature_names(list(X_train.columns))
    X_tr = X_train.copy()
    X_tr.columns = clean_names
    X_v = X_val.copy()
    X_v.columns = clean_names
    return X_tr, X_v


def _train_separate(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    config: ModelConfig,
) -> MultiOutputRegressor:
    """Train one ``LGBMRegressor`` per target via ``MultiOutputRegressor``."""
    base = LGBMRegressor(
        n_estimators=config.n_estimators,
        learning_rate=config.learning_rate,
        max_depth=config.max_depth,
        random_state=42,
        verbose=-1,
    )
    model = MultiOutputRegressor(base, n_jobs=-1)
    model.fit(X_train, y_train.values)
    return model


class _StackedModel:
    """Wrapper around a single ``LGBMRegressor`` trained on stacked data.

    LightGBM's Python API doesn't natively support multi-output regression
    with shared tree splits. This wrapper implements the "stacking trick":
    each sample is replicated ``n_targets`` times with an added
    ``target_index`` feature (0 .. n_targets-1), and a single model is
    trained on the flattened (n * n_targets) rows.

    If ``y_scaler`` is provided, targets are scaled before training and
    ``.predict()`` automatically inverts the scaling so downstream code
    always works with original-scale values.
    """

    def __init__(self, base_model: LGBMRegressor, n_targets: int, y_scaler: StandardScaler | None = None):
        self.base_model = base_model
        self.n_targets = n_targets
        self.y_scaler = y_scaler

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        n = len(X)
        target_idx = np.tile(np.arange(self.n_targets), n)
        X_aug = np.column_stack([np.repeat(X.values, self.n_targets, axis=0), target_idx])
        X_aug = pd.DataFrame(
            X_aug, columns=list(X.columns) + ["target_index"],
        )
        y_flat = self.base_model.predict(X_aug)
        y_pred = y_flat.reshape(-1, self.n_targets)
        if self.y_scaler is not None:
            y_pred = self.y_scaler.inverse_transform(y_pred)
        return y_pred

    @property
    def feature_importances_(self) -> np.ndarray:
        return self.base_model.feature_importances_[:self._n_features]


def _train_shared(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    X_val: pd.DataFrame,
    y_val: pd.DataFrame,
    config: ModelConfig,
) -> _StackedModel:
    """Train a single model with shared tree splits across targets."""
    n_targets = y_train.shape[1]

    scaler = StandardScaler()
    y_train_scaled = scaler.fit_transform(y_train)
    y_val_scaled = scaler.transform(y_val)

    base = LGBMRegressor(
        n_estimators=config.n_estimators,
        learning_rate=config.learning_rate,
        max_depth=config.max_depth,
        random_state=42,
        verbose=-1,
    )

    n_val = len(X_val)
    X_val_stacked = np.repeat(X_val.values, n_targets, axis=0)
    y_val_flat = y_val_scaled.ravel(order="C")
    target_idx_val = np.tile(np.arange(n_targets), n_val)
    X_val_aug = np.column_stack([X_val_stacked, target_idx_val])

    n_train = len(X_train)
    X_train_stacked = np.repeat(X_train.values, n_targets, axis=0)
    y_train_flat = y_train_scaled.ravel(order="C")
    target_idx_train = np.tile(np.arange(n_targets), n_train)
    X_train_aug = np.column_stack([X_train_stacked, target_idx_train])

    aug_columns = list(X_train.columns) + ["target_index"]
    X_train_aug = pd.DataFrame(X_train_aug, columns=aug_columns)
    X_val_aug = pd.DataFrame(X_val_aug, columns=aug_columns)

    base.fit(
        X_train_aug, y_train_flat,
        eval_set=[(X_val_aug, y_val_flat)],
        eval_metric="l2",
        callbacks=[
            lgb.early_stopping(config.early_stopping_rounds),
            lgb.log_evaluation(0),
        ],
    )

    wrapped = _StackedModel(base, n_targets, y_scaler=scaler)
    wrapped._n_features = X_train.shape[1]
    wrapped._feature_names = list(X_train.columns)
    return wrapped


@register_model("lightgbm")
def train_all_targets(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    X_val: pd.DataFrame,
    y_val: pd.DataFrame,
    config: ModelConfig | None = None,
    strategy: str = "shared",
) -> TrainedModel:
    """
    Train a multi-output model for all targets.

    Parameters
    ----------
    X_train : pd.DataFrame
        Training features.
    y_train : pd.DataFrame
        Training targets (one column per target).
    X_val : pd.DataFrame
        Validation features.
    y_val : pd.DataFrame
        Validation targets (one column per target).
    config : ModelConfig | None
        Training configuration. Uses defaults if None.
    strategy : str
        ``"shared"`` (default) or ``"separate"``.

    Returns
    -------
    TrainedModel
        Container with trained model, config, and per-target metrics.
    """
    if config is None:
        config = ModelConfig()

    target_names = list(y_train.columns)

    lambdas = fit_boxcox_lambdas(y_train)
    y_train_tfm = apply_target_transforms(y_train, lambdas)
    y_val_tfm = apply_target_transforms(y_val, lambdas)

    X_train_clean, X_val_clean = _sanitize_xy(X_train, X_val)

    logger.info(
        "Training LightGBM (strategy=%s) on %d targets (Box-Cox lambdas: %s)",
        strategy,
        y_train.shape[1],
        {k: f"{v:.3f}" for k, v in lambdas.items()},
    )

    if strategy == "shared":
        model = _train_shared(X_train_clean, y_train_tfm, X_val_clean, y_val_tfm, config)
    elif strategy == "separate":
        model = _train_separate(X_train_clean, y_train_tfm, config)
    else:
        raise ValueError(f"Unknown strategy: {strategy!r}. Choose 'shared' or 'separate'.")

    y_pred_tfm = model.predict(X_val_clean)
    y_pred = inverse_target_transforms(y_pred_tfm, target_names, lambdas)
    y_val_orig = y_val.values

    all_metrics = {}
    for i, target_name in enumerate(target_names):
        rmse = float(root_mean_squared_error(y_val_orig[:, i], y_pred[:, i]))
        r2 = float(r2_score(y_val_orig[:, i], y_pred[:, i]))
        all_metrics[target_name] = {"rmse": rmse, "r2": r2}
        logger.info("%s - RMSE: %.6f, R\u00b2: %.4f", target_name, rmse, r2)

    avg_rmse = sum(m["rmse"] for m in all_metrics.values()) / len(all_metrics)
    avg_r2 = sum(m["r2"] for m in all_metrics.values()) / len(all_metrics)
    logger.info("Aggregate - Avg RMSE: %.6f, Avg R\u00b2: %.4f", avg_rmse, avg_r2)

    return TrainedModel(
        model=model,
        config=config,
        target_names=target_names,
        metrics=all_metrics,
        lambdas=lambdas,
    )
