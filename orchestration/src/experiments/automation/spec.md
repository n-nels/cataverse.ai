# Autonomous Model Experimentation Specification

## Purpose

This package supports controlled, autonomous experimentation for prediction models.

The goal is to allow a coding agent to run bounded overnight model experiments—primarily hyperparameter searches—without changing the curated dataset, feature engineering, target definitions, data-splitting rules, or evaluation contract.

The agent may search for better model configurations. It may not redefine what “better” means.

---

## Core Principles

1. **Reproducibility**
   - Every experiment must have a named configuration and recorded results.
   - Every result must be traceable to a Git commit, model configuration, dataset fingerprint, split fingerprint, and random seed.

2. **Fair comparison**
   - Candidate models must use the existing dataset, curated features, targets, split logic, and evaluation metrics.
   - Models may only be compared when they use the same evaluation protocol.

3. **Validation-first tuning**
   - Hyperparameter selection is based on validation performance only.
   - The test set must not be used to guide hyperparameter search.

4. **Bounded autonomy**
   - The agent may operate autonomously within the approved scope and resource budget.
   - The agent must stop when it reaches the configured time or trial limit.
   - The agent must not run indefinitely.

5. **No automatic promotion**
   - An experiment may produce a recommended candidate.
   - Only a human may change the default model, production artifact, or baseline configuration.

6. **Append-only results**
   - Completed experiment artifacts must never be overwritten.
   - Each experiment receives a unique experiment ID and output directory.

---

## Protected Scope

The following are protected and must not be modified by the autonomous experiment agent unless the user explicitly authorizes it in a task:

- Dataset extraction and loading behavior.
- Curated feature definitions.
- Feature-engineering logic.
- Feature-reduction logic.
- Target definitions.
- Target transforms.
- Canonical train/validation/test split behavior.
- Evaluation metric definitions.
- Existing baseline model artifacts.
- Default model selection.
- Production configuration.
- Existing completed experiment artifacts.
- Dependency files and package versions.
- Files outside the approved experiment scope.

The agent must not attempt to improve performance by changing the dataset, features, target values, split boundaries, or official evaluation metrics.

---

## Official Optimization Metric

The primary optimization metric is:

```text
validation average RMSE
```

Lower is better.

Validation average RMSE is the arithmetic mean of per-target RMSE values produced by the existing evaluation pipeline.

Secondary metrics may be recorded for review, including:

```text
validation average R²
per-target RMSE
per-target R²
test average RMSE
test average R²
runtime
memory usage, when available
```

Secondary metrics do not override the primary metric unless the experiment manifest explicitly defines a different approved selection policy.

---

## Dataset and Split Policy

All candidate experiments must use:

- The existing curated feature set.
- The existing target definitions.
- The existing dataset-building pipeline.
- The existing canonical train/validation/test split behavior.
- The same random seed specified in the experiment manifest.

The agent must not:

- Reshuffle data to seek a better score.
- Change chronological boundaries.
- Alter validation holdout behavior.
- Combine validation and test sets.
- Train directly on the test set during tuning.
- Repeatedly inspect test-set performance while searching.

---

## Test Set Policy

The test set is reserved for final confirmation only.

Required workflow:

1. Train each trial using the training data.
2. Evaluate each trial on the validation data.
3. Rank completed trials by validation average RMSE.
4. Select the top `K` validation candidates.
5. Evaluate only those finalists on the test set.
6. Record test metrics in the final experiment report.

Default value:

```text
top K = 3
```

The agent must not use test-set metrics to decide which hyperparameter trials to retain during the active search loop.

---

## Experiment Manifest Requirement

Every experiment must begin with an experiment manifest.

The manifest must define at least:

```text
experiment_id
description
model_name
baseline_experiment
dataset_version or dataset fingerprint
split identifier or split fingerprint
random seed
primary metric
search method
allowed hyperparameters
maximum trial count
maximum wall-clock duration
maximum parallel workers
maximum test finalists
artifact output location
```

The agent must not run an experiment without a valid manifest.

---

## Hyperparameter Search Policy

The default search method is bounded random search.

Grid search may be used only when the total number of combinations is small and explicitly bounded.

The agent must not invent unsupported parameters or set values outside the configured ranges.

---

## Default Resource Limits

Unless an experiment manifest specifies stricter limits, use:

```text
maximum trials: 30
maximum wall-clock time: 2 hours
maximum parallel trials: 2
maximum test finalists: 3
maximum retries for a broken trial: 2
```

A trial must be stopped and marked as failed if it exceeds the configured per-trial timeout.

The agent must not bypass limits by launching additional processes, changing parallelism settings, or creating extra manifests.

---

## Git Workflow

All autonomous experimentation must occur on a dedicated branch.

Branch naming convention:

```text
autoresearch/<run-tag>
```

Example:

```text
autoresearch/rf-v1
```

Before beginning the loop, the agent must:

1. Confirm the current Git working tree is clean.
2. Create or switch to the dedicated autoresearch branch.
3. Record the starting commit hash.
4. Create the experiment manifest.
5. Initialize the results ledger.
6. Run a baseline experiment if no baseline result exists for the current protocol.

The agent must not:

- Commit directly to `main` or `master`.
- Merge branches.
- Push branches.
- Rewrite shared history.
- Delete branches.
- Use destructive Git commands outside the dedicated autoresearch branch.
- Commit generated experiment artifacts, trained model binaries, plots, caches, or the results ledger unless explicitly requested.

---

## Autonomous Experiment Loop

For each experiment iteration:

