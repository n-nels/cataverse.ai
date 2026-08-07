# Experiment Report: svr_v2_0001

- **Branch:** (smoke)
- **Starting commit:** (smoke)
- **Ending commit:** (smoke)
- **Model tested:** svr
- **Baseline used:** svr_baseline
- **Dataset fingerprint:** ab2c62c60bc8947dbe127d5a79cc377b1e3a5de2bd7067b99ec9b7fbfe085ce09aaf3476196200b82e8a61c946b2e3ff6bc18fa74200c92b302d669d85c67afe
- **Split fingerprint:** df61c7f2af47257a4673ecd9f3c3ac34fd364c9994911444ab97e18c2dd619b2

## Trials

- Trials attempted: 31
- Successful trials: 29
- Failed trials: 2

## Results

- Best validation avg RMSE: 0.114195
- Baseline validation avg RMSE: 0.116519
- Best test avg RMSE: 0.065168
- Baseline test avg RMSE: 0.065168

## Best retained configuration

```yaml
C: 6.430325
epsilon: 0.022255
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
- models/xgboost.py
