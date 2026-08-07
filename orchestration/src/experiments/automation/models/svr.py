"""
Support Vector Regression model for PFO-Sec parameter prediction.

SVR is inherently single-output, so this model only supports the ``separate``
strategy: one ``SVR`` per target via ``MultiOutputRegressor``. The ``shared``
strategy is rejected because scikit-learn's ``SVR`` has no native multi-output
support.

Uses the same Box-Cox target transforms as the other models for fair
comparison and standardizes features before distance-based prediction.
"""

import logging

import numpy as np
import pandas as pd
from sklearn.metrics import root_mean_squared_error, r2_score
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR

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

# SVR default config: brand-new baseline. Uses sklearn's own SVR estimator
# defaults (kernel="rbf", C=1.0, epsilon=0.1, gamma="scale", degree=3,
# coef0=0.0) and ignores the shared tree/boosting fields in ModelConfig.
SVR_DEFAULT = ModelConfig()
register_default_config("svr", SVR_DEFAULT)


def _make_svr(config: ModelConfig) -> SVR:
    return SVR(
        kernel=config.kernel,
        C=config.C,
        epsilon=config.epsilon,
        gamma=config.svr_gamma,
        degree=config.degree,
        coef0=config.coef0,
    )


def _train_separate(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    config: ModelConfig,
) -> Pipeline:
    """Train one ``SVR`` per target via ``MultiOutputRegressor``."""
    model = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            ("regressor", MultiOutputRegressor(_make_svr(config), n_jobs=-1)),
        ]
    )
    model.fit(X_train, y_train.values)
    return model


@register_model("svr")
def train_svr(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    X_val: pd.DataFrame,
    y_val: pd.DataFrame,
    config: ModelConfig | None = None,
    strategy: str = "separate",
) -> TrainedModel:
    """Train a multi-output SVR model for all targets.

    Only ``strategy="separate"`` is supported because scikit-learn's ``SVR``
    is single-output.
    """
    if config is None:
        config = SVR_DEFAULT

    target_names = list(y_train.columns)

    lambdas = fit_boxcox_lambdas(y_train)
    y_train_tfm = apply_target_transforms(y_train, lambdas)
    y_val_tfm = apply_target_transforms(y_val, lambdas)

    logger.info(
        "Training SVR (strategy=%s) on %d targets (Box-Cox lambdas: %s)",
        strategy,
        y_train.shape[1],
        {k: f"{v:.3f}" for k, v in lambdas.items()},
    )

    if strategy == "separate":
        model = _train_separate(X_train, y_train_tfm, config)
    else:
        raise ValueError(
            f"Unknown strategy: {strategy!r}. SVR is single-output; "
            "only 'separate' is supported."
        )

    y_pred_tfm = model.predict(X_val)
    y_pred = inverse_target_transforms(y_pred_tfm, target_names, lambdas)
    if hasattr(y_pred, "shape") and not np.isfinite(y_pred).all():
        raise ValueError(
            "SVR predictions contain NaN/Inf — config likely too extreme "
            f"(kernel={config.kernel}, C={config.C}, svr_gamma={config.svr_gamma})"
        )
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