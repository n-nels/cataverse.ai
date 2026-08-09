"""Build sequential examples from the persisted RF boundary artifacts."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .contract import TARGET_COLUMNS
from .examples import SequentialExample, build_sequential_examples


def _success_flag(json_path: Path) -> bool:
    """Read the existing experiment success flag."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    flags = data.get("filename_flags", {})
    return bool(flags.get("success", flags.get("exp_success", False)))


def _load_predictions(artifact_dir: Path) -> dict[str, pd.Series]:
    """Load and validate one held-out RF prediction row per experiment."""
    predictions = pd.read_csv(artifact_dir / "rf_predictions.csv")
    required = {"base_name", "prediction_provenance", *TARGET_COLUMNS}
    missing = required.difference(predictions.columns)
    if missing:
        raise ValueError(f"RF predictions missing columns: {sorted(missing)}")
    if predictions["base_name"].duplicated().any():
        raise ValueError("RF predictions contain duplicate base_name values")
    if predictions[list(TARGET_COLUMNS)].isna().any().any():
        raise ValueError("RF predictions contain missing target values")
    if not np.isfinite(predictions[list(TARGET_COLUMNS)].to_numpy(dtype=float)).all():
        raise ValueError("RF predictions contain non-finite target values")
    if predictions["prediction_provenance"].isna().any():
        raise ValueError("RF prediction provenance is missing")
    return {
        str(row["base_name"]): row
        for _, row in predictions.iterrows()
    }


def build_examples_from_artifacts(
    artifact_dir: str | Path,
    *,
    min_points: int | None = None,
    time_tolerance_s: float | None = None,
) -> tuple[SequentialExample, ...]:
    """Build leakage-safe examples from the Phase 0 RF selection artifacts.

    The persisted assignment table is the only experiment-selection boundary.
    Every cutoff inherits its experiment assignment and its held-out RF
    prediction; raw observations are read only from the paired CSV path.
    """
    artifact_path = Path(artifact_dir)
    config = json.loads((artifact_path / "run_config.json").read_text(encoding="utf-8"))
    assignments = pd.read_csv(artifact_path / "split_assignments.csv")
    required = {"base_name", "assignment", "json_path", "csv_path"}
    missing = required.difference(assignments.columns)
    if missing:
        raise ValueError(f"Split assignments missing columns: {sorted(missing)}")
    if assignments["base_name"].duplicated().any():
        raise ValueError("Split assignments contain duplicate base_name values")
    if not assignments["assignment"].isin({"train", "validation", "test"}).all():
        raise ValueError("Split assignments contain an unknown partition")

    prediction_by_name = _load_predictions(artifact_path)
    assignment_names = {str(value) for value in assignments["base_name"]}
    prediction_names = set(prediction_by_name)
    if assignment_names != prediction_names:
        missing_predictions = sorted(assignment_names - prediction_names)
        extra_predictions = sorted(prediction_names - assignment_names)
        raise ValueError(
            "RF prediction coverage does not match split assignments: "
            f"missing={missing_predictions}, extra={extra_predictions}"
        )

    configured_min_points = int(config["minimum_fit_points"])
    configured_tolerance = float(config["time_tolerance_s"])
    examples: list[SequentialExample] = []
    for _, assignment_row in assignments.sort_values("base_name").iterrows():
        experiment_id = str(assignment_row["base_name"])
        csv_path = Path(str(assignment_row["csv_path"]))
        json_path = Path(str(assignment_row["json_path"]))
        if not csv_path.exists():
            raise FileNotFoundError(csv_path)
        if not json_path.exists():
            raise FileNotFoundError(json_path)

        prediction = prediction_by_name[experiment_id]
        experiment_examples = build_sequential_examples(
            pd.read_csv(csv_path),
            experiment_id=experiment_id,
            successful=_success_flag(json_path),
            min_points=configured_min_points if min_points is None else min_points,
            time_tolerance_s=(
                configured_tolerance if time_tolerance_s is None else time_tolerance_s
            ),
            assignment=str(assignment_row["assignment"]),
            csv_path=str(csv_path),
            json_path=str(json_path),
            rf_prediction=tuple(float(prediction[column]) for column in TARGET_COLUMNS),
            rf_prediction_provenance=str(prediction["prediction_provenance"]),
        )
        examples.extend(experiment_examples)
    return tuple(examples)


def write_examples_artifact(
    examples: tuple[SequentialExample, ...],
    output_dir: str | Path,
) -> Path:
    """Write examples and a compact summary for reproducible downstream use."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    with (output_path / "examples.jsonl").open("w", encoding="utf-8") as handle:
        for example in examples:
            handle.write(json.dumps(asdict(example), default=str) + "\n")

    experiment_assignments = {
        example.experiment_id: example.assignment for example in examples
    }
    manifest = {
        "example_count": len(examples),
        "experiment_count": len(experiment_assignments),
        "assignment_counts": dict(Counter(experiment_assignments.values())),
        "cutoffs_per_experiment": dict(Counter(example.experiment_id for example in examples)),
        "rf_prediction_provenance_counts": dict(
            Counter(example.rf_prediction_provenance for example in examples)
        ),
    }
    (output_path / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return output_path
