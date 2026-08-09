# Sequential Forecasting Data Contract

Status: initial contract validated against the Phase 0 experiment selection.

## Scope and identity

- The source boundary is the existing RF-selected experiment population.
- The canonical experiment ID is `ExperimentRecord.base_name`, paired with its
  `*_CarbonylPeakArea.csv` path.
- Only rows with `Peak_Name == "monomer_sum"` enter sequential examples or
  metrics.
- `Delta_Group` is provenance only. It is never an experiment ID, feature,
  target, split key, or evaluation group.
- All cutoffs from one experiment inherit one RF partition.

## Observation normalization

The observation table contains one row per flattened experiment/time cutoff:

| Field | Meaning | Contract |
| --- | --- | --- |
| `experiment_id` | Canonical experiment ID | `base_name` |
| `cutoff_id` | Unique example ID | `{experiment_id}:{index:04d}` |
| `Peak_Name` | Selected peak | Always `monomer_sum` |
| `Time (s)` | Observation/cutoff time | Seconds; ascending |
| `Cumulative_Peak_Area` | Observed adsorption area | Finite numeric value |
| `observation_count` | Number of observations in the prefix | Positive integer |
| `q_0` | Known initial adsorption amount | First flattened observation area |
| `pfo-sec_*` | Stored intermediate fit values | Value plus availability mask |
| `pfo-sec_r^2`, `pfo-sec_rmse` | Stored fit diagnostics | Optional finite diagnostics |

Rows are sorted by `Time (s)`. Timestamps within `1e-3` seconds are one
observation cluster. The last source row in each cluster is retained to match
the existing kinetics writer. Each collision records its source rows, files,
`Delta_Group` values, time range, retained row, and count.

Near-equal timestamps are not averaged. This avoids creating a synthetic
measurement and prevents artificial `Delta_Group` copies from receiving extra
training weight.

## Reference target and final time

The reference target is the six-value secondary-PFO vector in this order:

```text
pfo-sec_k_a_s-1
pfo-sec_q_e_au
pfo-sec_k_s_s-1
pfo-sec_k_p_s-1
pfo-sec_q_inf_au
pfo-sec_q0_au
```

For an experiment with complete stored parameters, the reference row is the
latest flattened row containing all six finite parameters. Its time is the
known final time. `q_0` is replaced by the first flattened observation and is
not learned.

For a successful experiment with no complete fit and no adsorption, the record
is retained with status `successful_no_adsorption`, an all-zero reference
target, and final time equal to the maximum flattened `monomer_sum` time.
Unsuccessful experiments remain excluded by the existing ETL.

## Cutoffs and leakage rules

Every flattened observation through the final time is a valid cutoff. The
example at cutoff `t` contains only observations with time `<= t`. It may use
the current stored fit row and diagnostics, but never later observations or
later fit values.

The example carries the complete-series reference target separately from its
inputs. At inference, the full ODE trajectory is generated for the current
parameter prediction; known prefix observations are retained, and remaining
curve RMSE is scored only at observed points with time strictly greater than
the cutoff.

The Phase 2 serialized example also records the RF prediction and its
held-out/out-of-fold provenance, the RF assignment, paired source paths,
reference-target provenance, observation and elapsed-time progress, time
remaining, and per-parameter fit-availability coverage. The current fit row is
included as a prefix-only input. Historical fit sequences are deferred until a
baseline feature representation is selected.

## Intermediate-fit availability

Each parameter has both a value and a boolean availability mask. Missingness is
not converted to zero. The current status is one of:

```text
fit_not_yet_eligible
fit_missing_for_cutoff
fit_partially_populated
fit_missing_for_whole_experiment
fit_failed
fit_valid
successful_no_adsorption
```

The initial discovered minimum is four unique observations, exposed as
configuration rather than a hidden constant. Stored fit gaps are reported and
are not silently regenerated or used as valid fits.

## Parameter contract

`k_a`, `k_s`, and `k_p` use inverse seconds. `q_e`, `q_inf`, and `q_0` use
adsorption-area units (`au`). The initial secondary-PFO validity bounds are:

- `k_a` and `k_s` in `[0, 0.01]` s^-1.
- `q_e` and `q_inf` in `[0, 2 * q_guess]` au.
- `k_p_ratio` in `[0, 1]`, with `k_p = k_a * k_p_ratio`.
- `q_0` is the known first observation and is passed through.

Predictions must be finite before ODE integration. ODE failures, invalid
parameters, and fallback reasons must remain visible in status artifacts.

## Validation requirements

The Phase 1 validation report must demonstrate, on real records, that:

- every example has one experiment ID and one cutoff ID;
- cutoff observations are sorted and contain no future row;
- reference targets come only from complete-series fits or the explicit
  successful-no-adsorption rule;
- `q_0` equals the first flattened observation;
- no non-`monomer_sum` row or `Delta_Group` feature enters an example;
- duplicate collisions, fit statuses, exclusions, and cutoff counts are
  reported; and
- the RF train/validation/test partition is experiment-disjoint.
