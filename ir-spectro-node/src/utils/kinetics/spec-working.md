# spec-working — segment-wise kinetics for the new classifier

**Status: iteration 1 BUILT (2026-10-03). Fits run on 7 measurements; features on all 296.**

`spec.md` describes the package as it was before this work. This file holds the
segment-mode design, the decisions (§1), what was built and checked (§5–§6), and the
open questions (§7). When the work settles, it moves into `spec.md` and this file is
archived.

Scope: offline only (`src/utils/kinetics/`). Live `src/analysis/kinetics_fitting.py`
is not touched.

---

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

History: a one-shot mode existed before. `f87abfc` had
`fit_cli --mode {rolling, full_series}`; `8462e2b` removed it for live parity. D1
brings it back as the default, with segments.

## 2. Segment rules (`--mode segments`)

The regime is the measurement's **final** label (the latch ever engaged). Boundaries
come from the **sum** trajectory. Its constituents use the same boundaries (D13).

| Rows | Regime | Spike | Segments (model) |
|---|---|---|---|
| monomer_sum + 3 constituents | continuous | — | `adsorption` (secondary_pfo) |
| | discontinuous | — | `supersaturation`: t0 → monomer max (secondary_pfo); `depletion`: monomer max → end (exp_decay) |
| cluster_sum + 15 constituents | continuous | — | `adsorption` (pfo) |
| | discontinuous | no | `ripening` (pfo) |
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

pfo and secondary_pfo are unchanged. A segment with fewer than `--min-points` rows
(default 4) gets NaN parameters, and its row is still written.

## 3. Outputs

Files go to `<dataset>\_reprocess\<output-folder>\` (default `_test`). The suffixes
are in `config/paths.yaml`.

**`<base>_CarbonylKineticParams.csv`** has one row per `(Peak_Name, segment)`:
- Identifier and summary columns: `Measurement, Peak_Name, group, regime, segment,
  model, t_start_s, t_end_s, n_points, r^2, rmse`.
- Then the parameter columns:
  - `pfo_*` (as in the live schema);
  - `pfo-sec_*` (as in the live schema);
  - `exp_k_s-1, exp_k_stderr, exp_y_inf_au, exp_y_inf_stderr, exp_y_b_au`.
- A row's columns for other models are NaN.
- `model = none` marks a blank segment.

**`<base>_CarbonylKineticFeatures.csv`** has one row:
- `Measurement`, `n_points`, `classification`, `growth_onset_s`, `latch_time_s`;
- `monomer_max_s`, `monomer_max_au`;
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
| `segments.py` (new) | `smoothed`, `smoothed_max`, `detect_spike`, `plan_segments`, `segment_curve` (evaluate a params row, for plots), `SegmentWriter` (features, per-segment fits, write), `SEGMENT_WRITER` |
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
- **Segment runs:** 000-026, 000-000, 000-002, 000-014 (continuous), 000-028, 003-097
  and 004-008 (274 points).
  - Each took 5–36 s. Rolling takes up to ~5 h per long file.
  - There were 0 ODE timeouts.
- **Sum fits:**
  - monomer_sum supersaturation R² 0.95–1.00 and depletion 0.81–0.99.
  - cluster_sum ripening/pre_nucleation 0.81–0.97.
  - The exceptions: continuous 000-014 cluster_sum has R² 0.17, because the signal is
    flat noise (0.42–0.48 au), not because the fit is bad. 003-097's depletion is
    0.81, because the run ends while the decay is still nearly linear.
- **Constituent fits:** 144 fitted. 7 are NaN (constituents ≤ 0 throughout: the
  existing pfo/secondary_pfo bound inversion) and 49 have R² < 0.5 (§7 Q3).

## 7. Open questions (surfaced during the build)

Resolved: Q1–Q3 → D9–D11, Q4 → D12, Q9 → D13, Q5 → D14, Q10 → D15, Q7 → D16.

- **Q5a. Spike labels (pending, user).** `ground_truth.json` has no `spike` entries
  yet. The detector's current positives are 000-000/026/029/032/034/041; the
  borderline negatives are 001-034 and 003-097. These are not labels.
- **Q6. Continuous files whose monomer_sum peaks and then decays.**
  - The count: 61/226 continuous files. Their smoothed max falls before 80% of the
    run, and the signal falls > 30% of its range after it. They occur in every
    dataset: 24 in nn1120-3_001, 19 in 003, 10 in nn1120-4_000, 7 in 004.
  - Current rule: one secondary_pfo over the whole run.
  - On 004-013 (1.29 → 0.19 au over 150 h), secondary_pfo gets R² 0.976 but with
    systematic residuals. It overshoots the max by about 0.08 au and sits under the
    data from 40–70 h.
  - The question: should continuous files also get supersaturation → depletion?
    That would mean the monomer split follows the monomer's own peak, not the
    nucleation label.
  - On the same file, cluster_sum's Delta_Groups diverge after ~50 h (one group
    falls to 0.1 au), so a pooled pfo means little there.
- **Q8. One file vs. two.** Revisit after the user has looked at the output (D7).
