"""RF split assignment persistence."""

from __future__ import annotations

import pandas as pd

from load import Dataset, DatasetSplit


def assignment_table(splits: DatasetSplit, dataset: Dataset) -> pd.DataFrame:
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
