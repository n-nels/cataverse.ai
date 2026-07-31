"""
XGBoost model for PFO-Sec parameter prediction.

Supports two strategies:

- **shared** (default): native XGBoost multi-output regression with
  ``multi_strategy="multi_output_tree"``. Tree structure is shared across
  all targets. Supports early stopping.

- **separate**: native XGBoost multi-output regression with
  ``multi_strategy="one_output_per_tree"``. Each target gets its own trees.
  Supports early stopping.
"""

import logging

import pandas as pd
from sklearn.metrics import root_mean_squared_error, r2_score
from xgboost import XGBRegressor

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

# XGBoost default config: optimized via autoresearch campaign xgboost_v3_0001
# (trial 5, strategy="separate"). Best validation avg RMSE 0.127288 vs
# baseline 0.145436 (12.5% relative improvement).
XGBOOST_DEFAULT = ModelConfig(
    n_estimators=1091,
    learning_rate=0.138458,
    max_depth=13,
    subsample=0.76054,
    colsample_bytree=0.418369,
    reg_alpha=2.44694,
    reg_lambda=2.478752,
    early_stopping_rounds=37,
    random_state=233,
    min_child_weight=16.983727,
    gamma=0.853505,
)
register_default_config("xgboost", XGBOOST_DEFAULT)


def _build_regressor(config: ModelConfig, multi_strategy: str) -> XGBRegressor:
    """Build an ``XGBRegressor`` with the repo's shared config fields."""
    return XGBRegressor(
        objective="reg:squarederror",
        n_estimators=config.n_estimators,
        learning_rate=config.learning_rate,
        max_depth=config.max_depth,
        subsample=config.subsample,
        colsample_bytree=config.colsample_bytree,
        reg_alpha=config.reg_alpha,
        reg_lambda=config.reg_lambda,
        min_child_weight=config.min_child_weight,
        gamma=config.gamma,
        early_stopping_rounds=config.early_stopping_rounds,
        random_state=config.random_state,
        n_jobs=-1,
        tree_method="hist",
        eval_metric="rmse",
        multi_strategy=multi_strategy,
        verbosity=0,
    )


def _as_matrix(X: pd.DataFrame):
    """Return raw values so XGBoost doesn't reject repo feature names.

    The existing feature set includes characters like ``[`` and ``<`` in some
    names. XGBoost rejects those names during fitting, so we train on raw numpy
    matrices while leaving the actual feature definitions untouched.
    """
    return X.values


@register_model("xgboost")
def train_xgboost(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    X_val: pd.DataFrame,
    y_val: pd.DataFrame,
    config: ModelConfig | None = None,
    strategy: str = "separate",
) -> TrainedModel:
    """Train a multi-output XGBoost model for all targets."""
    if config is None:
        config = XGBOOST_DEFAULT

    target_names = list(y_train.columns)

    lambdas = fit_boxcox_lambdas(y_train)
    y_train_tfm = apply_target_transforms(y_train, lambdas)
    y_val_tfm = apply_target_transforms(y_val, lambdas)

    logger.info(
        "Training XGBoost (strategy=%s) on %d targets (Box-Cox lambdas: %s)",
        strategy,
        y_train.shape[1],
        {k: f"{v:.3f}" for k, v in lambdas.items()},
    )

    if strategy == "shared":
        model = _build_regressor(config, multi_strategy="multi_output_tree")
    elif strategy == "separate":
        model = _build_regressor(config, multi_strategy="one_output_per_tree")
    else:
        raise ValueError(f"Unknown strategy: {strategy!r}. Choose 'shared' or 'separate'.")

    model.fit(
        _as_matrix(X_train),
        y_train_tfm.values,
        eval_set=[(_as_matrix(X_val), y_val_tfm.values)],
        verbose=False,
    )

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
