---
name: automation-add-model
description: Add a new ML model implementation under `src/experiments/automation/models/` / `@models/` when the user names a model family such as xgboost, catboost, extra trees, or elastic net. Use this skill whenever the user asks to add, scaffold, wire up, or plumb a new automation model into the model registry, CLI, pipeline, or harness without changing ETL. Do NOT use it for hyperparameter tuning, benchmark campaigns, EDA, or changes to `extract.py`, `transform.py`, or `load.py`.
---

# Automation Add Model

This skill adds model-layer plumbing for the automation package. The goal is a
new model that can run through the existing registry, pipeline, CLI, and
harness. The goal is not optimization.

## Ask first

- The model family name is required. If the user says "add a new model" but
  does not name it, ask.
- If the request is ambiguous at the library level, ask before choosing an
  implementation.
- If the user asks for tuning or search, stop and use
  `autoresearch-optimizer` instead.

## Repo facts to load into working memory

- Target package: `orchestration/src/experiments/automation/`
- Existing patterns live in:
  - `model.py` — `ModelConfig`, `TrainedModel`, `register_model`,
    `register_default_config`, `get_default_config`, `DEFAULT_CONFIGS`
  - `pipeline.py` — `train_model(splits, model_name, config=None, strategy=None)`
  - `models/__init__.py` — imports all model modules to trigger registration
  - `models/lightgbm.py`, `models/random_forest.py`, `models/xgboost.py`
- Two registrations happen per model module, both at import time:
  - `@register_model("<name>")` on the trainer function (existing pattern)
  - `register_default_config("<name>", <NAME>_DEFAULT)` for the model's
    default config (new pattern — see "Per-model default configs" below)
- `pipeline.py` imports `models` to populate the registry.
- `train.py --model` choices come from `sorted(MODEL_REGISTRY)`.
- The harness routes through `pipeline.train_model(...)` and
  `harness/trial.py:build_model_config(params, model_name)`.
- Match the actual prediction flow in this repo: trainers and
  `evaluate_on_test()` expect `trained_model.model.predict(X)` to return target
  predictions in the transformed space, and shared helpers invert the target
  transforms afterward.
- `visualize.py` generates feature-importance plots. A new model should either
  expose compatible feature importances or come with the smallest safe
  compatibility change so visualization does not break.

## Hard guardrails

Never change:

- `extract.py`
- `transform.py`
- `load.py`
- split logic
- feature definitions
- target definitions
- target transforms
- official metrics

Those are protected by `spec.md`. This skill stays in model-layer plumbing.

## Per-model default configs (critical)

`ModelConfig` is a shared `NamedTuple` container, but its defaults are
**conservative and shared across all models**. Each model MUST register its
own default config so that:

1. `train.py --model <name>` (which passes `config=None`) uses the right
   defaults for that model, not the shared `ModelConfig()` defaults.
2. The autoresearch harness campaign baseline
   (`harness/campaign.py:baseline_params(model_name)`) anchors against the
   right per-model defaults.
3. Trial config building (`harness/trial.py:build_model_config(params,
   model_name)`) fills unsampled fields from the right per-model defaults.

**Why this matters:** If a new model changes the shared `ModelConfig` defaults
to its own optimal values, every other model inherits those values and breaks.
This happened before — XGBoost-optimal defaults (high learning rate, deep
trees, strong regularization) were set as shared defaults and silently
destroyed LightGBM's performance. Do not repeat this.

### How to register a per-model default

In the new model module, after the imports and `logger = ...`:

```python
from model import (
    ModelConfig,
    TrainedModel,
    ...,
    register_default_config,
    register_model,
)

logger = logging.getLogger(__name__)

# <Model> default config: <one line describing the source/rationale>
<MODEL>_DEFAULT = ModelConfig(
    # only override fields that differ from the shared conservative defaults
    # leave the rest at ModelConfig()'s values
)
register_default_config("<model_name>", <MODEL>_DEFAULT)
```

Then in the trainer:

```python
if config is None:
    config = <MODEL>_DEFAULT
```

### Choosing the default values

- For a brand-new model with no tuning history: use `ModelConfig()` (the
  shared conservative defaults) as the default. Do not invent a tuning pass.
- If the user has already tuned the model via `autoresearch-optimizer` and
  wants the tuned config as the new default: use the exact values from the
  winning trial's `best_params.yaml`, and note the campaign/trial of origin
  in a comment.
- Never change the shared `ModelConfig` defaults to model-specific values.
  Override via the per-model `<MODEL>_DEFAULT` constant instead.

## Default workflow

1. Read the contract before coding.
   - Open `model.py`, `pipeline.py`, `models/__init__.py`, and the existing
     model modules (especially the most recently added one — it will show the
     current patterns, including per-model default config registration).
   - If harness compatibility matters, also inspect `harness/trial.py` and
     `harness/campaign.py`.

