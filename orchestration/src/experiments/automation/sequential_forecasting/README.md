# Sequential Forecasting Handoff

This package implements the sequential forecasting workflow without changing
the protected RF ETL. The canonical source boundary is the RF artifact bundle;
all cutoff examples inherit its experiment-level assignments.

## Reproduce the workflow

Run these commands from:

```text
orchestration/src/experiments/automation/
```

The default data root is `X:\peakFit`. The default exclusions are `test` and
`nn1120-4_pd_ceo2_000`; repeat `--exclude-folder` to override them.

```powershell
python -m sequential_forecasting.cli rf-artifacts `
  --data-root X:\peakFit `
  --exclude-folder test `
  --exclude-folder nn1120-4_pd_ceo2_000 `
  --artifact-dir sequential_forecasting/artifacts/phase0 `
  --model-path models/random_forest.joblib

python -m sequential_forecasting.cli validate-rf-boundary `
  --artifact-dir sequential_forecasting/artifacts/phase0

python -m sequential_forecasting.cli validate-contract `
  --artifact-dir sequential_forecasting/artifacts/phase0

python -m sequential_forecasting.cli build-examples `
  --artifact-dir sequential_forecasting/artifacts/phase0

python -m sequential_forecasting.cli evaluate-baselines `
  --artifact-dir sequential_forecasting/artifacts/phase0

python -m sequential_forecasting.cli train-sequential-model `
  --artifact-dir sequential_forecasting/artifacts/phase0

python -m sequential_forecasting.cli run-inference `
  --artifact-dir sequential_forecasting/artifacts/phase0

python -m sequential_forecasting.cli evaluate-sequential `
  --artifact-dir sequential_forecasting/artifacts/phase0 `
  --assignment test
```

The final evaluation command must run only after model selection is frozen. It
rejects selection manifests that report `test_used_for_selection: true`.

## Artifact contract

The artifact directory contains the persisted run configuration, provenance,
dataset and split fingerprints, experiment assignments, held-out RF
predictions, validation reports, baseline predictions, model-selection
manifest, inference trace, and final evaluation report/plots.

The current selected candidate is `rf_only`. The Ridge implementation remains
available as selection evidence but is not active for inference. The final
test report is under:

```text
sequential_forecasting/artifacts/phase0/evaluation/report.md
```

Generated artifacts and raw data are excluded from source control by the
repository `.gitignore`.

## Scientific provenance

The local secondary-PFO implementation mirrors the sibling ODE behavior and
does not import across repositories. The Phase 0 provenance artifact records
the exact repository revision and dependency versions used for the run:

```text
sequential_forecasting/artifacts/phase0/provenance.json
```

For the validated run, both repository entries record commit
`b9c1ef07c81b9ef3547adab02ec14b41e2c8a71d`. The provenance also records Python
`3.13.2`, NumPy `2.5.1`, pandas `3.0.5`, SciPy `1.18.0`, scikit-learn `1.9.0`,
and joblib `1.5.3`; the repositories were dirty, so the commit and dirty-state
must be considered together when reproducing the run.

## Verification

The focused sequential package suite covers schema validation, flattening,
leakage prevention, split integrity, ODE mapping and fallback behavior,
baseline metrics, sequential inference, and evaluation aggregation. Run it
from the automation directory with:

```powershell
python -m pytest `
  tests/test_data_validation.py `
  tests/test_sequential_adapter.py `
  tests/test_rf_boundary.py `
  tests/test_baselines.py `
  tests/test_sequential_forecasting.py `
  tests/test_sequential_model.py `
  tests/test_inference.py `
  tests/test_evaluation.py -q
```