1. Inspect the current branch, commit, manifest, and results ledger.
2. Select one bounded experiment idea.
3. Modify only approved configuration or implementation files.
4. Commit the proposed change on the autoresearch branch.
5. Run the experiment with output redirected to a run log.
6. Read the structured result output.
7. Record the result in `results.tsv`.
8. Compare validation average RMSE against the current retained best result.
9. Keep the commit only if it improves the primary metric by the required threshold.
10. Discard or revert the change if it is equal, worse, invalid, or crashes.
11. Continue until the configured trial or time budget is exhausted.

The agent must not ask for permission between normal iterations. It should continue within the approved budget.

The agent must stop and report if it encounters a protected-scope change, a missing dependency, invalid data, ambiguous requirements, or a safety concern.

---

## Keep / Discard Rule

A candidate may be retained only when all of the following are true:

1. The experiment completed successfully.
2. The result is reproducible.
3. The dataset and split fingerprints match the experiment manifest.
4. The candidate used only approved parameters.
5. The candidate improves validation average RMSE.
6. The improvement exceeds the configured minimum threshold.
7. No protected files were modified.

Default minimum improvement threshold:

```text
0.5% relative improvement in validation average RMSE
```

If the current best validation average RMSE is `baseline_rmse` and the candidate score is `candidate_rmse`, then:

```text
relative_improvement =
    (baseline_rmse - candidate_rmse) / baseline_rmse
```

A candidate is retained only when:

```text
relative_improvement >= 0.005
```

A human may approve a different threshold in the experiment manifest.

---

## Failed Trial Policy

A failed experiment must be recorded, not hidden.

Examples of failure:

- Python exception.
- Invalid parameter combination.
- Out-of-memory failure.
- Timeout.
- Missing model dependency.
- Invalid output shape.
- Missing metrics.
- Dataset or split mismatch.
- Any modification to protected scope.

For an obvious implementation mistake, such as a typo or missing import, the agent may attempt up to two fixes.

If the underlying experiment idea is broken or repeatedly fails, the agent must:

1. Mark the trial as `crash` or `invalid`.
2. Record a concise reason in `results.tsv`.
3. Discard the candidate change.
4. Continue to the next approved experiment idea.

---

## Results Ledger

Each autonomous campaign must maintain an untracked file named:

```text
results.tsv
```

The file must remain uncommitted unless the user explicitly requests otherwise.

The required tab-separated columns are:

```text
commit
experiment_id
model
validation_avg_rmse
validation_avg_r2
test_avg_rmse
test_avg_r2
runtime_minutes
status
description
```

Allowed statuses:

```text
keep
discard
crash
invalid
```

Example:

```tsv
commit	experiment_id	model	validation_avg_rmse	validation_avg_r2	test_avg_rmse	test_avg_r2	runtime_minutes	status	description
a1b2c3d	rf_baseline	random_forest	0.842100	0.610000	0.861200	0.590000	8.4	keep	initial baseline
b2c3d4e	rf_v1_trial_01	random_forest	0.831400	0.618000				10.1	keep	increase n_estimators and adjust max_features
c3d4e5f	rf_v1_trial_02	random_forest	0.846200	0.603000				9.6	discard	reduce min_samples_leaf
d4e5f6g	rf_v1_trial_03	random_forest	0.000000	0.000000				2.1	crash	invalid max_features configuration
```

Test metrics may remain blank for discarded candidates because test evaluation is reserved for finalists.

---

## Required Experiment Artifacts

Each completed experiment must write artifacts to a unique directory:

```text
artifacts/experiments/<experiment_id>/
```

Required files:

```text
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

Optional artifacts:

```text
run.log
plots/
models/
```

Existing artifact directories must never be overwritten.

---

## Final Report Requirement

At the end of an autonomous campaign, the agent must create a concise Markdown report containing:

```text
experiment ID
branch name
starting commit
ending commit
model tested
baseline used
dataset fingerprint
split fingerprint
number of trials attempted
number of successful trials
number of failed trials
best validation result
baseline validation result
best test result, if evaluated
baseline test result
best retained configuration
recommendation
list of changed source files
list of protected files confirmed unchanged
```

The report recommendation must be one of:

```text
retain for human review
no improvement found
experiment failed
needs human decision
```

The agent must not state that a candidate is “production-ready” or automatically change the default model.

---

## Human Review and Promotion

A retained candidate is not automatically promoted.

Only a human may:

- Merge the autoresearch branch.
- Update the default model.
- Replace a baseline.
- Replace a saved production artifact.
- Modify the canonical experiment protocol.
- Approve a new model family.
- Approve feature or target changes.
- Approve dependency changes.

A candidate should be considered for promotion only after human review of:

```text
validation improvement
test-set performance
per-target metrics
runtime and resource use
reproducibility
model complexity
interpretability
failure behavior
```

---

## Stop Conditions

The agent must stop the campaign when any of the following occurs:

- Maximum trial count is reached.
- Maximum wall-clock budget is reached.
- A required dependency is missing and installation was not approved.
- The dataset cannot be loaded or validated.
- The split fingerprint differs from the manifest.
- A protected file would need modification.
- The agent encounters an ambiguous requirement that materially affects fairness or safety.
- The user interrupts the process.

When stopping, the agent must write the final report and leave the repository in a clean state on the dedicated autoresearch branch.

---

## Explicit Non-Goals

This system does not currently support autonomous changes to:

- Feature engineering.
- Data cleaning.
- Target transformation strategy.
- Train/test split strategy.
- Time-series or walk-forward validation strategy.
- Ensemble construction.
- Automatic dependency installation.
- Automatic model promotion.
- Automatic merging or pushing to remote repositories.
- Unlimited experimentation.
