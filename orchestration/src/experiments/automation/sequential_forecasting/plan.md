# Sequential Forecasting Implementation Plan

Status: Phase 6 complete; ready for Phase 7

This is the working north star for implementing the sequential forecasting
system described in `spec.md`. Future coding sessions should update the
checkboxes, record evidence, and resolve questions here before adding model
complexity.

## 1. Package Boundary

The existing `automation/` directory is the RF model package. Its current RF
ETL, model registry, experiment harness, manifests, and completed artifacts
remain in place.

The sequential forecasting task lives in:

```text
orchestration/src/experiments/automation/sequential_forecasting/
```

This directory contains:

- `spec.md` - the approved problem specification.
- `plan.md` - this implementation plan and decision log.
- New sequential-forecasting code, tests, and documentation added in later phases.

The initial implementation must not move or rewrite the RF package merely to
make the new package convenient to import. Establish an explicit import
contract first and keep protected ETL behavior unchanged.

The sequential workflow should reuse the RF ETL as its curated dataset
boundary rather than independently scanning and selecting a second population
of experiments. The intended integration is:

- Reuse the existing extraction and experiment-record pairing.
- Reuse the existing curated reference-target extraction.
- Reuse the existing RF dataset construction and train/validation/test assignment.
- Add time-series observations, cutoff rows, fit-availability masks, and intermediate-fit history through additive sequential interfaces.
- Preserve the existing RF mode, target values, transforms, metrics, and split behavior.

Any edit to a protected ETL file must be additive, narrowly scoped, and
verified against the unchanged RF workflow before it is accepted.

## 2. Working Rules

- [ ] Treat `spec.md` and this plan as the governing requirements.
- [ ] Keep `extract.py`, `transform.py`, and `load.py` behavior-protected.
- [ ] Do not change RF target definitions, target transforms, official metrics, or canonical RF split behavior.
- [ ] Keep all sequential examples from one underlying experiment in one partition.
- [ ] Use `Peak_Name == "monomer_sum"` before building examples, fitting the sequential model, or scoring.
- [ ] Flatten `Delta_Group` without using it as an experiment, feature, target, split, or evaluation group.
- [ ] Treat missing `pfo-sec_*` values as valid fit-availability data; never convert them to zero or silently discard the experiment.
- [ ] Record every unresolved assumption in this plan instead of silently choosing one.
- [ ] Use training experiments only for learned preprocessing, feature selection, and model selection.
- [ ] Use validation experiments for selection and test experiments only for final confirmation.
- [ ] Reuse the existing ODE and RF implementations where practical; do not replace either system in the initial version.
- [ ] Prefer a simple, interpretable model and add complexity only when held-out validation evidence supports it.

## 3. Discovered Repository Context

These facts were established during initial inspection. They are starting
evidence, not substitutes for validating the real dataset.

- [x] The current RF package is rooted at `orchestration/src/experiments/automation/`.
- [x] The current RF model is registered as `random_forest` in `models/random_forest.py`.
- [x] The current RF uses the six target columns in `transform.py` and applies Box-Cox transforms through `model.py`.
- [x] `transform.py` filters target extraction to `Peak_Name == "monomer_sum"`.
- [x] `transform.py` currently reads all matching rows together and selects a maximum-time complete target row; this must be audited against `Delta_Group` duplication before sequential examples are trusted.
- [x] The current RF dataset has one assembled row per `ExperimentRecord`, but the sequential dataset will have multiple cutoff rows per experiment.
- [x] The current `load.split_dataset()` uses record-level `train_test_split`; it cannot be reused unchanged for cutoff examples because multiple cutoffs from one experiment would be split independently.
- [x] The current RF harness records dataset and split fingerprints, but it does not yet establish that stored RF predictions are held out for every experiment.
- [x] The ODE implementation is in the sibling `ir-spectro-node` repository, primarily `src/analysis/kinetics_fitting.py` and `src/utils/kinetic_fit_writer.py`.
- [x] The secondary PFO ODE parameter order in the fitting code is `k_a, q_e, k_s, k_p, q_inf, q_0`.
- [x] `orchestration/src/experiments/automation/eda.py` maps the six RF target names into that ODE order and provides a reference implementation of curve solving.
- [x] The ODE fitting code currently uses a default minimum of four points in several rolling-fit entry points; the actual production rule and data path still require confirmation.
- [x] The ODE fixes `q_0` to the first observed intensity and initializes the secondary state to zero.
- [x] The existing secondary-fit implementation uses bounded nonnegative values for several parameters and derives `k_p` from `k_a * k_p_ratio`; these are implementation constraints to verify, not yet the complete project constraint contract.
- [x] The raw data schema includes at least `Peak_Name`, `Time (s)`, `Cumulative_Peak_Area`, six kinetic target columns, and `Delta_Group` in relevant workflows.
- [x] The default raw data root in the current RF code is `X:\peakFit`, but the usable data location has not been confirmed for this task.

## 3a. Owner Clarifications Applied

