"""
Model training for PFO-Sec parameter prediction.

Trains LightGBM models for each target with early stopping.
"""

import logging
from pathlib import Path

from load import build_dataset, split_dataset, save_dataset
from visualize import generate_all_visualizations
from model import (
    ModelConfig,
    train_all_targets,
    evaluate_on_test,
    save_model,
)

logger = logging.getLogger(__name__)

# Default model directory
DEFAULT_MODEL_DIR = Path(__file__).parent / "models"


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("=== Building dataset ===")
    dataset = build_dataset()

    print("\n=== Saving dataset ===")
    save_dir = save_dataset(dataset)

    print("\n=== Splitting dataset ===")
    splits = split_dataset(dataset.X, dataset.y)

    print("\n=== Training models ===")
    config = ModelConfig()
    trained_model = train_all_targets(
        splits.X_train, splits.y_train,
        splits.X_val, splits.y_val,
        config,
        strategy="separate",  # "shared" or "separate"
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

    print("\n=== Generating visualizations ===")
    viz_paths = generate_all_visualizations(
        dataset.y, trained_model, list(dataset.X.columns), splits.X_test,
    )
    print(f"Generated {len(viz_paths)} visualizations")

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
