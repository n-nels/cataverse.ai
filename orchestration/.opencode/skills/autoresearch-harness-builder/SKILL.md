---
name: autoresearch-harness-builder
description: Build an LLM-driven hyperparameter optimization harness around an existing ML training pipeline. Use this skill whenever the user wants to set up autonomous/bounded/overnight model experimentation, hyperparameter search infrastructure, an "autoresearch" loop, or wants to wrap a training pipeline with safe search + recording + keep/discard logic so an agent can optimize model configs without touching the ETL. Also use it when the user mentions wanting an agent to "tune hyperparameters overnight", "search model configs autonomously", or "build the autoresearch harness". Do NOT use it for one-off model training, basic EDA, or when the user just wants a quick grid search with sklearn — this skill builds durable, agent-driven infrastructure.
---

# Autoresearch Harness Builder

This skill scaffolds an **LLM-driven hyperparameter optimization loop** around an
existing ML training pipeline. The agent (an LLM) is the brain that runs
campaigns, observes results, reasons, and adjusts; the harness is the safety
rail + recording layer that keeps the search bounded, reproducible, and
non-destructive to the ETL pipeline.

## What you're building

A thin adapter layer + a harness package + a CLI + manifests + tests + a spec:

```
<package>/
├── pipeline.py          # 5 adapters routing to the repo's existing functions
├── autoresearch.py      # CLI: --smoke (verify) and --git (real campaign)
├── harness/
│   ├── __init__.py
│   ├── manifest.py      # load/validate manifest; advisory hyperparameters
│   ├── fingerprints.py  # dataset + split fingerprints for traceability
│   ├── gitstate.py      # branch checks, reset --hard discard, ETL protection
│   ├── ledger.py        # append-only results.tsv
│   ├── trial.py         # sample config, train one trial, per-trial timeout
│   ├── artifacts.py     # write the 11 required experiment artifacts
│   ├── report.py        # render report.md
│   └── campaign.py      # orchestrator: baseline -> trials -> finalists -> report
├── manifests/
│   ├── example.yaml
│   └── smoke.yaml
├── tests/
│   └── test_harness.py
└── spec.md              # the contract (see references/spec.md)
```

The agent is the **outer loop** (run campaign → observe → reason → adjust
manifest/model code/deps → run next campaign). The harness is the **inner loop**
(bounded random search within one campaign, with keep/discard, fingerprints,
ledger, artifacts). Read `references/spec.md` before writing any harness code —
it is the contract that makes the search safe and reproducible.

### The outer loop: observe-reason-act (default 3 iterations)

The outer loop is the LLM-driven part. It runs a **fixed number of iterations**
(default 3, configurable) and is the core of what makes this "agent-driven"
rather than a dumb random search:

```
for i in 1..3 (default):
    1. OBSERVE: Run one campaign (inner loop, ~30 trials of random search).
       Read its outputs: results.tsv, leaderboard.csv, report.md,
       comparison_to_baseline.json, per-target metrics.
    2. REASON: Analyze what happened. Which hyperparameters correlated with
       improvement? Which ranges were unexplored? Did any target underperform?
       Would a new model family or a new hyperparameter help? Did the best
       config plateau (suggesting diminishing returns)?
    3. ACT: Write a NEW manifest with a new experiment_id and adjusted
       hyperparameter bounds/ranges/choices based on the reasoning. Optionally
       extend ModelConfig or the model trainer to expose new knobs. Optionally
       install a new dependency (uv pip install). Then run the next campaign.
```

