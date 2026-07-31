"""Tests for the XGBoost automation model wiring."""

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

import models  # noqa: F401
from model import MODEL_REGISTRY, ModelConfig, get_feature_importances


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


def test_xgboost_is_registered():
    assert "xgboost" in MODEL_REGISTRY


@pytest.mark.parametrize("strategy", ["shared", "separate"])
def test_xgboost_trains_and_exposes_feature_importance(strategy):
    X_train, y_train, X_val, y_val = _toy_dataset()

    trained = MODEL_REGISTRY["xgboost"](
        X_train,
        y_train,
        X_val,
        y_val,
        ModelConfig(n_estimators=20, learning_rate=0.1, max_depth=3, early_stopping_rounds=5),
        strategy=strategy,
    )

    preds = trained.model.predict(X_val)
    importance = get_feature_importances(trained)

    assert trained.target_names == list(y_train.columns)
    assert set(trained.metrics) == set(y_train.columns)
    assert preds.shape == (len(X_val), len(y_train.columns))
    assert importance.shape == (X_train.shape[1],)
    assert np.isfinite(importance).all()


def test_xgboost_rejects_unknown_strategy():
    X_train, y_train, X_val, y_val = _toy_dataset()

    with pytest.raises(ValueError, match="Unknown strategy"):
        MODEL_REGISTRY["xgboost"](
            X_train,
            y_train,
            X_val,
            y_val,
            ModelConfig(n_estimators=5, early_stopping_rounds=2),
            strategy="bogus",
        )
