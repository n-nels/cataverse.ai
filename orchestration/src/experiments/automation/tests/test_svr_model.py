"""Tests for the SVR automation model wiring."""

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

import models  # noqa: E402
from model import MODEL_REGISTRY, get_default_config  # noqa: E402
from visualize import plot_feature_importance  # noqa: E402


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


def test_svr_is_registered():
    assert "svr" in MODEL_REGISTRY


def test_svr_trains_with_separate_strategy():
    X_train, y_train, X_val, y_val = _toy_dataset()

    trained = MODEL_REGISTRY["svr"](
        X_train,
        y_train,
        X_val,
        y_val,
        None,
        strategy="separate",
    )

    preds = trained.model.predict(X_val)

    assert trained.config == get_default_config("svr")
    assert trained.target_names == list(y_train.columns)
    assert set(trained.metrics) == set(y_train.columns)
    assert preds.shape == (len(X_val), len(y_train.columns))


def test_svr_uses_default_config_when_none():
    X_train, y_train, X_val, y_val = _toy_dataset()

    trained = MODEL_REGISTRY["svr"](X_train, y_train, X_val, y_val, None)

    assert trained.config == get_default_config("svr")
    assert trained.config.kernel == "rbf"
    assert trained.config.C == 1.0


def test_svr_rejects_shared_strategy():
    X_train, y_train, X_val, y_val = _toy_dataset()

    with pytest.raises(ValueError, match="only 'separate' is supported"):
        MODEL_REGISTRY["svr"](
            X_train,
            y_train,
            X_val,
            y_val,
            None,
            strategy="shared",
        )


def test_svr_rejects_unknown_strategy():
    X_train, y_train, X_val, y_val = _toy_dataset()

    with pytest.raises(ValueError, match="Unknown strategy"):
        MODEL_REGISTRY["svr"](
            X_train,
            y_train,
            X_val,
            y_val,
            None,
            strategy="bogus",
        )


def test_svr_skips_feature_importance_plot(tmp_path):
    X_train, y_train, X_val, y_val = _toy_dataset()
    trained = MODEL_REGISTRY["svr"](X_train, y_train, X_val, y_val, None)

    paths = plot_feature_importance(trained, list(X_train.columns), output_dir=tmp_path)

    assert paths == []