2. Confirm dependencies.
   - If the requested library is missing, install it with
     `uv pip install <package>`.
   - Do not use `pip` or `uv add`.
   - Note: the venv Python is at
     `orchestration/.venv/Scripts/python.exe`; the system `python` on PATH may
     point elsewhere. Use the venv python explicitly when running anything.

3. Add `models/<model_name>.py`.
   - Follow the existing module style: module docstring, `logger`, and small
     helpers only when they pull their weight.
   - Register the trainer with `@register_model("<model_name>")`.
   - Register the default config with
     `register_default_config("<model_name>", <MODEL>_DEFAULT)` (see above).
   - Use the trainer signature:

     ```python
     def train_<name>(
         X_train: pd.DataFrame,
         y_train: pd.DataFrame,
         X_val: pd.DataFrame,
         y_val: pd.DataFrame,
         config: ModelConfig | None = None,
         strategy: str = "<shared|separate>",
     ) -> TrainedModel:
     ```

   - Choose the `strategy` default that is the best-supported path for this
     model family (`"shared"` or `"separate"`). The trainer's own default
     applies when `pipeline.train_model` is called with `strategy=None`
     (which is what `train.py` does when `--strategy` is not passed).
   - Reuse the shared helpers from `model.py`:
     - `fit_boxcox_lambdas`
     - `apply_target_transforms`
     - `inverse_target_transforms`
     - `ModelConfig`
     - `TrainedModel`
   - Compute validation RMSE/R² in the same pattern as the existing trainers.
   - Return `TrainedModel(model=..., config=..., target_names=..., metrics=..., lambdas=...)`.

4. Decide strategy support deliberately.
   - `pipeline.train_model` defaults `strategy=None` and only passes it
     through to the trainer when explicitly set, so each trainer's own
     `strategy` default is respected. Pick the right default for the model.
   - Prefer supporting `shared` if the model family can do it cleanly.
   - If only `separate` is realistic, set `strategy: str = "separate"` as the
     trainer default and raise on `"shared"`.
   - If both are reasonable, implement both and pick the better-performing or
     more natural one as the default.

5. Wire the module into discovery.
   - Import the new module in `models/__init__.py`.
   - Only touch `model.load_model()` if deserialization needs an explicit
     import or compatibility shim for custom wrapper classes.

6. Check downstream compatibility.
   - `train.py` should discover the new model automatically once it is
     registered.
   - `pipeline.py` should not need changes unless the new model needs a
     different call shape.
   - `visualize.py` may need a tiny compatibility adjustment if the model has
     no native `feature_importances_`.
   - If you add new `ModelConfig` fields, give them defaults that do not
     change existing models, and wire them through the new model's trainer
     only. Do not assume other models use the new fields.

7. Add tests when there is something stable to test.
   - Prefer lightweight unit tests over expensive training runs.
   - Good targets:
     - registry/discovery behavior
     - strategy default or unsupported-strategy errors
     - config-field plumbing (including that the per-model default is used
       when `config=None`)
     - feature-importance fallback logic
   - If a full training test would require the real dataset or long runtimes,
     do not add a brittle heavy test just to say a test exists.

8. Verify cheaply.
   - Run targeted `pytest` for the tests you added or touched.
   - Run a cheap import/CLI verification when useful, for example
     `python train.py --help`.
   - Only run full training if the user explicitly asks for it.

## Design rules

- Keep the implementation thin and readable.
- Match the existing model modules; do not refactor the whole training stack.
- Prefer shared helpers in `model.py` over model-specific copies.
- If the new model needs a custom wrapper, keep it minimal and focused on
  prediction and feature-importance compatibility.
- If you have to pick defaults for a brand-new model, choose sane library
  defaults or the smallest explicit baseline needed to make the trainer usable.
  Do not invent a tuning pass.
- Never change the shared `ModelConfig` defaults to model-specific values.
  Override via the per-model `<MODEL>_DEFAULT` constant instead.

## Common gotchas in this repo

- Forgetting to import the new module in `models/__init__.py` leaves the
  registry empty.
- Forgetting to register a per-model default config means `train.py` and the
  harness baseline fall back to the shared `ModelConfig()` defaults, which may
  not be appropriate for the new model.
- Changing the shared `ModelConfig` defaults to values optimal for one model
  silently breaks every other model. Always use the per-model default config
  registry instead.
- Forgetting transformed-target handling breaks evaluation consistency.
- Returning predictions on the wrong scale causes RMSE/R² to be misleading.
- A model with no feature-importance interface can break
  `generate_all_visualizations()`.
- A model that rejects the repo default `strategy="shared"` can break the CLI
  and harness unless you set the trainer's own `strategy` default correctly
  (the pipeline defers to the trainer's default when `strategy=None`).

## Example prompts this skill should handle

- "Add an xgboost model under @models/ and wire it into the automation
  pipeline. No tuning."
- "Implement catboost as a new registered model in
  `src/experiments/automation/models` and keep the ETL untouched."
- "Plumb an elastic-net regressor into the automation model registry so
  `train.py` can select it."