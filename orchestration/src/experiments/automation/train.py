"""
Model training for PFO-Sec parameter prediction.

Trains LightGBM models for each target with early stopping.
"""

import logging
import re
from pathlib import Path
from typing import NamedTuple

import joblib
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_squared_error, r2_score

from load import build_dataset, split_dataset

logger = logging.getLogger(__name__)

# Default model directory
DEFAULT_MODEL_DIR = Path(__file__).parent / "models"


def sanitize_feature_names(columns: list[str]) -> list[str]:
    """
    Sanitize feature names for LightGBM.

    Removes characters that LightGBM doesn't support in feature names.

    Parameters
    ----------
    columns : list[str]
        Original column names.

    Returns
    -------
    list[str]
        Sanitized column names.
    """
    return [re.sub(r"[^\w\.\-]", "_", col) for col in columns]


class ModelConfig(NamedTuple):
    """Training configuration."""

    n_estimators: int = 1000
    learning_rate: float = 0.05
    max_depth: int = 6
    early_stopping_rounds: int = 50


class TrainedModel(NamedTuple):
    """Container for trained model."""

    models: dict  # {target_name: LGBMRegressor}
    config: ModelConfig
    metrics: dict  # {target_name: {rmse: float, r2: float}}


def train_target_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    target_name: str,
    config: ModelConfig,
) -> tuple[LGBMRegressor, dict]:
    """
    Train a single LightGBM model for one target.

    Parameters
    ----------
    X_train : pd.DataFrame
        Training features.
    y_train : pd.Series
        Training target.
    X_val : pd.DataFrame
        Validation features.
    y_val : pd.Series
        Validation target.
    target_name : str
        Name of the target variable.
    config : ModelConfig
        Training configuration.

    Returns
    -------
    tuple[LGBMRegressor, dict]
        Trained model and validation metrics.
    """
    model = LGBMRegressor(
        n_estimators=config.n_estimators,
        learning_rate=config.learning_rate,
        max_depth=config.max_depth,
        random_state=42,
        verbose=-1,
    )

    model.fit(
        X_train,
        y_train,
        eval_set=[(X_val, y_val)],
        callbacks=[
            __import__("lightgbm").early_stopping(config.early_stopping_rounds),
            __import__("lightgbm").log_evaluation(0),  # Silent
        ],
    )

    # Evaluate on validation set
    y_pred = model.predict(X_val)
    rmse = float(mean_squared_error(y_val, y_pred, squared=False))
    r2 = float(r2_score(y_val, y_pred))

    metrics = {"rmse": rmse, "r2": r2}
    logger.info("%s - RMSE: %.6f, R²: %.4f", target_name, rmse, r2)

    return model, metrics


def train_all_targets(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    X_val: pd.DataFrame,
    y_val: pd.DataFrame,
    config: ModelConfig | None = None,
) -> TrainedModel:
    """
    Train LightGBM models for all targets.

    Parameters
    ----------
    X_train : pd.DataFrame
        Training features.
    y_train : pd.DataFrame
        Training targets.
    X_val : pd.DataFrame
        Validation features.
    y_val : pd.DataFrame
        Validation targets.
    config : ModelConfig | None
        Training configuration. Uses defaults if None.

    Returns
    -------
    TrainedModel
        Container with trained models, config, and metrics.
    """
    if config is None:
        config = ModelConfig()

    models = {}
    all_metrics = {}

    # Sanitize feature names for LightGBM
    clean_feature_names = sanitize_feature_names(list(X_train.columns))
    X_train_clean = X_train.copy()
    X_train_clean.columns = clean_feature_names
    X_val_clean = X_val.copy()
    X_val_clean.columns = clean_feature_names

    for target_name in y_train.columns:
        logger.info("Training model for: %s", target_name)
        model, metrics = train_target_model(
            X_train_clean, y_train[target_name],
            X_val_clean, y_val[target_name],
            target_name, config,
        )
        models[target_name] = model
        all_metrics[target_name] = metrics

    # Compute aggregate metrics
    avg_rmse = sum(m["rmse"] for m in all_metrics.values()) / len(all_metrics)
    avg_r2 = sum(m["r2"] for m in all_metrics.values()) / len(all_metrics)
    logger.info("Aggregate - Avg RMSE: %.6f, Avg R²: %.4f", avg_rmse, avg_r2)

    return TrainedModel(models=models, config=config, metrics=all_metrics)


