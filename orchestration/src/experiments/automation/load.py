"""
Dataset assembly, validation, and splitting for PFO-Sec parameter prediction.

Phase 5: Assemble feature matrix X and target matrix Y.
Phase 5b: Data validation.
Phase 6: Train/test split.
"""

import logging
from typing import NamedTuple
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from extract import ExperimentRecord, extract_data
from model import LOG_TRANSFORM_TARGETS
from transform import (
    TARGET_COLUMNS,
    add_previous_targets,
    compute_chain_features,
    extract_current_features,
    extract_targets,
)

DEFAULT_OUTPUT_DIR = Path(__file__).parent / "outputs"

logger = logging.getLogger(__name__)


class DatasetSplit(NamedTuple):
    """Container for train/test/validation splits."""

    X_train: pd.DataFrame
    y_train: pd.DataFrame
    X_val: pd.DataFrame
    y_val: pd.DataFrame
    X_test: pd.DataFrame
    y_test: pd.DataFrame


class Dataset(NamedTuple):
    """Container for full dataset."""

    X: pd.DataFrame
    y: pd.DataFrame
    records: list[ExperimentRecord]


def reduce_features(
    X: pd.DataFrame,
    pre_steps_dropped: list[int],
) -> pd.DataFrame:
    """
    Reduce feature set by dropping whole pretreatment steps.

    All columns whose prefix matches ``pre_{step}_`` for each step in
    ``steps_to_drop`` are removed (both gas one-hot and numeric fields).

    Parameters
    ----------
    X : pd.DataFrame
        Full feature matrix (from :func:`assemble_dataset`).
    steps_to_drop : list[int]
        1-indexed pretreatment step numbers to drop entirely.

    Returns
    -------
    pd.DataFrame
        Reduced feature matrix.
    """

    cols_to_drop = []
    for step in pre_steps_dropped:
        prefix = f"pre_{step}_"
        cols_to_drop.extend(c for c in X.columns if c.startswith(prefix))

    if cols_to_drop:
        logger.info(
            "Dropping %d feature(s) for pretreatment step(s) %s",
            len(cols_to_drop),
            pre_steps_dropped,
        )
        X = X.drop(columns=cols_to_drop)
    else:
        logger.info("No columns matched steps_to_drop=%s", pre_steps_dropped)

    logger.info("Reduced feature matrix: X=%s", X.shape)
    return X


