# Autonomous Model Experimentation Specification

This is the contract the harness implements. Read it before writing harness code
so you understand *why* each invariant exists, not just *what* to build.

## Purpose

Allow a coding agent to run bounded overnight model experiments — primarily
hyperparameter searches — without changing the curated dataset, feature
engineering, target definitions, data-splitting rules, or evaluation contract.

The agent may search for better model configurations. It may not redefine what
"better" means.

## Core Principles

1. **Reproducibility** — every result traceable to a git commit, model config,
   dataset fingerprint, split fingerprint, and random seed.
2. **Fair comparison** — candidates use the existing dataset, features, targets,
   split logic, and evaluation metrics. Same evaluation protocol for all.
3. **Validation-first tuning** — hyperparameter selection on validation only.
   The test set never guides the search.
4. **Bounded autonomy** — the agent operates within the approved budget; stops
   at trial/time limits; never runs indefinitely.
5. **No automatic promotion** — the agent recommends; a human promotes.
6. **Append-only results** — artifacts never overwritten; each experiment gets a
   unique ID and directory.

## Protected Scope

The **ETL pipeline** is the protected boundary. The agent must not modify the
files that implement:

- Dataset extraction and loading.
- Curated feature definitions / feature-engineering / feature-reduction.
- Target definitions / target transforms.
- Canonical train/validation/test split behavior (seed 42, split ratios).
- Evaluation metric definitions.

The agent **may** modify for optimization purposes:

- The model config class (extending with new hyperparameter fields).
- Model implementations (adding new families, extending trainers).
- The harness itself.
- Manifests.
- New files within the experiment package.

The agent must not improve performance by changing the dataset, features, target
values, split boundaries, or official evaluation metrics.

## Official Optimization Metric

Primary: **validation average RMSE** (mean per-target RMSE on the validation
set). Lower is better.

Secondary (recorded, not selecting): validation average R², per-target RMSE/R²,
test average RMSE/R², runtime.

## Baseline Definition

Two distinct baselines, do not conflate:

1. **Reference baseline (sanity check):** mean-prediction baseline (predicts
   training mean, uses no features). Confirms a real model outperforms a
   no-information predictor. NOT the keep/discard anchor.
2. **Campaign baseline (keep/discard anchor):** the model's default config
   (e.g. default `ModelConfig` + default strategy). The harness runs this first
   and records it as the initial "keep" row. Candidates must beat it by the
   threshold to be retained.

If no campaign baseline exists, run it first. If the default config doesn't
outperform the reference baseline, stop and report (don't search for a baseline).

## Dataset and Split Policy

- Use the existing curated features, targets, dataset pipeline, and split logic.
- The **split seed is 42** (ETL-protected, hardcoded in split logic). The harness
  records it; never overrides it.
- The **model seed** is a searchable hyperparameter (the agent may vary it for
  robustness testing by declaring `random_state` in the manifest).
- Never reshuffle, change boundaries, combine val+test, train on test, or
  repeatedly inspect test performance during search.

## Fingerprints

Make results traceable and gate keep/discard.

**Dataset fingerprint** (`dataset_fingerprint.json`):
- `shape`: X and y shapes.
- `columns`: ordered X and y column lists.
- `hash`: SHA256 of concatenated dataset bytes (parquet file bytes if cached,
  else in-memory parquet serialization).

**Split fingerprint** (`split_fingerprint.json`):
- `seed`: 42.
- `ratios`: train/val ratios.
- `train_index`, `val_index`, `test_index`: ordered row labels per partition.
- `hash`: SHA256 of canonical serialization (labels as strings, newline-
  separated, in train/val/test order).

A candidate is retained only when both fingerprints match the manifest. A
mismatch is a stop condition.

## Test Set Policy

Test set is for final confirmation only:

1. Train each trial on training data.
2. Evaluate each trial on validation data.
3. Rank completed trials by validation average RMSE.
4. Select the top `K` validation candidates (default K=3).
5. Evaluate only those finalists on the test set.
6. Record test metrics in the final report.

Never use test metrics to decide which trials to retain during the search.

## Experiment Manifest

A YAML file (`manifest.yaml`) defining at least:

```
experiment_id
description
model_name
baseline_experiment
dataset_version or dataset fingerprint
split identifier or split fingerprint
split_seed (must be 42)
primary metric
search method
allowed hyperparameters (advisory)
maximum trial count
maximum wall-clock duration
maximum test finalists
artifact output location
```

No experiment without a valid manifest.

### Allowed Hyperparameters (advisory)

Each entry: `name`, `type` (numeric|categorical), `range` (for numeric), or
`choices` (for categorical). The declared set is a **starting point, not a
ceiling**. The agent may search beyond it. The harness logs (not rejects)
undeclared or out-of-range params. All params used must be recorded in the trial
artifact.

## Dependency Installation

The agent may install missing packages with `uv pip install <pkg>` (not plain
`pip`, not `uv add` — this project is uv-managed). Record installed packages in
`environment.json`. Never modify pinned dependency files (`pyproject.toml`,
`setup.py`, `requirements*.txt`) without human approval. Install failure is a
stop condition.

## Default Resource Limits

Unless the manifest specifies stricter:

```
maximum trials: 30
maximum wall-clock time: 2 hours
maximum test finalists: 3
maximum retries for a broken trial: 2
per-trial timeout: 10 minutes
```

The harness runs trials sequentially. Model-internal parallelism (e.g.
`n_jobs=-1`) stays at its default.

## Git Workflow

All autonomous experimentation on a dedicated `autoresearch/<run-tag>` branch.

The harness **auto-creates** this branch in git mode if the agent is not already
on one. The branch name is derived from the manifest's `run_tag` field (or
`experiment_id` if `run_tag` is unset). The agent does not need to create the
branch manually.

