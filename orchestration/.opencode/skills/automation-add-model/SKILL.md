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
  - `model.py`
  - `pipeline.py`
  - `models/__init__.py`
  - `models/lightgbm.py`
  - `models/random_forest.py`
- Registration happens via `@register_model("<name>")`.
- `pipeline.py` imports `models` to populate the registry.
- `train.py --model` choices come from `sorted(MODEL_REGISTRY)`.
- The harness also routes through `pipeline.train_model(...)`.
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

## Default workflow

1. Read the contract before coding.
   - Open `model.py`, `pipeline.py`, `models/__init__.py`, and the existing
     model modules.
   - If harness compatibility matters, also inspect `harness/trial.py` and
     `harness/campaign.py`.

2. Confirm dependencies.
   - If the requested library is missing, install it with
     `uv pip install <package>`.
   - Do not use `pip` or `uv add`.

3. Add `models/<model_name>.py`.
   - Follow the existing module style: module docstring, `logger`, and small
     helpers only when they pull their weight.
   - Register the trainer with `@register_model("<model_name>")`.
   - Use the trainer signature:

     ```python
     def train_<name>(
         X_train: pd.DataFrame,
         y_train: pd.DataFrame,
         X_val: pd.DataFrame,
         y_val: pd.DataFrame,
         config: ModelConfig | None = None,
         strategy: str = "shared",
     ) -> TrainedModel:
     ```

   - Reuse the shared helpers from `model.py`:
     - `fit_boxcox_lambdas`
     - `apply_target_transforms`
     - `inverse_target_transforms`
     - `ModelConfig`
     - `TrainedModel`
   - Compute validation RMSE/R² in the same pattern as the existing trainers.
   - Return `TrainedModel(model=..., config=..., target_names=..., metrics=..., lambdas=...)`.

4. Decide strategy support deliberately.
   - The rest of the repo often calls models with `strategy="shared"` by
     default.
   - Prefer supporting `shared` if the model family can do it cleanly.
   - If only `separate` is realistic, keep the `strategy` parameter but make
     the smallest end-to-end plumbing change needed so the default path does
     not invoke an unsupported strategy.
   - If both `shared` and `separate` are reasonable, implement both.

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
   - If you add new `ModelConfig` fields, give them defaults that do not change
     existing models.

7. Add tests when there is something stable to test.
   - Prefer lightweight unit tests over expensive training runs.
   - Good targets:
     - registry/discovery behavior
     - strategy default or unsupported-strategy errors
     - config-field plumbing
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

## Common gotchas in this repo

- Forgetting to import the new module in `models/__init__.py` leaves the
  registry empty.
- Forgetting transformed-target handling breaks evaluation consistency.
- Returning predictions on the wrong scale causes RMSE/R² to be misleading.
- A model with no feature-importance interface can break
  `generate_all_visualizations()`.
- A model that rejects the repo default `strategy="shared"` can break the CLI
  and harness unless you adjust the plumbing.

## Example prompts this skill should handle

- "Add an xgboost model under @models/ and wire it into the automation
  pipeline. No tuning."
- "Implement catboost as a new registered model in
  `src/experiments/automation/models` and keep the ETL untouched."
- "Plumb an elastic-net regressor into the automation model registry so
  `train.py` can select it."
