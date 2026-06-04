"""
Dataset assembly, validation, and splitting for PFO-Sec parameter prediction.

Phase 5: Assemble feature matrix X and target matrix Y.
Phase 5b: Data validation.
Phase 6: Train/test split.
"""

import logging
from typing import NamedTuple

import pandas as pd

from extract import ExperimentRecord, extract_data
from transform import (
    TARGET_COLUMNS,
    PRETREATMENT_GAS,
    add_previous_targets,
    compute_chain_features,
    extract_current_features,
    extract_targets,
)

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


def assemble_dataset(
    records: list[ExperimentRecord],
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """
    Phase 5: Assemble feature matrix X and target matrix Y.

    Parameters
    ----------
    records : list[ExperimentRecord]
        Chronologically sorted experiment records.

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame, int]
        X (features), y (targets), zero_target_count.
    """
    # Extract targets
    targets = []
    zero_count = 0
    for rec in records:
        target = extract_targets(rec.csv_path)
        if (target == 0.0).all():
            zero_count += 1
        targets.append(target)
    logger.info("Extracted targets: %d total, %d zero targets", len(targets), zero_count)

    # Extract current features
    current_features = [extract_current_features(rec.json_data) for rec in records]

    # Compute chain features
    chain_features = compute_chain_features(records)

    # Add previous targets
    prev_features = add_previous_targets(records, targets)

    # Combine features into DataFrame
    X_data = []
    for curr, chain, prev in zip(current_features, chain_features, prev_features):
        row = {**curr, **chain, **prev}
        X_data.append(row)

    X = pd.DataFrame(X_data, index=[rec.base_name for rec in records])

    # Combine targets into DataFrame
    y_data = []
    for target in targets:
        y_data.append({col: target[col] for col in TARGET_COLUMNS if col in target.index})

    y = pd.DataFrame(y_data, index=[rec.base_name for rec in records])

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

    # Check dimensions
    expected_features = 121  # Approximate
    if X.shape[1] < expected_features - 10 or X.shape[1] > expected_features + 10:
        issues.append(f"Feature count {X.shape[1]} differs from expected ~{expected_features}")

    # Check for NaN targets
    nan_targets = y.isna().sum().sum()
    if nan_targets > 0:
        issues.append(f"Found {nan_targets} NaN values in targets")

    # Check for unknown gases in one-hot columns
    gas_cols = [col for col in X.columns if "_gas_" in col and "exp_" not in col]
    for col in gas_cols:
        gas_name = col.split("_gas_")[-1]
        if gas_name not in PRETREATMENT_GAS and gas_name != "":
            issues.append(f"Unknown gas in feature: {gas_name}")

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
    n = len(X)
    test_start = int(n * train_ratio)
    val_start = int(test_start * (1 - val_ratio))

    # Chronological split — no shuffling
    X_train_full = X.iloc[:test_start]
    y_train_full = y.iloc[:test_start]

    X_test = X.iloc[test_start:]
    y_test = y.iloc[test_start:]

    X_train = X_train_full.iloc[:val_start]
    y_train = y_train_full.iloc[:val_start]

    X_val = X_train_full.iloc[val_start:]
    y_val = y_train_full.iloc[val_start:]

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
) -> Dataset:
    """
    Build complete dataset from raw data.

    Parameters
    ----------
    data_root : str
        Root directory containing experiment folders.
    force_refresh : bool
        If True, ignore cache and do full walk.

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

    # Phase 5b: Validate
    issues = validate_dataset(X, y)
    if issues:
        for issue in issues:
            logger.warning("Validation: %s", issue)

    return Dataset(X=X, y=y, records=records)


DEFAULT_OUTPUT_DIR = Path(__file__).parent / "outputs"


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
    import sys

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
