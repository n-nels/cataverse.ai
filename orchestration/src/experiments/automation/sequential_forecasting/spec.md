# Sequential Forecasting of Final CO Adsorption Kinetic Parameters

## 1. Purpose

Build a sequential forecasting system that predicts, as early as possible, the final kinetic parameters for a CO adsorption experiment.

The final parameters are defined as the parameters obtained by fitting the existing ODE kinetic model to the complete experimental time series. These are referred to as the **reference parameters** or **reference target**.

The system must update its prediction as new measurements become available. The updated parameter prediction will be used with the existing ODE model and the known final experiment time to forecast the remainder of the adsorption curve.

This document intentionally defines the goal and important safeguards without prescribing a specific machine-learning architecture. The implementation agent should select methods appropriate for the existing data, codebase, and dataset size.

---

## 2. Conceptual workflow

For each experiment:

1. Before any time-series measurements are available, the existing Random Forest predicts the final reference kinetic parameters.
2. Raw adsorption measurements arrive one at a time.
3. After the minimum required number of observations is available, the existing ODE fitting process fits the kinetic model using all measurements collected so far.
4. This produces an intermediate kinetic-parameter estimate.
5. After each new observation and ODE fit, the sequential forecasting model updates its prediction of the final reference parameters.
6. The updated final-parameter prediction is inserted into the ODE and evaluated through the known final time to forecast the remaining adsorption curve.
7. The process repeats until the experiment is complete.

The primary objective is to produce an accurate forecast of the final parameters and remaining adsorption curve as early in the experiment as possible.

---

## 3. Terminology

### Reference parameters or reference target

The kinetic parameters obtained by fitting the ODE to the complete experimental time series.

These values are fitted estimates rather than independently measured physical ground truth. They are nevertheless the supervised-learning target for this project.

### RF prediction

The existing Random Forest’s pre-measurement prediction of the reference parameters.

### Intermediate ODE parameters

The parameters produced by fitting the ODE to all observations available at a particular cutoff time.

These parameters change as additional measurements become available. Their trajectory generally converges toward the reference parameters.

### Sequential prediction

The sequential model’s current prediction of the reference parameters, based only on information available at the current cutoff time.

### Cutoff or update point

A point during an experiment at which only the observations collected up to that time are made available to the forecasting system.

---

## 4a. Existing data and assumptions

The repository contains approximately 240 complete experiments.

Each experiment includes, or can be linked to:

- The raw time-series measurements.
- The corresponding measurement times.
- Intermediate ODE fits performed using all data available at each valid cutoff.
- Six fitted kinetic parameters.
- The complete-series ODE fit used as the reference target.
- The existing RF prediction of the reference target, or the information needed to produce it.
- The known final time of the experiment.
- Potential additional data that may be incorporated later.

One of the six parameters represents the initial adsorption amount and is known from the first measurement. The agent should inspect the existing implementation and determine whether this parameter should be:

- passed through as a known value,
- included as a model input,
- excluded from the prediction target,
- or retained in the output vector for compatibility.

In practice, the learned prediction problem may therefore contain five unknown parameters while the system continues to return a complete six-parameter vector.

Experiments generally use similar measurement schedules, but exceptions exist. The implementation must not assume that every experiment has an identical number of observations or exactly identical measurement times unless the data confirm that assumption.

The ODE is not fitted during the first few observations. The minimum is believed to be between three and five observations, but the exact rule must be identified from the existing code or confirmed later. It must be configurable rather than embedded as an undocumented assumption.

Add the following section to `spec.md` after **Existing data and assumptions**:

---

## 4b. Data scope and flattening requirements

### Peak selection

This project is concerned only with kinetic parameters associated with:

```text
Peak_Name == "monomer_sum"
```

The agent must filter the relevant data to `monomer_sum` before constructing training examples, fitting the sequential model, or calculating evaluation metrics.

Other `Peak_Name` values are outside the scope of the initial implementation and must not be mixed into the model inputs, targets, or reported results.

### `Delta_Group` handling

`Delta_Group` represents artificial data inflation rather than a meaningful experimental grouping variable.

The data must be **flattened across `Delta_Group`**.

Specifically:

- Do not train separate models by `Delta_Group`.
- Do not aggregate or summarize the data using `groupby("Delta_Group")`.
- Do not use `Delta_Group` to define experiments, sequences, targets, train/validation/test partitions, or evaluation groups.
- Do not treat `Delta_Group` as a categorical model feature unless explicitly requested later.
- Remove the `Delta_Group` hierarchy or index level where necessary so the relevant records can be processed in the ordinary flattened experiment/time-series structure.