The outer loop stops early only if a stop condition fires (budget exhausted, ETL
violation, dependency install failure, or the agent judges further iteration
won't help — e.g. two consecutive campaigns with no improvement). Otherwise it
runs all 3 (or the configured count).

Each outer iteration produces its own experiment_id, artifact directory, and
ledger rows. The ledger accumulates across iterations so the agent can compare
across campaigns.

## When to use

- User wants autonomous/overnight/bounded hyperparameter search.
- User has an existing training pipeline and wants to wrap it with safe search infra.
- User says "build the autoresearch harness", "set up model optimization loop".
- User wants an LLM agent to tune model configs without touching the ETL.

## When NOT to use

- One-off model training (just call the existing trainer).
- Basic EDA / data exploration.
- Quick `GridSearchCV` / `RandomizedSearchCV` — that's sklearn, not durable infra.
- Repo has no reusable training function to wrap (build that first).

## Prerequisites

Before building, confirm the target repo has:

1. **Importable training functions** — a way to build/load a dataset, split it,
   train a model, and evaluate. They can have any names; `pipeline.py` adapts.
2. **A config class** for model hyperparameters (e.g. a `NamedTuple` or
   dataclass). If none exists, guide the user to create a minimal one.
3. **A cached dataset** (parquet/csv/pickle) for smoke testing without re-running
   expensive ETL. If none exists, build one first.
4. **Python deps**: `pyyaml`, the model library (lightgbm/sklearn/etc.),
   `pandas`, `numpy`, `scipy`, `joblib`. Install missing ones with
   `uv pip install <pkg>` (not `pip`, not `uv add`).

If any prerequisite is missing, stop and tell the user what's needed before
proceeding.

## The 5 adapter interfaces

`pipeline.py` is the ONLY file that knows about the target repo's actual
functions. Everything else in the harness talks to these 5 interfaces. Implement
them by routing each to the repo's existing equivalent:

```python
def prepare_dataset(data_dir=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (X, y). Route to the repo's dataset-build/load function.
    e.g. return data.load_data(data_dir)  # whatever the repo calls it"""

def prepare_splits(X, y) -> "Splits":
    """Return train/val/test splits. Route to the repo's split function.
    Must use the canonical split seed (42) — do NOT reshuffle.
    The return type is whatever the repo's split container is called
    (DatasetSplit, Splits, etc.) — it just needs X_train, y_train, X_val,
    y_val, X_test, y_test attributes."""

def train_model(splits, model_name, config, strategy="shared") -> "TrainedModel":
    """Train one model. Route to the repo's model registry/trainer.
    Unpack splits to pass to the repo's trainer signature, e.g.:
      trainer = MODEL_REGISTRY[model_name]
      return trainer(splits.X_train, splits.y_train, splits.X_val, splits.y_val,
                     config, strategy=strategy)
    The returned object must expose .metrics (per-target val dict with
    {name: {rmse, r2}}) and a predict method — either .model.predict(X)
    or .predict(X) directly on the container."""

def validation_avg_rmse(trained_model) -> float:
    """Mean per-target validation RMSE. The primary optimization metric."""

def test_metrics(trained_model, splits) -> dict:
    """Evaluate on the held-out test set. Returns dict with an 'aggregate'
    key containing {'avg_rmse': ..., 'avg_r2': ...}."""
```

The harness never imports the repo's ETL directly — only `pipeline.py` does.
This is the seam that keeps ETL protected.

## Module pattern sketches

Write each module fresh per the target repo's shape. These sketches capture the
essence, not the exact code. Read `references/spec.md` for the *why* behind each
invariant.

### harness/manifest.py
**Purpose:** Load + validate the experiment manifest; provide advisory
hyperparameter checks.
**Interface:** `load_manifest(path) -> Manifest`, `Manifest.is_approved_params(params) -> (True, warning_str)`.
**Invariants:** Split seed must be 42 (ETL-protected); hyperparameters are
advisory (log warnings, never reject); required manifest fields enforced.
**Repo-coupled:** None — fully generic. The `CANONICAL_SEED = 42` constant is
universal.
**Sketch:**
```python
@dataclass
class HyperparameterSpec:
    name: str; type: str  # "numeric" | "categorical"
    range: tuple | None; choices: list | None
    def contains(self, value) -> bool: ...

@dataclass
class Manifest:
    experiment_id, description, model_name, baseline_experiment, split_seed,
    primary_metric, search_method, allowed_hyperparameters, maximum_trial_count,
    maximum_wall_clock_minutes, maximum_test_finalists, artifact_output_location
    # + optional: per_trial_timeout_minutes, minimum_improvement_threshold, raw

    def is_approved_params(self, params) -> tuple[bool, str]:
        # ALWAYS returns (True, warning_str). Advisory only.
        # Collect warnings for undeclared/out-of-range params; never reject.

def load_manifest(path) -> Manifest:
    # YAML; validate required fields; reject split_seed != 42;
    # parse allowed_hyperparameters into HyperparameterSpec list.
```

### harness/fingerprints.py
**Purpose:** Dataset + split fingerprints for traceability and keep/discard gating.
**Interface:** `compute_dataset_fingerprint(X, y, parquet_dir=None) -> DatasetFingerprint`,
`compute_split_fingerprint(splits, seed=42) -> SplitFingerprint`,
`fingerprints_match(recorded, observed) -> bool`.
**Invariants:** Dataset fingerprint = SHA256 of dataset bytes + columns + shape.
Split fingerprint = SHA256 of canonical train/val/test index-label serialization.
**Repo-coupled:** The parquet-file path convention. If the repo caches data
differently, compute the hash from in-memory serialization instead.
**Sketch:**
```python
@dataclass
class DatasetFingerprint:
    x_shape, y_shape, x_columns, y_columns, hash  # hash = sha256(X_bytes + y_bytes)

@dataclass
class SplitFingerprint:
    seed, train_ratio, val_ratio, train_index, val_index, test_index, hash
    # hash = sha256("\n".join(train_labels) + "\n\n" + "\n".join(val_labels) + ...)

def compute_dataset_fingerprint(X, y, parquet_dir=None):
    # If parquet_dir has X.parquet/y.parquet, hash file bytes.
    # Else hash X.to_parquet() + y.to_parquet() bytes.

def compute_split_fingerprint(splits, seed=42):
    # labels = [str(x) for x in df.index]; hash canonical join.
```

### harness/gitstate.py
**Purpose:** Branch checks, commit/discard, ETL-protected-file detection.
**Interface:** `current_state(cwd) -> GitState`, `assert_clean_tree(cwd)`,
`assert_autoresearch_branch(cwd)`, `commit_all(cwd, msg) -> str`,
`discard_to(cwd, prev_commit)`, `protected_files_changed(cwd, ref) -> list`.
**Invariants:** Destructive ops (`reset --hard`) ONLY on `autoresearch/*` branches.
Refuse off-branch. `PROTECTED_FILES` lists the repo's ETL files.
**Repo-coupled:** `PROTECTED_FILES` — populate with the target repo's ETL file
list (the files that build features, split data, define targets). This is the
core safety boundary.
**Sketch:**
```python
AUTORESEARCH_PREFIX = "autoresearch/"
PROTECTED_FILES = ("extract.py", "transform.py", "load.py")  # ADAPT to repo

def is_autoresearch_branch(branch) -> bool: return branch.startswith(prefix)
def assert_autoresearch_branch(cwd):
    # raise GitError if not on autoresearch/* branch
def discard_to(cwd, prev_commit):
    # assert_autoresearch_branch first; then git reset --hard prev_commit
def protected_files_changed(cwd, ref="HEAD") -> list:
    # git diff --name-only + status --porcelain; intersect with PROTECTED_FILES
```

### harness/ledger.py
**Purpose:** Append-only `results.tsv` — the durable record of every trial.
**Interface:** `init_ledger(dir)`, `append_row(dir, row)`, `read_rows(dir) -> list`,
`best_kept_row(dir) -> row | None`, `make_row(...) -> LedgerRow`.
**Invariants:** TSV with fixed columns; statuses in {keep, discard, crash, invalid};
test metrics blank for non-finalists; never overwrite, only append.
**Repo-coupled:** None — fully generic.
**Sketch:**
```python
LEDGER_COLUMNS = ("commit","experiment_id","model","validation_avg_rmse",
    "validation_avg_r2","test_avg_rmse","test_avg_r2","runtime_minutes",
    "status","description")
ALLOWED_STATUSES = {"keep","discard","crash","invalid"}

def make_row(...) -> LedgerRow:  # floats -> "%.6f" or "" if None
def append_row(dir, row):  # csv.writer with delimiter="\t", append mode
def best_kept_row(dir):  # min by validation_avg_rmse among kept rows
```

### harness/trial.py
**Purpose:** Sample a candidate config, train one trial, enforce per-trial timeout.
**Interface:** `sample_params(manifest, rng) -> dict`,
`build_model_config(params) -> config`, `train_trial_inprocess(data_dir, model_name, params) -> TrialResult`,
`run_trial_subprocess(data_dir, model_name, params, timeout_minutes) -> TrialResult`,
`eval_finalist_inprocess(data_dir, model_name, params) -> test_metrics_dict`.
**Invariants:** Bounded random sampling from manifest's advisory params; per-trial
timeout via hermetic subprocess that rebuilds dataset+split deterministically.
**Repo-coupled:** `build_model_config` — must translate the `params` dict into the
repo's config class. Filter to known fields of that class. This is the one place
the harness knows the config shape.
**Sketch:**
```python
@dataclass
class TrialResult:
    status: str  # success | crash | invalid | timeout
    params: dict
    validation_avg_rmse, validation_avg_r2: float | None
    per_target: dict | None
    runtime_minutes: float | None
    reason: str

def sample_params(manifest, rng):
    # for each declared hp: numeric -> rng.uniform/randint in range;
    # categorical -> rng.choice(choices)

def build_model_config(params):
    # ADAPTATION POINT: import the repo's config class; filter params to its
    # fields; return config_class(**filtered). If the repo has no config class,
    # guide the user to create one (a NamedTuple of the model's hyperparameters).

def train_trial_inprocess(data_dir, model_name, params):
    # import pipeline; prepare_dataset + prepare_splits; build_model_config;
    # train_model; return TrialResult with val metrics + runtime.
```

### harness/artifacts.py
**Purpose:** Write the 11 required experiment artifacts to a unique dir.
**Interface:** `init_experiment_dir(dir, experiment_id) -> Path` (refuses if
exists), `write_manifest`, `write_git_state`, `write_environment`,
`write_dataset_fingerprint`, `write_split_fingerprint`, `write_trial_results`,
`write_leaderboard`, `write_best_params`, `write_final_metrics`,
`write_comparison`, `write_report`, `write_run_log`.
**Invariants:** Append-only (refuse to overwrite existing experiment dir); all
11 required files written; JSON/YAML/CSV formats per spec.
**Repo-coupled:** None — fully generic.
**Sketch:**
```python
def init_experiment_dir(automation_dir, experiment_id):
    d = automation_dir / "artifacts" / "experiments" / experiment_id
    if d.exists(): raise FileExistsError(...)  # never overwrite
    d.mkdir(parents=True)

# write_* helpers: _write_json(path, obj), _write_yaml(path, obj),
# write_trial_results writes CSV (one row per trial), write_leaderboard
# writes CSV ranked by val_rmse ascending.
```

### harness/report.py
**Purpose:** Render the final `report.md` from a fixed schema.
**Interface:** `build_report(...) -> str`, `write_report(dir, text)`.
**Invariants:** Recommendation must be one of {retain for human review, no
improvement found, experiment failed, needs human decision}. Never say
"production-ready".
**Repo-coupled:** None — fully generic.
**Sketch:**
```python
REPORT_RECOMMENDATIONS = ("retain for human review","no improvement found",
    "experiment failed","needs human decision")

def build_report(experiment_id, branch, starting_commit, ending_commit,
    model_name, baseline_experiment, dataset_fingerprint, split_fingerprint,
    trials_attempted, successful_trials, failed_trials, best_validation,
    baseline_validation, best_test, baseline_test, best_config, recommendation,
    changed_source_files, protected_files_unchanged) -> str:
    # validate recommendation in REPORT_RECOMMENDATIONS; render markdown.
```

### harness/campaign.py
**Purpose:** Orchestrator — ties everything together for one campaign.
**Interface:** `run_campaign(manifest_path, automation_dir, data_dir=None,
smoke=False, git=False, max_trials_override=None, wall_clock_override=None) -> CampaignSummary`.
**Invariants:** Builds dataset+splits+fingerprints once; runs campaign baseline
first; loops trials with keep/discard by validation RMSE threshold; evaluates
top-K finalists on test; writes all artifacts + report. Smoke mode = no git,
in-process. Git mode = **auto-creates** the `autoresearch/<run_tag>` branch if
not already on one (derives `run_tag` from the manifest field or `experiment_id`),
then commits/discards per trial.
**Repo-coupled:** `baseline_params()` - return the repo's default config as a
dict (the keep/discard anchor).
**Sketch:**
```python
def baseline_params():
    # ADAPTATION POINT: return the repo's default model config as a dict.
    # e.g. {**DefaultConfig()._asdict(), "strategy": "shared"}

def run_campaign(manifest_path, automation_dir, data_dir=None, smoke=False, git=False, ...):
    manifest = load_manifest(manifest_path)
    # git setup:
    #   assert_clean_tree
    #   if not on autoresearch/* branch: create_branch("autoresearch/<run_tag>")
    #     where run_tag = manifest.run_tag or manifest.experiment_id
    #   protected_files check (refuse if ETL files dirty)
    # dataset + splits + fingerprints (once)
    # init ledger + artifact dir (refuse if exists)
    # run campaign baseline; record in ledger as "keep"
    # loop trials: sample -> (git: commit candidate.yaml) -> train -> record ->
    #   keep if rel_improvement >= threshold else discard (git: reset --hard)
    # finalists: top-K by val_rmse -> eval on test
    # write all artifacts + report
    # return CampaignSummary
```

### autoresearch.py (CLI)
**Purpose:** Entry point. `--smoke` for verification, `--git` for real campaigns.
**Repo-coupled:** Import paths; the automation_dir resolution.
**Sketch:**
```python
# Mutually exclusive --smoke / --git. --max-trials and --wall-clock shrink budget.
# Calls harness.campaign.run_campaign(...). Prints summary at end.
```

## Workflow

Follow these steps in order. The smoke test at step 9 is the verification gate —
do not declare done until it passes.

1. **Audit the target repo.** Find: the dataset-build/load function, the split
   function, the model trainer/registry, the config class, the cached dataset
   location, and the list of ETL files that must be protected. Write these down.
2. **Write `pipeline.py`.** Implement the 5 adapters routing to the repo's
   existing functions. Do NOT reimplement ETL — only call it. This is the seam.
3. **Write `harness/` modules** following the pattern sketches above, adapting
   the repo-coupled parts (`PROTECTED_FILES`, `build_model_config`,
   `baseline_params`).
4. **Write `autoresearch.py`** CLI with `--smoke` and `--git` modes.
5. **Write manifests.** `manifests/example.yaml` (full budget) and
   `manifests/smoke.yaml` (tiny budget, unique experiment_id) for the repo's
   model. Use `split_seed: 42`. Declare advisory hyperparameters matching the
   repo's config class fields. Optionally set `run_tag` (defaults to
   `experiment_id`) for the autoresearch branch name.
