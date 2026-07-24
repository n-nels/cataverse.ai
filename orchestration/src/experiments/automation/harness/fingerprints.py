"""Dataset and split fingerprints for traceability and keep/discard gating.

Per spec.md "Fingerprints":

- Dataset fingerprint: SHA256 of concatenated X.parquet + y.parquet bytes,
  plus columns and shape.
- Split fingerprint: SHA256 of the canonical serialization of the train/val/test
  index labels (labels as strings, newline-separated, in train/val/test order),
  plus seed and ratios.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path

import pandas as pd

from load import DatasetSplit


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class DatasetFingerprint:
    x_shape: list[int]
    y_shape: list[int]
    x_columns: list[str]
    y_columns: list[str]
    hash: str

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


def compute_dataset_fingerprint(
    X: pd.DataFrame,
    y: pd.DataFrame,
    parquet_dir: str | Path | None = None,
) -> DatasetFingerprint:
    """Compute the dataset fingerprint.

    If ``parquet_dir`` is given and contains ``X.parquet`` / ``y.parquet``, the
    hash is computed from those file bytes (matching what ``save_dataset``
    wrote). Otherwise the hash is computed from the in-memory parquet
    serialization of the supplied frames.
    """
    if parquet_dir is not None:
        x_path = Path(parquet_dir) / "X.parquet"
        y_path = Path(parquet_dir) / "y.parquet"
        if x_path.exists() and y_path.exists():
            digest = _sha256_file(x_path) + _sha256_file(y_path)
        else:
            digest = _sha256_bytes(X.to_parquet()) + _sha256_bytes(y.to_parquet())
    else:
        digest = _sha256_bytes(X.to_parquet()) + _sha256_bytes(y.to_parquet())

    return DatasetFingerprint(
        x_shape=list(X.shape),
        y_shape=list(y.shape),
        x_columns=list(X.columns),
        y_columns=list(y.columns),
        hash=digest,
    )


@dataclass
class SplitFingerprint:
    seed: int
    train_ratio: float
    val_ratio: float
    train_index: list[str]
    val_index: list[str]
    test_index: list[str]
    hash: str

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


def _canonical_index_bytes(
    train_index: list[str], val_index: list[str], test_index: list[str],
) -> bytes:
    parts = []
    for labels in (train_index, val_index, test_index):
        parts.append("\n".join(labels))
    return ("\n\n".join(parts) + "\n").encode("utf-8")


def compute_split_fingerprint(
    splits: DatasetSplit,
    train_ratio: float = 0.8,
    val_ratio: float = 0.2,
    seed: int = 42,
) -> SplitFingerprint:
    def labels(df: pd.DataFrame) -> list[str]:
        return [str(x) for x in df.index.tolist()]

    train_idx = labels(splits.X_train)
    val_idx = labels(splits.X_val)
    test_idx = labels(splits.X_test)
    h = _sha256_bytes(_canonical_index_bytes(train_idx, val_idx, test_idx))
    return SplitFingerprint(
        seed=seed,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        train_index=train_idx,
        val_index=val_idx,
        test_index=test_idx,
        hash=h,
    )


def fingerprints_match(
    recorded: dict | None,
    observed: dict,
) -> bool:
    """Compare two fingerprint dicts by their hash field."""
    if recorded is None:
        return True  # nothing recorded yet
    return recorded.get("hash") == observed.get("hash")