- [x] Use `X:\peakFit\<folder_name>\*CarbonylPeakArea.csv` as the raw experiment source.
- [x] Exclude folder names `test` and `nn1120-4_pd_ceo2_000` by default.
- [x] Surface the data root and exclusions as explicit sequential-pipeline arguments so they are easy to find and override.
- [x] Use the existing RF training workflow with `--model random_forest` and the same train/validation/test assignments.
- [x] Generate RF predictions for the test experiments and run sequential forecasting on those same test files.
- [x] Treat `q_0` as known from the first observation, before ODE fitting begins; pass it through into the complete ODE-compatible output rather than learning it.
- [x] Use `ir-spectro-node/src/analysis/kinetics_fitting.py` as the primary source for secondary-PFO fit eligibility, parameter ordering, bounds, solver behavior, and fit failure behavior.
- [x] Record that the current `train.py` CLI exposes `--model` and `--strategy`, but not data-root or exclusion arguments; future plumbing must make the RF and sequential runs consume the same explicit selection configuration.
- [x] Confirm that `X:\peakFit` is available in the working environment.
- [x] Confirm that no additional owner-supplied physical constraints are required beyond the existing ODE implementation.
- [x] Use RMSE on observed points strictly after each cutoff as the initial remaining-curve metric unless repository inspection finds an existing project convention.
- [x] Inspect representative included `CarbonylPeakArea.csv` files and confirm that they already contain rolling `pfo-sec_*` fit columns; early rows are blank until the fit becomes eligible.
- [x] Confirm that missing `pfo-sec_*` values can persist for part or all of an experiment and must be represented as valid missing-fit data rather than automatic exclusions.
- [x] Confirm that the sequential workflow should use the existing RF ETL as the curated experiment-selection boundary, with mostly additive time-series fields.
- [x] Confirm that repeated timestamp rows with different areas are expected measurement variance; preserve the current flattening behavior for the initial baseline while retaining raw rows and collision provenance for later all-data evaluation.

Required data-selection arguments/configuration:

```text
--data-root X:\peakFit
--exclude-folder test
--exclude-folder nn1120-4_pd_ceo2_000
```

The defaults must be visible in the sequential CLI help and in the saved run
configuration. The implementation must report the effective root and excluded
folder names at startup.

## 3b. Discovery Findings (2026-08-07)

- The included folders were readable under `X:\peakFit`, and the existing
  JSON-to-CSV pairing produced 243 experiments. Every paired CSV stem matched
  `ExperimentRecord.base_name`.
- All 243 included files contain `monomer_sum` rows and at least one repeated
  exact `Time (s)` value across `Delta_Group`. There are up to five rows at one
  exact timestamp; 4,456 repeated-time groups contain distinct
  `Cumulative_Peak_Area` values. This confirms that duplicate handling cannot be
  chosen from row order without changing the data meaning.
- Six complete secondary-PFO parameter columns are present in the files. Seven
  files contain no complete stored fit and require reporting or regeneration:
  `20250128_064524_pd_ceo2_000-023`,
  `20250203_075315_pd_ceo2_000-026`,
  `20250216_072220_pd_ceo2_000-033`,
  `20250528_202944_pd_ceo2_001-036`,
  `20260130_215303_pd_ceo2_003-107`,
  `20260505_063850_pd_ceo2_004-018`, and
  `20260526_091836_pd_ceo2_004-025`.
- No included file has partially populated secondary-PFO parameter vectors.
  However, 17 files have gaps in complete-fit availability after their first
  valid rolling fit, concentrated in later `nn1120-3_pd_ceo2_004` data. Stored
  fits must therefore be represented with explicit availability/status fields.
- Of the 236 files with at least one complete fit, 233 first become valid at
  the fourth unique observation time. Three files first become valid at unique
  time ranks 2, 7, and 23. This supports `min_points=4` as a discovered
  default, but does not establish it as a universal production rule.
- No explicit final-time field was found in the paired JSON metadata. For all
  243 files, the maximum `Time (s)` in `monomer_sum` equals the maximum time in
  the complete CSV; for every file with a complete fit, it also equals the
  maximum complete-fit time. The owner confirmed the complete-fit maximum as
  the final time, with maximum flattened monomer time for zero-target cases.
  CSV row order is not chronological in 145 files, so timelines must be sorted
  explicitly.
- No existing remaining-curve scorer was found. Existing RMSE calculations
  score fit residuals over the supplied full observation set; they do not
  define the strict post-cutoff remainder metric. The plan's initial candidate
  remains RMSE over observed points strictly after each cutoff.
- The sibling ODE implementation preserves the required parameter order,
  bounds, `q_0` pass-through, `solve_ivp`/`RK45` behavior, and timeout/failure
  signaling. The sequential package implements this behavior locally and does
  not import across repositories.

## 3c. Owner Clarifications (2026-08-07)

- Experiments with the JSON success flag set to true but no adsorption are
  valid data points, not failed experiments. They should remain in the
  sequential dataset and receive an explicit successful-no-adsorption status
  with an all-zero reference target, rather than being silently excluded.
- For exact duplicate `(Peak_Name, Time (s))` keys across `Delta_Group`, the
  sequential flattening step will retain the last source row, matching the
  existing ODE writer's `drop_duplicates(..., keep="last")` behavior. Every
  collision must be logged with the experiment, time, retained source row,
  discarded source rows, and collision count.
- The final time is the maximum `Time (s)` that has all six parameters. For
  successful-no-adsorption experiments with no complete parameter row, use the
  maximum flattened `monomer_sum` time alongside the zero-target status.
- Near-duplicate timestamps should be merged with a configurable default
  tolerance of `1e-3` seconds. Each merge is part of the collision log.
- At every cutoff, generate the full ODE trajectory from the first measured
  time through final time, retain the known prefix, and score only observed
  points strictly after the cutoff. Progress snapshots are reporting views;
  they are not a restriction to three forecast points.
- The sequential package must not import across repositories. It will use a
  local implementation of the same ODE equations, parameter order, bounds,
  solver settings, and failure behavior. Here, an "adapter" means only a
  local wrapper translating sequential data into that behavior; it does not
  mean importing `ir-spectro-node`.

## 3d. Implementation Evidence (2026-08-08)

- `sequential_forecasting/data/observations.py` filters to `monomer_sum`, merges timestamps
  within `1e-3` seconds, retains the last source row, and returns structured
  collision records.
