# Experiment Report: svr_v1_0001

- **Branch:** (smoke)
- **Starting commit:** (smoke)
- **Ending commit:** (smoke)
- **Model tested:** svr
- **Baseline used:** svr_baseline
- **Dataset fingerprint:** ab2c62c60bc8947dbe127d5a79cc377b1e3a5de2bd7067b99ec9b7fbfe085ce09aaf3476196200b82e8a61c946b2e3ff6bc18fa74200c92b302d669d85c67afe
- **Split fingerprint:** df61c7f2af47257a4673ecd9f3c3ac34fd364c9994911444ab97e18c2dd619b2

## Trials

- Trials attempted: 31
- Successful trials: 16
- Failed trials: 15

## Results

- Best validation avg RMSE: 0.116519
- Baseline validation avg RMSE: 0.116519
- Best test avg RMSE: 0.065168
- Baseline test avg RMSE: 0.065168

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
min_samples_split: 2
random_state: 42
boosting_type: gbdt
min_child_weight: 1
gamma: scale
n_neighbors: 5
weights: uniform
algorithm: auto
leaf_size: 30
p: 2
kernel: rbf
C: 1.0
epsilon: 0.1
degree: 3
coef0: 0.0
strategy: separate
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
- models/xgboost.py
