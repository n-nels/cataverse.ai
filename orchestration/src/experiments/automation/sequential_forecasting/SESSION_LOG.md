# Sequential Forecasting — Session Log

A running, high-level log of the *reasoning* behind each work session on
`sequential_forecasting/` — decisions made, why, what evidence drove them,
and what's still open. This is not a changelog of code (git history and
`plan.md` already cover that); it's the "why," the dead ends, and the
context a future session would otherwise have to re-derive from scratch.

New entries go at the top. Keep each entry to what genuinely isn't
recoverable by reading the code or `plan.md`'s decision log.

---

## 2026-09-19 (later) — Ran the proposed three steps. The ceiling is flat and low, the scoreboard is fixed, and the raw-measurement model is the best parameter predictor in the project and the worst curve forecaster — which identifies the real problem as the training objective, not the architecture

**Starting point.** The user said "let's try the new approach," meaning the
three steps proposed at the end of the previous entry. All three were done in
order. Working tree changes are listed at the end.

### Step 1 — the ceiling is flat, low, and says early is wide open

Each validation experiment's own reference parameters were run through the ODE
at every cutoff and scored on the remaining curve. Result: **0.033 early,
0.025 middle, 0.026 late** across 2,004 scored cutoffs from 39 experiments.
Per-cutoff median 0.027, worst single cutoff 0.12. (The 39 unscored cutoffs
are each experiment's last one, which has no remainder.)

Two things follow, and they reframe the project:

1. **The ODE is not the limitation.** Given the right parameters it
   reproduces these curves to roughly a fortieth of the signal range, and it
   does so just as well from the first cutoff as from the last.
2. **The early/late gradient every candidate shows is entirely prediction
   error.** The best early number any method has ever produced is 0.279
   (RF-only) against a ceiling of 0.033 — a factor of eight. Late, the ODE fit
   reaches 0.064 against a ceiling of 0.026, a factor of 2.5. So late is
   *closer* to solved but not solved, and early has enormous headroom. The
   previous entry's guess that a poor early ceiling might mean "no
   architecture will rescue early" is **ruled out**.

Caveat to carry forward: the reference fit is itself chosen to minimize error
over the whole series, so this is the best achievable by anything aiming at
the reference parameters, not a hard lower bound on remainder error.

### Step 2 — the scoreboard now measures the objective, and both evaluators share one aggregation

`selection_score` was `pooled parameter RMSE + early curve RMSE`. It is now
the **equal-weighted mean of the early, middle, and late remaining-curve
RMSE**. Equal weighting was chosen because spec.md §14 asks for early, middle
and late to be visible, and because no evidence yet justifies favouring one
stage; the choice is now recorded in the manifest instead of being an
unexamined default. Every candidate record also carries per-target parameter
RMSE and a scale-normalized average (per-target error divided by the training
reference spread), so the rate constants are no longer invisible.

The learned-candidate and baseline evaluators previously each had their own
copy of the aggregation — the mechanism behind the earlier validation/test
mismatch. They now call one shared function, so that class of bug cannot
recur.

Validation standings under the new score (39 experiments, 2,043 cutoffs, all
candidates scored on all cutoffs with RF fallback):

| Candidate | Score | Early | Middle | Late | Norm. param |
|---|---:|---:|---:|---:|---:|
| **current_ode** | **0.2096** | 0.3956 | 0.1694 | **0.0637** | 2.798 |
| gated_blend_4 | 0.2402 | 0.3447 | 0.2418 | 0.1341 | 1.137 |
| rf_ode_blend | 0.2704 | 0.3369 | 0.2568 | 0.2176 | 1.888 |
| rf_only | 0.2957 | **0.2787** | 0.2990 | 0.3093 | 1.250 |
| raw_series_mlp_gated | 0.3834 | 0.4433 | 0.3808 | 0.3259 | **1.060** |
| trajectory_10 | 0.4778 | 0.3519 | 0.5626 | 0.5190 | 1.223 |
| ridge (best alpha) | 0.5224 | 0.5032 | 0.5461 | 0.5180 | 1.198 |

This confirms Finding 3 of the previous entry: the plain ODE fit wins, and no
learned candidate beats it. Written to a **new** artifact directory
(`sequential_model_curve_score/`) so the deployed `rf_only` artifacts and the
frozen test report remain accurate. **The test set was not reopened.**

### Step 3 — the raw-measurement model, and the result that matters

Built `raw_series_model.py`: one supervised regressor that reads the
measurements collected so far — resampled onto a fixed log-spaced grid of
absolute seconds with an availability mask, plus shape descriptors, the RF
prediction and the current fit — and outputs the final parameter vector end to
end. No blending, no switching rule. Two deliberate design choices, both
responses to earlier failures recorded in this log:

- **Constraints by construction.** `k_a` is predicted in log space, `k_p` as a
  bounded fraction of `k_a` (the fitter's own parameterization), capacities as
  non-negative values. Nothing can be driven onto a degenerate boundary by
  clipping, which is exactly what killed the trajectory model.
- **Scale-standardized targets**, so the three rate constants carry equal
  weight with the two capacities during fitting.

`observation_fraction` was deliberately excluded because its denominator is
the experiment's total observation count, which is not known during an
experiment. **Note for a future session: that field is still an input to the
older Ridge candidate, so that candidate has a real, if small, leak.**

**It is the best parameter predictor in the project.** Average scale-normalized
error 1.04 (MLP) and 1.05 (gradient boosting), against RF-only 1.25,
predicting the training mean 1.31, and the current ODE fit 2.80. Restricted to
the four identifiable parameters (excluding `q_inf`, where every method
including the mean is hopeless because 40% of experiments have it at exactly
zero) it scores 0.46 against RF-only's 0.75. The user's instinct that the raw
series carries learnable signal is **correct and now measured**.

**And its curves are the worst of any serious candidate**: 0.383 mean, versus
0.210 for the plain ODE fit and 0.296 for RF-only. Three things were checked
before drawing any conclusion from that:

- **Not outlier-driven.** It is worse at the *median* too (0.266 vs 0.217 for
  RF-only). The worst 10% of cutoffs contribute 30% of the mean, which is
  normal, not pathological.
- **Not a scale artifact.** The pooled and the normalized parameter metrics
  agree it is the most accurate, and both disagree with the curve metric.
- **Not overfitting.** This one needed a real experiment, described next.

### The overfitting objection, tested and rejected

The model memorizes: training error is 0.08 normalized against validation
1.05 for the boosted trees. An overfit model makes erratic *joint* predictions,
which is an alternative explanation for bad curves that has nothing to do with
the choice of objective. Six variants were therefore scored, spanning heavy to
light regularization, with the decision rule fixed before running: if any
variant reached a mean curve RMSE near 0.25, the objective story was wrong and
this entry would have to be rewritten.

| Variant | Curve mean | Early | Middle | Late | Norm. param | 4-param | Train |
|---|---:|---:|---:|---:|---:|---:|---:|
| current_ode | **0.210** | 0.396 | 0.169 | **0.064** | 2.798 | 2.676 | — |
| rf_only | 0.296 | **0.279** | 0.299 | 0.309 | 1.250 | 0.753 | — |
| mlp_light (alpha 1) | 0.383 | 0.443 | 0.381 | 0.326 | 1.060 | **0.503** | 0.326 |
| gbm_light | 0.447 | 0.443 | 0.465 | 0.431 | 1.069 | 0.532 | 0.080 |
| gbm_medium | 0.465 | 0.463 | 0.493 | 0.440 | 1.065 | 0.521 | 0.347 |
| mlp_medium (alpha 10) | 0.492 | 0.511 | 0.501 | 0.463 | 1.071 | 0.541 | 0.628 |
| gbm_heavy | 0.598 | 0.576 | 0.641 | 0.576 | 1.126 | 0.603 | 0.613 |
| mlp_heavy (alpha 100) | 0.623 | 0.593 | 0.662 | 0.615 | 1.145 | 0.628 | 0.712 |

**Regularization makes both metrics worse, monotonically.** Closing the
train/validation gap (training error 0.08 to 0.71) degrades curves from 0.45 to
0.62. Nothing comes near 0.25. Overfitting is real but is not what is producing
the bad curves.

### The finding this session actually produced

**Within any given stage of an experiment, better parameters do not produce
better curves.** The comparison has to be made stage by stage, because
comparing pooled figures mixes early and late cutoffs and produces a spurious
result — see the correction below.

Stage-matched, against RF-only, the raw-series model has better parameters and
worse curves in *every* stage:

| Stage | Raw-series param | RF-only param | Raw-series curve | RF-only curve |
|---|---:|---:|---:|---:|
| Early | **1.126** | 1.249 | 0.443 | **0.279** |
| Middle | **1.037** | 1.254 | 0.381 | **0.299** |
| Late | **0.997** | 1.249 | 0.326 | **0.309** |

The sharpest single comparison is late-stage against the plain ODE fit, where
parameter accuracy is essentially *identical* — 0.997 for the raw-series model
versus 0.975 for the ODE fit — and curve accuracy differs by a factor of five,
0.326 versus 0.064.

The reason is that the fitting process lands on a parameter combination whose
errors cancel along the curve; it was fitted to that curve. A regressor trained
on coordinate-wise parameter error lands near the reference in each coordinate
separately, which is not the same thing, and the resulting combination sits off
the low-error valley. The ceiling result shows how narrow that valley is: the
right combination gives 0.027, and being close in each coordinate separately
gives 0.33.

### Correction to this entry's own first draft, and to the previous entry

An earlier draft argued the dissociation "runs in both directions," citing the
ODE fit's terrible pooled parameter error (2.80) alongside its best curves.
**That is a stage-mixing artifact and is withdrawn.** Per stage, the ODE fit's
normalized parameter error is 4.32 early, 1.22 middle, 0.975 late while its
curves are 0.396, 0.169, 0.064 — parameters and curves move *together* for
that method, which is the opposite of dissociation. Its pooled figure is
dominated by early-cutoff wildness.

The same caveat applies to Finding 1's table in the previous entry: the
"best parameters, worst curves" ordering there was also pooled across stages
and should not be cited as evidence on its own. The stage-matched raw-series
versus RF-only comparison above is the evidence that survives.

**Therefore: further architecture work on parameter prediction is wasted
effort.** The objective is wrong, not the model. Tuning the raw-series model
would improve the metric that has just been shown not to predict curve
quality.

### Proposed next step, not started

Train against curve error by putting the ODE inside the objective. The
cleanest version, which also matches spec.md §1's actual goal: **forecast the
remaining curve directly with a sequence model, then recover the parameter
vector by fitting the existing ODE to the forecast complete series.** Curve
and parameters are then consistent by construction, the quantity optimized is
the quantity reported, and the existing fitter does the identifiability work
it already does well. The ceiling result says the achievable target is roughly
0.03 at every stage.

### Two smaller things a future session should not have to rediscover

- **The new normalized parameter metric has its own blind spot.** Averaged
  over all five parameters it is essentially a `q_inf` number: `q_inf` is
  exactly zero for 40% of experiments and near zero for 70%, so its training
  spread is tiny and every method including predicting the training mean
  scores above 3 on it. The manifest therefore also carries the average over
  the four better-determined parameters, which is the figure to read. This is
  the same disease as the pooled RMSE it replaced, in a different organ.
- **Selecting `current_ode` cannot actually be deployed.** The inference path
  only loads a learned model or falls back to RF-only, so a manifest naming a
  baseline and carrying no model file would silently run RF-only in
  production. This has not been changed and is not urgent — it only matters if
  someone decides to deploy the new selection — but it should not be
  discovered by surprise.

**If resuming this thread:** do not tune `raw_series_model.py` to improve
parameter RMSE — six regularization settings were swept and the metric and the
curves move independently. Do not re-derive blends or gates. Do not cite pooled
cross-stage parameter comparisons as evidence about curve quality. The open
question is no longer which parameter predictor is best — it is whether a
curve-objective model can get below the plain ODE fit's 0.210, especially
early, where the ceiling says there is a factor of eight available.

**State at end of session:** nothing committed. New files:
`raw_series_model.py`, `artifacts/phase0/sequential_model_curve_score/`.
Modified: `sequential_model.py` (shared aggregation, new selection score,
normalized metrics, raw-series candidate), `cli.py`
(`--raw-series-estimator`), `inference.py` (the learned-candidate gate now
honours a model's own eligibility rule instead of hard-coding the valid-fit
requirement), `tests/test_sequential_model.py` (four new tests), `plan.md`.
Deployed candidate is still `rf_only` and `artifacts/phase0/` is otherwise
untouched, so the existing test report remains accurate. Full suite: 63
passed, 1 skipped, plus the same pre-existing unrelated `test_get_strategy_default`
failure.

---

## 2026-09-19 — Analysis-only session: the selection metric is measuring the wrong two parameters, no learned candidate beats the raw ODE fit under a curve objective, and no model has ever been shown the raw measurement series

**No code was written or changed this session.** Nothing was retrained, no
artifacts were regenerated, and the deployed candidate is still `rf_only`. This
entry is findings and a proposed direction only.

**Starting point.** The user asked to re-examine the strategy from first
principles — "no assumptions and no priors, start at the top, I want to
forecast, how?" — and to read the specs rather than continue from where the
last session left off. Later in the session they redirected twice, and both
redirects should shape how the next session works:

1. **Explain in plain sentences, not code references.** Their words: "You wrote
   a bunch of code that I haven't read. So when you reference code I have no
   idea what you are talking [about]."
2. **They want a pure ML model; heuristics are "engineering hacks" for later.**
   Blending two estimates, switching between methods by a rule, and the whole
   `rf_only`/`gated_blend`/gate framing all read to them as plumbing rather
   than as an answer to the scientific question. Propose the learned approach
   first; report heuristic scores as evidence, not as the recommendation.

### Finding 1 — the selection score is blind to the parameters that shape the curve

`selection_score = parameter_rmse + early_curve_rmse` (`sequential_model.py`
~line 363), where `parameter_rmse` is a **pooled** `sqrt(mean(all squared
errors))` across the five learned parameters. Because the parameters differ by
four orders of magnitude — `q_e ≈ 0.30`, `q_inf ≈ 0.17`, `k_s ≈ 0.004`,
`k_a ≈ 0.0001`, `k_p ≈ 0.00005` in per-target RMSE — the pooled figure is
essentially a `q_e`/`q_inf` number. The three rate constants contribute
nothing measurable.

The previous entry already noted the scale problem per-target; the consequence
was not drawn. It is: **curve shape is driven by the rate constants, and the
selection metric cannot see them.** "Parameter accuracy" and "curve accuracy"
have therefore been measuring nearly disjoint quantities all along.

The test results show exactly that dissociation:

| Method (test, n=2312) | Param RMSE | Param R² | Curve RMSE |
|---|---:|---:|---:|
| rf_ode_blend | **0.0495** (best) | 0.201 | 0.2156 (worst) |
| rf_only | 0.0536 | **0.270** (best) | 0.2112 |
| current_ode | 0.0705 (worst) | **−0.364** (worst) | **0.1988** (best) |

Best parameters produced the worst curves; worst parameters produced the best
curves. Every model comparison made in this project so far was decided by a
score that does not track the stated objective in `spec.md` §14.

### Finding 2 — validation and test parameter numbers were never comparable

Selection (`sequential_model.py`) uses pooled `sqrt(mean(all squared errors))`.
Final evaluation (`evaluation.py` `_metric_summary`) uses **mean of per-target
RMSE** over six targets including the pass-through `q_0`, whose error is ~0.
That is why the same method reads 0.2208 on validation and 0.0536 on test —
roughly a factor of four, entirely from the aggregation formula and the extra
near-zero target, not from test being "easier."

Also: `evaluation.py` already computes `avg_normalized_rmse` (per-target RMSE
divided by that target's reference standard deviation) — the scale-aware
metric that *would* expose rate-constant error. It is computed and then used
nowhere, in neither selection nor the report's headline table.

### Finding 3 — under a curve objective, the plain ODE fit beats every learned candidate

Mean of the three stage curve-RMSE values from
`artifacts/phase0/sequential_model/manifest.json` (validation, 39 experiments):

| Candidate | Early | Middle | Late | Mean |
|---|---:|---:|---:|---:|
| **current_ode** | 0.396 | 0.169 | **0.064** | **0.210** |
| gated_blend_4 | 0.345 | 0.242 | 0.134 | 0.240 |
| rf_ode_blend | 0.337 | 0.257 | 0.218 | 0.270 |
| rf_only | **0.279** | 0.299 | 0.309 | 0.296 |
| trajectory_10 | 0.352 | 0.563 | 0.519 | 0.478 |

Test agrees on the ordering that matters: `current_ode` 0.199 < `rf_only`
0.211 < `rf_ode_blend` 0.216.

**This corrects a standing claim in the 2026-09-18 entry below.** That entry
predicted broadening the selection score "would very likely make gated-blend
the deployed candidate instead of RF-only." That prediction is **wrong by the
manifest's own numbers** — Baseline B, the raw intermediate ODE fit with zero
machine learning, wins under any curve-based aggregation checked
(equal-weighted stage means, and overall cutoff-weighted on test). Do not
re-derive gated-blend as the answer; it loses to doing nothing but fitting the
ODE, and its late-stage blending is shrinkage toward RF that actively hurts
(0.134 vs the ODE fit's 0.064).

### Finding 4 — no model has ever been shown the raw measurement series

This is the gap, and it is the reason the user's "pure ML model" instinct is
the right one rather than a preference to be talked out of.

The feature list in the model manifest contains, as its only
raw-observation-derived inputs: `q_0`, `last_area`, `mean_area`, `std_area`,
`observed_duration_s` — five summary scalars. Everything else is the RF's
output, the current fit's output, availability masks, status flags, and
schedule counts.

**The shape of the adsorption curve — its slope, its curvature, how it is
bending — has never been an input to any candidate.** Note the distinction:
`trajectory_extrapolation_model.py` does read a history, but it reads the
history of *stored fitted parameters*, not the raw measurements. No candidate
has consumed the measurement series itself.

The untried approach is therefore a single model that takes the raw
measurements collected so far (times and areas) plus the static setup
metadata, and outputs the final parameter vector directly — learned end to
end, no combination of two pre-existing estimates. Each experiment supplies
many training examples, one per valid cutoff.

### False alarm, recorded so it is not re-investigated

An apparent sign reversal between the validation manifest and
`evaluation/report.md` (validation says the ODE fit is worst early / best
late; the test report's `current_ode` block appeared to say the opposite) is
**not a bug**. In `evaluation.py` `_comparison` (~lines 275-326), `candidate`
is always `selected_model`, and each block is *keyed by the baseline being
compared against*. Since `selected_model` is `rf_only`, the block labelled
`current_ode` with `candidate_beats_curve: true` at `early` means "rf_only
beats current_ode early" — consistent with validation, not contradictory.
Both this session and an `advisor()` consult misread it at first glance. The
naming is confusing but the numbers are correct; the early/late crossover is
real and confirmed on both partitions.

### Proposed direction, not yet started

In order, because the first two are cheap and make the third interpretable:

1. **Measure the ceiling (no training).** Take each experiment's known
   reference parameters, run them through the ODE at every cutoff, and score
   remaining-curve RMSE by stage on validation. That is the best any model
   could achieve. If the late-stage ceiling is already matched by the plain
   ODE fit, late is solved and only the early regime is open; if the early
   ceiling is poor, no architecture will rescue early and we should say so
   rather than spend weeks discovering it.
2. **Fix the scoreboard.** Select on curve RMSE across stages rather than
   `pooled_param_rmse + early_curve_rmse`, and report `avg_normalized_rmse`
   (already implemented, currently unused) as the parameter headline so the
   rate constants are visible. When proposing the replacement, name the
   weighting explicitly and say why — equal-weighted stage means, cutoff-
   weighted overall, or per-experiment-then-averaged. All three select
   `current_ode` today, so the choice does not change the current answer, but
   the existing formula is an unexamined default and the user explicitly asked
   for no unexamined assumptions.
3. **Build the sequence model** that reads the raw measurement series plus
   static metadata.

**Test-set discipline for whoever picks this up:** the reasoning above is
justified on validation; test figures are cited only as post-hoc confirmation
of the already-frozen `rf_only` comparison, and test was *not* used to select
anything. If the deployed candidate changes as a result of steps 1-3, that is
a legitimate one-time test re-run under the protocol in the entry below — log
it in `plan.md`, then run `run-inference` → `evaluate-sequential --assignment
test` exactly once, with no iterating on test.

**State at end of session:** working tree unchanged except this log entry.
Branch `feature/ml-eda`, clean before the edit. Deployed candidate still
`rf_only`; `artifacts/phase0/` untouched, so
`artifacts/phase0/evaluation/report.md` remains accurate for the deployed
model. The selection-criterion decision flagged as open in both 2026-09-18
entries is **still open**, but Finding 3 changes what it is a decision
*between*: it is no longer "keep rf_only vs. deploy gated-blend," it is
"keep the early-weighted score vs. adopt a curve-based score under which the
raw ODE fit is the incumbent to beat."

**If resuming this thread:** do not restart by proposing blends, gates, or
switching rules — the user has explicitly deferred those as engineering
hacks, and Finding 3 shows the best of them still loses to the plain ODE fit.
Do not re-litigate the sign reversal (Finding 4's false alarm) or re-derive
gated-blend as the winner. Start at step 1 above.

---

## 2026-09-18 (later) — Added trajectory-extrapolation candidate; it wins on parameters but loses on curves, sharpening rather than resolving the selection-criterion question

**Starting point.** The user's reasoning, unprompted by any file read: the
current-fit parameters visibly converge to `params_final` over an
experiment, `params_final` is exactly the training target, there's plenty of
convergence data, the params are probably correlated, so this "should" be
learnable — why isn't it working? Talked through it before touching code:
the RF already captures everything predictable from static metadata across
~155 training experiments; what's left is a within-experiment trajectory
signal, and early cutoffs are close to uninformative because an ODE fit on
2-3 sparse points is barely constrained. The user also floated, then
partly self-corrected, an idea: fit each experiment's own convergence curve
(param value vs. time) and extrapolate to the endpoint, while noting the
smoothness they'd been observing when plotting might be an artifact of how
least-squares fits behave as sample size grows, not evidence of a strong
cross-experiment signal. Both points turned out to be directionally right.

**What was built: `trajectory_extrapolation_model.py`, a new (third)
sequential candidate.** Unlike Ridge (`sequential_model.py`) and gated-blend
(`gated_blend_model.py`), which both use only the single current-fit
snapshot at the cutoff, this candidate uses the *history* of an experiment's
own stored rolling `pfo-sec_*` fits (already present per-row in the source
CSV, re-read via `example.csv_path` and sliced to `example.observation_count`
so it never reads past the cutoff). For each of the five learned parameters,
it fits `value ~ intercept + slope * (1 / observation_count)` by OLS across
every fit-valid row seen so far in that same experiment, and uses the
intercept (the `n -> infinity` limit) as the final-parameter prediction.
This is a deterministic per-experiment numerical technique, not a
cross-experiment regression — the only hyperparameter is
`min_trajectory_points` (how many historical valid fits are required before
attempting extrapolation; below that, the model reports invalid and the
existing RF-fallback path activates, per spec.md #12). Because each
parameter is extrapolated independently, `k_p <= k_a` is not guaranteed by
construction (unlike gated-blend's convex-combination trick); it's enforced
by clipping `k_p` into `[0, k_a]` after `k_a` is extrapolated, then
re-validated with `validate_secondary_pfo_parameters` as a backstop.
Self-gated on `example.fit_status == fit_valid` at the current cutoff,
matching `gated_blend_model.py` and `inference.py`'s `_model_candidate` (an
earlier version of this candidate was missing this gate — see "bug found and
fixed" below). Wired into `select_initial_model`/`train_initial_model`/
`cli.py` alongside the existing candidates, with `--trajectory-min-points`
mirroring the existing `--gated-blend-bins`/`--ridge-alpha` flags. Five new
tests cover: sufficient history predicts correctly, short history falls back
with the exact `insufficient_trajectory_points` reason, an ineligible current
cutoff falls back before any trajectory logic runs, `k_p` gets clipped to
`k_a` when the raw stored fit values would otherwise violate the constraint,
and the candidate is selectable through `select_initial_model`. Full suite:
60 tests collected (59 passed, 1 skipped, plus the same pre-existing
unrelated `test_get_strategy_default` failure noted in the README).

**Result after re-running `train-sequential-model` on real data (155
train / 39 validation, same split as always, `trajectory_min_points =
(3, 4, 6, 10)`):**

| Candidate | Param RMSE (late) | Curve RMSE (early) | Curve RMSE (late) | Selection score |
|---|---|---|---|---|
| rf_only (currently selected) | 0.2203 | 0.2787 (best) | 0.3093 | **0.4996** (best) |
| gated_blend_4 | 0.1214 | 0.3447 | 0.1341 | 0.5180 |
| trajectory_10 | 0.1185 | 0.3519 | 0.5190 | 0.5249 |
| current_ode | 0.1203 | 0.3956 | 0.0637 (best) | 0.6127 |

(Full per-candidate, per-progress-group numbers for all four
`trajectory_min_points` values and all five Ridge alphas are in
`artifacts/phase0/sequential_model/manifest.json`, `candidate_results`.)

**At first glance the aggregate numbers read as "best late-stage parameter
RMSE of any candidate, worst curve RMSE of any learned candidate" — advisor
review flagged this as needing verification before trusting it, and a
read-only diagnostic (no retraining) confirmed the real story is different
and more useful:**

- `parameter_rmse` is an unweighted RMSE across five parameters on very
  different scales: `k_a`/`k_s`/`k_p` live in `[0, 0.01]` (squared errors
  ~1e-6–1e-8) while `q_e`/`q_inf` are adsorption-area units (squared errors
  ~1e-2). The aggregate is almost entirely a `q_e`/`q_inf` number. Per-target
  RMSE on the same validation set (`k_a`, `q_e`, `k_s`, `k_p`, `q_inf`):
  trajectory `0.000136 / 0.2999 / 0.00426 / 0.000048 / 0.1657` vs. current-ODE
  `0.000086 / 0.3270 / 0.00401 / 0.000060 / 0.1674`. Trajectory is *worse*
  than current-ODE on `k_a` and `k_s` — the two parameters that actually
  shape curve dynamics — and only wins the aggregate because `q_e` happens to
  be slightly better and dominates the sum. "Best parameter RMSE" was true
  but misleading; it was never true of the rate constants.
- The reason: with only a handful of early, often-noisy rolling fits at high
  `1/n` leverage, the OLS intercept for `k_a` frequently extrapolates to
  zero or below and gets clipped to `0.0` — **1291 of 1476 valid trajectory
  predictions (87%) have `k_a` clipped to exactly `0.0`**. Because `k_p` is
  in turn clipped into `[0, k_a]`, the same predictions get `k_p = 0.0` too.
  With `k_a = k_p = 0`, the secondary-PFO ODE (`coupled_pfo_odes`) has zero
  time derivatives — the forecast is flat at `q_0` for the entire remaining
  curve. That is the real, verified cause of the bad curve RMSE: not a
  handful of outlier experiments, and not "nonlinear sensitivity to combined
  small errors" (both hypotheses in an earlier draft of this entry were
  unverified and are now retracted) — it's the extrapolation method itself
  reliably killing the reaction-rate parameters via the lower-bound clip.
- **Bug found and fixed during this check:** the initial implementation had
  no gate on `example.fit_status`, so `_evaluate_model` was scoring 97
  validation predictions (of 1573) at cutoffs where the current fit wasn't
  actually valid — cutoffs production `inference.py` would never route to a
  learned candidate at all. Added the same `fit_status == fit_valid` gate
  `gated_blend_model.py` already uses; the table above reflects the
  corrected numbers (`n=1476`, `0` gating mismatches confirmed by rerunning
  the diagnostic).

**What this does and doesn't validate about the user's original intuition.**
The "params converge smoothly, should be learnable" framing was right for
`q_e`/`q_inf` — trajectory extrapolation is competitive with current-ODE
there. It was wrong for `k_a`/`k_p`: those rate constants apparently do
*not* converge cleanly enough, early on, for a simple `1/n` extrapolation
to recover them — the rolling fits are too often degenerate at low `n`, and
a 2-3-point line through degenerate-then-converged values overshoots past
zero. This is a more precise, falsifiable version of the "maybe the
smoothness I saw was a fitting-numerics artifact" self-doubt the user raised
before any code was touched — it appears to be specifically true of the two
rate constants, not the two capacity parameters.

**Open decision, still not resolved.** `rf_only` remains selected under the
current `selection_score = overall_parameter_rmse + early_curve_rmse`; nothing
changed for the deployed candidate, so `run-inference`/`evaluate-sequential
--assignment test` were not re-run. The broaden-the-selection-score question
from the earlier 2026-09-18 entry is still open and still the user's call —
this session doesn't add evidence either way on that specific question,
since trajectory-extrapolation's problem (dead rate constants) isn't one a
different aggregation of the same metric would fix.

**State at end of session:** nothing committed to git. New file:
`trajectory_extrapolation_model.py`. Modified: `sequential_model.py`,
`cli.py`, `tests/test_sequential_model.py`.
`artifacts/phase0/sequential_model/manifest.json` was regenerated (twice —
once before, once after the fit_status gating fix) and now includes the
trajectory candidates; the *selected* candidate is still `rf_only`.

**If resuming this thread:** the flat-`k_a`/`k_p` failure mode is now
understood and reproducible, not a mystery. Two concrete next steps, neither
started: (1) anchor the extrapolation to the current fit and only extrapolate
a bounded *correction*, or require more/weight late points more heavily so a
handful of early degenerate fits can't single-handedly drag the intercept
past zero; (2) try extrapolating `k_p / k_a` (the ratio the underlying
fitter itself uses, bounded in `[0, 1]`) instead of `k_p` directly, since a
ratio can't independently collapse to zero the way an unconstrained
intercept can. Do not restart from "maybe it's outlier experiments" or
"maybe it's nonlinear sensitivity" — both were checked and ruled out this
session.

---

## 2026-09-18 — Diagnosed why the learned model "performed terribly"; added a second candidate; surfaced an open selection-criterion decision

**Starting point.** The user's framing was essentially: "we have an RF prior,
we have historical convergence data, train something on the convergence data
to correct the RF as measurements arrive — this seems easy." That is exactly
what Phase 6 (`plan.md` §10, §15) already tried: a Ridge regression correcting
the RF prediction using the current ODE fit. It scored badly and RF-only was
selected instead (selection_score 0.4996 vs Ridge's best 0.8296 — see
`artifacts/phase0/sequential_model/manifest.json` before this session).

**Root cause was NOT what it looked like at first.** Two competing hypotheses
were on the table before touching code:
1. The Ridge model corrects each of the 5 parameters independently, which can
   break the physical constraint `k_p <= k_a` (they're coupled: `k_p = k_a *
   k_p_ratio`), producing curves that blow up even when the constraint
   happens to pass.
2. A scoring bug: `_evaluate_model` in `sequential_model.py` `continue`d past
   any cutoff where the Ridge prediction was physically invalid, instead of
   scoring the required RF fallback (spec.md §12 explicitly requires
   fallback, not silent exclusion). This meant Ridge's reported parameter
   RMSE was computed on only ~54% of cutoffs (1098/2043) — its easiest cases
   — while every other candidate was scored on all 2043. Classic survivorship
   bias.

An `advisor()` consult (which sees the full transcript, not just files)
confirmed **(2) was the dominant, provable issue** and told us to stop
theorizing about (1) and just fix the fallback gap first, as a prerequisite
for any fair comparison. (1) is still a real constraint that any new model
must respect by construction — it just wasn't what tanked Ridge's numbers.

**What we changed:**
- Fixed `_evaluate_model` (`sequential_model.py`) to fall back to the RF
  prediction and score it, exactly like production `inference.py` already
  does, instead of dropping invalid predictions from the metric.
- Added a new candidate family: `gated_blend_model.py`. Instead of Baseline
  C's single fixed RF/ODE blend weight for the whole experiment, it learns a
  *different* blend weight per elapsed-time-fraction bin (not
  `observation_fraction` — that field's denominator depends on total
  observation count, which is future information at inference time;
  `elapsed_time_fraction` only needs the known final time, which spec.md §5
  explicitly permits).
  - `k_a` and `k_p` are always blended with **one shared weight** per bin.
    This isn't a stylistic choice — a convex combination `w*a + (1-w)*b` of
    two individually-valid vectors preserves `k_p <= k_a` for *any* shared
    `w` (linearity of the inequality). Blending them independently would not
    have this guarantee. `q_e`, `k_s`, `q_inf` get independent per-bin
    weights since they only have interval bounds, no coupling.
  - Weight per (group, bin) is a clipped least-squares slope of
    `(reference - rf)` on `(current_fit - rf)`, fit on training examples
    only, weighted `1/cutoffs_per_experiment` (same scheme Ridge already
    used, so no experiment dominates by having more cutoffs).
  - Only activates when `fit_status == fit_valid`; every output is still
    re-validated with `validate_secondary_pfo_parameters` regardless, so an
    unexpected invalid blend still falls back rather than being trusted.
- Wired it into `select_initial_model` alongside the Ridge alphas and the
  three required baselines, so it's evaluated with identical, fallback-aware
  scoring and identical manifest/provenance plumbing (`test_used_for_selection`
  etc. unchanged). Added a `--gated-blend-bins` CLI flag mirroring
  `--ridge-alpha`.

**Result after re-running `train-sequential-model` on real data (155
train / 39 validation experiments, same split as always):**

| Progress stage | RF-only curve RMSE | Best gated-blend (4 bins) |
|---|---|---|
| Early (first third) | 0.279 (best) | 0.345 (worse) |
| Middle | 0.299 | 0.242 (~19% better) |
| Late (final third) | 0.309 | 0.134 (~57% better) |

Gated-blend is now a *legitimately* strong candidate — night-and-day better
than the old, buggily-scored Ridge attempt (whose selection scores are still
visibly terrible even after the fallback fix: 0.68–0.80). But **RF-only is
still the model the pipeline selects**, because `select_initial_model`'s
`selection_score = overall_parameter_rmse + early_curve_rmse` only looks at
early-cutoff curve accuracy plus an unweighted overall parameter error — it
never sees the middle/late wins at all. This is a pre-existing, intentional
design choice (arguably matching spec.md §9's "as early as possible" framing),
not something introduced or broken this session — advisor's guidance was
explicit not to silently redefine it.

**Open decision, not yet made by the user:** whether to broaden the
selection score to also reward middle/late accuracy (which would very likely
make gated-blend the deployed candidate instead of RF-only), or keep the
early-weighted rule as-is (RF-only stays deployed; gated-blend remains
validated-but-unused evidence). Asked the user directly; they asked for a
conceptual explanation of the system instead of answering yet, so this
decision is **still open going into the next session**.

**State at end of session:**
- Nothing committed to git. Changed/new files: `sequential_model.py`,
  `cli.py`, `tests/test_sequential_model.py` (modified);
  `gated_blend_model.py`, `model_prediction.py` (new, the latter just holds
  the shared `ModelPrediction` dataclass to avoid a circular import between
  `sequential_model.py` and `gated_blend_model.py`).
- `train-sequential-model` was re-run against the real `phase0` artifacts, so
  `artifacts/phase0/sequential_model/manifest.json` now reflects the fixed,
  fallback-aware scoring and includes the gated-blend candidates — but the
  *selected* candidate is still `rf_only`, identical to before, so
  **`run-inference` and `evaluate-sequential --assignment test` were
  deliberately NOT re-run** — nothing changed for the frozen/deployed
  candidate, and there was no reason to reopen the test set.
  `artifacts/phase0/evaluation/report.md` (the last test-set evaluation) is
  therefore still accurate for the currently-deployed model.
  `sequential_model/model_not_selected.txt` still explains RF-only won.
- Focused suite (30 tests incl. 4 new for gated-blend + fallback fairness)
  and full automation suite (54 passed, 1 unrelated pre-existing failure —
  `test_get_strategy_default`, documented in `plan.md`/README as unrelated)
  both pass.
- `plan.md` §14 (Deferred Work) was **not yet updated** with this session's
  findings — worth doing once the selection-criterion decision is made, so
  the decision log stays authoritative per `plan.md`'s own convention.

**If resuming this thread:** don't re-litigate whether Ridge's coupling
theory was "the" bug — it wasn't, the survivorship-bias fix was. Go straight
to the open decision above. If the user picks "broaden the score," the
concrete next step is a validation-only change to `_evaluate_model`'s
`selection_score` formula (e.g. mean curve RMSE across early/middle/late
instead of early-only), re-run `train-sequential-model`, and — only if a
*different* candidate than the currently-frozen one gets selected — treat
that as a genuine re-opening of test-set evaluation (log it in `plan.md`,
then re-run `run-inference` → `evaluate-sequential --assignment test` exactly
once, no iterating on test).