- `sequential_forecasting/data/examples.py` creates one prefix-only example per
  flattened cutoff, preserves reference-target provenance, passes through the
  first-observation `q_0`, and records intermediate-fit masks/statuses.
- `sequential_forecasting/models/secondary_pfo.py` provides local secondary-PFO fitting,
  full-trajectory cutoff forecasting, and strict post-cutoff RMSE.
- Focused tests pass (`9 passed`). A real-data smoke check produced 73
  leakage-safe examples from a fitted experiment and retained a successful
  no-adsorption experiment as 44 zero-target examples.
- Phase 0 artifacts under `sequential_forecasting/artifacts/phase0/` contain
  the run configuration, provenance, dataset/split fingerprints, assignment
  table, RF predictions, and prediction-provenance summary. The dataset and
  split hashes match `rf_v2_0001` exactly: 243 records with a 155/39/49
  train/validation/test split.
- RF prediction coverage is complete: 194 out-of-fold predictions for
  train/validation experiments and 49 held-out-test predictions. No
  in-sample predictions are used for sequential training inputs.
- Phase 1 is validated by `data_contract.md`, `data/validation.py`, and
  `validation_report.json` plus the reproducible
  `artifacts/phase0/phase1/validation_report.json`. The real-data report is
  valid with 243 experiments, 12,013 cutoff examples, 5,281 collision
  clusters, 236 complete-fit references, 7 successful-no-adsorption
  references, and no validation failures. It records 17 currently accepted
  records under the configured excluded folder inventory.

## 3e. Package Organization (2026-08-09)

The package is organized by responsibility rather than project milestone:

```text
sequential_forecasting/
├── config.py
├── cli.py
├── baselines.py
├── sequential_model.py
├── data/
│   ├── contract.py
│   ├── observations.py
│   ├── examples.py
│   └── validation.py
├── models/
│   └── secondary_pfo.py
└── rf/
    ├── provenance.py
    ├── splits.py
    ├── predictions.py
    └── artifacts.py
```

Generated artifacts default to `automation/artifacts/sequential_forecasting/`
and are excluded from source control. The command-line preparation commands
are `rf-artifacts` and `validate-contract`. No source modules or tests use
`phase0.py` or `phase1.py` names.

This directory structure is a working organizational plan, not a permanent
API or architectural constraint. At the end of every successful phase, review
the package boundaries, module responsibilities, import relationships, and
artifact locations before beginning the next phase. If the implementation has
revealed a clearer separation of concerns, update this section and migrate the
package while the change is still small. Do not preserve a structure merely
because an earlier phase used it; staying organized is an explicit project
requirement.

## 3f. Phase 2 Implementation Evidence (2026-08-09)

- `data/adapter.py` builds examples only from the persisted RF split-assignment
  table, paired source files, and held-out RF prediction table; it does not
  create a second experiment-selection population.
- Each serialized example carries its experiment assignment, RF prediction and
  provenance, source paths, reference-target provenance, progress fields, and
  per-parameter fit-coverage summary.
- Prefix observations and current fit values remain cutoff-limited. Historical
  fit sequences are deferred until a baseline feature representation is
  selected; no learned preprocessing is applied in this phase.
- `build-examples` writes `examples.jsonl` and `manifest.json` from the persisted
  Phase 0 artifacts.
- Focused Phase 2 tests pass (`13 passed`), and the real-data adapter smoke check
  produced 12,013 examples from 243 experiments with the 155/39/49 assignment
  counts and out-of-fold/held-out-test RF provenance.

## 3g. Phase 3 Implementation Evidence (2026-08-09)

- `rf/validation.py` validates the persisted assignment table, partition
  disjointness, one-to-one RF prediction coverage, target order, held-out
  provenance, fold metadata, and train-only test-model coverage.
- RF artifacts now include a SHA-256 fingerprint for `rf_predictions.csv` and
  explicitly record both the source RF target order and the sequential target
  order. The source RF order is allowed to differ; predictions are joined by
  target name rather than position.
- The `validate-rf-boundary` command validates the persisted Phase 0 artifacts.
- Real-artifact validation passed for 243 experiments: 155 train, 39
  validation, 49 test; 194 out-of-fold predictions and 49 held-out-test
  predictions, with no failures.

## 3h. Phase 4 Implementation Evidence (2026-08-09)

- The sequential package uses a local secondary-PFO implementation rather than
  importing the sibling repository. The equation, parameter order, `solve_ivp`
  `RK45` solver, `rtol=1e-8`, timeout signaling, and initial state are retained.
- `RunConfig` and the RF-artifact CLI expose minimum fit points, fit mode,
  timeout, initial guess, and prior-fit carry-forward behavior.
- `fit_expanding_prefixes` makes prefix-only fitting explicit. Complete finite
  parameter validation and structured `ForecastResult` fallback provenance are
  available before curve generation.
- Focused Phase 4 tests pass (`19 passed`). Numerical smoke fitting on a known
  six-point curve produced three ineligible prefix statuses followed by three
  valid fit attempts.

## 3i. Phase 5 Implementation Evidence (2026-08-09)

- `baselines.py` implements RF-only, current-valid-ODE, and RF/ODE-blend
  baselines with shared cutoffs, target ordering, q_0 pass-through, parameter
  validation, and strict post-cutoff curve scoring.
- Current-ODE fallback is the held-out RF prediction when the current stored fit
  is unavailable or invalid. The blend weight is selected on validation
  examples only; the tested candidate weights were `0.0`, `0.25`, `0.5`, `0.75`,
  and `1.0`.
- `evaluate-baselines` writes per-example `predictions.jsonl` and aggregated
  `manifest.json` results by assignment and early/middle/late progress group.
