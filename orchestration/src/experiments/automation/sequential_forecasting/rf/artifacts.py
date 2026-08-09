"""Build reproducible RF boundary artifacts for sequential forecasting."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from harness.fingerprints import compute_dataset_fingerprint, compute_split_fingerprint
from load import build_dataset, save_dataset, split_dataset
from model import load_model

from ..config import RunConfig
from .predictions import export_predictions
from .provenance import collect_provenance
from .splits import assignment_table


def _write_json(path: Path, value: object) -> None:
    """Write one indented JSON artifact."""
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


def build_artifacts(config: RunConfig) -> Path:
    """Build and persist RF boundary artifacts."""
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

    assignments = assignment_table(splits, dataset)
    assignments.to_csv(artifact_dir / "split_assignments.csv", index=False)

    model = load_model(config.model_path)
    predictions = export_predictions(
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
