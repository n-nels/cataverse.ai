"""Unit tests for the harness pure-logic components.

These tests need only pyyaml + pytest (no ML deps) and run against a temp
directory. Git integration is tested against a throwaway temp git repo.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

# Ensure the automation package dir is importable.
AUTOMATION_DIR = Path(__file__).resolve().parent.parent
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))

from harness import gitstate, ledger, report
from harness.manifest import (
    CANONICAL_SEED, Manifest, ManifestError, HyperparameterSpec, load_manifest,
)
from harness.trial import sample_params, build_model_config, get_strategy


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def _write_manifest(tmp_path: Path, **overrides) -> Path:
    base = {
        "experiment_id": "test_v1",
        "description": "test",
        "model_name": "lightgbm",
        "baseline_experiment": "baseline",
        "split_seed": 42,
        "primary_metric": "validation_avg_rmse",
        "search_method": "random",
        "allowed_hyperparameters": [
            {"name": "n_estimators", "type": "numeric", "range": [100, 500]},
            {"name": "strategy", "type": "categorical", "choices": ["shared", "separate"]},
        ],
        "maximum_trial_count": 5,
        "maximum_wall_clock_minutes": 10,
        "maximum_test_finalists": 2,
        "artifact_output_location": "artifacts/experiments",
    }
    base.update(overrides)
    p = tmp_path / "manifest.yaml"
    p.write_text(yaml.safe_dump(base), encoding="utf-8")
    return p


def test_load_manifest_valid(tmp_path):
    m = load_manifest(_write_manifest(tmp_path))
    assert m.experiment_id == "test_v1"
    assert m.split_seed == CANONICAL_SEED
    assert len(m.allowed_hyperparameters) == 2
    assert m.maximum_trial_count == 5


def test_load_manifest_missing_field(tmp_path):
    p = _write_manifest(tmp_path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    del raw["maximum_trial_count"]
    p.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ManifestError, match="missing required fields"):
        load_manifest(p)


def test_load_manifest_rejects_noncanonical_seed(tmp_path):
    p = _write_manifest(tmp_path, split_seed=99)
    with pytest.raises(ManifestError, match="split_seed must be the canonical seed"):
        load_manifest(p)


def test_hyperparameter_spec_numeric_requires_range():
    with pytest.raises(ManifestError, match="no valid range"):
        HyperparameterSpec(name="x", type="numeric", range=None)


def test_hyperparameter_spec_categorical_requires_choices():
    with pytest.raises(ManifestError, match="no choices"):
        HyperparameterSpec(name="x", type="categorical", choices=None)


def test_hyperparameter_spec_bad_type():
    with pytest.raises(ManifestError, match="unsupported type"):
        HyperparameterSpec(name="x", type="bogus", choices=[1])


def test_is_approved_params_warns_undeclared(tmp_path):
    m = load_manifest(_write_manifest(tmp_path))
    ok, reason = m.is_approved_params({"not_a_field": 1})
    assert ok  # advisory: always True
    assert "not declared" in reason


def test_is_approved_params_warns_out_of_range(tmp_path):
    m = load_manifest(_write_manifest(tmp_path))
    ok, reason = m.is_approved_params({"n_estimators": 99999})
    assert ok  # advisory: always True
    assert "outside declared bounds" in reason


def test_is_approved_params_accepts_valid(tmp_path):
    m = load_manifest(_write_manifest(tmp_path))
    ok, reason = m.is_approved_params({"n_estimators": 200, "strategy": "shared"})
    assert ok
    assert reason == ""  # no warnings for in-bounds declared params


# ---------------------------------------------------------------------------
# Trial sampling / config building
# ---------------------------------------------------------------------------

def test_sample_params_respects_bounds(tmp_path):
    import random
    m = load_manifest(_write_manifest(tmp_path))
    rng = random.Random(42)
    for _ in range(50):
        p = sample_params(m, rng)
        assert 100 <= p["n_estimators"] <= 500
        assert p["strategy"] in ("shared", "separate")


def test_build_model_config_filters_unknown_fields():
    cfg = build_model_config({"n_estimators": 50, "learning_rate": 0.1,
                              "max_depth": 3, "early_stopping_rounds": 5,
                              "strategy": "shared", "bogus": 999})
    assert cfg.n_estimators == 50
    assert not hasattr(cfg, "strategy")
    assert not hasattr(cfg, "bogus")


def test_get_strategy_default():
    assert get_strategy({}) == "shared"
    assert get_strategy({"strategy": "separate"}) == "separate"


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

def test_ledger_init_and_append(tmp_path):
    ledger.init_ledger(tmp_path)
    row = ledger.make_row(
        commit="abc", experiment_id="e1", model="lightgbm", status="keep",
        description="baseline", runtime_minutes=1.5,
        validation_avg_rmse=0.5, validation_avg_r2=0.6,
    )
    ledger.append_row(tmp_path, row)
    rows = ledger.read_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0].status == "keep"
    assert rows[0].validation_avg_rmse == "0.500000"


def test_ledger_rejects_bad_status(tmp_path):
    with pytest.raises(ValueError, match="invalid status"):
        ledger.make_row(commit="a", experiment_id="e", model="m",
                        status="bogus", description="x")


def test_best_kept_row(tmp_path):
    ledger.init_ledger(tmp_path)
    for rmse, status in [(0.5, "keep"), (0.4, "keep"), (0.3, "discard"), (None, "crash")]:
        ledger.append_row(tmp_path, ledger.make_row(
            commit="c", experiment_id="e", model="m", status=status,
            description="d", validation_avg_rmse=rmse,
        ))
    best = ledger.best_kept_row(tmp_path)
    assert best is not None
    assert float(best.validation_avg_rmse) == 0.4


def test_ledger_blank_test_for_discard(tmp_path):
    ledger.init_ledger(tmp_path)
    ledger.append_row(tmp_path, ledger.make_row(
        commit="c", experiment_id="e", model="m", status="discard",
        description="d", validation_avg_rmse=0.5,
    ))
    rows = ledger.read_rows(tmp_path)
    assert rows[0].test_avg_rmse == ""


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def test_report_rejects_bad_recommendation():
    with pytest.raises(ValueError, match="invalid recommendation"):
        report.build_report(
            experiment_id="e", branch="b", starting_commit="a", ending_commit="c",
            model_name="lightgbm", baseline_experiment="base",
            dataset_fingerprint={"hash": "h"}, split_fingerprint={"hash": "h"},
            trials_attempted=1, successful_trials=1, failed_trials=0,
            best_validation=0.5, baseline_validation=0.6,
            best_test=0.5, baseline_test=0.6, best_config={"a": 1},
            recommendation="production-ready",
            changed_source_files=[], protected_files_unchanged=[],
        )


def test_report_renders_valid():
    text = report.build_report(
        experiment_id="e", branch="autoresearch/x", starting_commit="a",
        ending_commit="c", model_name="lightgbm", baseline_experiment="base",
        dataset_fingerprint={"hash": "dh"}, split_fingerprint={"hash": "sh"},
        trials_attempted=3, successful_trials=2, failed_trials=1,
        best_validation=0.5, baseline_validation=0.6,
        best_test=0.5, baseline_test=0.6, best_config={"a": 1},
        recommendation="retain for human review",
        changed_source_files=["model.py"], protected_files_unchanged=["load.py"],
    )
    assert "retain for human review" in text
    assert "autoresearch/x" in text
    assert "model.py" in text
    assert "load.py" in text


# ---------------------------------------------------------------------------
# Git state (against a throwaway temp repo)
# ---------------------------------------------------------------------------

def _init_temp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = "test"
    env["GIT_AUTHOR_EMAIL"] = "test@example.com"
    env["GIT_COMMITTER_NAME"] = "test"
    env["GIT_COMMITTER_EMAIL"] = "test@example.com"
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    (repo / "f.txt").write_text("init", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True, env=env)
    return repo


def test_git_state_clean(tmp_path):
    repo = _init_temp_repo(tmp_path)
    state = gitstate.current_state(repo)
    assert state.dirty is False
    gitstate.assert_clean_tree(repo)


def test_git_state_dirty(tmp_path):
    repo = _init_temp_repo(tmp_path)
    (repo / "f.txt").write_text("changed", encoding="utf-8")
    state = gitstate.current_state(repo)
    assert state.dirty is True
    with pytest.raises(gitstate.GitError, match="not clean"):
        gitstate.assert_clean_tree(repo)


def test_git_refuses_destructive_off_autoresearch_branch(tmp_path):
    repo = _init_temp_repo(tmp_path)
    with pytest.raises(gitstate.GitError, match="not an autoresearch branch"):
        gitstate.discard_to(repo, "HEAD~1")


def test_git_commit_and_discard_on_autoresearch_branch(tmp_path):
    repo = _init_temp_repo(tmp_path)
    subprocess.run(["git", "checkout", "-q", "-b", "autoresearch/test"],
                   cwd=repo, check=True)
    (repo / "cand.txt").write_text("v1", encoding="utf-8")
    c1 = gitstate.commit_all(repo, "trial 1")
    assert gitstate.current_state(repo).commit == c1
    (repo / "cand.txt").write_text("v2", encoding="utf-8")
    c2 = gitstate.commit_all(repo, "trial 2")
    assert gitstate.current_state(repo).commit == c2
    # discard trial 2 -> back to trial 1
    gitstate.discard_to(repo, c1)
    assert gitstate.current_state(repo).commit == c1
    assert (repo / "cand.txt").read_text(encoding="utf-8") == "v1"


def test_git_create_branch_rejects_non_autoresearch(tmp_path):
    repo = _init_temp_repo(tmp_path)
    with pytest.raises(gitstate.GitError, match="non-autoresearch"):
        gitstate.create_branch(repo, "feature/x")


def test_git_protected_files_changed(tmp_path):
    repo = _init_temp_repo(tmp_path)
    # no changes -> empty
    assert gitstate.protected_files_changed(repo) == []
    # touch a protected file
    (repo / "load.py").write_text("changed", encoding="utf-8")
    changed = gitstate.protected_files_changed(repo)
    assert "load.py" in changed
    # touch a non-protected file
    (repo / "model.py").write_text("changed", encoding="utf-8")
    changed = gitstate.protected_files_changed(repo)
    assert "load.py" in changed
    assert "model.py" not in changed