Flattening must not break experiment-level leakage protection. If multiple artificially inflated records originate from the same underlying experiment, all such records must remain in the same train, validation, or test partition.

The agent should inspect how `Delta_Group` is represented in the existing files and code, document the flattening operation used, and verify that it does not accidentally duplicate targets, mix experiments across partitions, or give some experiments unintended weight during training or evaluation.

---

## 5. Prediction objective

At every valid update point, predict the same target:

> The kinetic-parameter vector obtained from fitting the ODE to the complete time series for that experiment.

The intermediate fitted parameters are model inputs and evidence about the developing experiment. They are not the ultimate target.

The system should learn how the available measurements and intermediate parameter trajectory alter or correct the RF’s pre-measurement prediction.

The forecast horizon is the known final time of the experiment.

---

## 6. Primary model inputs

The first implementation should use information available at the current cutoff, including:

- The RF prediction of the final reference parameters.
- Raw observations collected up to the current cutoff.
- Measurement times associated with those observations.
- The current and/or historical intermediate ODE parameter fits available up to the cutoff.
- Relevant indicators needed to represent unavailable, failed, or invalid fits.
- Any essential supporting variables already used by the existing ODE workflow.

Some additional data may eventually be included. The implementation should be reasonably extensible, but those additional inputs are not required for the initial version.

The original input features used by the RF are not part of the primary sequential model initially. Possible use of those features is described under deferred investigations.

The exact representation of variable-length measurement and parameter histories is an implementation decision for the agent.

---

## 7. Model output

At each valid update point, the model must return:

- An updated prediction of the final reference kinetic parameters.
- A complete parameter vector in the format expected by the existing ODE implementation.

The resulting parameter vector must be usable by the ODE to generate the predicted adsorption curve through the known final time.

Uncertainty intervals are not required in the initial version.

---

## 8. Behavior before the first valid ODE fit

The ODE cannot produce reliable intermediate parameters until the required minimum number of observations has been collected.

For the initial implementation:

- The RF prediction should remain the active final-parameter forecast before the first valid intermediate ODE fit.
- Sequential model updates should begin once the first valid ODE fit is available.
- The exact eligibility rule should be obtained from the existing fitting workflow and made configurable.

Updating directly from the earliest raw observations, before an ODE fit is available, may be considered later but is not required initially.

---

## 9. Modeling strategy

Do not assume that a deep-learning time-series model is required.

With approximately 240 complete experiments, the initial work should favor data-efficient, understandable approaches. The agent should begin with simple baselines and increase complexity only when validation results justify it.

A promising framing is to predict a correction to the RF estimate rather than relearning the complete parameter-prediction problem from scratch. This is a candidate approach, not a mandatory implementation.

Candidate model families may include:

- A simple blend between the RF prediction and current ODE fit.
- A supervised correction model using current-state and trajectory features.
- A model using summaries of the observations and fitted-parameter history.
- A sequence-aware model if the amount and structure of the data support it.

The final model choice should be based on held-out validation performance, particularly at early cutoff times, rather than assumed in advance.

The simplest model that delivers reliable improvement should be preferred.

---

## 10. Training-example construction

Each complete experiment can produce multiple training examples, one for each valid cutoff.

For a cutoff at time \(t\):

- Inputs must contain only information available at or before \(t\).
- The target is the reference parameter vector from the complete-series fit.
- No later raw measurements, intermediate fits, or future-derived features may be included.
- Any normalization, imputation, dimensionality reduction, or feature construction that learns from data must be fitted using training experiments only.

The agent must audit the existing data-generation and ODE-fitting code for future-information leakage.

Multiple cutoffs from the same experiment are correlated and must never be treated as independent when splitting the dataset.

---

## 11. Dataset splitting and leakage prevention

All splitting must occur by complete experiment.

Earlier and later cutoffs from the same experiment must always remain in the same partition.

The sequential model should use the same train, validation, and test experiment assignments as the existing RF workflow where practical.

Required safeguards:

- Test experiments must not influence RF training.
- Test experiments must not influence sequential-model training.
- Test experiments must not be used for model selection, feature selection, preprocessing decisions, or hyperparameter tuning.
- Validation experiments may be used for model selection but not final fitting decisions based on test results.
- All cutoffs from one experiment must remain together.

### RF predictions used for sequential training

The sequential model should be trained on RF predictions that realistically resemble predictions for unseen experiments.

If the RF prediction supplied for a training experiment was generated by an RF already fitted on that experiment, it may be unrealistically favorable and introduce leakage or a train/deployment mismatch.

The agent should therefore use out-of-fold or otherwise held-out RF predictions for sequential-model training experiments. Validation and test RF predictions must come from RF models that were not trained on those experiments.

