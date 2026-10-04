# spec-working — segment-wise kinetics for the new classifier

**Status: iteration 2 BUILT (2026-10-03): D17/D20 (depletion start), D18/D23 (spike
labels), D21 (no-spike cluster split), D22 (pfo clock). Fits re-run on the 8 test
measurements; the features files of the other 288 predate iteration 2 (no
`depletion_start_s`). See §0.**

`spec.md` describes the package as it was before this work. This file holds the
segment-mode design, the decisions (§1), what was built and checked (§5–§6), and the
open questions (§7). When the work settles, it moves into `spec.md` and this file is
archived.

Scope: offline only (`src/utils/kinetics/`). Live `src/analysis/kinetics_fitting.py`
is not touched.

---

## 0. Handoff (start here in a new session)

**Working tree:** iteration 1 is committed by the user as `9ce4dfb` ("kinetic segment
dev start"). Iteration 2 is uncommitted: `segments.py`, `ground_truth.json` and this
file. The user makes all commits; never commit. Files are CRLF (`ground_truth.json`
too): a shell `sed -i` or a Python text-mode write turns them to LF, so normalize
back if that happens.

**Iteration 2 (done 2026-10-03):** D17 + D20 (contiguous monomer segments at
`t_b = max(monomer max, growth onset)`, written as `depletion_start_s`), D18 + D23
(spike labels, 000-041 entry; `--validate-spikes` = 66/66), D21 (no-spike
cluster split at the growth onset), D22 (`t_ref_s`, the pfo clock). Results: �6.

**Next steps, in order:**
1. **The user looks at the redrawn figures** of the 8 test files
   (`C:\Figures\<folder>\plot_kinetic_segments\`), above all the D21 split
   (003-097, 004-008, 000-002, 000-028) and D17 on 000-026.
2. **Refresh the features on all data** (`--classify-only`, fast). This adds
   `depletion_start_s` to the 288 files not re-run.
3. Whole-folder fit runs are the user's to start (D16). The existing
   nn1120-4_000 `_test` params, apart from the 5 test files, are a sums-only
   pre-iteration-2 run: no D17/D21 segments and no `t_ref_s`.
   `segment_curve` falls back to the old clocks for them.
4. Q8 (one file vs. two) is still open.

The 8 test measurements, for re-runs (lab machine: one process, the default
below-normal priority):
- nn1120-4_pd_ceo2_000: 000-000, -002, -014, -026, -028
  (`20260630_141811_�-000`, `20260704_141909_�-002`, `20260801_054310_�-014`,
  `20260822_193302_�-026`, `20260827_172623_�-028`);
- nn1120-3_pd_ceo2_003: 003-097 (`20260115_215548_�-097`);
- nn1120-3_pd_ceo2_004: 004-008, 004-013 (`20260315_214542_�-008`,
  `20260411_100444_�-013`).

Scratch scripts from the first session (survey, spike scoring, ad-hoc plots) were
in that session's temp scratchpad and are gone. Everything that matters is in §4
and §6.

## 1. Decisions

| # | Decision | Date |
|---|---|---|
| D1 | The default fits **once over the full trajectory**, per segment, not at every row. | 2026-10-03 |
| D2 | The rolling (fit-after-every-row, live-equivalent) path stays available, unchanged (`--mode rolling`). | 2026-10-03 |
| D3 | Boundaries (maxima) are taken on a **smoothed** trajectory, with the window in points. Pooled vs. per-group: the better one is chosen (§4 survey → pooled). | 2026-10-03 |
| D4 | A truncation point belongs to **both** adjacent segments. | 2026-10-03 |
| D5 | Segments get physical names. Continuous = adsorption. Discontinuous = LaMer: monomer_sum is the monomer's view; cluster_sum is the cluster's view. | 2026-10-03 |
| D6 | The cluster spike segments (`burst_nucleation`, `diffusion_growth`) are **left blank**: rows are written, no model is fitted, while the user explores models. | 2026-10-03 |
| D7 | Outputs: a params file and a features file only (§3). No time-vs-fit file and no folder rollup for now; to be revisited after the user looks at the output. | 2026-10-03 |
| D8 | `pre_nucleation` = CO adsorption onto pre-existing clusters. The spike = CO adsorption onto emergent, new clusters. | 2026-10-03 |
| D9 | Early spikes keep the growth-onset base. On 000-000 (onset 0.75 h), `pre_nucleation` holds 9 points and `burst_nucleation` covers 0.75–6.6 h. That is the intended reading. | 2026-10-03 |
| D10 | Short supersaturation segments are left as they are. In about half of nn1120-4_000's discontinuous files, the monomer max is at 0.7–2 h, leaving 9–15 points for a 5-parameter secondary_pfo. There is no extra point minimum and no switch to pfo. | 2026-10-03 |
| D11 | Constituent fits are left as they are. pfo's `q_e ≥ 0` cannot follow falling or flat constituents: 49/144 fits have R² < 0.5, and constituents ≤ 0 throughout get NaN. There is no signed `q_e` and no amplitude skip. | 2026-10-03 |
| D12 | exp_decay's `y_b` is the smoothed value at the segment start, not the raw first point. pfo/secondary_pfo `q0` is unchanged. | 2026-10-03 |
| D13 | Confirmed: constituents use their sum's boundaries; unclassified files get the continuous segments. | 2026-10-03 |
| D14 | Spike labels go in `ground_truth.json`: an optional boolean `spike` per entry, scored by `run_kinetics_classification.py --validate-spikes`. The **user** labels, from the plots (D15). | 2026-10-03 |
| D15 | There is no `--plot` flag. Visualization is `src/visualizations/monomer_features.py`, rebuilt around the segments outputs. | 2026-10-03 |
| D16 | Whole-folder fit runs are started by the user. | 2026-10-03 |
| D17 | **(Implemented 2026-10-03.)** For monomer_sum and its constituents in discontinuous files, `depletion` (exp_decay) starts at `t_b = max(monomer_max_s, growth_onset_s)`. Supersaturation ends at the same `t_b` (D20). | 2026-10-03 |
| D18 | **(Implemented 2026-10-03.)** Spike labels: the detector is right on every file. True spikes: 000-000, 000-026, 000-029, 000-032, 000-034, 000-041 (all nn1120-4_pd_ceo2_000). Every other discontinuous file has no spike. 000-041 now has an entry (D23). | 2026-10-03 |
| D19 | Continuous files keep one secondary_pfo over the whole run for monomer_sum, even when it peaks and decays (Q6 → no). | 2026-10-03 |
| D20 | Q11 → (a): the monomer segments stay contiguous. `supersaturation` ends where `depletion` starts, at `t_b = max(monomer max, growth onset)`. `t_b` is written to the features file as `depletion_start_s`. | 2026-10-03 |
| D21 | In discontinuous files with no spike, cluster_sum (and, by D13, its constituents) gets two pfo segments: `pre_nucleation` from t0 to the growth onset, then `ripening` from the onset to the end. If the onset is NaN, the fallback is one `ripening` over the whole run; no file hits this today (0/70). | 2026-10-03 |
| D22 | A pfo segment that starts at a boundary (today only the D21 `ripening`) runs on its own clock, `t − t_ref`, where `t_ref` is its first point, so `q0` (fixed to that point) sits on the curve. Segments that start the trajectory keep absolute time, because the area CSVs start at ~420 s, not 0, and shifting them would change existing fits. `t_ref_s` is written per params row: 0 for absolute clocks, the first time for exp_decay and boundary-start pfo. `q0` stays the raw first point (D12 is not extended). | 2026-10-03 |
| D23 | Spike labels for continuous entries: left unlabeled. The scorer only evaluates discontinuous files, so they score the same either way. 000-041 got a ground-truth entry: `label: discontinuous`, `spike: true`, `basis: user_declared_2026-10-03`. | 2026-10-03 |

History: a one-shot mode existed before. `f87abfc` had
`fit_cli --mode {rolling, full_series}`; `8462e2b` removed it for live parity. D1
brings it back as the default, with segments.

## 2. Segment rules (`--mode segments`)

The regime is the measurement's **final** label (the latch ever engaged). Boundaries
come from the **sum** trajectory. Its constituents use the same boundaries (D13).

| Rows | Regime | Spike | Segments (model) |
|---|---|---|---|
| monomer_sum + 3 constituents | continuous | — | `adsorption` (secondary_pfo) |
| | discontinuous | — | `supersaturation`: t0 → `t_b` (secondary_pfo); `depletion`: `t_b` → end (exp_decay), with `t_b = max(monomer max, growth onset)` (D17, D20) |
| cluster_sum + 15 constituents | continuous | — | `adsorption` (pfo) |
| | discontinuous | no | `pre_nucleation`: t0 → growth onset (pfo); `ripening`: growth onset → end (pfo, own clock, D22). One `ripening` if the onset is NaN (D21) |
| | discontinuous | yes | `pre_nucleation`: t0 → spike base (pfo); `burst_nucleation`: base → cluster max (none); `diffusion_growth`: cluster max → end (none) |

If the classification is NaN (too few points), the continuous segments are used and
`regime = unclassified` (D13).

**exp_decay** (new, `models._ExpDecayModel`):
`y = y_inf + (y_b − y_inf)·exp(−k·(t − t_b))`.
- `t_b` is the segment's first time. `y_b` is fixed to the **smoothed** trajectory
  (`smooth_n`-point centered median) at `t_b` (D12), passed as `p0[2]`. Without
  `p0[2]` the model falls back to the raw first value.
- Fitted: `k ∈ [0, 0.01]` and `y_inf ∈ [min − span, max + span]`.
- Solved with `curve_fit`.

pfo and secondary_pfo are unchanged. The segment layer shifts pfo's clock for
a segment that starts at a boundary (D22), so `pfo(t − t_ref_s)`; `segment_curve`
applies the same shift from the params row. A segment with fewer than `--min-points` rows
(default 4) gets NaN parameters, and its row is still written.

## 3. Outputs

Files go to `<dataset>\_reprocess\<output-folder>\` (default `_test`). The suffixes
are in `config/paths.yaml`.

**`<base>_CarbonylKineticParams.csv`** has one row per `(Peak_Name, segment)`:
- Identifier and summary columns: `Measurement, Peak_Name, group, regime, segment,
  model, t_start_s, t_end_s, t_ref_s, n_points, r^2, rmse`. `t_ref_s` is the
  model clock's zero (D22).
- Then the parameter columns:
  - `pfo_*` (as in the live schema);
  - `pfo-sec_*` (as in the live schema);
  - `exp_k_s-1, exp_k_stderr, exp_y_inf_au, exp_y_inf_stderr, exp_y_b_au`.
- A row's columns for other models are NaN.
- `model = none` marks a blank segment.

**`<base>_CarbonylKineticFeatures.csv`** has one row:
- `Measurement`, `n_points`, `classification`, `growth_onset_s`, `latch_time_s`;
- `monomer_max_s`, `monomer_max_au`, `depletion_start_s` (D20; NaN unless
  discontinuous);
- `spike_detected`, `spike_base_s`, `cluster_max_s`, `cluster_max_au`,
  `cluster_plateau_au`, `cluster_noise_au`, `spike_prominence`, `spike_rise`,
  `spike_note`.
- The `_au` maxima are smoothed values. The spike columns are evaluated for
  discontinuous files only; `spike_detected` is empty for continuous files.

`--classify-only` writes only the features file.

## 4. Boundaries and the spike (yaml `kinetics_reprocess_segments`)

- **Smoothing:** a centered running median of `smooth_n = 5` points over the pooled,
  time-sorted sum trajectory.
- **Monomer max:** the argmax of smoothed monomer_sum.
- **Spike** (discontinuous only), on smoothed cluster_sum:
  - **Candidate max:** the argmax within [monomer max − 2 h, monomer max + 8 h].
  - **Noise:** `1.4826·MAD(raw − smoothed)`.
  - **Prominence:** (max − plateau) / noise, where the plateau is the median of the
    smoothed values from 4 h after the max (at least 3 points).
  - **Rise:** (max − smoothed value at the base) / noise.
  - **Base:** `growth_onset_s`.
  - **Detected** when prominence ≥ 5 and rise ≥ 5 and base < max.

### Survey that set these (2026-10-03, 296 files, 70 discontinuous)

- **Pooled vs. per-group smoothing:** pooled wins.
  - A Delta_Group has ~17 points in a 52 h run, so a per-group centered window of 5
    spans ~15 h. Its max time runs consistently early: on 000-026 it gives 3.0 h
    vs. 10.1 h pooled, and the plot puts the max at 10 h.
  - Group offsets in the sums (median ~0.05 au) are small next to the monomer_sum
    range (~0.8 au), so pooling is safe.
  - Pooled windows 3–9 agree within ~1–2 h on most files; 5 was chosen.
- **Spike score:** it separates with a gap.
  - Detected (6, all in nn1120-4_000): `000-034` 25.7, `000-032` 17.4, `000-026` 15.3,
    `000-041` 8.8, `000-000` 6.0, `000-029` 5.3.
  - Next highest: `001-034` 4.9 (rise 2.7; a tiny-amplitude file), then `003-097` 3.9.
    All others are < 2.
  - Plots checked: 000-026/000/029 spike; 003-097, 001-034, 003-104 and 000-028 do
    not. 004-031 has an end-of-run drop, not a spike.
- **Spike base:** the walk-left / windowed-minimum base landed too early (6.6 h on
  000-026, where the rise visibly starts at ~11.5 h). `growth_onset_s` matched the
  visible start on the six spikes.

## 5. Code

| File | Change |
|---|---|
| `segments.py` (new) | `smoothed`, `smoothed_max`, `detect_spike`, `plan_segments`, `depletion_start`, `segment_curve` (evaluate a params row, for plots), `SegmentWriter` (features, per-segment fits, write), `SEGMENT_WRITER`. Iteration 2: D17/D20 depletion start, D21 no-spike split, D22 `t_ref_s` clock |
| `ground_truth.json` | Iteration 2: `spike` on the 66 discontinuous entries, plus the new 000-041 entry (D18, D23) |
| `models.py` | `_ExpDecayModel`, registered as `exp_decay`; `p0 = [k, y_inf, y_b]`, where a NaN `k`/`y_inf` takes the default guess and `y_b` is fixed |
| `validation.py` / `classify_cli.py` | `run_spike_validation`, `print_spike_summary`; `--validate-spikes` |
| `src/visualizations/monomer_features.py` | Rewritten. Per measurement it draws two panels (monomer_sum; cluster_sum + Peak_1988): raw points, smoothed curve, shaded segments and fitted curves, plus onset/latch lines. Output goes to `C:\Figures\<folder>\plot_kinetic_segments\` with a `kinetic_segments.csv` catalog. The old LaMer I/II/III domain catalog is in git (`fdd8a71`) |
| `api.py` | `process_file(mode=...)`, `MODES`. The default stays `rolling`, so `classify_cli` is unchanged |
| `fit_cli.py` | `--mode {segments, rolling}`, default `segments` |
| `config/analysis.yaml` | `kinetics_reprocess_segments` block |
| `config/paths.yaml` | `kinetic_params_suffix`, `kinetic_features_suffix`, `plot_kinetic_segments` |

`writer.py` and `classification.py` are unchanged.

## 6. Validation (iteration 1)

- **Rolling mode is unchanged.** `--mode rolling --classify-only` on 000-026 is
  byte-identical to `_test_classification`. Rolling *with fits* was not re-run.
  pfo, secondary_pfo, `REGIME_MODELS` and `writer.py` are untouched; `models.py`
  only gained a class.
- **Features on all data.** `--classify-only` (segments) ran on all 7 datasets:
  296/296 files, 0 failures, 226 continuous / 70 discontinuous.
  - `spike_detected` is exactly 000-000/026/029/032/034/041, matching the survey.
  - `spike_note` on the rest: 14 "growth onset at or after cluster max", 2 "no
    plateau after max".
- **Segment runs:** 000-026, 000-000, 000-002, 000-014 (continuous), 000-028, 003-097,
  004-008 (274 points) and 004-013 (continuous, decaying monomer). These were re-run
  after D12.
  - Each took 5–90 s. Rolling takes up to ~5 h per long file.
  - There were 0 ODE timeouts, except 004-013 with 41. Its long constituent
    secondary_pfo fits ran while another process loaded the machine; the 0.1 s
    timeout is wall-clock.
- **Figures:** `monomer_features.py` on nn1120-4_pd_ceo2_000: 39/39 drawn
  (`C:\Figures\nn1120-4_pd_ceo2_000\plot_kinetic_segments\`). Only the 5 test files
  there have fit curves; the rest have features only.
- **Spike scorer:** tested on a scratch copy of the ground truth. It skips unlabeled
  entries and reports a flipped label as FALSE_POSITIVE.
- **Sum fits:**
  - monomer_sum supersaturation R² 0.95–1.00 and depletion 0.81–0.99.
  - cluster_sum ripening/pre_nucleation 0.81–0.97.
  - The exceptions: continuous 000-014 cluster_sum has R² 0.17, because the signal is
    flat noise (0.42–0.48 au), not because the fit is bad. 003-097's depletion is
    0.81, because the run ends while the decay is still nearly linear.
- **Constituent fits:** 144 fitted. 7 are NaN (constituents ≤ 0 throughout: the
  existing pfo/secondary_pfo bound inversion) and 49 have R² < 0.5 (§7 Q3).

### Iteration 2 (2026-10-03)

- **Re-run:** the 8 test files with all peaks, one process, below-normal priority,
  ~2 min per folder. Before/after diff against a snapshot of the iteration-1
  outputs.
- **No leak into unchanged segments.**
  - Continuous 000-014 and 004-013: cluster pfo matches to ≤ 4e-14.
    secondary_pfo differs slightly on 004-013 (R² by ≤ 0.002), from its 20
    wall-clock ODE timeouts.
  - Spike files 000-000 and 000-026: cluster `pre_nucleation` is unchanged.
- **D17/D20:** among the test files only 000-026 has its onset after the monomer
  max (10.1 → 11.6 h). Its depletion R² goes 0.991 → 0.978 and supersaturation
  0.962. In 50/70 discontinuous files across all data the onset is after the monomer
  max, so the rule moves most of them.
- **D21** (cluster_sum `pre_nucleation` R² / `ripening` R²; old single ripening R²):
  - 003-097: 0.906 / 0.326 (0.837);
  - 004-008: 0.886 / 0.448 (0.852);
  - 000-002: 0.760 (8 pts, onset 0.5 h) / 0.913 (0.967);
  - 000-028: 0.962 / 0.698 (0.844).

  The clock is not the cause: in every figure the ripening curve starts on the data
  at the onset (D22). The low post-onset R² has a different cause per file:
  - 004-008: a fast rise, then a long noisy plateau. pfo tracks both; little variance
    is left to explain.
  - 000-028: a steady rise whose scatter grows after ~30 h. pfo follows the trend.
  - **003-097: a sub-threshold hump.** After the onset, cluster_sum rises to ~0.35
    at 21.6 h and falls back to ~0.25 by 32 h (the prominence-3.9 file just below
    the spike cutoff, §4). A monotone pfo (`q_e ≥ 0`) cannot follow the fall. This
    bears on the open model choice for post-onset segments.
- **Spikes:** `--validate-spikes` = 66/66 labeled files correct (6 spike).
- **Nucleation score:** `--validate` = 286/289. The misses are 003-098, 003-102 and
  004-016, with no false positives. The new 000-041 entry scores correct. These
  three misses predate iteration 2: their labels are unchanged since `9ce4dfb`,
  so HEAD scores 285/288. The 286/288 in `docs/JOURNAL_nuc-clf-refit.md` and
  `CLAUDE.md` (misses 003-077 FP, 003-102) is stale, presumably since the
  latch/onset commits (`b12e18a`..`034102f`). Not investigated.

## 7. Open questions (surfaced during the build)

Resolved: Q1–Q3 → D9–D11, Q4 → D12, Q9 → D13, Q5 → D14, Q10 → D15, Q7 → D16,
Q5a → D18, Q6 → D19, the depletion start → D17, Q11 → D20.

Context for D19 (Q6, answered "no"): 61/226 continuous files have a monomer_sum that
peaks and then decays: the smoothed max falls before 80% of the run, and the signal
falls > 30% of its range after it. On 004-013 (1.29 → 0.19 au over 150 h), the
single secondary_pfo gets R² 0.976, with systematic residuals: it overshoots the max
by about 0.08 au and sits under the data from 40–70 h. That file's cluster_sum
Delta_Groups also diverge after ~50 h.

- **Q8. One file vs. two.** Revisit after the user has looked at the output (D7).
- **Q11 (resolved → D20, option (a)). The gap D17 creates.** When
  `growth_onset_s > monomer_max_s`, `monomer_max_s → growth_onset_s` belongs to no
  segment if supersaturation still ends at the monomer max. On 000-026 that is
  10.1 → 11.6 h; in the survey the onset is usually 0–5 h after the monomer max.
  Options:
  - (a) supersaturation runs to the same `t_b`, so the segments stay contiguous;
  - (b) leave the gap unfitted;
  - (c) a separate, blank segment, like the cluster spike segments.

  When the onset comes first (e.g. 003-095: onset 9.1 h, monomer max 20.6 h),
  `t_b` = the monomer max and nothing changes.
