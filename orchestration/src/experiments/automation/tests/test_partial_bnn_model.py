"""Tests for the Partial BNN automation model wiring."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Ensure the automation package dir is importable.
AUTOMATION_DIR = Path(__file__).resolve().parent.parent
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))

# Skip the entire module if neurobayes (and jax) are not installed.
pytest.importorskip("neurobayes")

import models  # noqa: F401
from model import MODEL_REGISTRY, get_default_config


def _fast_config():
    """Small MCMC budget so tests run in seconds, not minutes."""
    return get_default_config("partial_bnn")._replace(
        num_warmup=30, num_samples=30, num_chains=1, hidden_dims=(4,)
    )


def _toy_dataset() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(42)
    X = pd.DataFrame(
        rng.normal(size=(40, 4)),
        columns=["feature[0]", "feature<1>", "feature c", "feature_d"],
    )
    y = pd.DataFrame(
        {
            "pfo-sec_q_inf_au": np.exp(0.3 * X["feature[0]"] + 0.1 * X["feature<1>"]),
            "pfo-sec_k_a_s-1": np.exp(-0.2 * X["feature c"] + 0.15 * X["feature_d"]),
        }
    )
    return X.iloc[:30], y.iloc[:30], X.iloc[30:], y.iloc[30:]


def test_partial_bnn_is_registered():
    assert "partial_bnn" in MODEL_REGISTRY


def test_partial_bnn_default_config_registered():
    cfg = get_default_config("partial_bnn")
    assert cfg.num_warmup == 1000
    assert cfg.num_samples == 1000
    assert cfg.num_chains == 1
    assert cfg.hidden_dims == (16,)


@pytest.mark.parametrize("strategy", ["shared", "separate"])
def test_partial_bnn_trains_with_both_strategies(strategy):
    X_train, y_train, X_val, y_val = _toy_dataset()
    cfg = _fast_config()

    trained = MODEL_REGISTRY["partial_bnn"](
        X_train, y_train, X_val, y_val, cfg, strategy=strategy,
    )
    preds = trained.model.predict(X_val)

    assert trained.config == cfg
    assert trained.target_names == list(y_train.columns)
    assert set(trained.metrics) == set(y_train.columns)
    assert preds.shape == (len(X_val), len(y_train.columns))
    assert np.isfinite(preds).all()


def test_partial_bnn_uses_default_config_when_none():
    X_train, y_train, X_val, y_val = _toy_dataset()

    trained = MODEL_REGISTRY["partial_bnn"](
        X_train, y_train, X_val, y_val, None, strategy="shared",
    )
    assert trained.config == get_default_config("partial_bnn")


def test_partial_bnn_rejects_unknown_strategy():
    X_train, y_train, X_val, y_val = _toy_dataset()
    cfg = _fast_config()

    with pytest.raises(ValueError, match="Unknown strategy"):
        MODEL_REGISTRY["partial_bnn"](
            X_train, y_train, X_val, y_val, cfg, strategy="bogus",
        )


def test_partial_bnn_model_is_picklable():
    import io
    import joblib

    X_train, y_train, X_val, y_val = _toy_dataset()
    cfg = _fast_config()

    trained = MODEL_REGISTRY["partial_bnn"](
        X_train, y_train, X_val, y_val, cfg, strategy="shared",
    )

    buf = io.BytesIO()
    joblib.dump(trained.model, buf)
    buf.seek(0)
    loaded = joblib.load(buf)

    preds_before = trained.model.predict(X_val)
    preds_after = loaded.predict(X_val)
    assert preds_after.shape == preds_before.shape
    assert np.allclose(preds_before, preds_after, atol=1e-5)