The agent should preserve the existing split structure while implementing this requirement in a way compatible with the current repository.

---

## 12. Parameter restrictions and physical validity

The kinetic parameters have known restrictions and potentially known relationships.

The project owner will surface these restrictions to the agent. The agent must identify and document:

- Valid ranges.
- Positivity requirements.
- Relationships among parameters.
- Invalid combinations.
- Any numerical stability requirements imposed by the ODE solver.

Predicted parameters must satisfy the applicable constraints before they are passed to the ODE.

The method used to enforce constraints should be chosen based on the existing model and fitting code. Invalid predictions must not be silently accepted.

The system should also detect and report:

- ODE fitting failures.
- ODE integration failures.
- Non-finite parameter values.
- Physically invalid forecasts.
- Cutoffs for which no valid update can be produced.

A reasonable fallback should preserve the previous valid prediction or the RF prediction rather than terminate the entire forecasting process.

---

## 13. Required baselines

The sequential model must be evaluated against at least the following:

### Baseline A: RF only

Use the original RF prediction at every cutoff without updating it.

This measures whether incoming time-series information adds value.

### Baseline B: Current ODE fit

Treat the intermediate ODE parameters at the current cutoff as the prediction of the final parameters.

This measures whether machine learning improves upon the existing natural convergence of the ODE fit.

### Baseline C: Simple combination

Use a simple blend or correction between the RF prediction and current ODE fit.

The agent should choose a straightforward implementation appropriate to the data. This determines whether a more complex sequential model is warranted.

### Candidate sequential model

Compare the selected sequential approach against all baselines using the same experiment partitions and cutoff definitions.

---

## 14. Evaluation

Evaluation must measure how performance changes as more of the experiment becomes available.

Reporting only one aggregate score or final-time performance is insufficient.

### Parameter accuracy

Evaluate the predicted final parameters against the complete-series reference parameters.

Use metrics compatible with the existing project, such as RMSE and \(R^2\), while accounting for differences in parameter scales. Report results per parameter as well as an appropriately summarized overall result.

The agent should determine whether transformed, normalized, relative, or scale-aware metrics are necessary for meaningful comparison.

### Adsorption-curve forecast accuracy

Insert the predicted parameters into the ODE and forecast from the current cutoff through the known final time.

Compare the forecasted remaining curve against the observed remainder of the experiment.

This is an essential evaluation because small parameter errors may not translate directly into meaningful curve errors, and vice versa.

### Performance over experiment progress

Report performance according to how much of the experiment has been observed. The exact grouping should reflect the available schedules but should make early, middle, and late performance visible.

Useful views may include:

- Number of observations collected.
- Fraction of observations collected.
- Fraction of experiment duration elapsed.
- Time remaining until the known final time.

Because schedules contain some exceptions, the agent should avoid relying on a single progress definition without checking that it is meaningful.

### Progressive improvement

The expected overall behavior is that predictions become more accurate as more information becomes available.

This should be evaluated across the dataset. It should not initially be imposed as a strict requirement that every individual prediction improve at every single step, because noise and fitting instability may cause occasional regressions.

The evaluation should identify:

- How early the sequential model beats the RF-only baseline.
- How early it beats the current ODE fit.
- Whether accuracy generally improves with additional measurements.
- Whether any parameters consistently become unstable.
- Whether improved parameter accuracy also improves curve forecasts.

### Final test usage

The test partition should be evaluated only after the modeling approach and settings have been selected using training and validation experiments.

---

## 15. Success criteria

The initial system is successful if it:

1. Produces an updated prediction of the final reference parameters at each eligible cutoff.
2. Uses no information from after the current cutoff.
3. Preserves complete-experiment train, validation, and test separation.
4. Uses realistic held-out RF predictions when training the sequential model.
5. Produces physically valid parameters accepted by the existing ODE workflow.
6. Generates a forecast of the remaining adsorption curve through the known final time.
7. Demonstrates when and by how much it improves over the required baselines.
8. Provides performance results as a function of experiment progress.
9. Handles differing schedules, unavailable early fits, and fitting failures without silently corrupting results.
10. Integrates with the existing repository without unnecessarily replacing working RF or ODE functionality.

No fixed numerical accuracy threshold is defined at this stage. Initial work should establish reliable baselines and determine the achievable improvement using the available data.

---

## 16. Outputs and deliverables

The implementation should provide:

