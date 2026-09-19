# Sequential Forecasting — Session Log

A running, high-level log of the *reasoning* behind each work session on
`sequential_forecasting/` — decisions made, why, what evidence drove them,
and what's still open. This is not a changelog of code (git history and
`plan.md` already cover that); it's the "why," the dead ends, and the
context a future session would otherwise have to re-derive from scratch.

New entries go at the top. Keep each entry to what genuinely isn't
recoverable by reading the code or `plan.md`'s decision log.

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