6. **Edit `opencode.json`.** Add the `autoresearch` agent profile per
   `references/opencode_agent_profile.md`. Default agents stay restrictive.
7. **Add an `AGENTS.md` note** in the package listing the ETL-protected files
   and pointing at `spec.md` as the contract.
8. **Write `tests/test_harness.py`** for the pure-logic modules (manifest
   validation, ledger, git helpers, report). Use a temp git repo for git tests.
9. **Smoke test:** `python autoresearch.py --manifest manifests/smoke.yaml
   --smoke --max-trials 2 --wall-clock 5`. Must complete with all artifacts
   written. If it fails, fix and re-run.
10. **Run unit tests:** `pytest tests/test_harness.py`. Must pass.
11. **Report to the user:** list of files created, smoke test result, and the
    next step (run a real optimization session — see "Running a real session"
    below).

## Running a real optimization session

Once the harness is built and smoke-tested, a real session uses the
observe-reason-act outer loop (default 3 iterations). The harness auto-creates
the `autoresearch/<run_tag>` branch in git mode — the agent does NOT need to
create it manually. The flow:

1. Run `python autoresearch.py --manifest manifests/example.yaml --git` (or a
   session-specific manifest). The harness auto-creates the branch if not on
   one, runs the campaign (inner loop, ~30 trials), and writes artifacts.
