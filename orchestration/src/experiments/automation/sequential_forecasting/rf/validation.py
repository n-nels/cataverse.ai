"""Validation of the persisted RF boundary used by sequential forecasting."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..data.contract import TARGET_COLUMNS


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one artifact file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_rf_boundary(artifact_dir: str | Path) -> dict[str, object]:
    """Validate split integrity and held-out RF prediction provenance."""
    artifact_path = Path(artifact_dir)
    assignments = pd.read_csv(artifact_path / "split_assignments.csv")
    predictions = pd.read_csv(artifact_path / "rf_predictions.csv")
    prediction_provenance = json.loads(
        (artifact_path / "prediction_provenance.json").read_text(encoding="utf-8")
    )
    failures: list[str] = []

    assignment_names = assignments["base_name"].astype(str)
    prediction_names = predictions["base_name"].astype(str)
    if assignment_names.duplicated().any():
        failures.append("split assignments contain duplicate base_name values")
    if prediction_names.duplicated().any():
        failures.append("RF predictions contain duplicate base_name values")

    assignment_sets = {
        name: set(assignment_names[assignments["assignment"] == name])
        for name in ("train", "validation", "test")
    }
    if not all(
        assignment_sets[left].isdisjoint(assignment_sets[right])
        for left, right in (("train", "validation"), ("train", "test"), ("validation", "test"))
    ):
        failures.append("train, validation, and test assignments overlap")

    if set(assignment_names) != set(prediction_names):
        failures.append("RF prediction IDs do not match split assignment IDs")

    target_columns_present = set(TARGET_COLUMNS).issubset(predictions.columns)
    if not target_columns_present:
        failures.append("RF predictions do not contain the sequential target order")
    elif not np.isfinite(predictions[list(TARGET_COLUMNS)].to_numpy(dtype=float)).all():
        failures.append("RF predictions contain non-finite target values")

    assignment_by_name = dict(zip(assignment_names, assignments["assignment"], strict=True))
    provenance_by_name = dict(
        zip(prediction_names, predictions["prediction_provenance"], strict=True)
    )
    for name, assignment in assignment_by_name.items():
        expected = "held_out_test" if assignment == "test" else "out_of_fold"
        if provenance_by_name.get(name) != expected:
            failures.append(f"unexpected RF provenance for {name}: expected {expected}")

    fold_ids = pd.to_numeric(predictions.get("fold_id"), errors="coerce")
    training_counts = pd.to_numeric(
        predictions.get("training_experiment_count"), errors="coerce"
    )
    train_val_count = len(assignment_sets["train"] | assignment_sets["validation"])
    train_count = len(assignment_sets["train"])
    if fold_ids.isna().loc[prediction_names.isin(assignment_sets["train"] | assignment_sets["validation"])].any():
        failures.append("out-of-fold predictions are missing fold IDs")
    if training_counts.isna().any():
        failures.append("RF predictions are missing training experiment counts")
    else:
        oof_mask = prediction_names.isin(assignment_sets["train"] | assignment_sets["validation"])
        test_mask = prediction_names.isin(assignment_sets["test"])
        if (training_counts.loc[oof_mask] >= train_val_count).any():
            failures.append("an out-of-fold RF prediction used all train/validation experiments")
        if not (training_counts.loc[test_mask] == train_count).all():
            failures.append("test RF predictions do not record train-only model coverage")

    expected_target_order = list(TARGET_COLUMNS)
    source_target_order = prediction_provenance.get("target_order")
    if source_target_order is None or set(source_target_order) != set(expected_target_order):
        failures.append("stored RF target set does not match the sequential contract")
    if prediction_provenance.get("sequential_target_order") != expected_target_order:
        failures.append("stored sequential target order is missing or incorrect")
    if prediction_provenance.get("test_model_excludes_test_experiments") is not True:
        failures.append("test RF exclusion provenance is not confirmed")

    prediction_path = artifact_path / "rf_predictions.csv"
    stored_hash = prediction_provenance.get("prediction_csv_sha256")
    if stored_hash is None:
        failures.append("RF prediction fingerprint is missing")
    elif stored_hash != _sha256_file(prediction_path):
        failures.append("RF prediction fingerprint does not match the CSV")

    split_fingerprint = json.loads(
        (artifact_path / "split_fingerprint.json").read_text(encoding="utf-8")
    )
    dataset_fingerprint = json.loads(
        (artifact_path / "dataset_fingerprint.json").read_text(encoding="utf-8")
    )
    if not split_fingerprint.get("hash"):
        failures.append("split fingerprint is missing")
    if not dataset_fingerprint.get("hash"):
        failures.append("dataset fingerprint is missing")

    return {
        "valid": not failures,
        "artifact_dir": str(artifact_path),
        "experiment_count": len(assignment_names),
        "prediction_count": len(prediction_names),
        "assignment_counts": assignments["assignment"].value_counts().to_dict(),
        "prediction_provenance_counts": predictions["prediction_provenance"]
        .value_counts()
        .to_dict(),
        "failures": failures,
        "dataset_fingerprint": dataset_fingerprint.get("hash"),
        "split_fingerprint": split_fingerprint.get("hash"),
        "prediction_csv_sha256": _sha256_file(prediction_path),
    }