- A reproducible training pipeline.
- A reproducible sequential inference pipeline.
- Saved model artifacts and required preprocessing artifacts.
- A clear mapping between experiments, cutoffs, inputs, predictions, and targets.
- Evaluation results for all required baselines and the selected model.
- Parameter-level metrics over experiment progress.
- Remaining-curve forecast metrics over experiment progress.
- Example plots showing:
  - reference parameters,
  - RF predictions,
  - intermediate ODE fits,
  - sequential final-parameter predictions,
  - and predicted versus observed adsorption curves.
- Documentation of data exclusions, failed fits, fallback behavior, and parameter constraints.
- A short record of model alternatives tested and the validation-based reason for the selected approach.

The agent should reuse existing project conventions and code wherever practical.

---

## 17. Deferred investigation: original RF inputs

The primary implementation should use the RF prediction as the static, pre-measurement estimate and should not initially include the RF’s original input features.

After the primary system and baselines are established, the following optional variants may be investigated:

### Variant 1: RF prediction plus original RF inputs

Provide both the RF output and its original static input features to the sequential model.

This may recover useful information that was compressed or lost when the RF reduced its inputs to the predicted parameter vector.

### Variant 2: Original RF inputs without the RF prediction

Train the sequential model using the original static features and evolving time-series information, allowing it to learn both the initial prediction and sequential update.

### Variant 3: Unified or staged architecture

Use separate components for static pre-measurement information and evolving time-series information, then combine them to predict the reference parameters.

These are secondary experiments rather than initial requirements. With only about 240 experiments, additional input complexity may increase overfitting. A variant should be adopted only if it produces reliable improvement on held-out validation experiments and performs well across early, middle, and late cutoffs.

The untouched test set must not be used to choose among these variants.

---

## 18. Explicitly out of scope for the initial version

The following are not required initially:

- Prediction intervals or other uncertainty estimates.
- Replacing the existing ODE kinetic model.
- Replacing the existing RF before establishing the sequential-update baseline.
- Updating before the first valid ODE fit.
- Deep-learning sequence models without validation evidence that they are needed.
- Real-time production deployment infrastructure.
- Incorporation of every potentially available auxiliary variable.
- Independent physical validation of the complete-series fitted parameters.

The implementation should remain extensible so these capabilities can be considered later.

---

## 19. Items requiring confirmation or discovery

The agent should inspect the repository and request clarification where necessary for:

- The exact minimum number of observations required before ODE fitting begins.
- The definitions and ordering of all six kinetic parameters.
- Treatment of the known initial adsorption parameter.
- The physical restrictions and valid ranges for every parameter.
- The exact raw-observation schema.
- The handling of irregular measurement schedules.
- Existing ODE fit-failure rules.
- The current RF train, validation, and test assignments.
- Whether existing stored RF predictions are genuinely held out for each experiment.
- The additional data that may be incorporated in a later version.
- The exact curve-generation and scoring conventions already used by the project.
- Confirmation that all modeling tables have been filtered to `Peak_Name == "monomer_sum"`.
- The current role of `Delta_Group` in indexes, joins, feature construction, and existing data splits.
- Verification that flattening `Delta_Group` does not cause duplicated records or train/test leakage.
- Verification that artificial inflation does not unintentionally distort experiment-level training weights or evaluation metrics.

These details should be documented once discovered rather than silently inferred.

---

## 20. Protected Scope

The **ETL pipeline** is the protected boundary. The agent must not modify the
following files or the behavior they implement unless the user explicitly
authorizes it in a task:

```text
extract.py        — raw data extraction
transform.py      — feature engineering, target extraction
load.py           — dataset assembly, feature reduction, split logic
```

The following behaviors are also protected (some live in files the agent may
otherwise edit; the agent must not change the behavior even if it touches the
file for other reasons):

- Dataset extraction and loading behavior.
- Curated feature definitions.
- Feature-engineering logic.
- Feature-reduction logic.
- Target definitions.
- Target transforms (Box-Cox lambdas, log transforms).
- Canonical train/validation/test split behavior (seed 42, split ratios).
- Evaluation metric definitions (RMSE, R², aggregation).
- Existing completed experiment artifacts.
- Default model selection and production configuration.

The agent **may** modify the following for optimization purposes without
explicit per-change approval:

- `model.py` — extending `ModelConfig` with new fields, adding new model
  registrations, adjusting model-internal defaults (but NOT target transforms,
  evaluation metrics, or split logic).
- `models/*.py` — adding new model implementations, extending existing trainers
  with new hyperparameters, adjusting model-internal behavior.
- `pipeline.py` — adjusting the reusable training pipeline for new model
  interfaces.
- `harness/*.py` — adjusting the harness itself.
- `manifests/*.yaml` — creating and editing experiment manifests.
- New files within the `automation/` package.

The agent must not attempt to improve performance by changing the dataset,
features, target values, split boundaries, or official evaluation metrics.