- Real-data Phase 5 artifacts contain 12,013 examples and 36,039 baseline
  records. Validation selected blend weight `0.5`; all three baselines have
  parameter and remaining-curve results across the test progress groups.
- Focused baseline/contract tests pass (`21 passed`).

## 3j. Phase 6 Implementation Evidence (2026-08-09)

- `sequential_model.py` implements a regularized Ridge correction to the first
  five RF parameters. It uses RF predictions, current-fit values and masks,
  fit diagnostics, prefix observation summaries, progress fields, and fit
  status flags; `q_0` is passed through and is not learned.
- Features are standardized using training experiments only, and cutoff rows
  are weighted so experiments with longer timelines do not dominate fitting.
- Candidate Ridge alphas `0.01`, `0.1`, `1.0`, `10.0`, and `100.0` were evaluated
  on validation parameter and curve metrics by progress group. The validation
  selection score combines overall parameter RMSE with early curve RMSE.
- The learned Ridge correction was not selected: its best score was `0.8296`,
  while RF-only scored `0.4996`. RF-only is therefore the selected simplest
  candidate, and no learned model artifact is treated as active for inference.
- Selection used 155 training and 39 validation experiments and explicitly did
  not use the 49 test experiments. The candidate manifest records both split
  fingerprints and `test_used_for_selection: false`.
- Focused Phase 6 tests pass (`23 passed`).
- Phase 6 completion was re-verified on 2026-08-10 with
  `python -m pytest tests/test_data_validation.py tests/test_sequential_adapter.py tests/test_rf_boundary.py tests/test_baselines.py tests/test_sequential_forecasting.py tests/test_sequential_model.py -q` (`23 passed`). The persisted model manifest confirms `selected_candidate: rf_only`, `learned_model_selected: false`, 155 training experiments, 39 validation experiments, and `test_used_for_selection: false`.
- Because RF-only was selected, compact trajectory and sequence-aware candidates
  remain intentionally deferred rather than adding complexity without a
  validated gap.

## 4. Phase 0: Establish Provenance

Goal: make the project reproducible before producing any training examples.

- [x] Validate that `X:\peakFit` is readable and enumerate `*_CarbonylPeakArea.csv` files under each included folder.
- [x] Use the existing ETL pairing (`*_expParams.json` -> `*_CarbonylPeakArea.csv`) and `ExperimentRecord.base_name` as the canonical experiment ID; verify this against the CSV path/file stem.
- [x] Audit all selected `CarbonylPeakArea.csv` files for complete-series and rolling/intermediate `pfo-sec_*` fit coverage; consume the stored fits initially and report files requiring regeneration rather than regenerating them silently.
- [x] Record repository revision/version metadata for both `orchestration` and `ir-spectro-node` when source code from both is used. This is provenance only; it does not require creating a commit.
- [x] Record the current RF dataset fingerprint and RF split fingerprint without modifying the RF ETL.
- [x] Identify the existing RF train, validation, and test experiment assignments.
- [x] Run the existing RF workflow with `--model random_forest` using the same data root and exclusions.
- [x] Add or use non-ETL argument plumbing so the RF invocation receives `--data-root` and both `--exclude-folder` values while preserving existing defaults.
- [x] Persist the exact RF split assignments keyed by `base_name`; sequential cutoff rows must inherit these assignments unchanged.
- [x] Persist per-experiment RF predictions, including the test predictions used by sequential forecasting. The current `train.py` evaluates the test set but does not visibly export a per-record prediction table, so add a sequential-side export step rather than changing protected ETL behavior.
- [x] Define held-out RF predictions for sequential training and validation rows; do not use in-sample RF predictions merely because the RF model artifact exists.
- [x] Add a sequential run configuration containing data paths, the two exclusion defaults, minimum fit points, cutoff policy, target order, split seed, and artifact paths.

Exit criteria:

- A new agent can identify every source table/file and reproduce the RF assignment used by the sequential pipeline.
- RF predictions used for sequential training are labeled as held-out, in-fold, or unknown; unknown predictions are not silently used as realistic training inputs.

## 5. Phase 1: Write the Data Contract

Goal: define one canonical representation of an experiment and its valid
cutoffs without changing upstream ETL behavior.

- [x] Define the canonical experiment ID initially as `ExperimentRecord.base_name`, linked to its paired `CarbonylPeakArea.csv` path; verify this mapping during Phase 0.
- [x] Define the observation table fields, units, ordering, duplicate policy, and missing-value policy.
- [x] Filter the sequential source to `Peak_Name == "monomer_sum"` and assert that no other peak enters an example or metric.
- [x] Inspect every representation of `Delta_Group` in CSVs, indexes, joins, caches, and generated fit tables.
- [x] Define and document the flattening operation across `Delta_Group`.
- [x] Quantify whether flattening creates duplicate `(experiment, time)` rows and define a deterministic resolution rule that does not aggregate artificial copies into extra experimental weight.
- [x] Verify that flattened rows do not duplicate the complete-series reference target.
- [x] Verify that flattening cannot place records from one underlying experiment into different partitions.
- [x] Define the known final time and how it is linked to each experiment.
- [x] Define valid cutoff points from observed measurements, including irregular schedules and repeated timestamps.
- [x] Define the minimum number of observations required for the first ODE fit as configuration, not a hidden constant.
- [x] Define the representation of failed, missing, non-finite, and unavailable intermediate fits.
- [x] Distinguish fit-not-yet-eligible, fit-missing-for-this-cutoff, fit-partially-populated, fit-missing-for-the-whole-experiment, fit-failed, and fit-valid states.
- [x] Preserve a value and an availability mask for each `pfo-sec_*` parameter; missingness is not a numeric zero.
- [x] Define the six target names and ordering in one shared contract.
- [x] Pass `q_0` through from the first observation, exclude it from learned targets, and retain it in the six-value output vector for ODE compatibility.
- [x] Document parameter units, ranges, positivity requirements, relationships, invalid combinations, and solver stability limits.

