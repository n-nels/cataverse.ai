# spec.md — PFO-Sec Parameter Prediction Model

## Goal

Predict the **6 PFO-sec adsorption isotherm parameters** at max time `t` for a given experiment, conditioned on experimental parameters from `*_expParams.json`.

**Inputs:** Experimental parameters (JSON) + max `Time (s)`
**Output:** Set of 6 correlated parameters needed to model the isotherm:

| Column | Description |
|--------|-------------|
| `pfo-sec_k_a_s-1` | Adsorption rate constant |
| `pfo-sec_q_e_au` | Equilibrium adsorbed quantity |
| `pfo-sec_k_s_s-1` | Surface reaction rate |
| `pfo-sec_k_p_s-1` | Pore diffusion rate |
| `pfo-sec_q_inf_au` | Infinite-time adsorbed quantity |
| `pfo-sec_q0_au` | Initial adsorbed quantity |

## Data Pipeline (Implemented)

The ETL pipeline is in place and documented in the source code. Key files:

| File | Role |
|------|------|
| `extract.py` | Filesystem walk, JSON/CSV parsing, cache |
| `transform.py` | Feature engineering, target extraction, chain features |
| `load.py` | Dataset assembly, validation, chronological split |

See docstrings in each module for detailed processing rules. Major design decisions:

- **Delta_Group flattening** — all groups lumped together; take the row with max `Time (s)` where all 6 targets are non-NaN
- **Pretreatment padding** — all experiments padded to 8 steps (binary gas encoding + numeric fields)
- **Step feature reduction** — only `temp` and `duration` numeric fields used currently (`transform.py:50`)
- **Previous targets** — 6 previous-experiment target values per notebook chain
- **Unknown gas flagging** — halt on unrecognized gas combinations
- **Chronological ordering** — preserved by `<YYYYMM>_<hhmmss>` prefix

## Model Architecture

Models implement a common interface so they can be hot-swapped. The interface is defined in `model.py` and each concrete model lives in its own file under `models/`.

### Interface

A model trainer is a callable (or class with a `train` method) that accepts:

```python
(X_train, y_train, X_val, y_val, config) -> TrainedModel
```

`TrainedModel` wraps:
- `.model` — a `predict(X) -> np.ndarray` object
- `.config` — the `ModelConfig` used
- `.target_names` — column order for prediction output
- `.metrics` — per-target validation metrics
- `.lambdas` — Box-Cox lambdas (or None)

### Registry

Models self-register by name via a decorator in `model.py`:

```python
MODEL_REGISTRY: dict[str, ModelTrainer] = {}
```

Dispatch in `train.py` reads `--model` and looks up the trainer.

### Current Models

#### LightGBM (`models/lightgbm.py`)
- **Strategies:** `shared` (stacking trick, shared tree splits, early stopping) or `separate` (per-target `LGBMRegressor` via `MultiOutputRegressor`)
- **Target transform:** Box-Cox on 4 wide-dynamic-range targets
- **Baseline model** — currently trained as default

#### Random Forest (`models/random_forest.py`) *— new*
- **Implementation:** `RandomForestRegressor` with `MultiOutputRegressor` (one forest per target)
- **Target transform:** Box-Cox (same as LightGBM for fair comparison)
- **State:** Default parameters for initial baseline; grid search to follow

### Adding a New Model

1. Create `models/<name>.py`
2. Implement a `train_<name>(X_train, y_train, X_val, y_val, config) -> TrainedModel`
3. Decorate with `@register_model("<name>")`
4. Run via `python train.py --model <name>`

## Training Interface

```bash
# LightGBM (default, existing behavior)
python train.py

# Random Forest
python train.py --model random_forest
```

Both models share the same data pipeline, split, evaluation, and visualization code. Results are comparable directly.

## Model Comparison Protocol

- **Split:** Chronological 80/20 train-test, with 20% of training held out for validation (random, seeded)
- **Metrics:** Per-target RMSE and R² + aggregate averages
- **Baseline:** Training-set mean prediction (no-information baseline)
- **Visualization:** `visualize.py` generates parity plots, residual plots, feature importance, and prediction distributions for any model

## Future Work

- Grid search for both LightGBM and Random Forest hyperparameters
- Additional model types (XGBoost, MLP, etc.)
- Walk-forward validation scheme
- Feature selection / importance-driven reduction
