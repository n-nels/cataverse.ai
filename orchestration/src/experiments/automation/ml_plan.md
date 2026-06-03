# ml_plan.md — Implementation Plan

## Phase 1: Data Loading

- [ ] Walk `X:\peakFit` for `*_expParams.json` files
- [ ] Parse `<YYYYMM>_<hhmmss>` from filename to get datetime
- [ ] Sort all experiments chronologically by datetime
- [ ] Filter out experiments where `has_csv == false`
- [ ] Filter out experiments where `exp_success == false`
- [ ] For each passing experiment, load corresponding `*_CarbonylPeakArea.csv`

## Phase 2: Target Extraction

- [ ] Filter CSV rows to `Peak_Name == 'monomer_sum'`
- [ ] Flatten Delta_Groups (lump all together, no grouping)
- [ ] Find the last non-NaN row by max `Time (s)` where all 6 `pfo-sec_*` targets are populated
- [ ] Extract the 6 target values as the output vector for that experiment

## Phase 3: Feature Engineering — Current Experiment

- [ ] Extract `is_new`, `is_reference`, `metal_loading` from JSON
- [ ] Flatten pretreatments to 8 steps, pad missing steps with zeros/NaNs
- [ ] For each step, extract: gas (one-hot per unique combination), pressure_calc (normalized per spec), temp, rate, duration
- [ ] Extract `exp_conditions`: gas (one-hot per unique combination), pressure_calc, temp

## Phase 3b: Derived Chain Features

- [ ] Sort all experiments chronologically by datetime (same as Phase 1)
- [ ] For each notebook, compute chain features based on chronological order
- [ ] Compute `distance_from_isnew` — count since last `is_new=true` (resets to 0 at each `is_new=true`)
- [ ] Compute `consecutive_isref` — count of consecutive `is_reference=true` (resets to 0 when `is_reference=false`)
- [ ] Compute `distance_from_isref` — count of consecutive `is_reference=false` since last `is_reference=true` (resets to 0 at `is_reference=true`)

## Phase 4: Feature Engineering — Previous Experiment

- [ ] For each experiment, append the 6 target values from the previous experiment in the same notebook
- [ ] First experiment in chain: use zeros for all previous target features

## Phase 5: Dataset Assembly

- [ ] Assemble feature matrix X and target matrix Y
- [ ] Verify no NaN targets remain
- [ ] Optionally impute or flag NaN features from pretreatment padding

## Phase 5b: Data Validation

- [ ] Verify feature matrix dimensions are correct (N samples × ~121 features)
- [ ] Check for unknown gases — flag and halt if found
- [ ] Sanity check value ranges (temperatures, pressures, rates)
- [ ] Verify chronological ordering is preserved

## Phase 6: Train/Test Split

- [ ] Split chronologically — first 80% by datetime is train, last 20% is test
- [ ] Further split train into train (80% of train) and validation (20% of train) for early stopping
- [ ] Do NOT shuffle — preserve temporal order to simulate real-world prediction
- [ ] Ensure no data leakage: test set contains only future experiments

## Phase 7: Model Training

- [x] Start with gradient boosting (LightGBM) — handles mixed features well
- [x] Train on train set, use validation set for early stopping
- [x] Evaluate on test set with appropriate metrics (RMSE, R² per target)

## Phase 8: Iteration

- [ ] Feature importance analysis
- [ ] Ablation: remove previous experiment features, measure impact
- [ ] Tune hyperparameters