Before the loop:
1. Confirm the working tree is clean.
2. Harness auto-creates `autoresearch/<run_tag>` if not on an autoresearch branch.
3. Record the starting commit hash.
4. Create the manifest.
5. Initialize the results ledger.
6. Run the campaign baseline if none exists.

Never: commit to main/master, merge, push, rewrite shared history, delete
branches, use destructive git off the autoresearch branch, or commit generated
artifacts/models/ledger unless requested.

## Autonomous Experiment Loop

The agent is the intelligent driver; the harness is the tool.

### Outer loop (agent-driven, default 3 iterations)

The outer loop runs a **fixed number of iterations** (default 3, configurable).
Each iteration is one full campaign (inner loop, ~30 trials of random search by
default). The loop stops early only if a stop condition fires (budget exhausted,
ETL violation, dependency install failure, or the agent judges further iteration
won't help — e.g. two consecutive campaigns with no improvement).

For each iteration:

1. **Observe:** Run a campaign (inner loop) with the current manifest and model
   code. Read its outputs: `results.tsv`, `leaderboard.csv`, `report.md`,
   `comparison_to_baseline.json`, per-target metrics.
2. **Reason:** Analyze what happened. Which hyperparameters correlated with
   improvement? Which ranges were unexplored? Did any target underperform? Would
   a new model family or hyperparameter help? Did the best config plateau?
3. **Act:** Write a NEW manifest with a new `experiment_id` and adjusted
   hyperparameter bounds based on the reasoning. Optionally extend the config
   class or model trainer. Optionally install a new dependency
   (`uv pip install`). Then run the next campaign.

Do not ask permission between normal outer-loop iterations. Each iteration
produces its own experiment_id, artifact directory, and ledger rows. The ledger
accumulates across iterations.

### Inner loop (campaign, harness-driven)

Within one campaign, bounded random search:

1. Run the campaign baseline if none exists.
2. For each trial:
   a. Sample a candidate config from the manifest's advisory hyperparameters.
      The "trial change" is this config (recorded as `trial_params.yaml`), NOT a
      source-code edit.
   b. Commit the candidate config on the autoresearch branch (git mode).
   c. Run the experiment with output to a run log.
   d. Record the result in `results.tsv` with the trial's commit hash.
   e. Compare validation average RMSE to the current best.
   f. Keep if it improves by the threshold; else discard.
   g. Discard = `git reset --hard <prev_commit>` on the autoresearch branch
      (destructive ops permitted ONLY on the autoresearch branch). The ledger
      row is the durable record.
3. Continue until the trial/time budget is exhausted.
4. Evaluate the top-K finalists on the test set.

Stop and report on: ETL-protected change, dependency install failure, invalid
data, ambiguous requirements, or safety concerns.

## Keep / Discard Rule

Retain a candidate only when ALL true:

1. The experiment completed successfully.
2. Reproducibility is attested (commit + config + seed + fingerprints recorded).
3. Dataset and split fingerprints match the manifest.
4. The candidate improves validation average RMSE.
5. The improvement exceeds the minimum threshold (default 0.5% relative).
6. No ETL-protected files were modified.

`relative_improvement = (baseline_rmse - candidate_rmse) / baseline_rmse`.
Retain when `relative_improvement >= 0.005` (default; manifest may override).

## Failed Trial Policy

Record failures, don't hide them. Examples: exception, invalid params, OOM,
timeout, missing dependency, invalid output shape, missing metrics, dataset/split
mismatch, ETL-protected file modification.

For an obvious mistake (typo, missing import), the agent may attempt up to 2
fixes. If the idea is broken or repeatedly fails: mark `crash` or `invalid`,
record the reason in `results.tsv`, discard, continue.

## Results Ledger

Untracked `results.tsv` at the package root. Append-only. Columns:

```
commit  experiment_id  model  validation_avg_rmse  validation_avg_r2
test_avg_rmse  test_avg_r2  runtime_minutes  status  description
```

Statuses: `keep`, `discard`, `crash`, `invalid`. Test metrics blank for
non-finalists.

## Required Experiment Artifacts

Each experiment writes to `artifacts/experiments/<experiment_id>/` (relative to
the package dir). Required files:

```
manifest.yaml
git_state.json
environment.json
dataset_fingerprint.json
split_fingerprint.json
trial_results.csv
leaderboard.csv
best_params.yaml
final_metrics.json
comparison_to_baseline.json
report.md
```

Optional: `run.log`, `plots/`, `models/`. Existing artifact dirs never overwritten.

## Final Report

Concise markdown containing: experiment ID, branch, starting/ending commit,
model, baseline, fingerprints, trials attempted/successful/failed, best
validation, baseline validation, best test, baseline test, best config,
recommendation, changed source files, protected files confirmed unchanged.

Recommendation must be one of: `retain for human review`, `no improvement found`,
`experiment failed`, `needs human decision`. Never "production-ready".

## Stop Conditions

Stop when: max trials reached, max wall-clock reached, dependency install fails,
dataset can't load/validate, split fingerprint differs from manifest, an
ETL-protected file would need modification, ambiguous requirement affecting
fairness/safety, or user interrupts. On stop, write the final report and leave
the repo clean on the autoresearch branch.

## Explicit Non-Goals

No autonomous changes to: feature engineering, data cleaning, target
transformation strategy, train/test split strategy, time-series/walk-forward
validation, ensemble construction, automatic model promotion, automatic
merging/pushing, unlimited experimentation.