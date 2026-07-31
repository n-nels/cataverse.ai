# Experiment Report: rf_v2_0001

- **Branch:** (smoke)
- **Starting commit:** (smoke)
- **Ending commit:** (smoke)
- **Model tested:** random_forest
- **Baseline used:** rf_baseline
- **Dataset fingerprint:** ab2c62c60bc8947dbe127d5a79cc377b1e3a5de2bd7067b99ec9b7fbfe085ce09aaf3476196200b82e8a61c946b2e3ff6bc18fa74200c92b302d669d85c67afe
- **Split fingerprint:** df61c7f2af47257a4673ecd9f3c3ac34fd364c9994911444ab97e18c2dd619b2

## Trials

- Trials attempted: 31
- Successful trials: 31
- Failed trials: 0

## Results

- Best validation avg RMSE: 0.119324
- Baseline validation avg RMSE: 0.137005
- Best test avg RMSE: 0.052749
- Baseline test avg RMSE: 0.102651

## Best retained configuration

```yaml
n_estimators: 1809
max_depth: 23
min_child_samples: 1
subsample: 0.922465
colsample_bytree: 0.348978
random_state: 72
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