Required validation checks:

- [x] Every example has exactly one underlying experiment ID and one cutoff ID.
- [x] Cutoff observations are sorted and contain no observation after the cutoff.
- [x] The reference target comes only from the complete series.
- [x] `q_0` in every example equals the first valid `Cumulative_Peak_Area` observation and is never learned from later observations.
- [x] Intermediate fit data at cutoff `t` uses only observations at or before `t`.
- [x] The final-time row is not used as a feature at earlier cutoffs.
- [x] The number of examples, experiments, cutoffs, duplicate rows, failed fits, and excluded records is reported.

Exit criteria:

- A versioned data-contract document and validation report exist.
- The contract can reconstruct one experiment's full timeline and every eligible cutoff from source data.
- The duplicate and `Delta_Group` policy is demonstrated on real records, not only unit fixtures.

## 6. Phase 2: Build Leakage-Safe Sequential Examples

Goal: create a reproducible table or serialized structure with one row per
experiment/cutoff and variable-length histories represented explicitly.

- [x] Implement the sequential data adapter inside `sequential_forecasting/`, reusing the RF ETL's selected records and curated reference targets rather than creating a parallel experiment-selection path.
- [x] Join held-out RF predictions to the canonical experiment ID.
- [x] Join raw observations through the current cutoff only.
- [x] Join the current intermediate ODE fit and, if selected, prior intermediate fits through the current cutoff only.
- [x] Include fit-status and validity indicators instead of silently imputing failed fits as valid values.
- [x] Include per-parameter availability masks and an experiment-level coverage summary for `pfo-sec_*` columns.
- [x] Do not exclude an experiment merely because one or more intermediate `pfo-sec_*` columns are missing for part or all of its timeline.
- [x] Include progress fields only when computable without future information; distinguish observation fraction, elapsed-time fraction, and time remaining.
- [x] Attach the complete-series reference target separately from model inputs.
- [x] Store an auditable mapping from each example to source files, experiment ID, cutoff time, observation count, fit status, RF prediction provenance, and reference target provenance.
- [x] Fit any learned normalization, imputation, dimensionality reduction, or feature selection on training experiments only; no learned preprocessing is used in this phase.
- [x] Add tests that deliberately inject future rows and verify they cannot enter earlier examples.
- [x] Add tests that verify all cutoffs from one experiment are inseparable during splitting.
- [x] Add tests that verify invalid and missing fits are represented and counted.

Candidate initial feature representation:

- [x] RF prediction vector.
- [x] Current ODE parameter vector and fit diagnostics when valid.
- [ ] Previous ODE parameter vector or compact trajectory summaries when available.
- [ ] Raw observation summaries through the cutoff, with explicit counts and missingness.
- [x] Measurement-time summaries and progress indicators.
- [x] Fit-validity indicators (forecast fallback indicators are deferred to the inference phase).

The first version should avoid feeding arbitrary padded histories or the
original RF static features until the simpler representation has a validated
baseline.

Exit criteria:

- Training examples can be regenerated from source data.
- A leakage audit passes for representative early, middle, late, irregular, duplicate, and failed-fit cases.
- The example builder produces no `Delta_Group` feature and no mixed-peak record.

## 7. Phase 3: Create Experiment-Level Splits and RF Inputs

Goal: preserve leakage protection while making RF inputs realistic at
deployment time.

- [x] Capture the RF split object produced by the existing workflow keyed by `base_name`, with train/validation/test assignments.
- [x] Reuse those exact RF assignments for every cutoff row; do not create a second split for sequential test evaluation.
- [x] Assert that every cutoff for an experiment has the same assignment.
- [x] Assert that train, validation, and test experiment IDs are disjoint.
- [x] Run `train.py --model random_forest` with the shared RF data root, exclusions, and split configuration.
- [x] Export RF predictions by `base_name` from the trained RF artifact and the exact RF split object; the sequential test files must match the RF test files one-to-one.
- [x] Use RF predictions from the RF model trained without the test experiments for sequential test inference.
- [x] For sequential model training and validation, generate held-out RF predictions with fold-specific RF models that exclude the predicted experiments; do not use in-sample train predictions.
- [x] Keep RF model artifacts, fold assignments, prediction provenance, and random seeds with the sequential run artifacts.
- [x] Add split and prediction-provenance fingerprints.

Exit criteria:

- No sequential training example contains an RF prediction from an RF trained on its own experiment.
- A test experiment cannot influence RF fitting, preprocessing, feature selection, model selection, or hyperparameter tuning.

## 8. Phase 4: Integrate the Existing ODE Safely

Goal: use the existing secondary PFO model for intermediate fits and forecast
curves without changing the scientific implementation silently.

