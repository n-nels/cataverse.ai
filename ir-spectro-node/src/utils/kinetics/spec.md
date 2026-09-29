# src/utils/kinetics — offline kinetics reprocessing

**Status: in build.** Offline only. The live server never calls it, and it never writes
into source data. The working spec, with the decisions, validation tables and
progress log, is `spec-working.md`. Classifier design is in `docs/spec_nuc-clf.md`.

## 0. Read first

```bash
# 1. refit params -> area CSVs, then 2. classify + kinetic fits (live-equivalent)
uv run python scripts\run_kinetics_fit.py --folder nn1120-3_pd_ceo2_004 --build-areas
uv run python scripts\run_kinetics_fit.py --folder nn1120-3_pd_ceo2_004 --classify-only   # fast
uv run python scripts\run_kinetics_fit.py --folder nn1120-3_pd_ceo2_004 --measurements <base name>
uv run python scripts\run_kinetics_fit.py --folder nn1120-3_pd_ceo2_004 --workers 8   # one process per measurement

# Score a detector against ground_truth.json
uv run python scripts\run_kinetics_classification.py --validate
uv run python scripts\run_kinetics_classification.py --validate --input-subfolder _reprocess
```

### Traps

- **Time never comes from params rows.** `Time (s)` is a running sum of
  `Time_Delta (s)`, so a missing or failed fit would shift every later time. The
  timeline (`timeline.py`) takes each spectrum's `Time_Delta` from the subIFG log
  instead.
- **The sums are fixed in the area CSV.** They come from the `ir_fitting.fit` groups
  (`utils.group_peak_names`): monomer = 2113/2103/2093, cluster = 15 peaks, including
  the six low-band peaks. There are no per-run sum flags. Rebuild the areas to change a sum.
- **`classification` is causal.** Each row carries the latch state as of that time
  (`classification.latch_sweep`: 3 consecutive fires, never reverts). It is not a
  hindsight label, and it is the same sweep the ground-truth harness scores.
- **Sort order is part of parity.** `sorted_trajectory` sorts exactly as live does.
  A stable sort changes floating-point sums enough to move ill-conditioned
  secondary_pfo fits.
- **secondary_pfo is slow**, and has a 0.1 s wall-clock ODE timeout per solve, so a
  heavily loaded machine can change results. Run at below-normal priority (the CLI
  default). `--workers N` runs N measurements at once, one process each, as the
  refit does. More load means more timeouts, which are reported per file
  (`N ODE timeouts`).

## 1. Pipeline

```
<dataset>\_reprocess\*_CarbonylPeakFitParams.csv         (refit output)
   │  timeline.build_timeline  (subIFG log + exp params → Time_Delta per spectrum)
   │  areas.build_peak_area_df (live compute_cumulative_peak_area_df on the full grid,
   ▼                            sums from ir_fitting.fit groups)
<dataset>\_reprocess\*_CarbonylPeakArea.csv
   │  writer.prepare_measurement_rows:
   │    classify_by_time   causal cluster_sum label (latch_sweep)
   │    rolling fits       REGIME_MODELS[(group, regime)] per time point
   ▼
<dataset>\_reprocess\_test\*_CarbonylPeakArea.csv          (live schema)
```

| Module | Role |
|---|---|
| `timeline.py` | One row per subIFG spectrum (from the log), with `Time_Delta (s)` |
| `areas.py` | Params + timeline → area CSV. A spectrum with no fit keeps its time and gets NaN area |
| `classification.py` | Detectors (`combined` = flat-then-rise OR drawdown), `latch_sweep`, `sorted_trajectory` |
| `models.py` | pfo and secondary_pfo (copies of live, same results) |
| `writer.py` | `REGIME_MODELS`, per-measurement classify + rolling fit + write; singletons |
| `api.py` | `build_areas`, `process_file`, `process_folder` |
| `validation.py` | Ground-truth harness (`run_validation`, `ever_fires`) |
| `fit_cli.py` / `classify_cli.py` | The two CLIs (`scripts\run_kinetics_fit.py`, `scripts\run_kinetics_classification.py`) |
| `monomer_features.py` | Research module (LaMer landmarks); not part of the pipeline |

## 2. Models

`REGIME_MODELS` maps `(group, regime)` to a model. The regime at a time point is the
cluster_sum latch state at that time.

| Group (rows fitted) | continuous | discontinuous |
|---|---|---|
| monomer peaks + `monomer_sum` | secondary_pfo | secondary_pfo (placeholder) |
| cluster peaks + `cluster_sum` | pfo | pfo (placeholder) |

The discontinuous entries are placeholders until the before/after-detection models
exist (four equations: two sums × two regimes). Fits are rolling (an expanding window
at every unique time, live `latest_only=False`). The secondary_pfo p0 search starts
fresh at every point, as live does; `--use-prior-p0` turns carry-forward on.
Unknown-group peaks get areas but no fits.

## 3. Validation (details in `spec-working.md`)

| Check | Result |
|---|---|
| Timeline `Time_Delta` vs saved live params, all 7 datasets | 24,199/24,199 exact |
| Area builder vs live area CSVs (live params, `voigt_fit` groups), nn1120-3_004 | 34/34 identical (float rounding) |
| Kinetic fits vs live `append_fit_results(latest_only=False)`, `004-019`, all peaks | all 20 kinetic columns bit-identical, 453 rows |
| Written `classification` vs harness verdict, nn1120-3_004 | 34/34 agree, never reverts |
| Harness `combined`: live / refit 9-peak / refit 15-peak | 285 / 275 / 257 of 288 |

## 4. Open

- Classifier on the refit 15-peak `cluster_sum`: 257/288 (21/48 discontinuous found).
  The low band grows and fills in the nn1120-4 drawdown hump. Accepted for now;
  retuning is separate work.
- secondary_pfo returns NaN when `monomer_sum` is all ≤ 0 (inverted `q_e` bound), as
  live does. This affects 14/296 refit files.
- The discontinuous-regime models (above).
