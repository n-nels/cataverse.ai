# Experiment Report: lightgbm_v3_0001

- **Branch:** (smoke)
- **Starting commit:** (smoke)
- **Ending commit:** (smoke)
- **Model tested:** lightgbm
- **Baseline used:** lgbm_baseline
- **Dataset fingerprint:** 9612c37f626eb4b6ad776f4a5a8176ec55b5ab30ebf32db010b8abf5b0f5041f7d89ab2b228cf86d2b633f4f2c050e0a074e4b719a7ab8283edaba8fdc72d9f4
- **Split fingerprint:** df61c7f2af47257a4673ecd9f3c3ac34fd364c9994911444ab97e18c2dd619b2

## Trials

- Trials attempted: 31
- Successful trials: 31
- Failed trials: 0

## Results

- Best validation avg RMSE: 0.123778
- Baseline validation avg RMSE: 0.123778
- Best test avg RMSE: 0.057426
- Baseline test avg RMSE: 0.057426

## Best retained configuration

```yaml
n_estimators: 1000
learning_rate: 0.05
max_depth: 6
num_leaves: 31
min_child_samples: 20
subsample: 1.0
colsample_bytree: 1.0
reg_alpha: 0.0
reg_lambda: 0.0
early_stopping_rounds: 50
random_state: 42
boosting_type: gbdt
strategy: shared
```

## Recommendation

**no improvement found**

## Changed source files

_none_

## Protected files confirmed unchanged

- load.py
- extract.py
- transform.py
- model.py
- models/lightgbm.py
- models/random_forest.py
