"""Write the required experiment artifacts for a completed campaign.

All artifacts go under ``automation/artifacts/experiments/<experiment_id>/``.
Existing artifact directories are never overwritten (the campaign refuses to
run if the directory already exists).
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml


def experiment_dir(automation_dir: str | Path, experiment_id: str) -> Path:
    return Path(automation_dir) / "artifacts" / "experiments" / experiment_id


def init_experiment_dir(automation_dir: str | Path, experiment_id: str) -> Path:
    """Create and return the experiment artifact dir; refuse if it exists."""
    d = experiment_dir(automation_dir, experiment_id)
    if d.exists():
        raise FileExistsError(
            f"artifact directory already exists: {d} "
            "(spec: existing completed experiment artifacts must never be overwritten)"
        )
    d.mkdir(parents=True, exist_ok=False)
    return d


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def _write_yaml(path: Path, obj: Any) -> None:
    path.write_text(yaml.safe_dump(obj, sort_keys=False), encoding="utf-8")


def write_manifest(dir_path: Path, manifest_raw: dict) -> None:
    _write_yaml(dir_path / "manifest.yaml", manifest_raw)


def write_git_state(dir_path: Path, git_state: dict) -> None:
    _write_json(dir_path / "git_state.json", git_state)


def write_environment(dir_path: Path, env: dict) -> None:
    _write_json(dir_path / "environment.json", env)


def write_dataset_fingerprint(dir_path: Path, fp: dict) -> None:
    _write_json(dir_path / "dataset_fingerprint.json", fp)


def write_split_fingerprint(dir_path: Path, fp: dict) -> None:
    _write_json(dir_path / "split_fingerprint.json", fp)


def write_trial_results(dir_path: Path, trial_results: list[dict]) -> None:
    """Write trial_results.csv (one row per trial)."""
    import csv

    if not trial_results:
        # still write a header-only file
        cols = ["trial", "status", "validation_avg_rmse", "validation_avg_r2",
                "runtime_minutes", "params", "reason"]
    else:
        cols = ["trial", "status", "validation_avg_rmse", "validation_avg_r2",
                "runtime_minutes", "params", "reason"]
    with (dir_path / "trial_results.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(cols)
        for i, t in enumerate(trial_results, start=1):
            writer.writerow([
                i,
                t.get("status", ""),
                t.get("validation_avg_rmse", "") if t.get("validation_avg_rmse") is not None else "",
                t.get("validation_avg_r2", "") if t.get("validation_avg_r2") is not None else "",
                f"{t['runtime_minutes']:.2f}" if t.get("runtime_minutes") is not None else "",
                json.dumps(t.get("params", {}), sort_keys=True),
                t.get("reason", ""),
            ])


def write_leaderboard(dir_path: Path, leaderboard: list[dict]) -> None:
    """Write leaderboard.csv ranked by validation_avg_rmse ascending."""
    import csv

    cols = ["rank", "trial", "validation_avg_rmse", "validation_avg_r2", "params"]
    with (dir_path / "leaderboard.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(cols)
        for i, row in enumerate(leaderboard, start=1):
            writer.writerow([
                i,
                row.get("trial", ""),
                f"{row['validation_avg_rmse']:.6f}" if row.get("validation_avg_rmse") is not None else "",
                f"{row['validation_avg_r2']:.6f}" if row.get("validation_avg_r2") is not None else "",
                json.dumps(row.get("params", {}), sort_keys=True),
            ])


def write_best_params(dir_path: Path, best_params: dict) -> None:
    _write_yaml(dir_path / "best_params.yaml", best_params)


def write_final_metrics(dir_path: Path, final_metrics: dict) -> None:
    _write_json(dir_path / "final_metrics.json", final_metrics)


def write_comparison(dir_path: Path, comparison: dict) -> None:
    _write_json(dir_path / "comparison_to_baseline.json", comparison)


def write_report(dir_path: Path, report_text: str) -> None:
    (dir_path / "report.md").write_text(report_text, encoding="utf-8")


def write_run_log(dir_path: Path, log_text: str) -> None:
    (dir_path / "run.log").write_text(log_text, encoding="utf-8")


def copy_run_log(dir_path: Path, src_log: str | Path) -> None:
    shutil.copy2(src_log, dir_path / "run.log")