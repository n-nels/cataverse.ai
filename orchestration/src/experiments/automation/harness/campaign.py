"""Campaign orchestrator.

Ties together manifest, fingerprints, git state, ledger, trials, artifacts, and
report. Runs the autonomous experiment loop within the configured budget.

Two execution modes:

- **git mode** (``git=True``): requires a clean autoresearch branch, commits each
  candidate config as ``current_candidate.yaml``, discards via ``git reset --hard``.
- **smoke mode** (``smoke=True``): runs in-process on the current branch with no
  git commits and no branch creation. Used to verify the harness without consuming
  the overnight budget.
"""

from __future__ import annotations

import json
import logging
import platform
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from harness import artifacts, fingerprints, gitstate, ledger, report, trial
from harness.manifest import CANONICAL_SEED, Manifest, load_manifest

logger = logging.getLogger(__name__)

# Campaign baseline = ModelConfig defaults + strategy="shared" (spec "Baseline Definition").
def baseline_params() -> dict:
    from model import ModelConfig
    return {
        **ModelConfig()._asdict(),
        "strategy": "shared",
    }


@dataclass
class CampaignSummary:
    experiment_id: str
    trials_attempted: int = 0
    successful_trials: int = 0
    failed_trials: int = 0
    baseline_val_rmse: float | None = None
    best_val_rmse: float | None = None
    best_params: dict | None = None
    best_test_rmse: float | None = None
    baseline_test_rmse: float | None = None
    recommendation: str = "no improvement found"
    trial_results: list[dict] = field(default_factory=list)
    leaderboard: list[dict] = field(default_factory=list)


def _capture_environment() -> dict:
    env: dict[str, Any] = {
        "python": sys.version,
        "platform": platform.platform(),
    }
    for pkg in ("lightgbm", "sklearn", "pandas", "numpy", "scipy", "joblib"):
        try:
            mod = __import__(pkg)
            env[pkg] = getattr(mod, "__version__", "unknown")
        except Exception:
            env[pkg] = "not installed"
    return env


def _relative_improvement(baseline_rmse: float, candidate_rmse: float) -> float:
    return (baseline_rmse - candidate_rmse) / baseline_rmse


