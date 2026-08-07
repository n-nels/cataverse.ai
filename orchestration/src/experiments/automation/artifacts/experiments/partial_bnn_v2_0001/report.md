# Experiment Report: partial_bnn_v2_0001

- **Branch:** (smoke)
- **Starting commit:** (smoke)
- **Ending commit:** (smoke)
- **Model tested:** partial_bnn
- **Baseline used:** partial_bnn_baseline
- **Dataset fingerprint:** ab2c62c60bc8947dbe127d5a79cc377b1e3a5de2bd7067b99ec9b7fbfe085ce09aaf3476196200b82e8a61c946b2e3ff6bc18fa74200c92b302d669d85c67afe
- **Split fingerprint:** df61c7f2af47257a4673ecd9f3c3ac34fd364c9994911444ab97e18c2dd619b2

## Trials

- Trials attempted: 11
- Successful trials: 6
- Failed trials: 5

## Results

- Best validation avg RMSE: 0.117181
- Baseline validation avg RMSE: 19255.705193
- Best test avg RMSE: 0.054474
- Baseline test avg RMSE: inf

## Best retained configuration

```yaml
hidden_dims:
- 8
- 4
strategy: separate
num_chains: 1
num_warmup: 416
num_samples: 374
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
