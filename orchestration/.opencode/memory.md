---
name: memory
description: Capture meeting minutes
---

## Sequential Forecasting Handoff

- Phase 2 is complete and verified. Phase 3 has not started; do not begin it
  until the owner resumes or requests the next phase.
- Phase 0 and Phase 1 are complete and validated against 243 experiments from
  `X:\peakFit`, excluding `test` and `nn1120-4_pd_ceo2_000`.
- RF split is 155 train, 39 validation, 49 test. RF predictions include 194
  out-of-fold train/validation rows and 49 held-out test rows. Dataset and split
  fingerprints match `rf_v2_0001`.
- Successful experiments with no adsorption remain valid zero-target records.
  `q_0` is passed through from the first flattened observation.
- Repeated timestamps across `Delta_Group` are expected source behavior; the
  different areas represent measurement variance or uncertainty. The initial
  implementation should preserve the current configurable 1 ms merge
  tolerance with `keep="last"` and collision logging. The raw rows and
  collision provenance remain available for a later evaluation that includes
  all duplicate measurements, if the baseline shows that doing so is useful.
- Final time is the latest row with all six finite parameters; successful
  no-adsorption records use the maximum flattened monomer time. Remaining-curve
  RMSE uses observed points strictly after each cutoff while retaining the known
  prefix in the full trajectory.
- No cross-repository ODE import is used. The local secondary-PFO implementation
  mirrors the sibling ODE equations and solver behavior.
- Current package organization is responsibility-based: `data/`, `models/`,
  `rf/`, plus `config.py` and `cli.py`. Generated artifacts belong under
  `automation/artifacts/sequential_forecasting/` and are ignored by Git.
- Phase 2 adds the RF-to-sequential adapter and `build-examples` command. A
  real-data smoke check produced 12,013 prefix examples from 243 experiments,
  preserving the 155/39/49 assignments and held-out RF provenance.
- Focused Phase 2 tests pass: 13 tests. Review package boundaries and update
  the structure after every successful future phase.