2. **Observe:** read `results.tsv`, `leaderboard.csv`, `report.md`,
   `comparison_to_baseline.json` from the experiment's artifact dir.
3. **Reason:** which hyperparameters helped? which ranges were unexplored? did
   any target underperform? would a new knob or model family help? did the best
   config plateau?
4. **Act:** write a new manifest with a new `experiment_id` and adjusted bounds.
   Optionally extend `ModelConfig`/model code or `uv pip install` a new dep.
5. Run the next campaign. Repeat for 3 iterations (default) or until a stop
   condition fires.

The harness auto-creates the branch on the first `--git` run; subsequent
iterations stay on the same branch (the agent is already on it). The ledger
accumulates across iterations.

## Constraints

- **Never touch ETL.** The dataset-build, feature-engineering, split, target-
  transform, and evaluation-metric logic is protected. `pipeline.py` only calls
  it. `gitstate.PROTECTED_FILES` lists it. The harness refuses to start a git-mode
  campaign if protected files are dirty.
- **Never reimplement.** Reuse the repo's existing functions via `pipeline.py`.
- **Never overwrite artifacts.** Each experiment gets a unique `experiment_id`
  and a fresh directory; the harness refuses to overwrite.
- **The spec is the contract.** Read `references/spec.md` before writing harness
  code. It defines Protected Scope, the manifest schema, the loop, keep/discard,
  fingerprints, and stop conditions.
- **Split seed is 42.** ETL-protected. The manifest records it; the harness
  rejects a different split seed. Model seeds may vary (searchable).
- **Hyperparameters are advisory.** The manifest declares a starting set; the
  agent may search beyond it. The harness logs warnings, never rejects.
- **No automatic promotion.** The harness recommends; a human promotes.

## Edge cases

- **No config class:** Guide the user to create a minimal `NamedTuple` of the
  model's hyperparameters. The harness needs one to build configs from param dicts.
- **Different function names:** Map them in `pipeline.py`. The harness talks only
  to the 5 adapter interfaces.
- **No cached dataset:** Build one first (run the repo's ETL once, save to
  parquet). The smoke test needs it to avoid re-running expensive ETL.
- **Windows paths:** Use `pathlib.Path` everywhere; avoid hardcoded separators.
- **Multiple model families:** The manifest's `model_name` selects which
  registered trainer to call. Register each family in the repo's model registry.

## References

- `references/spec.md` — the contract (Protected Scope, manifest, loop,
  keep/discard, fingerprints, stop conditions). Read before writing harness code.
- `references/opencode_agent_profile.md` — the `autoresearch` agent profile
  snippet for `opencode.json`.