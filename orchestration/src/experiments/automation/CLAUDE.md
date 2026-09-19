# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this package is

`orchestration/src/experiments/automation/` is a self-contained Python package (no `pyproject.toml`/`setup.py` — run everything from this directory with plain `python`/`pytest`) that predicts 6 PFO-Sec CO-adsorption kinetic parameters from experiment metadata, plus a newer sequential-forecasting extension that updates those predictions as time-series measurements arrive during an experiment. There are two "generations" of code here:

- **Root-level ETL/model pipeline** (`extract.py`, `transform.py`, `load.py`, `model.py`, `models/`, `pipeline.py`, `train.py`) — the original, protected PFO-Sec regression pipeline. Spec: `legacy/spec.md`.
- **`sequential_forecasting/`** — a package built on top of the root pipeline's RF model and artifacts to do sequential (time-series) re-forecasting. Spec: `sequential_forecasting/spec.md`, data contract: `sequential_forecasting/data_contract.md`, usage: `sequential_forecasting/README.md`.
- **`legacy/`** — superseded pre-refactor implementation (`data.py`, `decision_engine.py`, `peak_feature_engr.py`, `run.py`). Not imported by current code; keep for historical reference only.
- **`harness/`, `autoresearch.py`, `manifests/`** — an autonomous hyperparameter-search harness that runs bounded campaigns over the root model registry.

## Protected scope — read before editing

`legacy/spec.md` §20 defines a hard boundary enforced partly by tooling (`harness/gitstate.py` `PROTECTED_FILES`) and partly by convention:

**Do not modify without explicit user authorization:**
- `extract.py` — raw data extraction
- `transform.py` — feature engineering, target extraction
- `load.py` — dataset assembly, feature reduction, split logic (seed 42, ratios)
- Box-Cox/log target transforms in `model.py` (`LOG_TRANSFORM_TARGETS`, `fit_boxcox_lambdas`)
- Evaluation metric definitions (RMSE, R², aggregation)
- Existing completed experiment artifacts under `artifacts/experiments/`

**Freely editable for optimization:** `model.py` (new `ModelConfig` fields, new model registrations — but not transforms/metrics/splits), `models/*.py`, `pipeline.py`, `harness/*.py`, `manifests/*.yaml`, and new files anywhere in the package. `harness/gitstate.py` programmatically refuses to start an autoresearch campaign if `extract.py`/`transform.py`/`load.py` are dirty.

The autoresearch harness itself never edits protected files — trial "changes" are hyperparameter configs (`current_candidate.yaml`), never source edits.

## Commands

Run everything from this directory (`orchestration/src/experiments/automation/`).

```powershell
# Build dataset from raw data + train + evaluate + save model + visualizations
python train.py --model lightgbm --data-root X:\peakFit
python train.py --model random_forest --strategy separate
python train.py --model partial_bnn --skip-visualizations

# Rebuild just the cached X/y parquet dataset (also runnable as a script)
python load.py

# Run the full test suite (no pytest.ini; tests self-insert this dir onto sys.path)
python -m pytest -q
python -m pytest tests/test_harness.py -q          # single file
python -m pytest tests/test_harness.py::test_name -q  # single test

# Autonomous hyperparameter campaign (see harness/ below)
python autoresearch.py --manifest manifests/lightgbm_v1_0001.yaml --smoke --max-trials 2 --wall-clock 5
python autoresearch.py --manifest manifests/lightgbm_v1_0001.yaml --git
```

`sequential_forecasting` has its own CLI (`python -m sequential_forecasting.cli <command>`) and its own focused test invocation — see `sequential_forecasting/README.md` for the full ordered command sequence (rf-artifacts → validate-rf-boundary → validate-contract → build-examples → evaluate-baselines → train-sequential-model → run-inference → evaluate-sequential) and the exact pytest file list.

There is no lint/format config in this package (no ruff/flake8/black config found) — match surrounding style.

## Architecture: root pipeline

Data flows through four phases, each owned by one module, chained by `load.build_dataset()`:

