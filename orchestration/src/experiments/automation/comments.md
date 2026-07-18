1. Remove the "Phase X" line out text in ETL pipeline
2. prefix helper functions with underscore in ETL, maybe it is just transform?
3. we need to set is_new = true for the first .json and CarbonylPeakArea.csv joint occurrence. 
4. [load.py reduce_features()] reduce_features should drop with gas = RoughPump or TurboPump instead of steps
5. [load.py split_dataset()] has incorrectly described doc string
6. [lightgbm.py, line 207] pfo-sec_q0_au is negative but gets boxcoxed, skip it 
7. [lightgbm.py _train_shared, lines 126-128] StandardScaler applied on top of Box-Cox is redundant — LightGBM trees are invariant to monotonic transforms. Adds unnecessary complexity and a second inverse step.
8. [lightgbm.py _train_shared vs _train_separate] Inconsistent preprocessing: shared strategy applies StandardScaler on top of Box-Cox, separate strategy does not. Same input, different transforms depending on path.
9. [model.py fit_boxcox_lambdas] Only 4 of 6 targets get Box-Cox transformed (LOG_TRANSFORM_TARGETS). The other 2 targets pass through raw. May be intentional but worth confirming.
10. [lightgbm.py _sanitize_feature_names vs model.py sanitize_feature_names] Duplicate regex logic in two files. lightgbm.py defines its own _sanitize_feature_names instead of importing from model.py.