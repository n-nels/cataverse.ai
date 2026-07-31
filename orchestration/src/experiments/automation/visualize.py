"""
Visualizations for PFO-Sec parameter prediction model.

Generates diagnostic plots for model evaluation.
"""

import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from load import load_dataset, split_dataset
from model import (
    DEFAULT_MODEL_DIR,
    TrainedModel,
    inverse_target_transforms,
    get_feature_importances,
    load_model,
)

logger = logging.getLogger(__name__)

# Default output directory
DEFAULT_OUTPUT_DIR = Path(__file__).parent / "outputs"

# Plot settings
plt.rcParams.update({
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.labelsize": 10,
})


def plot_target_distributions(
    y: pd.DataFrame,
    output_dir: str | Path | None = None,
) -> list[Path]:
    """
    Plot histograms of target distributions.

    Shows zero-inflation and distribution shapes.
    """
    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []

    for col in y.columns:
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))

        data = y[col].dropna()
        axes[0].hist(data, bins=30, edgecolor="black", alpha=0.7)
        axes[0].set_xlabel(col)
        axes[0].set_ylabel("Count")
        axes[0].set_title(f"Distribution: {col}")

        nonzero = data[data > 0]
        if len(nonzero) > 0:
            axes[1].hist(nonzero, bins=30, edgecolor="black", alpha=0.7, color="orange")
            axes[1].set_xscale("log")
            axes[1].set_xlabel(f"{col} (log scale)")
            axes[1].set_ylabel("Count")
            axes[1].set_title(f"Distribution (non-zero): {col}")
        else:
            axes[1].text(0.5, 0.5, "All zeros", ha="center", va="center")
            axes[1].set_title(f"No non-zero values: {col}")

        plt.tight_layout()

        safe_name = col.replace("-", "_").replace(".", "_")
        save_path = out_dir / f"dist_{safe_name}.tiff"
        fig.savefig(save_path, format="tiff", bbox_inches="tight")
        plt.close(fig)
        saved_paths.append(save_path)
        logger.info("Saved distribution plot: %s", save_path)

    return saved_paths


def plot_feature_importance(
    trained_model: TrainedModel,
    feature_names: list[str],
    top_n: int = 20,
    output_dir: str | Path | None = None,
) -> list[Path]:
    """
    Plot global feature importance from the multi-output model.

    Parameters
    ----------
    trained_model : TrainedModel
        Trained model container.
    feature_names : list[str]
        Original feature names (positionally aligned with model internals).
    top_n : int
        Number of top features to show.
    output_dir : str | Path | None
        Directory to save plots. Defaults to outputs/.
    """
    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    importance = get_feature_importances(trained_model)
    indices = np.argsort(importance)[::-1][:top_n]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(range(top_n), importance[indices][::-1])
    ax.set_yticks(range(top_n))
    ax.set_yticklabels([feature_names[i] for i in indices][::-1])
    ax.set_xlabel("Importance")
    ax.set_title("Global Feature Importance (multi-output model)")

    plt.tight_layout()

    save_path = out_dir / "importance_global.tiff"
    fig.savefig(save_path, format="tiff", bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved global feature importance plot: %s", save_path)

    return [save_path]


def plot_predicted_vs_actual(
    y_true: pd.DataFrame,
    y_pred: np.ndarray,
    output_dir: str | Path | None = None,
) -> list[Path]:
    """
    Plot predicted vs actual scatter for each target.
    """
    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []

    for i, col in enumerate(y_true.columns):
        true_vals = y_true[col].values
        pred_vals = y_pred[:, i]

        fig, ax = plt.subplots(figsize=(6, 6))

        ax.scatter(true_vals, pred_vals, alpha=0.5, edgecolors="black", linewidths=0.5)

        min_val = min(true_vals.min(), pred_vals.min())
        max_val = max(true_vals.max(), pred_vals.max())
        ax.plot([min_val, max_val], [min_val, max_val], "r--", label="Perfect prediction")

        ax.set_xlabel("Actual")
        ax.set_ylabel("Predicted")
        ax.set_title(f"Predicted vs Actual: {col}")
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        safe_name = col.replace("-", "_").replace(".", "_")
        save_path = out_dir / f"parity_{safe_name}.tiff"
        fig.savefig(save_path, format="tiff", bbox_inches="tight")
        plt.close(fig)
        saved_paths.append(save_path)
        logger.info("Saved parity plot: %s", save_path)

    return saved_paths


def generate_all_visualizations(
    y: pd.DataFrame,
    trained_model: TrainedModel,
    feature_names: list[str],
    X_test: pd.DataFrame,
    output_dir: str | Path | None = None,
) -> list[Path]:
    """
    Generate all visualizations.

    Parameters
    ----------
    y : pd.DataFrame
        Full target matrix (for distributions).
    trained_model : TrainedModel
        Trained model container.
    feature_names : list[str]
        Original feature names.
    X_test : pd.DataFrame
        Test features (for predictions).
    output_dir : str | Path | None
        Directory to save plots.
    """
    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    all_paths = []

    # 1. Target distributions
    logger.info("Generating target distributions...")
    paths = plot_target_distributions(y, out_dir)
    all_paths.extend(paths)

    # 2. Feature importance
    logger.info("Generating feature importance plots...")
    paths = plot_feature_importance(trained_model, feature_names, output_dir=out_dir)
    all_paths.extend(paths)

    # 3. Predicted vs actual (on test set)
    logger.info("Generating predicted vs actual plots...")
    y_pred_tfm = trained_model.model.predict(X_test)
    y_pred = inverse_target_transforms(y_pred_tfm, trained_model.target_names, trained_model.lambdas)

    y_test = y.loc[X_test.index]
    paths = plot_predicted_vs_actual(y_test, y_pred, out_dir)
    all_paths.extend(paths)

    logger.info("Generated %d visualizations in %s", len(all_paths), out_dir)
    return all_paths


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("=== Loading dataset ===")
    X, y = load_dataset(DEFAULT_OUTPUT_DIR)

    print("\n=== Splitting dataset ===")
    splits = split_dataset(X, y)

    import glob
    model_joblibs = list(Path(DEFAULT_MODEL_DIR).glob("*.joblib"))
    if not model_joblibs:
        print("No model files found in", DEFAULT_MODEL_DIR)
        raise SystemExit(1)

    model_path = model_joblibs[0]
    print(f"\n=== Loading model: {model_path.name} ===")
    trained = load_model(model_path)

    print("\n=== Generating visualizations ===")
    paths = generate_all_visualizations(
        y, trained, list(X.columns), splits.X_test,
    )
    print(f"\nGenerated {len(paths)} visualizations:")
    for p in paths:
        print(f"  {p}")
