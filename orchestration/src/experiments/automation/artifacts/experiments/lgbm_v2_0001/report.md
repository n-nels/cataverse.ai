# Experiment Report: lgbm_v2_0001

- **Branch:** (smoke)
- **Starting commit:** (smoke)
- **Ending commit:** (smoke)
- **Model tested:** lightgbm
- **Baseline used:** lgbm_baseline
- **Dataset fingerprint:** 5488e72781fb76a54901ed3f671558562783507d973f3e9a297b68b75d677d12dc1885bdffbddf2f3bb9e42e6dca4b76f5ee77a5857d7856974acb12b146c193
- **Split fingerprint:** 2fb1604e764b5673d3addc7dd8f423fc408112a5efea86a4041d1089e7b00501

## Trials

- Trials attempted: 31
- Successful trials: 31
- Failed trials: 0

## Results

- Best validation avg RMSE: 0.074407
- Baseline validation avg RMSE: 0.082424
- Best test avg RMSE: 0.052265
- Baseline test avg RMSE: 0.052265

## Best retained configuration

```yaml
n_estimators: 1475
learning_rate: 0.197195
max_depth: 10
num_leaves: 95
min_child_samples: 14
subsample: 0.504658
colsample_bytree: 0.734811
reg_alpha: 0.562994
reg_lambda: 0.099981
early_stopping_rounds: 88
random_state: 3493
strategy: separate
```

## Recommendation

**retain for human review**

## Changed source files

_none_

## Protected files confirmed unchanged

- load.py
- extract.py
- transform.py
- model.py
- models/lightgbm.py
- models/random_forest.py