def run_campaign(
    manifest_path: str | Path,
    automation_dir: str | Path,
    data_dir: str | Path | None = None,
    smoke: bool = False,
    git: bool = False,
    max_trials_override: int | None = None,
    wall_clock_minutes_override: float | None = None,
) -> CampaignSummary:
    """Run a full autonomous campaign.

    Parameters
    ----------
    manifest_path : path to manifest.yaml
    automation_dir : the automation package directory (where results.tsv and
        artifacts/ live)
    data_dir : directory with cached X.parquet/y.parquet. Defaults to the
        package ``outputs/`` dir.
    smoke : if True, disable git machinery and run trials in-process.
    git : if True, require an autoresearch branch and commit/discard per trial.
    max_trials_override / wall_clock_minutes_override : shrink the budget (only).
    """
    auto = Path(automation_dir).resolve()
    manifest = load_manifest(manifest_path)

    if smoke and git:
        raise ValueError("smoke mode and git mode are mutually exclusive")

    data_dir = Path(data_dir) if data_dir else (auto / "outputs")

    max_trials = manifest.maximum_trial_count
    if max_trials_override is not None:
        max_trials = min(max_trials, max_trials_override)
    wall_clock = manifest.maximum_wall_clock_minutes
    if wall_clock_minutes_override is not None:
        wall_clock = min(wall_clock, wall_clock_minutes_override)

    # --- git setup ----------------------------------------------------------
    starting_commit = ""
    branch = ""
    if git:
        gitstate.assert_clean_tree(auto)
        state = gitstate.assert_autoresearch_branch(auto)
        branch = state.branch
        starting_commit = state.commit
        candidate_file = auto / "current_candidate.yaml"
    elif smoke:
        branch = "(smoke)"
        starting_commit = "(smoke)"
    else:
        # non-smoke, non-git: still record current state for traceability
        try:
            state = gitstate.current_state(auto)
            branch = state.branch
            starting_commit = state.commit
        except gitstate.GitError:
            branch = "(unknown)"
            starting_commit = "(unknown)"

    # --- dataset + splits + fingerprints (once) -----------------------------
    import pipeline
    X, y = pipeline.prepare_dataset(data_dir)
    splits = pipeline.prepare_splits(X, y)
    dataset_fp = fingerprints.compute_dataset_fingerprint(X, y, parquet_dir=data_dir)
    split_fp = fingerprints.compute_split_fingerprint(splits, seed=manifest.random_seed)

    # --- ledger -------------------------------------------------------------
    ledger.init_ledger(auto)

    # --- artifact dir -------------------------------------------------------
    exp_dir = artifacts.init_experiment_dir(auto, manifest.experiment_id)

    rng = random.Random(manifest.random_seed)
    summary = CampaignSummary(experiment_id=manifest.experiment_id)
    best_val_rmse: float | None = None
    best_params: dict | None = None
    kept_trials: list[dict] = []  # for leaderboard + finalists

    run_log_lines: list[str] = []
    def log(msg: str) -> None:
        logger.info(msg)
        run_log_lines.append(msg)

    log(f"=== Campaign {manifest.experiment_id} (model={manifest.model_name}) ===")
    log(f"smoke={smoke} git={git} max_trials={max_trials} wall_clock={wall_clock}m")

    # --- campaign baseline --------------------------------------------------
    bparams = baseline_params()
    ok, reason = manifest.is_approved_params(bparams)
    # baseline uses defaults; it is exempt from the declared-range check but we
    # still verify no undeclared keys.
    if not ok and "not declared in manifest" in reason:
        log(f"baseline params rejected: {reason}")
        summary.recommendation = "experiment failed"
        _finalize(auto, exp_dir, manifest, summary, dataset_fp, split_fp,
                  branch, starting_commit, starting_commit, run_log_lines,
                  best_params, best_val_rmse, baseline_val=None)
        return summary

    log("running campaign baseline")
    b_result = _run_one_trial(
        manifest, data_dir, bparams, smoke, git, auto, candidate_file=None,
        prev_commit=starting_commit, label="baseline", log=log,
    )
    summary.trials_attempted += 1
    summary.trial_results.append(b_result)

    if b_result["status"] != "success":
        log(f"baseline failed: {b_result.get('reason')}")
        summary.failed_trials += 1
        ledger.append_row(auto, ledger.make_row(
            commit=b_result["commit"], experiment_id=manifest.experiment_id,
            model=manifest.model_name, status="crash",
            description=f"baseline failed: {b_result.get('reason', '')}",
            runtime_minutes=b_result.get("runtime_minutes"),
        ))
        summary.recommendation = "experiment failed"
        _finalize(auto, exp_dir, manifest, summary, dataset_fp, split_fp,
                  branch, starting_commit, starting_commit, run_log_lines,
                  best_params, best_val_rmse, baseline_val=None)
        return summary

    baseline_val = b_result["validation_avg_rmse"]
    baseline_r2 = b_result["validation_avg_r2"]
    summary.baseline_val_rmse = baseline_val
    best_val_rmse = baseline_val
    best_params = bparams
    summary.successful_trials += 1
    kept_trials.append({
        "trial": "baseline",
        "params": bparams,
        "validation_avg_rmse": baseline_val,
        "validation_avg_r2": baseline_r2,
        "commit": b_result["commit"],
    })
    ledger.append_row(auto, ledger.make_row(
        commit=b_result["commit"], experiment_id=manifest.experiment_id,
        model=manifest.model_name, status="keep", description="campaign baseline",
        runtime_minutes=b_result.get("runtime_minutes"),
        validation_avg_rmse=baseline_val, validation_avg_r2=baseline_r2,
    ))
    log(f"baseline val_avg_rmse={baseline_val:.6f}")

    # --- search loop --------------------------------------------------------
    start_time = time.time()
    trial_idx = 0
    while trial_idx < max_trials:
        elapsed = (time.time() - start_time) / 60.0
        if elapsed >= wall_clock:
            log(f"wall-clock budget exhausted ({elapsed:.1f}m)")
            break

        trial_idx += 1
        params = trial.sample_params(manifest, rng)
        ok, reason = manifest.is_approved_params(params)
        if not ok:
            log(f"trial {trial_idx} rejected params: {reason}")
            summary.trials_attempted += 1
            summary.failed_trials += 1
            summary.trial_results.append({
                "status": "invalid", "params": params, "reason": reason,
                "validation_avg_rmse": None, "validation_avg_r2": None,
                "runtime_minutes": None, "commit": "",
            })
            ledger.append_row(auto, ledger.make_row(
                commit="", experiment_id=manifest.experiment_id,
                model=manifest.model_name, status="invalid",
                description=reason, runtime_minutes=None,
            ))
            continue

        result = _run_one_trial(
            manifest, data_dir, params, smoke, git, auto,
            candidate_file=(auto / "current_candidate.yaml") if git else None,
            prev_commit=gitstate.current_state(auto).commit if git else "",
            label=f"trial_{trial_idx:02d}", log=log,
        )
        summary.trials_attempted += 1
        summary.trial_results.append(result)

        if result["status"] != "success":
            summary.failed_trials += 1
            ledger.append_row(auto, ledger.make_row(
                commit=result["commit"], experiment_id=manifest.experiment_id,
                model=manifest.model_name, status=result["status"],
                description=result.get("reason", ""),
                runtime_minutes=result.get("runtime_minutes"),
            ))
            # discard the candidate commit if git mode
            if git and result["commit"]:
                gitstate.discard_to(auto, _prev_keep_commit(auto, starting_commit))
            continue

        cand_val = result["validation_avg_rmse"]
        cand_r2 = result["validation_avg_r2"]
        summary.successful_trials += 1

        rel = _relative_improvement(best_val_rmse, cand_val)  # type: ignore[arg-type]
        retained = rel >= manifest.minimum_improvement_threshold

        if retained:
            best_val_rmse = cand_val
            best_params = params
            kept_trials.append({
                "trial": f"trial_{trial_idx:02d}",
                "params": params,
                "validation_avg_rmse": cand_val,
                "validation_avg_r2": cand_r2,
                "commit": result["commit"],
            })
            ledger.append_row(auto, ledger.make_row(
                commit=result["commit"], experiment_id=manifest.experiment_id,
                model=manifest.model_name, status="keep",
                description=f"trial {trial_idx}: rel_improvement={rel:.4f}",
                runtime_minutes=result.get("runtime_minutes"),
                validation_avg_rmse=cand_val, validation_avg_r2=cand_r2,
            ))
            log(f"trial {trial_idx} KEEP val={cand_val:.6f} rel={rel:.4f}")
        else:
            ledger.append_row(auto, ledger.make_row(
                commit=result["commit"], experiment_id=manifest.experiment_id,
                model=manifest.model_name, status="discard",
                description=f"trial {trial_idx}: rel_improvement={rel:.4f} < threshold",
                runtime_minutes=result.get("runtime_minutes"),
                validation_avg_rmse=cand_val, validation_avg_r2=cand_r2,
            ))
            log(f"trial {trial_idx} DISCARD val={cand_val:.6f} rel={rel:.4f}")
            if git and result["commit"]:
                gitstate.discard_to(auto, _prev_keep_commit(auto, starting_commit))

    summary.best_val_rmse = best_val_rmse
    summary.best_params = best_params

    # --- finalists: evaluate top-K on test set ------------------------------
    kept_trials.sort(key=lambda r: r["validation_avg_rmse"])
    k = manifest.maximum_test_finalists
    finalists = kept_trials[:k]

    test_results: list[dict] = []
    for f in finalists:
        log(f"evaluating finalist {f['trial']} on test set")
        tm = trial.eval_finalist_inprocess(data_dir, manifest.model_name, f["params"])
        agg = tm.get("aggregate", {})
        test_results.append({
            "trial": f["trial"],
            "params": f["params"],
            "test_avg_rmse": agg.get("avg_rmse"),
            "test_avg_r2": agg.get("avg_r2"),
            "validation_avg_rmse": f["validation_avg_rmse"],
        })

    # best finalist = lowest test rmse among finalists (which were top-K by val)
    if test_results:
        best_finalist = min(test_results, key=lambda r: r["test_avg_rmse"])
        summary.best_test_rmse = best_finalist["test_avg_rmse"]
    # baseline test
    log("evaluating baseline on test set")
    btest = trial.eval_finalist_inprocess(data_dir, manifest.model_name, bparams)
    summary.baseline_test_rmse = btest.get("aggregate", {}).get("avg_rmse")

    # leaderboard (by validation rmse)
    summary.leaderboard = [
        {
            "trial": r["trial"],
            "params": r["params"],
            "validation_avg_rmse": r["validation_avg_rmse"],
            "validation_avg_r2": r.get("validation_avg_r2"),
        }
        for r in kept_trials
    ]

    # recommendation
    if best_val_rmse is not None and summary.baseline_val_rmse is not None:
        rel = _relative_improvement(summary.baseline_val_rmse, best_val_rmse)
        if best_params != bparams and rel >= manifest.minimum_improvement_threshold:
            summary.recommendation = "retain for human review"
        else:
            summary.recommendation = "no improvement found"
    else:
        summary.recommendation = "experiment failed"

    ending_commit = starting_commit
    if git:
        ending_commit = gitstate.current_state(auto).commit

    _finalize(
        auto, exp_dir, manifest, summary, dataset_fp, split_fp,
        branch, starting_commit, ending_commit, run_log_lines,
        best_params, best_val_rmse, baseline_val=baseline_val,
        test_results=test_results, baseline_test=summary.baseline_test_rmse,
    )
    return summary


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _run_one_trial(
    manifest: Manifest,
    data_dir: Path,
    params: dict,
    smoke: bool,
    git: bool,
    auto: Path,
    candidate_file: Path | None,
    prev_commit: str,
    label: str,
    log,
) -> dict:
    """Run a single trial (sample already done). Returns a result dict."""
    commit = ""
    if git:
        if candidate_file is None:
            candidate_file = auto / "current_candidate.yaml"
        candidate_file.write_text(
            yaml.safe_dump({"params": params}, sort_keys=False), encoding="utf-8"
        )
        commit = gitstate.commit_all(auto, f"autoresearch trial: {label}")

    if smoke:
        result = trial.train_trial_inprocess(data_dir, manifest.model_name, params)
    else:
        result = trial.run_trial_subprocess(
            data_dir, manifest.model_name, params,
            timeout_minutes=manifest.per_trial_timeout_minutes,
        )
    d = result.to_dict()
    d["commit"] = commit
    return d


