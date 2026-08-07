"""
Partial Bayesian neural network model for PFO-Sec parameter prediction.

Uses the ``PartialBNN`` from `neurobayes` (ported from the legacy
``decision_engine.ActiveLearningEngine.train_partial_bnn``): a neural
network where the first and last dense layers have probabilistic (Bayesian)
weights sampled via NUTS MCMC, while the remaining hidden layers use
deterministic (point-estimate) weights.

Supports two strategies:

- **shared** (default): a single ``PartialBNN`` with
  ``target_dim=n_targets``. The probabilistic layers are shared across all
  targets.

- **separate**: one ``PartialBNN`` per target (``target_dim=1``), each with
  its own posterior. Matches the legacy per-target training pattern.

Same Box-Cox target transforms as the other models for fair comparison.
Features are standardized before training. The fitted model is stored as
MCMC samples + deterministic weights in a picklable wrapper (the neurobayes
model object itself is not joblib-picklable due to jax activation function
references).
"""

import logging

import numpy as np
import pandas as pd
from sklearn.metrics import root_mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler

import neurobayes as nb

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

# Partial BNN default config: conservative MCMC settings matching the legacy
# usage (num_warmup=1000, num_samples=1000, num_chains=1, hidden_dims=[16]).
# The tree/boosting fields in ModelConfig are ignored by this trainer.
PARTIAL_BNN_DEFAULT = ModelConfig(
    num_warmup=1000,
    num_samples=1000,
    num_chains=1,
    hidden_dims=(16,),
)
register_default_config("partial_bnn", PARTIAL_BNN_DEFAULT)


class _PartialBNNWrapper:
    """Picklable wrapper around a fitted single- or multi-output PartialBNN.

    Stores the MCMC posterior samples and deterministic weights instead of
    the model object itself (which is not joblib-picklable due to jax
    activation function references). Reconstructs the architecture on demand
    for prediction.
    """

    def __init__(
        self,
        hidden_dims,
        target_dim,
        probabilistic_layer_names,
        samples,
        deterministic_weights,
        X_scaler,
        y_scaler,
    ):
        self.hidden_dims = hidden_dims
        self.target_dim = target_dim
        self.probabilistic_layer_names = probabilistic_layer_names
        self.samples = samples
        self.deterministic_weights = deterministic_weights
        self.X_scaler = X_scaler
        self.y_scaler = y_scaler

    def _build_model(self):
        net = nb.FlaxMLP(
            hidden_dims=list(self.hidden_dims), target_dim=self.target_dim
        )
        model = nb.PartialBNN(
            net, probabilistic_layer_names=list(self.probabilistic_layer_names)
        )
        model._model.deterministic_weights = self.deterministic_weights
        return model

    def predict(self, X):
        X_scaled = np.asarray(self.X_scaler.transform(X), dtype=np.float32)
        model = self._build_model()
        mean, _ = model._model.predict(X_scaled, samples=self.samples)
        mean = np.asarray(mean)
        if self.y_scaler is not None:
            mean = self.y_scaler.inverse_transform(mean)
        return mean


class _PartialBNNSeparate:
    """Multi-output wrapper holding one single-output PartialBNN per target."""

    def __init__(self, wrappers):
        self.wrappers = wrappers

    def predict(self, X):
        preds = [w.predict(X).flatten() for w in self.wrappers]
        return np.column_stack(preds)


@register_model("partial_bnn")
def train_partial_bnn(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    X_val: pd.DataFrame,
    y_val: pd.DataFrame,
    config: ModelConfig | None = None,
    strategy: str = "shared",
) -> TrainedModel:
    """Train a multi-output Partial Bayesian neural network for all targets."""
    if config is None:
        config = PARTIAL_BNN_DEFAULT

    target_names = list(y_train.columns)
    n_targets = len(target_names)

    lambdas = fit_boxcox_lambdas(y_train)
    y_train_tfm = apply_target_transforms(y_train, lambdas)
    y_val_tfm = apply_target_transforms(y_val, lambdas)

    hidden_dims = list(config.hidden_dims)
    prob_layer_names = ["Dense0", f"Dense{len(hidden_dims)}"]

    X_scaler = StandardScaler()
    X_scaled = X_scaler.fit_transform(X_train)

    logger.info(
        "Training PartialBNN (strategy=%s) on %d targets (Box-Cox lambdas: %s)",
        strategy,
        n_targets,
        {k: f"{v:.3f}" for k, v in lambdas.items()},
    )

    if strategy == "shared":
        y_scaler = StandardScaler()
        y_scaled = y_scaler.fit_transform(y_train_tfm.values)
        net = nb.FlaxMLP(hidden_dims=hidden_dims, target_dim=n_targets)
        model = nb.PartialBNN(net, probabilistic_layer_names=prob_layer_names)
        model.fit(
            X_scaled,
            y_scaled,
            num_warmup=config.num_warmup,
            num_samples=config.num_samples,
            num_chains=config.num_chains,
            progress_bar=False,
        )
        wrapper = _PartialBNNWrapper(
            hidden_dims,
            n_targets,
            prob_layer_names,
            model._model.mcmc.get_samples(),
            model._model.deterministic_weights,
            X_scaler,
            y_scaler,
        )
    elif strategy == "separate":
        wrappers = []
        for i, target_name in enumerate(target_names):
            y_i = y_train_tfm.iloc[:, i].values.reshape(-1, 1)
            y_scaler = StandardScaler()
            y_scaled = y_scaler.fit_transform(y_i)
            net = nb.FlaxMLP(hidden_dims=hidden_dims, target_dim=1)
            model = nb.PartialBNN(net, probabilistic_layer_names=prob_layer_names)
            model.fit(
                X_scaled,
                y_scaled,
                num_warmup=config.num_warmup,
                num_samples=config.num_samples,
                num_chains=config.num_chains,
                progress_bar=False,
            )
            wrappers.append(
                _PartialBNNWrapper(
                    hidden_dims,
                    1,
                    prob_layer_names,
                    model._model.mcmc.get_samples(),
                    model._model.deterministic_weights,
                    X_scaler,
                    y_scaler,
                )
            )
            logger.info(
                "Trained separate PartialBNN for target %d/%d (%s)",
                i + 1,
                n_targets,
                target_name,
            )
        wrapper = _PartialBNNSeparate(wrappers)
    else:
        raise ValueError(
            f"Unknown strategy: {strategy!r}. Choose 'shared' or 'separate'."
        )

    y_pred_tfm = wrapper.predict(X_val)
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
        model=wrapper,
        config=config,
        target_names=target_names,
        metrics=all_metrics,
        lambdas=lambdas,
    )