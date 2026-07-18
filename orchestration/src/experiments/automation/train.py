"""Model training for PFO-Sec parameter prediction."""

import argparse
import logging
from pathlib import Path

import models  # noqa: F401 — trigger model registration
from load import build_dataset, split_dataset, save_dataset
from visualize import generate_all_visualizations
from model import (
    MODEL_REGISTRY,
    ModelConfig,
    evaluate_on_test,
    evaluate_baseline,
    save_model,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL_DIR = Path(__file__).parent / "models"


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Train a PFO-Sec parameter prediction model.")
    parser.add_argument(
        "--model",
        default="lightgbm",
        choices=sorted(MODEL_REGISTRY),
        help="Model to train (default: lightgbm)",
    )
    parser.add_argument(
        "--strategy",
        default="shared",
        choices=["shared", "separate"],
        help="Training strategy for LightGBM (default: shared, ignored by other models)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("=== Building dataset ===")
    dataset = build_dataset()

    print("\n=== Saving dataset ===")
    save_dir = save_dataset(dataset)

    print("\n=== Splitting dataset ===")
    splits = split_dataset(dataset.X, dataset.y)

    print(f"\n=== Training model: {args.model} ===")
    config = ModelConfig()
    trainer = MODEL_REGISTRY[args.model]

    # All trainers accept strategy (unused by some); pass it uniformly
    trained_model = trainer(
        splits.X_train, splits.y_train,
        splits.X_val, splits.y_val,
        config,
        strategy=args.strategy,
    )

    print("\n=== Evaluating on test set ===")
    test_metrics = evaluate_on_test(trained_model, splits.X_test, splits.y_test)

    print("\n=== Baseline (training mean) ===")
    baseline_metrics = evaluate_baseline(splits.y_train, splits.y_test)
    print("  Baseline predicts training mean for every test sample — uses no features.")

    print("\n=== Saving model ===")
    model_path = save_model(
        trained_model,
        feature_names=list(dataset.X.columns),
        target_names=list(dataset.y.columns),
        model_name=args.model,
    )
    print(f"Model saved to: {model_path}")

    print("\n=== Generating visualizations ===")
    viz_paths = generate_all_visualizations(
        dataset.y, trained_model, list(dataset.X.columns), splits.X_test,
    )
    print(f"Generated {len(viz_paths)} visualizations")

    print("\n=== Summary ===")
    print(f"Model: {args.model}")
    print(f"Training samples: {len(splits.X_train)}")
    print(f"Validation samples: {len(splits.X_val)}")
    print(f"Test samples: {len(splits.X_test)}")
    print(f"Features: {dataset.X.shape[1]}")
    print(f"Targets: {dataset.y.shape[1]}")
    print(f"\nTest Metrics:")
    for target, metrics in test_metrics.items():
        if target != "aggregate":
            print(f"  {target}: RMSE={metrics['rmse']:.6f}, R\u00b2={metrics['r2']:.4f}")
    print(f"  Aggregate: RMSE={test_metrics['aggregate']['avg_rmse']:.6f}, R\u00b2={test_metrics['aggregate']['avg_r2']:.4f}")

    print(f"\nBaseline Metrics (training mean):")
    for target, metrics in baseline_metrics.items():
        if target != "aggregate":
            print(f"  {target}: RMSE={metrics['rmse']:.6f}, R\u00b2={metrics['r2']:.4f}")
    print(f"  Aggregate: RMSE={baseline_metrics['aggregate']['avg_rmse']:.6f}, R\u00b2={baseline_metrics['aggregate']['avg_r2']:.4f}")