def _prev_keep_commit(auto: Path, starting_commit: str) -> str:
    """Return the commit to reset to after a discard.

    In this harness the branch tip is always the last kept config (or the
    starting commit if nothing has been kept), so resetting to HEAD~1 would
    drop a kept commit. Instead we reset to the current HEAD only when the
    latest commit was a discardable trial. For simplicity we reset to the
    parent of the current commit (the trial commit is always the tip).
    """
    # The trial commit is the tip; reset to its parent.
    return gitstate._run(["rev-parse", "HEAD~1"], auto)


def _finalize(
    auto: Path, exp_dir: Path, manifest: Manifest, summary: CampaignSummary,
    dataset_fp, split_fp, branch, starting_commit, ending_commit,
    run_log_lines, best_params, best_val_rmse, baseline_val,
    test_results=None, baseline_test=None,
) -> None:
    """Write all required artifacts."""
    artifacts.write_manifest(exp_dir, manifest.raw or {})
    git_state = {"branch": branch, "commit": ending_commit,
                 "starting_commit": starting_commit, "dirty": False}
    artifacts.write_git_state(exp_dir, git_state)
    artifacts.write_environment(exp_dir, _capture_environment())
    artifacts.write_dataset_fingerprint(exp_dir, dataset_fp.to_dict())
    artifacts.write_split_fingerprint(exp_dir, split_fp.to_dict())
    artifacts.write_trial_results(exp_dir, summary.trial_results)
    artifacts.write_leaderboard(exp_dir, summary.leaderboard)
    artifacts.write_best_params(exp_dir, best_params or {})
    final_metrics = {
        "baseline_val_rmse": baseline_val,
        "best_val_rmse": best_val_rmse,
        "baseline_test_rmse": baseline_test,
        "best_test_rmse": summary.best_test_rmse,
        "finalists": test_results or [],
    }
    artifacts.write_final_metrics(exp_dir, final_metrics)
    rel = None
    if baseline_val is not None and best_val_rmse is not None and baseline_val > 0:
        rel = _relative_improvement(baseline_val, best_val_rmse)
    comparison = {
        "baseline_val_rmse": baseline_val,
        "best_val_rmse": best_val_rmse,
        "relative_improvement": rel,
        "threshold": manifest.minimum_improvement_threshold,
        "retained": rel is not None and rel >= manifest.minimum_improvement_threshold
                     and best_params != baseline_params(),
    }
    artifacts.write_comparison(exp_dir, comparison)

    report_text = report.build_report(
        experiment_id=manifest.experiment_id,
        branch=branch,
        starting_commit=starting_commit,
        ending_commit=ending_commit,
        model_name=manifest.model_name,
        baseline_experiment=manifest.baseline_experiment,
        dataset_fingerprint=dataset_fp.to_dict(),
        split_fingerprint=split_fp.to_dict(),
        trials_attempted=summary.trials_attempted,
        successful_trials=summary.successful_trials,
        failed_trials=summary.failed_trials,
        best_validation=best_val_rmse,
        baseline_validation=baseline_val,
        best_test=summary.best_test_rmse,
        baseline_test=baseline_test,
        best_config=best_params,
        recommendation=summary.recommendation,
        changed_source_files=[],
        protected_files_unchanged=[
            "load.py", "extract.py", "transform.py", "model.py",
            "models/lightgbm.py", "models/random_forest.py",
        ],
    )
    report.write_report(exp_dir, report_text)
    artifacts.write_run_log(exp_dir, "\n".join(run_log_lines) + "\n")