1. **`extract.py`** — walks `X:\peakFit` (or `--data-root`) for `*_expParams.json` files, parses the `YYYYMM_HHMMSS_...` chronological prefix from filenames, pairs each JSON with its `*_CarbonylPeakArea.csv`, and incrementally caches results to `experiment_cache.json` (JSON-serialized `ExperimentRecord` list, keyed by json path so reruns only process new files).
2. **`transform.py`** — turns one `ExperimentRecord` into a feature row and target row: `extract_targets()` pulls the 6 `pfo-sec_*` columns from the `monomer_sum` row with max `Time (s)`; `extract_current_features()` flattens up to 8 pretreatment steps (gas one-hot via 4-bit binary encoding + temp/duration) plus `exp_conditions`; `compute_chain_features()` and `add_previous_targets()` add cross-experiment state (`distance_from_isnew`, previous experiment's targets) keyed by notebook, so **record order matters and must stay chronological**.
3. **`load.py`** — `assemble_dataset()` combines the above into X/y DataFrames indexed by `base_name`; `reduce_features()` drops whole pretreatment-step column groups (`pre_{step}_*`); `split_dataset()` does a **random** (not chronological) 80/20/20 train/val/test split at `random_state=42` — this seed is canonical and manifest-enforced (`harness/manifest.py` rejects any `split_seed != 42`).
4. **`model.py` + `models/{lightgbm,random_forest,partial_bnn}.py`** — a plugin registry (`MODEL_REGISTRY`, populated by `@register_model` decorators when `models/__init__.py` is imported) of trainer functions with signature `(X_train, y_train, X_val, y_val, config, **kwargs) -> TrainedModel`. Targets in `LOG_TRANSFORM_TARGETS` get Box-Cox/log-transformed before training and inverse-transformed before scoring; `pfo-sec_q0_au` is intentionally left untransformed (see `comments.md` #6 — it can go negative). LightGBM and RandomForest both support a `strategy` kwarg: `"shared"` (one multi-output model, shared tree splits) vs `"separate"` (one single-output model per target via `MultiOutputRegressor`).

`pipeline.py` composes `load`/`model` into a reusable prepare→split→train→evaluate flow shared by `train.py` (CLI) and the harness — it must never reimplement logic that belongs in those modules. `eda.py` and `visualize.py` are diagnostic/plotting consumers of a trained model, not part of the data path.

`comments.md` is a running list of known issues/inconsistencies in this pipeline (e.g. duplicate `sanitize_feature_names` logic between `model.py` and `models/lightgbm.py`, StandardScaler-on-top-of-Box-Cox redundancy) — check it before "fixing" something that may already be a tracked, intentional-for-now issue.

## Architecture: autoresearch harness (`harness/`, `autoresearch.py`)

A bounded, autonomous hyperparameter-search loop, driven by a YAML **manifest** (`harness/manifest.py` — required fields include `model_name`, `split_seed` (must be 42), `allowed_hyperparameters`, `maximum_trial_count`, `maximum_wall_clock_minutes`; hyperparameter bounds are *advisory*, logged but not enforced). `harness/campaign.py:run_campaign()` orchestrates:

- Establishes a campaign baseline using each model's registered default config (`model.DEFAULT_CONFIGS`), then randomly samples trials (`harness/trial.py:sample_params`) up to the trial/wall-clock budget.
- Each trial is compared to the current best by **relative RMSE improvement** vs `manifest.minimum_improvement_threshold`; kept trials update the running best, others are discarded.
- Two execution modes: `--smoke` (in-process, no git, for verifying the harness itself) and `--git` (each trial is committed to an `autoresearch/<run_tag>` branch as `current_candidate.yaml`; discarded trials are `git reset --hard` back — `harness/gitstate.py` refuses these destructive resets on any branch not prefixed `autoresearch/`).
- Top-K (by validation RMSE) trials are re-evaluated on the held-out test set as "finalists" at the end.
- Every trial (kept, discarded, or crashed) is appended to `results.tsv` (`harness/ledger.py`, tab-separated, untracked/append-only, never rewritten) and full campaign artifacts (manifest copy, git state, environment, dataset/split fingerprints, leaderboard, report) are written under `artifacts/experiments/<experiment_id>/` (`harness/artifacts.py`, `harness/report.py`).
- `harness/fingerprints.py` hashes the dataset and split so campaigns can prove they ran against the exact protected dataset/split.

Non-smoke trials run in a **hermetic subprocess** (`harness/trial.py:run_trial_subprocess`) that rebuilds the dataset from the cached parquet and enforces a per-trial timeout — the parent process never imports heavy ML deps for trial execution outside of `--smoke` mode.

## Architecture: `sequential_forecasting/`

Builds on the root pipeline's Random Forest (loaded via `model.load_model`) without modifying it. Read `sequential_forecasting/spec.md` in full before working here — it encodes hard requirements that are easy to violate silently:

- **`Peak_Name == "monomer_sum"` only**; `Delta_Group` must be flattened (never grouped/split on), but flattening must not split one physical experiment across train/val/test.
- Every training example is one (experiment, cutoff-time) pair; inputs at cutoff `t` must contain **zero** information from after `t` (this is the primary leakage risk — audit any new feature for this).
- Splitting is always **by whole experiment**, reusing the root RF's train/val/test assignments where practical; all cutoffs of one experiment stay in the same partition.
- RF predictions used to train the sequential model must be **out-of-fold** (not from an RF that saw that experiment) — see `sequential_forecasting/rf/` (`artifacts.py`, `predictions.py`, `splits.py`, `provenance.py`, `validation.py`).
- Predicted parameters must satisfy the physical constraints of the ODE fit (`sequential_forecasting/models/secondary_pfo.py`) before being passed to it; invalid predictions must be surfaced, not silently accepted.

Module layout: `data/` (contract validation, observation flattening, training-example construction — `contract.py`, `observations.py`, `examples.py`, `validation.py`, `adapter.py`), `rf/` (OOF Random Forest artifact generation and RF/sequential boundary validation), `models/secondary_pfo.py` (the local ODE fit, mirrors a sibling repo's implementation without cross-repo imports — see provenance requirements in the README), `baselines.py` (Baseline A: RF-only, B: current-ODE-fit, C: simple blend — required comparisons per spec §13), `sequential_model.py` (candidate model), `inference.py`, `evaluation.py`, `cli.py` (the `python -m sequential_forecasting.cli <command>` entry point), `config.py` (the shared `RunConfig` defaults, e.g. `DEFAULT_DATA_ROOT`, `DEFAULT_EXCLUDE_FOLDERS`, `DEFAULT_MINIMUM_FIT_POINTS`).

Commands are run in a strict pipeline order (each stage reads the previous stage's artifact dir) — see `sequential_forecasting/README.md` for the exact sequence and flags. The final `evaluate-sequential --assignment test` command refuses to run if the model-selection manifest reports `test_used_for_selection: true`, enforcing the "test set only after selection is frozen" rule from the spec.

## Data source note

The canonical raw data root is `X:\peakFit` (a mapped network drive), hardcoded as the default in `extract.py`, `load.py`, and `sequential_forecasting/config.py`. `legacy/run.py` references an older UNC path (`\\rc-smb1.pnl.gov\...`) — that predates the `X:\peakFit` convention and is not part of the current data path. Cached `outputs/X.parquet` and `outputs/y.parquet` let most workflows (`pipeline.prepare_dataset`, the harness, sequential_forecasting) run without network access to the raw data root.