def assemble_dataset(
    records: list[ExperimentRecord],
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """
    Phase 5: Assemble feature matrix X and target matrix Y.

    Parameters
    ----------
    records : list[ExperimentRecord]
        Chronologically sorted experiment records.
    pre_steps_dropped : list[int] | None
        List of pretreatment steps to drop during feature reduction.

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame, int]
        X (features), y (targets), zero_target_count.
    """
    # Extract targets and max time
    targets = []
    time_features = []
    zero_count = 0
    for rec in records:
        target, max_time_s = extract_targets(rec.csv_path)
        if (target == 0.0).all():
            zero_count += 1
        targets.append(target)
        time_features.append({"max_time_s": max_time_s})
    logger.info("Extracted targets: %d total, %d zero targets", len(targets), zero_count)

    # Extract current features
    current_features = [extract_current_features(rec.json_data) for rec in records]

    # Compute chain features
    chain_features = compute_chain_features(records)
    # chain_features = [{} for _ in records] # disable chain features

    # Add previous targets
    prev_features = add_previous_targets(records, targets, prev_target_columns=None)

    # Combine features into DataFrame
    X_data = []
    for curr, chain, prev, time_feat in zip(current_features, chain_features, prev_features, time_features):
        row = {**curr, **chain, **prev, **time_feat}
        X_data.append(row)

    X = pd.DataFrame(X_data, index=[rec.base_name for rec in records])

    # Combine targets into DataFrame
    y_data = []
    for target in targets:
        y_data.append({col: target[col] for col in TARGET_COLUMNS if col in target.index})

    y = pd.DataFrame(y_data, index=[rec.base_name for rec in records])

    # Transform previous-target features to match training space
    for target in LOG_TRANSFORM_TARGETS:
        col = f"prev_{target}"
        if col in X.columns:
            X[col] = np.log(np.maximum(X[col], 1e-12))

    logger.info("Assembled dataset: X=%s, y=%s", X.shape, y.shape)

    return X, y, zero_count


def validate_dataset(X: pd.DataFrame, y: pd.DataFrame) -> list[str]:
    """
    Phase 5b: Validate dataset quality.

    Parameters
    ----------
    X : pd.DataFrame
        Feature matrix.
    y : pd.DataFrame
        Target matrix.

    Returns
    -------
    list[str]
        List of validation warnings/errors.
    """
    issues = []

    # Check for NaN targets
    nan_targets = y.isna().sum().sum()
    if nan_targets > 0:
        issues.append(f"Found {nan_targets} NaN values in targets")

    # Sanity check value ranges
    temp_cols = [col for col in X.columns if "temp" in col]
    for col in temp_cols:
        if X[col].min() < -50 or X[col].max() > 1500:
            issues.append(f"Temperature column {col} has unusual range: [{X[col].min():.1f}, {X[col].max():.1f}]")

    pressure_cols = [col for col in X.columns if "pressure" in col]
    for col in pressure_cols:
        if X[col].min() < -1 or X[col].max() > 100:
            issues.append(f"Pressure column {col} has unusual range: [{X[col].min():.2f}, {X[col].max():.2f}]")

    # Check chronological ordering (index should be sorted by datetime)
    logger.info("Dataset validation: %d issues found", len(issues))

    return issues


def split_dataset(
    X: pd.DataFrame,
    y: pd.DataFrame,
    train_ratio: float = 0.8,
    val_ratio: float = 0.2,
) -> DatasetSplit:
    """
    Phase 6: Split dataset chronologically.

    Parameters
    ----------
    X : pd.DataFrame
        Feature matrix (chronologically sorted).
    y : pd.DataFrame
        Target matrix (chronologically sorted).
    train_ratio : float
        Proportion of data for training (default 0.8).
    val_ratio : float
        Proportion of training data for validation (default 0.2).

    Returns
    -------
    DatasetSplit
        Named tuple with X_train, y_train, X_val, y_val, X_test, y_test.
    """
    # # Chronological split (no shuffling)
    # n = len(X)
    # test_start = int(n * train_ratio)
    # val_start = int(test_start * (1 - val_ratio))

    # # Chronological split — no shuffling
    # X_train_full = X.iloc[:test_start]
    # y_train_full = y.iloc[:test_start]

    # X_test = X.iloc[test_start:]
    # y_test = y.iloc[test_start:]

    # X_train = X_train_full.iloc[:val_start]
    # y_train = y_train_full.iloc[:val_start]

    # X_val = X_train_full.iloc[val_start:]
    # y_val = y_train_full.iloc[val_start:]

    # Random split
    X_train_full, X_test, y_train_full, y_test = train_test_split(
        X, y, test_size=1.0 - train_ratio, random_state=42,
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train_full, y_train_full, test_size=val_ratio, random_state=42,
    )

    logger.info(
        "Split: train=%d, val=%d, test=%d",
        len(X_train),
        len(X_val),
        len(X_test),
    )

    return DatasetSplit(
        X_train=X_train,
        y_train=y_train,
        X_val=X_val,
        y_val=y_val,
        X_test=X_test,
        y_test=y_test,
    )


def build_dataset(
    data_root: str = r"X:\peakFit",
    force_refresh: bool = False,
    pre_steps_dropped: list[int] | None = [1, 2, 4, 6, 8],
) -> Dataset:
    """
    Build complete dataset from raw data.

    Parameters
    ----------
    data_root : str
        Root directory containing experiment folders.
    force_refresh : bool
        If True, ignore cache and do full walk.
    steps_to_drop : list[int] | None
        List of pretreatment steps to drop during feature reduction.

    Returns
    -------
    Dataset
        Named tuple with X, y, and records.
    """
    # Phase 1: Load data
    records = extract_data(data_root=data_root, force_refresh=force_refresh)
    logger.info("Loaded %d records", len(records))

    # Phase 5: Assemble dataset
    X, y, zero_count = assemble_dataset(records)
    logger.info("Assembled: X=%s, y=%s, zero_targets=%d", X.shape, y.shape, zero_count)

    # Phase 5a: Feature reduction
    X = reduce_features(X, pre_steps_dropped=pre_steps_dropped)

    # Phase 5b: Validate
    issues = validate_dataset(X, y)
    if issues:
        for issue in issues:
            logger.warning("Validation: %s", issue)

    return Dataset(X=X, y=y, records=records)


def save_dataset(
    dataset: Dataset,
    output_dir: str | Path | None = None,
) -> Path:
    """
    Save dataset to disk as parquet files.

    Parameters
    ----------
    dataset : Dataset
        Dataset to save.
    output_dir : str | Path | None
        Output directory. Defaults to module-relative outputs/.

    Returns
    -------
    Path
        Path to output directory.
    """
    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save features
    X_path = out_dir / "X.parquet"
    dataset.X.to_parquet(X_path)

    # Save targets
    y_path = out_dir / "y.parquet"
    dataset.y.to_parquet(y_path)

    # Save metadata (record base_names)
    meta_path = out_dir / "records.csv"
    pd.DataFrame({
        "base_name": [r.base_name for r in dataset.records],
        "datetime": [r.datetime.isoformat() for r in dataset.records],
    }).to_csv(meta_path, index=False)

    logger.info("Saved dataset to %s (X=%s, y=%s)", out_dir, X_path, y_path)
    return out_dir


def load_dataset(
    input_dir: str | Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load dataset from disk.

    Parameters
    ----------
    input_dir : str | Path
        Directory containing X.parquet and y.parquet.

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        X (features), y (targets).
    """
    in_dir = Path(input_dir)
    X = pd.read_parquet(in_dir / "X.parquet")
    y = pd.read_parquet(in_dir / "y.parquet")
    logger.info("Loaded dataset: X=%s, y=%s", X.shape, y.shape)
    return X, y


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("=== Building dataset ===")
    dataset = build_dataset()

    print(f"\nDataset shape: X={dataset.X.shape}, y={dataset.y.shape}")
    print(f"Feature columns: {list(dataset.X.columns[:10])}...")
    print(f"Target columns: {list(dataset.y.columns)}")

    print("\n=== Splitting dataset ===")
    splits = split_dataset(dataset.X, dataset.y)
    print(f"Train: {splits.X_train.shape}")
    print(f"Val: {splits.X_val.shape}")
    print(f"Test: {splits.X_test.shape}")

    print("\n=== Summary ===")
    print(f"Total records: {len(dataset.records)}")
    print(f"Features: {dataset.X.shape[1]}")
    print(f"Targets: {dataset.y.shape[1]}")
