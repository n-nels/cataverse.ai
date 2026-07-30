---
name: autoresearch-optimizer
description: Run the observe-reason-act outer loop to optimize a specific model's hyperparameters using the autoresearch harness. Use this skill whenever the user wants to tune, optimize, or search for better hyperparameters for a named model (e.g. "optimize lightgbm", "tune the random forest", "find better hyperparameters for xgboost", "run a hyperparameter search on model X", "make the model better"). Also use it when the user references the autoresearch harness, manifests, or campaigns in the context of improving a model. Do NOT use it to build the harness itself (that's autoresearch-harness-builder), for one-off training, basic EDA, or when no model name is given and cannot be inferred.
---

# Autoresearch Optimizer

You are the **outer loop** of an autonomous hyperparameter search. The harness
(`autoresearch.py` + `harness/`) is the inner loop — it runs bounded random
search, records results, and applies the keep/discard rule. Your job is to
drive the search intelligently: run a campaign, read its results, reason about
what happened, and write a better manifest for the next campaign. Repeat.

This is reason-act-observe, not blind search. A dumb random search over the
same manifest 30 times just re-samples the same space. Your value is in
**changing the space** between campaigns based on what you learned.

## Prerequisites

Before starting, confirm the target package has the autoresearch harness
already built. Look for:

- `autoresearch.py` (the CLI)
- `harness/` (the inner-loop package)
- `manifests/` (existing example manifests to copy)
- `spec.md` (the contract — read it if you haven't; it defines Protected
  Scope, the manifest schema, keep/discard, and stop conditions)
- A cached dataset (e.g. `outputs/X.parquet`, `outputs/y.parquet`)

If the harness is missing, stop and tell the user to build it first (see the
`autoresearch-harness-builder` skill). This skill only *uses* an existing
harness; it does not build one.

## Inputs from the user

Two things matter:

1. **Model name — REQUIRED.** The user must name the model to optimize
   (e.g. `lightgbm`, `random_forest`, `xgboost`). This becomes the manifest's
   `model_name` and selects which registered trainer the harness calls. If the
   user says "optimize the model" without naming it, ask. Do not guess.

