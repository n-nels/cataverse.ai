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

**Future work:** A separate forecasting model will predict parameters at arbitrary times.

## Data Sources

1. **`*_expParams.json`** — experimental parameters per run
2. **`*_CarbonylPeakArea.csv`** — filtered to `Peak_Name == 'monomer_sum'` rows

### Filename format
`<YYYYMM>_<hhmmss>_<metal>_<support>_<sample_index>-<experiment_index>_<file type>.<ext>`

Example: `20260515_195430_pd_ceo2_004-022_expParams.json`

The `<YYYYMM>_<hhmmss>` prefix encodes chronological order — sort by this to preserve temporal sequence.

**Unknown gases:** The known pretreatment gas combinations are `CO2`, `H2`, `H2,O2`, `H2O`, `H2O,O2`, `O2`, `O2,H2`, `O2,H2O`, `RoughPump`, `TurboPump` (10 categories). The experiment gas `13CO` appears in `exp_conditions`, not pretreatments. If any unknown gas appears, flag it and halt for review.

## Data Processing Rules

### Delta_Group flattening
Delta_Groups (delta5, delta6, delta7, etc.) are **artificial data inflation**. Do NOT distinguish between Delta_Groups — they all get lumped together into one dataset. From that combined dataset, find the row with maximum `Time (s)` where all 6 target columns are non-NaN as the single observation for that experiment.

### Target extraction
Use the last non-NaN row (by max time) where all 6 `pfo-sec_*` target columns are populated. Note: when the fit converges, all 6 targets are co-fitted (always present together). NaNs appear in stderr columns, not targets.

### JSON feature set
Include from `*_expParams.json`:
- `is_new`, `is_reference`, `metal_loading` (features)
- All pretreatment and exp_conditions fields (features, encoded per rules below)

Exclude from both current and previous experiments:
- `material.*` (except `metal_loading`)
- `filename_flags.*` (except `is_new`, `is_reference`)
- `chiller` (exclude entirely)

### pressure_calc normalization
`pressure_calc` is either `null` (N/A, e.g. vacuum steps) or a single-element list `[value]`. 

- If `pressure_calc` is not null: extract the scalar from the list
- If `pressure_calc` is null AND gas is in ['RoughPump', 'TurboPump']: use `0`
- If `pressure_calc` is null AND gas is NOT in ['RoughPump', 'TurboPump']: use `pressure_meas_g1` as fallback

Do NOT include `pressure_meas_g1` or `pressure_meas_g2` as separate features.

### Pretreatment step padding
Experiments have 4, 6, or 8 pretreatment steps. Pad to **8 steps** (the max observed). Missing steps get zeros/NaNs.

Each step has these fields:
- `gas` (string — one-hot encoded per unique combination, 10 categories)
- `pressure_calc` (scalar, normalized per above rule)
- `temp` (float)
- `rate` (float)
- `duration` (float)

Result: 8 steps × (4 numeric fields + 10 gas one-hot columns) = **112 features** for pretreatments alone.

## Flagged for Deeper Dive

- **Q5:** Whether some targets can be NaN while others aren't. Initial inspection suggests targets are always co-fitted when fit converges — **resolved for now**.
- **Markov chain / history dependence:** Each experiment's outcome depends on prior experiments (catalyst aging, surface state). Need a strategy to encode experiment history as features — e.g., `notebook` sequence number, cumulative exposure, or previous experiment outcomes.

## History Encoding

Each experiment's outcome depends on prior experiments in the chain (same notebook/sample). Include features from the **previous experiment** in the chain to capture state dependence.

**Include from previous experiment:**
- Previous targets (6 pfo-sec values)

**Exclude from previous experiment:**
- All pretreatment params, exp_conditions, material, filename_flags, chiller

**First experiment in chain:** Use zeros for all previous features.

This adds 6 features (previous targets), bringing total feature count to ~121.

## Filters

- Skip experiments where `has_csv == false` (no kinetic parameters available)
- Skip experiments where `exp_success == false`

## Features (from JSON)

- `is_new` — boolean feature
- `is_reference` — boolean feature
- `metal_loading` — numeric feature

### Derived chain features

- `distance_from_isnew` — number of experiments since the last `is_new=true`. Resets to 0 at each `is_new=true`.
- `consecutive_isref` — count of consecutive `is_reference=true` experiments. Increments while `is_reference=true`, resets to 0 when `is_reference=false`.
- `distance_from_isref` — count of consecutive `is_reference=false` experiments since the last `is_reference=true`. Resets to 0 when `is_reference=true`.

## Open Questions

### Q5: Multi-gas encoding (RESOLVED)

Some pretreatment steps have two gases (e.g., `['H2', 'O2']`). Each unique gas combination is treated as its own category for one-hot encoding.

**Known combinations:** `CO2`, `H2`, `H2,O2`, `H2O`, `H2O,O2`, `O2`, `O2,H2`, `O2,H2O`, `RoughPump`, `TurboPump` (10 categories)

Gas order matters: `H2,O2` ≠ `O2,H1`. Unknown combinations should be flagged and halted.

### Q8: Validation strategy (PENDING)

With ~246 samples and chronological ordering, standard K-fold cross-validation could leak future data. Options:

1. **Chronological split only** — 80% train / 16% validation / 4% test, all by time. Simple, no leakage.
2. **Walk-forward validation** — train on months 1-N, test on month N+1, slide forward. More robust but complex.
3. **Group by notebook** — ensure all experiments from one notebook are in the same split. Tests generalization to unseen samples.

Recommendation: Start with option 1 (simple chronological split). If overfitting is suspected, try option 3.

