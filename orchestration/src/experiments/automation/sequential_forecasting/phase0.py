"""Phase 0 provenance, RF split, and prediction artifacts."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import importlib.metadata
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold

from harness.fingerprints import compute_dataset_fingerprint, compute_split_fingerprint
from load import Dataset, DatasetSplit, build_dataset, save_dataset, split_dataset
from model import TrainedModel, inverse_target_transforms, load_model
from models.random_forest import train_random_forest

from .data import DEFAULT_TIME_TOLERANCE_S, TARGET_COLUMNS


DEFAULT_DATA_ROOT = r"X:\peakFit"
DEFAULT_EXCLUDE_FOLDERS = ("test", "nn1120-4_pd_ceo2_000")
DEFAULT_ARTIFACT_DIR = Path(__file__).parent / "artifacts" / "phase0"
DEFAULT_MODEL_PATH = Path(__file__).parent.parent / "models" / "random_forest.joblib"


@dataclass(frozen=True)
class Phase0Config:
    """Reproducibility configuration for the Phase 0 run."""

    data_root: str = DEFAULT_DATA_ROOT
    exclude_folders: tuple[str, ...] = DEFAULT_EXCLUDE_FOLDERS
    artifact_dir: str = str(DEFAULT_ARTIFACT_DIR)
    model_path: str = str(DEFAULT_MODEL_PATH)
    minimum_fit_points: int = 4
    cutoff_policy: str = "every flattened monomer observation through final time"
    time_tolerance_s: float = DEFAULT_TIME_TOLERANCE_S
    split_seed: int = 42
    train_ratio: float = 0.8
    val_ratio: float = 0.2
    target_order: tuple[str, ...] = TARGET_COLUMNS
    oof_folds: int = 5


def _write_json(path: Path, value: object) -> None:
    """Write one indented JSON artifact."""
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


def _git_metadata(repository: Path) -> dict[str, object]:
    """Read repository revision state without changing the repository."""
    try:
        commit = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "-C", str(repository), "branch", "--show-current"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        git_root = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "-C", str(repository), "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return {
            "path": str(repository),
            "git_root": git_root,
            "commit": commit,
            "branch": branch,
            "dirty": dirty,
        }
    except (OSError, subprocess.CalledProcessError) as error:
        return {"path": str(repository), "error": str(error)}


def collect_provenance() -> dict[str, object]:
    """Collect repository and dependency provenance for the run."""
    orchestration_root = Path(__file__).resolve().parents[4]
    workspace_root = orchestration_root.parent
    sibling_root = workspace_root / "ir-spectro-node"
    package_versions: dict[str, str] = {}
    for package in ("numpy", "pandas", "scipy", "scikit-learn", "joblib"):
        try:
            package_versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            package_versions[package] = "unavailable"
    return {
        "python": __import__("platform").python_version(),
        "repositories": [
            _git_metadata(orchestration_root),
            _git_metadata(sibling_root),
        ],
        "dependencies": package_versions,
    }


def _predict(model: TrainedModel, features: pd.DataFrame) -> np.ndarray:
    """Predict in original target units."""
    transformed = model.model.predict(features)
    return inverse_target_transforms(transformed, model.target_names, model.lambdas)


def _assignment_table(splits: DatasetSplit, dataset: Dataset) -> pd.DataFrame:
    """Create one persisted train/validation/test assignment per base name."""
    assignment_by_name: dict[str, str] = {}
    for assignment, frame in (
        ("train", splits.X_train),
        ("validation", splits.X_val),
        ("test", splits.X_test),
    ):
        for base_name in frame.index:
            assignment_by_name[str(base_name)] = assignment
    records_by_name = {record.base_name: record for record in dataset.records}
    rows = []
    for base_name, assignment in assignment_by_name.items():
        record = records_by_name[base_name]
        rows.append(
            {
                "base_name": base_name,
                "assignment": assignment,
                "json_path": str(record.json_path),
                "csv_path": str(record.csv_path),
            }
        )
    return pd.DataFrame(rows).sort_values("base_name").reset_index(drop=True)


def _oof_predictions(
    model: TrainedModel,
    X_train_val: pd.DataFrame,
    y_train_val: pd.DataFrame,
    *,
    folds: int,
    seed: int,
) -> pd.DataFrame:
    """Generate fold-held-out predictions for train and validation records."""
    if folds < 2 or folds > len(X_train_val):
        raise ValueError("oof_folds must be between 2 and the training-record count")
    splitter = KFold(n_splits=folds, shuffle=True, random_state=seed)
    rows: list[dict[str, object]] = []
    for fold, (fit_indices, holdout_indices) in enumerate(
        splitter.split(X_train_val), start=1
    ):
        fold_model = train_random_forest(
            X_train_val.iloc[fit_indices],
            y_train_val.iloc[fit_indices],
            X_train_val.iloc[holdout_indices],
            y_train_val.iloc[holdout_indices],
            config=model.config,
            strategy="separate",
        )
        predictions = _predict(fold_model, X_train_val.iloc[holdout_indices])
        for row_index, values in zip(holdout_indices, predictions, strict=True):
            row: dict[str, object] = {
                "base_name": str(X_train_val.index[row_index]),
                "prediction_provenance": "out_of_fold",
                "fold_id": fold,
                "training_experiment_count": len(fit_indices),
            }
            row.update(
                {
                    name: float(value)
                    for name, value in zip(model.target_names, values, strict=True)
                }
            )
            rows.append(row)
    return pd.DataFrame(rows).sort_values("base_name").reset_index(drop=True)


def export_rf_predictions(
    model: TrainedModel,
    splits: DatasetSplit,
    *,
    folds: int,
    seed: int,
) -> pd.DataFrame:
    """Export held-out train/validation and held-out test RF predictions."""
    train_val_X = pd.concat([splits.X_train, splits.X_val])
    train_val_y = pd.concat([splits.y_train, splits.y_val])
    predictions = _oof_predictions(
        model,
        train_val_X,
        train_val_y,
        folds=folds,
        seed=seed,
    )
    test_values = _predict(model, splits.X_test)
    test_rows: list[dict[str, object]] = []
    for base_name, values in zip(splits.X_test.index, test_values, strict=True):
        row: dict[str, object] = {
            "base_name": str(base_name),
            "prediction_provenance": "held_out_test",
            "fold_id": None,
            "training_experiment_count": len(splits.X_train),
        }
        row.update(
            {
                name: float(value)
                for name, value in zip(model.target_names, values, strict=True)
            }
        )
        test_rows.append(row)
    return pd.concat([predictions, pd.DataFrame(test_rows)], ignore_index=True).sort_values(
        "base_name"
    ).reset_index(drop=True)


def run_phase0(config: Phase0Config) -> Path:
    """Build and persist all Phase 0 artifacts."""
    artifact_dir = Path(config.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    _write_json(artifact_dir / "run_config.json", asdict(config))
    _write_json(artifact_dir / "provenance.json", collect_provenance())

    dataset = build_dataset(
        data_root=config.data_root,
        force_refresh=False,
        exclude_folders=list(config.exclude_folders),
    )
    dataset_dir = artifact_dir / "dataset"
    save_dataset(dataset, output_dir=dataset_dir)
    splits = split_dataset(
        dataset.X,
        dataset.y,
        train_ratio=config.train_ratio,
        val_ratio=config.val_ratio,
    )
    dataset_fingerprint = compute_dataset_fingerprint(
        dataset.X, dataset.y, parquet_dir=dataset_dir
    )
    split_fingerprint = compute_split_fingerprint(
        splits,
        train_ratio=config.train_ratio,
        val_ratio=config.val_ratio,
        seed=config.split_seed,
    )
    _write_json(artifact_dir / "dataset_fingerprint.json", dataset_fingerprint.to_dict())
    _write_json(artifact_dir / "split_fingerprint.json", split_fingerprint.to_dict())

    assignments = _assignment_table(splits, dataset)
    assignments.to_csv(artifact_dir / "split_assignments.csv", index=False)

    model = load_model(config.model_path)
    predictions = export_rf_predictions(
        model,
        splits,
        folds=config.oof_folds,
        seed=config.split_seed,
    )
    predictions.to_csv(artifact_dir / "rf_predictions.csv", index=False)
    _write_json(
        artifact_dir / "prediction_provenance.json",
        {
            "rows": len(predictions),
            "provenance_counts": predictions["prediction_provenance"]
            .value_counts()
            .to_dict(),
            "target_order": model.target_names,
            "test_model_excludes_test_experiments": True,
        },
    )
    return artifact_dir


def _parse_args() -> Phase0Config:
    """Parse the Phase 0 command line."""
    parser = argparse.ArgumentParser(description="Build sequential forecasting Phase 0 artifacts")
    parser.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    parser.add_argument("--exclude-folder", dest="exclude_folders", action="append")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--model-path", default=str(DEFAULT_MODEL_PATH))
    parser.add_argument("--oof-folds", type=int, default=5)
    args = parser.parse_args()
    excludes = (
        tuple(args.exclude_folders)
        if args.exclude_folders is not None
        else DEFAULT_EXCLUDE_FOLDERS
    )
    return Phase0Config(
        data_root=args.data_root,
        exclude_folders=excludes,
        artifact_dir=args.artifact_dir,
        model_path=args.model_path,
        oof_folds=args.oof_folds,
    )


if __name__ == "__main__":
    output = run_phase0(_parse_args())
    print(f"Phase 0 artifacts written to {output}")