2. **Number of outer-loop turns — OPTIONAL, default 3.** The user may override
   this in the prompt (e.g. "optimize lightgbm, 5 turns" or "run 2 iterations
   on random_forest"). Parse an explicit number if present; otherwise default
   to 3. Each turn = one campaign (~30 trials of inner-loop random search) plus
   your reasoning.

Everything else (trial count, wall-clock, hyperparameter ranges) you decide
yourself, turn by turn. That's the point.

## The outer loop (default 3 turns)

For each turn, in this order:

### 1. REASON — decide the manifest

Before writing anything, reason about what to search this turn.

- **Turn 1:** Start from the model's current `ModelConfig` defaults and any
  existing example manifests. What hyperparameters does this model family
  actually expose? Which ones are likely to matter? For tree models
  (LightGBM, XGBoost, RandomForest): tree complexity (`num_leaves`,
  `max_depth`), regularization (`min_child_samples`, `reg_alpha`, `reg_lambda`),
  sampling (`subsample`, `colsample_bytree`), and learning rate / estimator
  count. The spec explicitly permits extending `ModelConfig` and the model
  trainer to expose new knobs — that is not ETL. If a useful hyperparameter
  isn't wired through yet, wire it (see "Extending the model" below).

- **Turn 2+:** Reason from the previous campaign's results. What
  hyperparameters correlated with the kept (improving) trials? Which ranges
  were never sampled well? Did the best validation config blow up on the test
  set (overfitting)? Did one strategy beat another? Should you narrow around
  the winners, widen an unexplored region, or introduce a new knob?

### 2. ACT — write the manifest and run the campaign

Write a new YAML manifest in `manifests/`. Two non-negotiable rules:

- **Unique `experiment_id` every turn.** The harness refuses to overwrite an
  existing artifact directory (spec: append-only). If you reuse an
  `experiment_id`, the campaign crashes with `FileExistsError`. Use a scheme
  like `<model>_v<turn>_<nnnn>` (e.g. `lightgbm_v2_0001`). Check
  `artifacts/experiments/` for what already exists before picking an ID.

- **`split_seed: 42` always.** This is ETL-protected. The harness rejects any
  other value. The model seed (e.g. `random_state`) is searchable — declare
  it as a hyperparameter if you want to test robustness.

Then run the campaign. Default to **smoke mode** (in-process, no git) — it's
fast and sufficient for the optimization loop:

```
python autoresearch.py --manifest manifests/<your>.yaml --smoke
```

This uses the manifest's own `maximum_trial_count` and
`maximum_wall_clock_minutes` (typically 30 trials / 120 min). Only pass
`--max-trials` / `--wall-clock` to *shrink* the budget (e.g. for a quick
sanity check). Use `--git` instead of `--smoke` only if the user explicitly
wants commit-per-trial traceability on an `autoresearch/*` branch.

Run from the package directory that contains `autoresearch.py`. The command
blocks until the campaign finishes (baseline + trials + finalists + report).

### 3. OBSERVE — read the results

After the campaign completes, read these artifacts from
`artifacts/experiments/<experiment_id>/`:

- **`report.md`** — the human-readable summary: best vs baseline validation
  and test RMSE, the best config, recommendation, protected-files status.
- **`leaderboard.csv`** — all kept trials ranked by validation RMSE, with
  their full param dicts. This is your richest signal: it shows *which
  configurations actually won*.
- **`final_metrics.json`** — per-finalist test metrics. Compare validation
  rank vs test rank. A finalist that ranked #1 on validation but blew up on
  test is an overfitting signal.
- **`trial_results.csv`** — every trial (kept + discarded), useful for seeing
  the full distribution and crash patterns.
- **`comparison_to_baseline.json`** — the relative improvement and whether it
  cleared the threshold.

Also tail `results.tsv` at the package root — it accumulates across all
campaigns, so you can compare turns.

### 4. REASON — analyze (this is the important part)

This is where you earn your keep. Don't just run another random search. Look
for patterns:

- **Which hyperparameters separate kept from discarded trials?** If every
  kept trial used `subsample < 0.7` and every discarded one used
  `subsample > 0.9`, that's a signal to bias the next search lower.
- **Overfitting vs generalization.** The primary metric is validation RMSE,
  but the test set is your honesty check. If validation improved but test
  got worse (or exploded — RMSE orders of magnitude larger), the model is
  overfitting the validation set. Next turn, favor stronger regularization
  (higher `reg_alpha`/`reg_lambda`, higher `min_child_samples`), lower
  complexity (fewer `num_leaves`, shallower `max_depth`), or more aggressive
  sampling (lower `subsample`/`colsample_bytree`).
- **Strategy comparisons.** If the manifest includes a categorical like
  `strategy: [shared, separate]`, check which won. A strategy that wins on
  validation but is unstable on test may need different regularization bounds
  per strategy — or you may drop the losing strategy entirely next turn.
- **Unexplored corners.** Did any declared range get barely sampled? If
  `learning_rate` ranged [0.01, 0.3] but all kept trials clustered at
  [0.15, 0.25], narrow there and add finer granularity.
- **Plateaus.** If two consecutive campaigns show no improvement over
  baseline, you may be in a plateau. Consider introducing a new
  hyperparameter, a new model family, or stopping early (see Stop conditions).
- **Per-target failures.** The per-target metrics in `final_metrics.json` and
  the run log show if one target is consistently terrible (e.g. negative R²).
  That target may need different treatment — but you cannot change target
  transforms (ETL-protected). You can only adjust model capacity and
  regularization.

Write your reasoning down briefly before the next turn. State the hypothesis
the next manifest will test.

## Writing the next manifest

Each turn's manifest is a new file with a new `experiment_id`. Adjust the
`allowed_hyperparameters` ranges based on your reasoning:

- **Narrow around winners** when you've found a promising region.
- **Widen** when the search hit the bounds (e.g. kept trials all had
  `num_leaves` at the max — raise the max).
- **Introduce a new knob** by first extending `ModelConfig` and the model
  trainer (see below), then declaring it.
- **Drop a losing categorical choice** if one strategy clearly lost and you
  want to focus the budget.

Keep `model_name`, `split_seed: 42`, `primary_metric: validation_avg_rmse`,
and the budget fields (`maximum_trial_count`, `maximum_wall_clock_minutes`,
`maximum_test_finalists`, `minimum_improvement_threshold`,
`per_trial_timeout_minutes`) unless you have a reason to change them.

## Extending the model (permitted, non-ETL)

The spec explicitly allows you to extend `ModelConfig` with new fields and
wire them through the model trainer in `models/<model>.py`. This is **not**
ETL — ETL is `extract.py`, `transform.py`, `load.py` and the behaviors they
implement (features, targets, splits, transforms, metrics). You may:

- Add fields to `ModelConfig` (with sensible defaults that preserve baseline
  behavior — the campaign baseline is `ModelConfig()` defaults + the default
  strategy, so new defaults must not change what the baseline does).
- Pass the new fields into the model constructor in `models/<model>.py`.
- Declare the new fields as `allowed_hyperparameters` in the manifest.

You may NOT: change target transforms, evaluation metrics, split logic,
feature definitions, or dataset loading. If you catch yourself editing
`extract.py`, `transform.py`, or `load.py`, stop — that's a stop condition.

## Dependencies

If a model needs a package that isn't installed, install it with
`uv pip install <package>` (not plain `pip`, not `uv add` — the project is
uv-managed and `uv add` would modify `pyproject.toml`, which is out of
scope). Record what you installed in your final summary. If installation
fails, stop and report (stop condition).

## Stop conditions

Stop the outer loop early (before reaching the turn count) if:

- A dependency installation fails.
- The dataset cannot be loaded.
- A campaign crashes for an ETL reason (protected file would need changing).
- You see two consecutive campaigns with no improvement *and* no new idea to
  try (genuine plateau).
- The user interrupts.

Otherwise, run all turns. Even a turn that finds "no improvement" is
informative — it tells you that region of the space isn't worth more budget.

## Final summary

After the last turn, give the user a concise cross-campaign summary:

- The best configuration found across all turns, with its validation and test
  RMSE.
- Whether it beat the campaign baseline, and by how much (relative %).
- The test-set honesty check: did the best-validation model also generalize?
- The journey: what each turn tested and learned (one line per turn).
- A recommendation: `retain for human review`, `no improvement found`, or
  `needs human decision`. Never say "production-ready" — only a human
  promotes a model.

Point the user at the artifact directories so they can inspect the full
reports. Do not change the default model or saved production artifact — that's
a human decision.