- [x] Decide whether the sequential package can import the existing ODE API directly or needs a narrow adapter.
- [x] If an adapter is needed, preserve the existing equation, parameter mapping, solver method, tolerances, and timeout behavior unless explicitly approved otherwise.
- [x] Make minimum fit points, fit mode, initial guesses, and prior-fit carry-forward behavior explicit configuration.
- [x] Use `min_points=4` as the initial discovered default because the existing rolling-fit helpers use four points, while keeping it configurable.
- [x] Validate that each intermediate fit uses the expanding prefix of observations for its cutoff.
- [x] Validate the complete-series fit used as the reference target independently from intermediate fits.
- [x] Use the secondary-PFO target order `pfo-sec_k_a_s-1`, `pfo-sec_q_e_au`, `pfo-sec_k_s_s-1`, `pfo-sec_k_p_s-1`, `pfo-sec_q_inf_au`, `pfo-sec_q0_au` when reading and writing fit rows.
- [x] Require a complete finite parameter vector before using an intermediate fit as the current-ODE baseline or passing it directly to the ODE; partial fits remain valid source data but are never silently completed.
- [x] Allow partial-fit values and their masks as sequential-model inputs only when the selected model explicitly supports them; otherwise use the documented RF/previous-valid fallback.
- [x] Enforce the current fitter's candidate bounds: `k_a` and `k_s` in `[0, 0.01]`, `q_e` and `q_inf` in `[0, 2 * q_guess]`, and `k_p_ratio` in `[0, 1]` with `k_p = k_a * k_p_ratio`; no additional owner constraints are currently expected.
- [x] Preserve `q_0 = intensity[0]` and the ODE initial state `[q_0, 0.0]` for every fit and forecast.
- [x] Treat an update as valid only when the optimizer succeeds, the returned parameters are finite, and ODE integration succeeds with finite states.
- [x] Preserve the existing solver behavior for the initial adapter: `solve_ivp`, `RK45`, `rtol=1e-8`, and the current timeout/failure signaling.
- [x] Implement parameter validation before ODE integration.
- [x] Reject or mark non-finite, physically invalid, and numerically unstable predictions.
- [x] Implement fallback behavior: previous valid sequential prediction, then RF prediction, with an explicit fallback reason.
- [x] Return structured fit and solver status rather than hiding failures behind zeros or NaNs.
- [x] Add numerical tests for valid parameters, invalid parameters, solver failure, duplicate times, and a one-observation `q_0` pass-through.

Exit criteria:

- The same parameter vector produces the same curve through the shared ODE path.
- Every failed fit or forecast is visible in logs and evaluation artifacts.
- The adapter has no unrecorded scientific behavior changes.

## 9. Phase 5: Implement Required Baselines

Goal: establish the value of incoming time-series information before selecting
a sequential model.

- [x] Baseline A: use the held-out RF prediction unchanged at every cutoff, with the known first-observation `q_0` pass-through.
- [x] Baseline B: use the current valid ODE fit as the final-parameter prediction.
- [x] Define the fallback for Baseline B when no valid fit exists.
- [x] Baseline C: implement a simple RF/ODE blend or correction with parameters selected on training/validation experiments only.
- [x] Ensure all three baselines use identical experiment splits, cutoffs, target ordering, parameter validation, and curve scoring.
- [x] Save per-example predictions and status for every baseline.
- [x] Report parameter metrics and remaining-curve metrics by progress group.

Exit criteria:

- Baseline outputs are reproducible and auditable.
- The project has a measured early/middle/late reference point for deciding whether a learned sequential model is justified.

## 10. Phase 6: Train the Initial Sequential Model

Goal: select the simplest model that reliably improves held-out validation
performance over the required baselines.

- [x] Start with a correction target relative to RF, or an equally simple supervised formulation justified by the data contract.
- [x] Use only features available at the current cutoff.
- [x] Fit preprocessing on training experiments only.
- [x] Begin with data-efficient models appropriate for approximately 240 experiments.
- [x] Keep all cutoffs from one experiment together during fitting diagnostics and model selection; do not treat them as independent evidence for partitioning.
- [x] Tune only against validation metrics, especially early cutoffs and curve forecasts.
- [x] Record each model alternative, configuration, training data fingerprint, and validation result.
- [x] Prefer the least complex model that is stable across parameters and progress groups.
- [x] Do not add deep sequence models unless simpler models fail for a documented reason.

Initial candidate order:

- [x] RF-only and ODE-only sanity checks.
- [x] Fixed or learned RF/ODE blend.
- [x] Regularized correction model using current-state summaries.
- [ ] Correction model using compact intermediate-fit trajectories.
- [ ] Sequence-aware model only if the preceding candidates leave a validated gap.

Exit criteria:

- [x] One candidate is selected using training/validation evidence only.
- [x] Selection evidence includes early, middle, late, parameter-level, and curve-level behavior.
- [x] The untouched test set remains unopened for model selection.

## 11. Phase 7: Build Sequential Inference

Goal: provide a reproducible cutoff-by-cutoff forecast path for one complete
experiment.

- [ ] Load the saved model and preprocessing artifacts.
- [ ] Process measurements in chronological order without looking ahead.
- [ ] Keep the RF prediction active before the first valid ODE fit.
- [ ] Update only at eligible cutoffs after a valid intermediate ODE fit.
- [ ] Return a complete six-parameter vector in the existing ODE-compatible format.
- [ ] Apply and record physical constraints before curve generation.
- [ ] Forecast from the current cutoff through the known final time.
- [ ] Preserve the last valid prediction or RF prediction when an update or integration fails.
- [ ] Emit one structured record per cutoff containing inputs/provenance, prediction, curve status, fallback status, and errors.
- [ ] Add an end-to-end test using a small fixture with irregular observations and an induced failed fit.

Exit criteria:

- A single inference run produces a complete, ordered trace from first measurement through final time.
- No inference record contains future measurements or future fit values.
- Every eligible cutoff either has a valid update or an explicit fallback reason.

## 12. Phase 8: Evaluate and Report

Goal: establish whether sequential information improves parameter and physical
curve forecasts as the experiment progresses.

