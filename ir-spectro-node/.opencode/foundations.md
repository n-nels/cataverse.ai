# Project Foundations & Core Rules

This document contains foundational principles and permanent rules that must be followed throughout the project's lifecycle. These rules override any general instructions.

## 1. Parity-Safe Control Flow

- **Rule:** Do not introduce new early-return branches that alter legacy control flow without explicit parity confirmation.
- **Reason:** New exit points (for example, returning when a data check fails but legacy would continue) can silently skip output generation (e.g., missing `*_Carbonyl` files). Any added return paths must be explicitly reviewed for parity.

## 2. Prototype Scope Guardrails

- Prototype analysis scripts should operate on a single, explicitly named dataset folder until behavior is validated. Expand to additional folders only after the prototype run is reviewed.


## 3. Peak Name Formatting

- Peak name strings derived from numeric peak centers must match the formatting used in `Peak_Name` columns. Avoid truncation that can drop decimal precision unless the upstream data explicitly uses integer peak labels.

## 4. Delta-Group Aggregation in Visualizations

- Visualization scripts that plot cumulative peak areas should either (a) aggregate across `Delta_Group` when it is not a focus, or (b) clearly separate/group `Delta_Group` traces if they are plotted together.

## 5. Script Execution Context

- Modules are typically executed directly from VSCode (interactive runs) instead of CLI. Prefer editable constants at the top of sandbox scripts over strict CLI-only interfaces.

## 6. Sandbox Output Safety

- Write sandbox script outputs to a `_test` subfolder before overwriting any source data.

## 8. Peak Fitting Grouping Behavior

- When fitting PFO kinetics or classifying trajectories for any unique `Peak_Name` values (including but not limited to `monomer_sum`, `cluster_sum`), group only by `Peak_Name` to aggregate across all Delta_Group values.

## 9. Secondary PFO Model Constraints (Current Iteration)

- **q0 fixed to first data point:** `q_0` is not fitted; it is fixed to the first observed intensity value.
- **k_a > k_p constraint:** enforce via ratio parameterization: `k_p = k_a * k_p_ratio`, with `k_p_ratio ∈ (1e-6, 0.999999)`.
- **q_inf not constrained relative to q_e:** `q_inf` is fit directly (no `q_inf < q_e` constraint).
- **Non-negative p(t) in ODE:** clamp inside RHS: `p = max(p, 0.0)`.
- **Secondary dynamics:** `dp/dt = k_p * (q - q_inf - p)`.
- **Bounds:** `k_a ≥ 0`, `q_e ≥ 0`, `k_s ≥ 0`; `q_inf ≥ 0`.
- **Upper bounds:** `k_a_upper` and `k_s_upper` derived from time span; `q_e_upper` derived from intensity; `q_inf` capped at `2 * q_e_upper`.
- **Solver:** `solve_ivp(method="RK45", rtol=1e-8)` with 0.1s timeout and unique-time interpolation for duplicates.
- **Objective:** reject non-finite values (no `p < 0` rejection).
- **Optimizer:** single-start `L-BFGS-B` (multistart disabled).