def evaluate_on_test(
    trained_model: TrainedModel,
    X_test: pd.DataFrame,
    y_test: pd.DataFrame,
) -> dict:
    """
    Evaluate trained model on test set.

    Parameters
    ----------
    trained_model : TrainedModel
        Trained model container.
    X_test : pd.DataFrame
        Test features.
    y_test : pd.DataFrame
        Test targets.

    Returns
    -------
    dict
        Test metrics per target and aggregates.
    """
    test_metrics = {}

    # Sanitize feature names for LightGBM
    clean_feature_names = sanitize_feature_names(list(X_test.columns))
    X_test_clean = X_test.copy()
    X_test_clean.columns = clean_feature_names

    for target_name, model in trained_model.models.items():
        y_pred = model.predict(X_test_clean)
        rmse = float(mean_squared_error(y_test[target_name], y_pred, squared=False))
        r2 = float(r2_score(y_test[target_name], y_pred))
        test_metrics[target_name] = {"rmse": rmse, "r2": r2}
        logger.info("Test %s - RMSE: %.6f, R²: %.4f", target_name, rmse, r2)

    # Aggregate
    avg_rmse = sum(m["rmse"] for m in test_metrics.values()) / len(test_metrics)
    avg_r2 = sum(m["r2"] for m in test_metrics.values()) / len(test_metrics)
    test_metrics["aggregate"] = {"avg_rmse": avg_rmse, "avg_r2": avg_r2}
    logger.info("Test Aggregate - Avg RMSE: %.6f, Avg R²: %.4f", avg_rmse, avg_r2)

    return test_metrics


def save_model(
    trained_model: TrainedModel,
    feature_names: list[str],
    target_names: list[str],
    model_dir: str | Path | None = None,
) -> Path:
    """
    Save trained model to disk.

    Parameters
    ----------
    trained_model : TrainedModel
        Trained model container.
    feature_names : list[str]
        Names of feature columns.
    target_names : list[str]
        Names of target columns.
    model_dir : str | Path | None
        Directory to save model. Defaults to module-relative models/.

    Returns
    -------
    Path
        Path to saved model file.
    """
    save_dir = Path(model_dir) if model_dir else DEFAULT_MODEL_DIR
    save_dir.mkdir(parents=True, exist_ok=True)

    artifacts = {
        "models": trained_model.models,
        "config": trained_model.config,
        "metrics": trained_model.metrics,
        "feature_names": sanitize_feature_names(feature_names),
        "target_names": target_names,
    }

    model_path = save_dir / "model.joblib"
    joblib.dump(artifacts, model_path)
    logger.info("Saved model to %s", model_path)

    return model_path


def load_model(model_path: str | Path) -> TrainedModel:
    """
    Load trained model from disk.

    Parameters
    ----------
    model_path : str | Path
        Path to saved model file.

    Returns
    -------
    TrainedModel
        Loaded model container.
    """
    artifacts = joblib.load(model_path)
    return TrainedModel(
        models=artifacts["models"],
        config=artifacts["config"],
        metrics=artifacts["metrics"],
    )


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("=== Building dataset ===")
    dataset = build_dataset()

    print("\n=== Splitting dataset ===")
    splits = split_dataset(dataset.X, dataset.y)

    print("\n=== Training models ===")
    config = ModelConfig()
    trained_model = train_all_targets(
        splits.X_train, splits.y_train,
        splits.X_val, splits.y_val,
        config,
    )

    print("\n=== Evaluating on test set ===")
    test_metrics = evaluate_on_test(trained_model, splits.X_test, splits.y_test)

    print("\n=== Saving model ===")
    model_path = save_model(
        trained_model,
        feature_names=list(dataset.X.columns),
        target_names=list(dataset.y.columns),
    )
    print(f"Model saved to: {model_path}")

    print("\n=== Summary ===")
    print(f"Training samples: {len(splits.X_train)}")
    print(f"Validation samples: {len(splits.X_val)}")
    print(f"Test samples: {len(splits.X_test)}")
    print(f"Features: {dataset.X.shape[1]}")
    print(f"Targets: {dataset.y.shape[1]}")
    print(f"\nTest Metrics:")
    for target, metrics in test_metrics.items():
        if target != "aggregate":
            print(f"  {target}: RMSE={metrics['rmse']:.6f}, R²={metrics['r2']:.4f}")
    print(f"  Aggregate: RMSE={test_metrics['aggregate']['avg_rmse']:.6f}, R²={test_metrics['aggregate']['avg_r2']:.4f}")