- [ ] Evaluate reference-parameter accuracy per target and in an appropriate scale-aware aggregate.
- [ ] Preserve the project's official RMSE and R2 definitions where applicable; report any additional scale-aware metric separately.
- [ ] Evaluate remaining-curve accuracy from current cutoff through known final time against the observed remainder.
- [ ] Report results by observation count, observation fraction, elapsed-time fraction, and time remaining where each is meaningful.
- [ ] Show early, middle, and late progress groups without assuming identical schedules.
- [ ] Measure when the candidate first beats RF-only and current-ODE baselines.
- [ ] Measure whether aggregate accuracy generally improves with more observations without requiring every individual step to improve.
- [ ] Identify unstable parameters, invalid forecasts, failed fits, fallbacks, and excluded experiments.
- [ ] Compare parameter accuracy with curve accuracy rather than assuming they are equivalent.
- [ ] Generate required plots for reference parameters, RF predictions, intermediate fits, sequential predictions, and predicted versus observed remaining curves.
- [ ] Run the final test evaluation only after the candidate and settings are frozen from validation work.
- [ ] Write a report containing data exclusions, constraints, fallback behavior, model alternatives, and the validation-based selection reason.

Exit criteria:

- All required baselines and the selected model are scored on the same held-out experiment assignments and cutoff definitions.
- Results can be traced from a metric to an experiment, cutoff, source data, model artifact, and split fingerprint.
- The final test result is clearly separated from validation-based selection evidence.

## 13. Phase 9: Reproducibility and Handoff

- [ ] Add package-level tests for schema validation, flattening, leakage prevention, split integrity, ODE mapping, fallback behavior, and metric aggregation.
- [ ] Add a documented training command and inference command with explicit configuration paths.
- [ ] Save model artifacts, preprocessing artifacts, split assignments, fingerprints, configuration, and dependency/version metadata.
- [ ] Keep raw data, generated caches, and large model artifacts out of source control unless explicitly requested.
- [ ] Document the exact source revision used for the sibling ODE implementation.
- [ ] Document all discovered answers and remaining decisions in this plan.
- [ ] Mark completed checklist items only after their verification command or artifact is recorded.
- [ ] Update this plan when implementation decisions materially change the proposed architecture.

## 14. Deferred Work

Do not begin these until the initial baselines and candidate sequential model
are complete and validated:

- [ ] Add original RF input features alongside RF predictions.
- [ ] Train a model without the RF prediction.
- [ ] Evaluate a unified or staged static-plus-sequential architecture.
- [ ] Consider uncertainty intervals.
- [ ] Consider updating before the first valid ODE fit.
- [ ] Consider real-time production integration.

Each deferred item requires held-out validation evidence and must not use the
untouched test set for selection.

## 15. Decision Log

| Date | Decision or observation | Evidence | Consequence |
| --- | --- | --- | --- |
| 2026-08-07 | Use `automation/sequential_forecasting/` as the sequential task boundary. | Existing `automation/` contains the RF ETL, models, harness, manifests, and artifacts. | Keep RF package in place; put `spec.md`, `plan.md`, and new sequential code in the subdirectory. |
| 2026-08-07 | Move the current `spec.md` into the sequential package unchanged. | The working-tree version is the sequential forecasting specification supplied for this task. | Future work reads `sequential_forecasting/spec.md`. |
| 2026-08-07 | Do not reuse `load.split_dataset()` for cutoff examples. | It performs record-level random splitting; sequential data has multiple cutoffs per experiment. | Add an experiment-level sequential split adapter. |
| 2026-08-07 | Treat four observations as a discovered default, not a final decision. | Existing ODE code commonly defaults to `min_points=4`. | Confirm the production rule and expose it as configuration. |
| 2026-08-07 | Use `X:\peakFit` with default exclusions `test` and `nn1120-4_pd_ceo2_000`. | Owner clarification. | Surface `--data-root` and repeatable `--exclude-folder` arguments and report effective values. |
| 2026-08-07 | Reuse the RF workflow's exact train/validation/test assignments and evaluate sequential forecasting on the same RF test files. | Owner clarification and `train.py`/`load.py` inspection. | Persist RF split assignments by `base_name`; export RF predictions by `base_name` for sequential inference. |
| 2026-08-07 | Treat `q_0` as known after the first observation and pass it through. | Owner clarification and `fit_secondary_pfo_with_errors()` fixing `q_0` to `intensity[0]`. | Learn only the remaining five parameters while returning the six-parameter ODE vector. |
| 2026-08-07 | Use the existing secondary-PFO fitter's rules as the initial validity contract. | `ir-spectro-node/src/analysis/kinetics_fitting.py`. | Preserve parameter order, bounds, derived `k_p`, solver settings, and explicit failure status. |
| 2026-08-07 | Consume stored rolling `pfo-sec_*` fits initially instead of regenerating them. | Representative included `CarbonylPeakArea.csv` files contain fit columns with blank early rows and populated later rows. | Audit fit coverage and use blank/invalid rows as explicit unavailable-fit states. |
| 2026-08-07 | Preserve missing `pfo-sec_*` values as valid fit-availability information. | Owner clarification and representative CSVs with partial or absent fit columns. | Use masks and status fields; never impute missing fits as zero or silently exclude the experiment. |
| 2026-08-07 | Reuse the RF ETL as the curated sequential dataset boundary. | Owner clarification. | Extend the existing experiment records/split flow additively with time-series fields instead of creating a parallel selection pipeline. |
| 2026-08-07 | Audit 243 included experiments and identify seven files without any complete stored secondary-PFO fit plus 17 files with post-fit coverage gaps. | Read-only audit of paired `CarbonylPeakArea.csv` files under the included folders. | Report unavailable fits explicitly; do not regenerate or exclude silently. |
| 2026-08-07 | Treat repeated `(Peak_Name, Time (s))` rows as unresolved data-contract cases. | All 243 files contain repeated timestamps across `Delta_Group`; repeated rows can have distinct areas and, in one observed case, distinct stored fit vectors. | Obtain an explicit duplicate-resolution decision before building examples or metrics. |
| 2026-08-07 | Use `max(Time (s))` from sorted `monomer_sum` observations as the candidate final-time derivation. | No explicit final-time metadata was found; the candidate agrees with the complete CSV maximum for all 243 audited files. | Confirm this derivation before finalizing the data contract. |
| 2026-08-07 | No canonical remaining-curve metric exists in the inspected repositories. | Existing RMSE helpers score full supplied fit residuals, not post-cutoff observed remainders. | Retain strict post-cutoff RMSE as the initial candidate pending confirmation. |
| 2026-08-07 | Direct sibling ODE reuse requires an explicit import contract. | `ir-spectro-node` is not an `orchestration` dependency, although its implementation matches the required scientific behavior. | Decide between a supported cross-repository import and a narrow behavior-preserving adapter. |
| 2026-08-07 | Keep successful no-adsorption experiments as valid zero-target data. | The seven fitless audited files have `exp_success: true`; the owner confirmed their correct converged value is zero. | Add an explicit successful-no-adsorption status and retain the records rather than treating them as failed ETL cases. |
| 2026-08-07 | Resolve exact duplicate time keys by retaining the last source row and logging the collision. | The existing ODE writer uses `keep="last"`; the owner authorized selecting one row while recording duplicate instances. | Apply the same deterministic rule in the sequential flattening layer and preserve collision provenance. |
| 2026-08-07 | Implement ODE behavior locally rather than importing from the sibling repository. | Owner instruction; cross-repository imports are not desired. | Add a local behavior-preserving ODE module with tests for equations, parameter mapping, solver behavior, and failures. |
| 2026-08-07 | Generate a full trajectory at each cutoff and score only the strict future suffix. | Owner clarification: known observations must remain available and must not be discarded. | Keep the complete forecast trace, use all future observation points for the remaining-curve metric, and use progress percentages only for reporting. |
| 2026-08-07 | Merge timestamps within `1e-3` seconds and log every collision. | Owner clarification and observed floating-point near-duplicates. | Use a configurable tolerance in the sequential flattening layer and retain the last source row in each collision cluster. |
| 2026-08-09 | Treat repeated timestamp rows with different areas as valid measurement variance. | Owner clarification: the variation is expected and represents measurement uncertainty. | Keep the current `1e-3`/`keep="last"` behavior for the initial baseline, preserve raw rows and collision provenance, and defer an all-data representation until baseline results are available. |
| 2026-08-09 | Select RF-only as the active initial sequential candidate. | Ridge correction candidates and RF/ODE baselines were evaluated on 155 training and 39 validation experiments; RF-only scored `0.4996` versus `0.8296` for the best Ridge candidate, with no test use. | Begin Phase 7 inference with RF-only; retain the Ridge implementation and manifest as selection evidence, not as an active learned model. |

