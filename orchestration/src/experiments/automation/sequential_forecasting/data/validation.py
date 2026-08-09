"""Phase 1 data-contract validation over the Phase 0 experiment selection."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .contract import (
    AREA_COLUMN,
    DEFAULT_TIME_TOLERANCE_S,
    TARGET_COLUMNS,
    TIME_COLUMN,
)
from ..config import DEFAULT_ARTIFACT_DIR
from .examples import build_sequential_examples
from .observations import flatten_monomer_rows, reference_target_from_flattened


DEFAULT_VALIDATION_DIR = DEFAULT_ARTIFACT_DIR
FIT_STATUS_NAMES = (
    "fit_not_yet_eligible",
    "fit_missing_for_cutoff",
    "fit_partially_populated",
    "fit_missing_for_whole_experiment",
    "fit_failed",
    "fit_valid",
    "successful_no_adsorption",
)


def _success_flag(json_path: Path) -> bool:
    """Read the existing experiment success flag."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    flags = data.get("filename_flags", {})
    return bool(flags.get("success", flags.get("exp_success", False)))


def _count_folder_exclusions(data_root: str, exclude_folders: list[str]) -> int:
    """Count accepted paired records excluded by the configured folder rules."""
    count = 0
    for json_path in Path(data_root).rglob("*_expParams.json"):
        if not any(folder in str(json_path) for folder in exclude_folders):
            continue
        csv_path = json_path.with_name(
            json_path.name.replace("_expParams.json", "_CarbonylPeakArea.csv")
        )
        if not csv_path.exists():
            continue
        data = json.loads(json_path.read_text(encoding="utf-8"))
        flags = data.get("filename_flags", {})
        if flags.get("has_csv") is False or flags.get("exp_success") is False:
            continue
        count += 1
    return count


def validate_experiment(
    row: pd.Series,
    *,
    min_points: int,
    time_tolerance_s: float,
) -> tuple[dict[str, object], Counter[str]]:
    """Validate one real experiment and return summary/status counts."""
    experiment_id = str(row["base_name"])
    csv_path = Path(str(row["csv_path"]))
    json_path = Path(str(row["json_path"]))
    frame = pd.read_csv(csv_path)
    successful = _success_flag(json_path)
    if not successful:
        raise ValueError(f"Selected experiment is not successful: {experiment_id}")

    flattened, collisions = flatten_monomer_rows(
        frame, time_tolerance_s=time_tolerance_s
    )
    reference = reference_target_from_flattened(
        flattened,
        successful=successful,
        collisions=collisions,
    )
    examples = build_sequential_examples(
        frame,
        experiment_id=experiment_id,
        successful=successful,
        min_points=min_points,
        time_tolerance_s=time_tolerance_s,
    )
    if not examples:
        raise ValueError(f"No cutoff examples generated: {experiment_id}")
    if not (flattened["Peak_Name"] == "monomer_sum").all():
        raise ValueError(f"Non-monomer row entered flattened data: {experiment_id}")

    times = flattened[TIME_COLUMN].to_numpy(dtype=float)
    if len(times) > 1 and not np.all(np.diff(times) > time_tolerance_s):
        raise ValueError(f"Unresolved duplicate or unsorted time: {experiment_id}")
    if len(examples) != len(flattened.loc[times <= reference.final_time_s]):
        raise ValueError(f"Cutoff count mismatch: {experiment_id}")

    statuses: Counter[str] = Counter()
    for index, example in enumerate(examples):
        statuses[example.fit_status] += 1
        if example.experiment_id != experiment_id:
            raise ValueError(f"Experiment ID changed in example: {experiment_id}")
        if example.cutoff_id != f"{experiment_id}:{index:04d}":
            raise ValueError(f"Invalid cutoff ID: {experiment_id}")
        if len(example.observation_times_s) != index + 1:
            raise ValueError(f"Prefix length leaked or skipped: {experiment_id}")
        if any(time > example.cutoff_time_s for time in example.observation_times_s):
            raise ValueError(f"Future observation entered cutoff: {experiment_id}")
        if tuple(sorted(example.observation_times_s)) != example.observation_times_s:
            raise ValueError(f"Cutoff observations are not sorted: {experiment_id}")
        if example.q_0 != example.observation_area[0]:
            raise ValueError(f"q_0 is not the first observation: {experiment_id}")
        if len(example.current_fit_values) != len(TARGET_COLUMNS):
            raise ValueError(f"Fit value vector has wrong length: {experiment_id}")
        if len(example.current_fit_available) != len(TARGET_COLUMNS):
            raise ValueError(f"Fit mask has wrong length: {experiment_id}")
        if "Delta_Group" in example.__dict__:
            raise ValueError(f"Delta_Group entered example fields: {experiment_id}")

    complete = flattened[list(TARGET_COLUMNS)].notna().all(axis=1)
    complete &= np.isfinite(flattened[list(TARGET_COLUMNS)]).all(axis=1)
    complete_times = flattened.loc[complete, TIME_COLUMN]
    if reference.status == "fit_valid":
        if complete_times.empty or float(complete_times.max()) != reference.final_time_s:
            raise ValueError(f"Reference target is not from final complete fit: {experiment_id}")
        if not np.isclose(reference.values[-1], examples[0].q_0):
            raise ValueError(f"Reference q_0 is not passed through: {experiment_id}")
    elif reference.status != "successful_no_adsorption":
        raise ValueError(f"Unexpected reference status: {experiment_id}")

    summary = {
        "base_name": experiment_id,
        "assignment": str(row["assignment"]),
        "csv_path": str(csv_path),
        "raw_rows": len(frame),
        "raw_monomer_rows": int((frame["Peak_Name"] == "monomer_sum").sum()),
        "flattened_observations": len(flattened),
        "cutoff_count": len(examples),
        "collision_count": len(collisions),
        "complete_fit_rows": int(complete.sum()),
        "final_time_s": reference.final_time_s,
        "reference_status": reference.status,
        "first_observation_q0": examples[0].q_0,
        "status_counts": dict(statuses),
    }
    return summary, statuses


