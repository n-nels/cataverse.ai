"""
Visualizations for PFO-Sec parameter prediction model.

Generates diagnostic plots for model evaluation.
"""

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from train import TrainedModel, sanitize_feature_names

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

    Parameters
    ----------
    y : pd.DataFrame
        Target matrix.
    output_dir : str | Path | None
        Directory to save plots. Defaults to outputs/.

    Returns
    -------
    list[Path]
        Paths to saved plot files.
    """
    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []

    for col in y.columns:
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))

        # Histogram
        data = y[col].dropna()
        axes[0].hist(data, bins=30, edgecolor="black", alpha=0.7)
        axes[0].set_xlabel(col)
        axes[0].set_ylabel("Count")
        axes[0].set_title(f"Distribution: {col}")

        # Log-scale histogram (excluding zeros)
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

        # Save as TIFF
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
    Plot feature importance from trained models.

    Parameters
    ----------
    trained_model : TrainedModel
        Trained model container.
    feature_names : list[str]
        Original feature names.
    top_n : int
        Number of top features to show.
    output_dir : str | Path | None
        Directory to save plots. Defaults to outputs/.

    Returns
    -------
    list[Path]
        Paths to saved plot files.
    """
    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize feature names to match model
    clean_names = sanitize_feature_names(feature_names)

    saved_paths = []

    for target_name, model in trained_model.models.items():
        # Get feature importance
        importance = model.feature_importances_
        indices = np.argsort(importance)[::-1][:top_n]

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.barh(range(top_n), importance[indices][::-1])
        ax.set_yticks(range(top_n))
        ax.set_yticklabels([clean_names[i] for i in indices][::-1])
        ax.set_xlabel("Importance")
        ax.set_title(f"Feature Importance: {target_name}")

        plt.tight_layout()

        safe_name = target_name.replace("-", "_").replace(".", "_")
        save_path = out_dir / f"importance_{safe_name}.tiff"
        fig.savefig(save_path, format="tiff", bbox_inches="tight")
        plt.close(fig)
        saved_paths.append(save_path)
        logger.info("Saved feature importance plot: %s", save_path)

    return saved_paths


def plot_predicted_vs_actual(
    y_true: pd.DataFrame,
    y_pred: np.ndarray,
    output_dir: str | Path | None = None,
) -> list[Path]:
    """
    Plot predicted vs actual scatter for each target.

    Parameters
    ----------
    y_true : pd.DataFrame
        Actual target values.
    y_pred : np.ndarray
        Predicted target values (n_samples x n_targets).
    output_dir : str | Path | None
        Directory to save plots. Defaults to outputs/.

    Returns
    -------
    list[Path]
        Paths to saved plot files.
    """
    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []

    for i, col in enumerate(y_true.columns):
        true_vals = y_true[col].values
        pred_vals = y_pred[:, i]

        fig, ax = plt.subplots(figsize=(6, 6))

        # Scatter plot
        ax.scatter(true_vals, pred_vals, alpha=0.5, edgecolors="black", linewidths=0.5)

        # Parity line
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

    Returns
    -------
    list[Path]
        All saved plot paths.
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
    # Sanitize feature names for prediction
    clean_names = sanitize_feature_names(list(X_test.columns))
    X_test_clean = X_test.copy()
    X_test_clean.columns = clean_names

    y_pred_list = []
    for target_name in trained_model.models.keys():
        pred = trained_model.models[target_name].predict(X_test_clean)
        y_pred_list.append(pred)
    y_pred = np.column_stack(y_pred_list)

    # Get y_test (same index as X_test)
    y_test = y.loc[X_test.index]
    paths = plot_predicted_vs_actual(y_test, y_pred, out_dir)
    all_paths.extend(paths)

    logger.info("Generated %d visualizations in %s", len(all_paths), out_dir)
    return all_paths