## 16. Resolved Decisions and Deferred Discovery

The owner clarifications and Phases 1–6 evidence resolve the initial data-root,
exclusion, split, `q_0`, duplicate, final-time, curve-scoring, and primary
ODE-source questions. The following decisions govern Phase 7 and later work:

1. The coverage audit found seven files with no complete stored fit and 17 with gaps after the first valid fit. Successful fitless files remain explicit zero-target cases, and rolling-fit gaps are represented with status and availability fields.
2. Exact and near-duplicate timestamp clusters are expected measurement variance. The initial implementation uses `keep="last"` with collision logging and a default `1e-3` second tolerance; raw rows and collision provenance remain available for a later all-data evaluation.
3. Final time is the maximum `Time (s)` with all six finite parameters, with maximum flattened `monomer_sum` time as the successful-no-adsorption fallback.
4. Remaining-curve RMSE uses the full generated trajectory but scores only observed points strictly after each cutoff.
5. The ODE is implemented locally with matching behavior; no cross-repository import is used.
6. No additional owner-supplied physical constraints are currently expected; retain the existing fitter bounds and `k_p = k_a * k_p_ratio` relationship unless later evidence requires reevaluation.

Any change to these decisions requires new validation evidence and must not
silently alter the protected RF workflow or expose future information.

## 17. Follow-up Note: Repeated Observation Times

The repeated `Time (s)` values across `Delta_Group` appear to be an expected
property of the source data rather than an accidental corruption. The Phase 1
audit found repeated timestamps in all 243 included experiments, with 5,281
timestamp clusters after applying the configured `1e-3` second tolerance.
Several clusters contain different `Cumulative_Peak_Area` values, and at least
one observed cluster contains different stored intermediate-fit values.

The current sequential contract uses the existing writer-compatible
`keep="last"` rule and logs every collision. The owner confirmed that differing
areas at repeated timestamps are expected measurement variance or uncertainty,
not invalid rows. This rule is retained as the initial baseline so the first
system remains comparable to current behavior; the raw rows and collision
provenance are not discarded and can support a later representation that
includes all measurements. Any such change must be evaluated for experiment
weighting, target duplication, cutoff definition, and leakage consequences.

The repeated-time decision no longer blocks the initial baseline and was used
through Phase 6. The current flattening policy remains the validated initial
choice; evaluate all-measurement alternatives only after the required held-out
model comparisons are complete.

## 18. Handoff Notes

Phase 6 is complete after validation of the initial sequential-model candidate.
The next agent should begin Phase 7 sequential inference by reviewing the
responsibility-based structure in Section 3e, the Phase 2–6 evidence, and the
repeated-time note above. Do not reopen model selection before implementing
inference.

The current structure and duplicate policy are working decisions, not fixed
architecture. Review package boundaries, imports, artifact locations, and test
organization after each future successful phase. Preserve the protected RF ETL
and do not treat the current `keep="last"` repeated-time choice as a final
scientific conclusion without further evidence.