def run_validation(
    artifact_dir: str | Path = DEFAULT_VALIDATION_DIR,
    *,
    output_dir: str | Path | None = None,
) -> Path:
    """Run the full data-contract validation and write its report."""
    artifact_path = Path(artifact_dir)
    out_path = Path(output_dir) if output_dir is not None else artifact_path / "contract_validation"
    out_path.mkdir(parents=True, exist_ok=True)
    config = json.loads((artifact_path / "run_config.json").read_text(encoding="utf-8"))
    assignments = pd.read_csv(artifact_path / "split_assignments.csv")
    summaries: list[dict[str, object]] = []
    status_counts: Counter[str] = Counter()
    failures: list[dict[str, str]] = []
    for _, row in assignments.iterrows():
        try:
            summary, statuses = validate_experiment(
                row,
                min_points=int(config["minimum_fit_points"]),
                time_tolerance_s=float(config["time_tolerance_s"]),
            )
            summaries.append(summary)
            status_counts.update(statuses)
        except (OSError, ValueError, pd.errors.ParserError) as error:
            failures.append({"base_name": str(row["base_name"]), "error": str(error)})

    assignment_sets = {
        name: set(assignments.loc[assignments["assignment"] == name, "base_name"])
        for name in ("train", "validation", "test")
    }
    disjoint = all(
        assignment_sets[left].isdisjoint(assignment_sets[right])
        for left, right in (("train", "validation"), ("train", "test"), ("validation", "test"))
    )
    complete_status_counts = {
        status: int(status_counts.get(status, 0)) for status in FIT_STATUS_NAMES
    }
    report = {
        "valid": not failures and len(summaries) == len(assignments) and disjoint,
        "artifact_dir": str(artifact_path),
        "data_contract": "sequential_forecasting/data_contract.md",
        "data_root": config["data_root"],
        "exclude_folders": config["exclude_folders"],
        "excluded_by_folder_count": _count_folder_exclusions(
            str(config["data_root"]), list(config["exclude_folders"])
        ),
        "experiment_count": len(summaries),
        "cutoff_count": sum(int(summary["cutoff_count"]) for summary in summaries),
        "raw_monomer_rows": sum(int(summary["raw_monomer_rows"]) for summary in summaries),
        "flattened_observations": sum(
            int(summary["flattened_observations"]) for summary in summaries
        ),
        "collision_count": sum(int(summary["collision_count"]) for summary in summaries),
        "complete_fit_rows": sum(int(summary["complete_fit_rows"]) for summary in summaries),
        "reference_status_counts": dict(
            Counter(str(summary["reference_status"]) for summary in summaries)
        ),
        "fit_status_counts": complete_status_counts,
        "assignment_counts": assignments["assignment"].value_counts().to_dict(),
        "partitions_disjoint": disjoint,
        "failures": failures,
    }
    (out_path / "experiment_validation.csv").write_text(
        pd.DataFrame(summaries).to_csv(index=False), encoding="utf-8"
    )
    (out_path / "validation_report.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return out_path

