# Kinetics reprocessing on refit data (working spec)

**Status: in build (started 2026-09-29).** This is the working spec, following the
`ir_fitting` convention: a working spec while building, then a condensed `spec.md`.
The progress log at the bottom records what has landed and the measured results.

## Context

The 24-peak refit (`src/utils/ir_fitting`) has been run over all 7 datasets into
`C:\Data\peakFit\<dataset>\_reprocess\`. Kinetics (`src/utils/kinetics`) must now be
rerun on that data, with redefined sums, and the new classifier
(`classify_trajectory_combined`) must be confirmed to still classify correctly on
the new areas.

**Scope of this round:** build what is known to be needed. The model redesign for
discontinuous trajectories comes later and is out of scope here. That redesign means
four equations: monomer_sum and cluster_sum, each before and after detection. The
build should leave a clean seam for it, but must not attempt it.

Recon found three blockers:
1. **Nothing turns refit params into areas.** `_reprocess/` holds only
   `*_CarbonylPeakFitParams.csv`. Every kinetics entry point reads `*_CarbonylPeakArea.csv`.
2. **The written `classification` column is not what is validated.** The writer stamps one
   full-trajectory label on every row. The 285/288 harness scores a causal prefix sweep
   that latches after 3 consecutive fires.
3. **Sum groups come from the `voigt_fit` block of `analysis.yaml`** (live), and the classify
   path and harness can't see a redefined `cluster_sum` at all.

## Decisions (agreed)

- `cluster_sum` = the 15 cluster peaks of `ir_fitting.fit`.
- `monomer_sum` = Peak_2113 / 2103 / 2093.
- Groups are read from the `ir_fitting.fit` block and baked into the new area CSVs.
- `classification` = a causal per-row latch (3 consecutive fires). Label names stay as they are for now.
- Output is one live-equivalent file per measurement.
- Areas go to `<dataset>\_reprocess\`. Kinetics go to `<dataset>\_reprocess\_test\`.
- First folder: `nn1120-3_pd_ceo2_004`.
- **Every spectrum gets a time, fit or no fit.** The time axis comes from a per-spectrum timeline, never from which params rows happen to exist (step 1a).
- Models, unchanged from live: monomer peaks + `monomer_sum` get secondary_pfo; cluster peaks + `cluster_sum` get pfo.
- After the latch, rows get the same continuous-model fit as placeholders. The four-equation work replaces them later.
- Fits cover the sums plus all 18 atomic group peaks (3 monomer + 15 cluster). Unknown-group peaks keep their areas and get no fits.
- **The user makes all commits.** I do not run `git commit`.

## Build steps

### 0. `src/utils/kinetics/spec-working.md`
- Capture this plan there first, following the `ir_fitting` convention of a working spec plus a final condensed spec.
- Keep it updated as steps land, including the cleanup ledger (§7).

### 1a. Timeline: new `src/utils/kinetics/timeline.py`

**Why.** Cumulative `Time (s)` is a running sum of `Time_Delta (s)` over a delta group's params rows, so a spectrum with no row (a failed or unrecorded fit) silently drops its time step and every later time shifts. Recon across all 7 datasets found:
- **200 refit spectra with NaN `Time_Delta`.** The refit copies time from the saved live rows (`runner._carry_file_columns`), so it gets NaN wherever live never recorded the spectrum:
  - 58 spectra in 14 measurements;
  - all of nn1120-2 `-001`/`-002` and nn1120-3_003 `-072`.
- The same gap means the **live `*_CarbonylPeakArea.csv` times are already shifted** in those 14 measurements, and the ground truth was labeled on them.
- 1 refit failure (nn1120-4 `-000` delta8.0130): a 14,400 s shift for the rest of that delta group.
- 11 spectra of nn1120-4 `-041` fitted live but not refit. The measurement was probably still acquiring when the refit ran.
- 3 corrupted `File` values in the live params (`.638`, `99.548`, `146918916` in nn1120-3_003 `-027/-038/-106`).

**What.** `build_timeline(folder, measurement)` returns one row per subIFG spectrum:
- It uses the same discovery as the refit: isoX excluded, `manually_skip_files` applied.
- `Time_Delta (s)` comes from the subIFG log + exp params, via the live `src/analysis/io.py` loaders and `spectral_fitting.resolve_time_delta`. That is the same computation live used, but run for every spectrum.
- Gate: timeline `Time_Delta` equals the saved params `Time_Delta` wherever both exist.

### 1. Area builder: new `src/utils/kinetics/areas.py`
- Walk the **timeline**, not the params rows. Every spectrum advances cumulative time.
- A spectrum with no params row gets a row with the correct `Time (s)` and NaN area. Later cumulative areas lack its (unknown) increment. That is left as is, with no interpolation, and the gap count is logged per delta group.
- Kinetics already drops NaN-area rows before fitting, so the NaN rows break nothing downstream.
- Per-peak cumulative rows come from `src/analysis/output.py::compute_cumulative_peak_area_df`, reused by import.
  - Its monomer list is a parameter, but its cluster_sum goes through `kinetics_fitting.build_cluster_sum`. That function always reads `voigt_fit.cluster_peaks_base` and has no override.
  - So drop both synthesized sums and rebuild them with `_KineticUtilities.append_sum_rows(monomer_sum_peaks=, cluster_sum_peaks=)`.
- Group names come from `src/utils/ir_fitting/config.py::get_group_peaks` + `peak_name`.
- `build_folder_areas(dataset, input_subfolder="_reprocess")` logs one warning per missing params row.
- **Parity gate:** run the builder on the source params of all 34 `nn1120-3_pd_ceo2_004` files with the `voigt_fit` groups, and diff against the source `*_CarbonylPeakArea.csv` on the first 7 columns.
  - For measurements with no gaps, the gate is equal rows and a max abs diff of about 0.
  - Measurements with gaps are expected to differ, only in time after the gap. Report them rather than force them to match.

### 2. Group source switch: `utils.py`
- `get_peak_names` / `get_monomer_peak_names` read `ir_fitting.fit`. This decides which atomic peaks get which model.

### 3. Causal latch, one function shared by harness and writer
- Extract the prefix sweep from `validation.ever_fires` into `classification.latch_sweep(...)`. It returns the latch index plus the classify result at that prefix.
- `ever_fires` wraps it.
- `writer._classification_payload`, cluster_sum only:
  - Rows before the latch get `continuous`.
  - Rows from the latch on get `discontinuous`, with `growth_onset_s` and `pre_/post_*` from the latching result.
  - Rows below `min_points` get NaN.
  - Duplicate Delta_Group times take the state after their last row.

### 4. Validation on new data: `validation.py` + `classify_cli.py`
- `run_validation(..., input_subfolder=None, cluster_sum_peaks=None)` and `--input-subfolder`.
- Mismatches are also reported grouped by ground-truth `basis`.
- Ground truth is not edited without the user.

### 5. Live-equivalent kinetics run: `api.py`, `writer.py`, `fit_cli.py`
- One per-measurement entry point: each group gets its model per the decisions above, plus the causal classification.
- It is built fresh from the area CSV. This is the replacement for the merge-onto-input `write_fit_params_to_legacy`.
- Structure the per-group model assignment as a small table keyed by `(group, regime)`, where regime is `continuous` or `discontinuous`. The later four-equation work then only fills in entries.
- `_discover_area_csvs(dataset, input_subfolder=None)`:
  - With `input_subfolder`: non-recursive glob of that folder only.
  - Without it: also exclude `_reprocess`.
- Lower priority by default, reusing `ir_fitting/refit_cli.py::_lower_priority`, with a `--normal-priority` opt-out. Fit once per file, not twice.

### 6. Docs
- `src/utils/kinetics/spec.md`: the sums are now fixed in the area CSV, which reverses its "sums are a fitting concern only" line.
- Fix the `docs/spec.md` references to point at `docs/spec_nuc-clf.md`.
- Update CLAUDE.md's kinetics paragraph, including its stale `kinetic_fit_writer.py` mentions.

### 7. Cleanup ledger (ongoing)
Remove as the surrounding code is touched. Record each removal in spec-working.md.

| Candidate | Why it is legacy | Action |
|---|---|---|
| `remove_legacy_pfo_columns_file/folder` (`api`, `writer`, `__init__`) | One-off column migration. Outputs are now built fresh. | Remove |
| `legacy_pfo_columns` list + `write_fit_params_to_legacy` merge-onto-input | Only needed when merging onto old CSVs | Replace in step 5 |
| `_prepare_model_rows_for_file` | Pass-through wrapper | Remove |
| `full_series` mode (duplicated loop body, no live equivalent) | Rolling covers it | Remove, or reduce to "last row only" in the rolling loop |
| Single-model `fit_file`/`fit_folder` + separate classify CLI | Superseded by the per-measurement entry point | Fold into one CLI, keeping `--validate` |
| `classify_trajectory_sustained_rise` | Tried and was net worse (spec_nuc-clf §6.2) | Remove. Keep `default` + `drawdown` as `combined`'s parts |
| Hardcoded `FLAT_WINDOW_S`… in `classification.py` | `kinetics_classification:` yaml block exists but is unread offline | Read yaml |
| `monomer_features.py` | Research module from an iterate loop; nothing imports it | Leave. Revisit at the four-equation stage |
| `sys.path` bootstraps in every module | Only entry scripts need them | Trim where touched |

## Verification (nn1120-3_pd_ceo2_004 first)

1. The area-builder parity gate passes.
2. `--validate` on source data still gives **285/288**, which confirms the latch refactor changed nothing.
3. Harness results table:

   | Input | Result |
   |---|---|
   | source, 9-peak | 285 baseline |
   | refit, 9-peak | scratch script via kwarg |
   | refit, 15-peak | the chosen definition |

4. In each written file, the final-row `classification` equals `ever_fires` for that file.
5. The per-measurement kinetics run on 004 → `_reprocess\_test\`. Check that:
   - the column set is a superset of the live PeakArea columns;
   - every group peak and both sums have rows;
   - median r² sits beside the source values.
6. **Stop and report.** Other folders run one at a time after confirmation.

## Out of scope
- The discontinuous-regime models (the four equations) and the label rename.
- `src/analysis/`, `voigt_fit`, and the live path.
- Retuning `rise_delta` or the classifier.
- Labeling the 6 unlabeled nn1120-4 files and the 3 refit-only measurements.

## Progress log

- 2026-09-29: working spec created (step 0).
- 2026-09-29, step 1a (`timeline.py`): spectra come from the subIFG log (the record of
  every subtraction), plus any extra file on disk. Gate over all 7 datasets, 297 measurements:
  24,199/24,199 spectra match the saved live `Time_Delta` exactly, with 0 NaN and 0 errors.
  58 spectra are timeline-only (never recorded live) and now get real times.
  nn1120-2 `-004` delta8.0026 is logged and was fitted live, but its file is gone from disk.
- 2026-09-29, step 1 (`areas.py`) and step 2 (`utils.group_peak_names`):
  - Parity against the live area CSVs, built from live params with the `voigt_fit` groups.
    `nn1120-3_pd_ceo2_004`: 34/34 identical (rows equal; max diff 6e-11 s, 4e-16 au).
  - `nn1120-3_pd_ceo2_000` differs, and every difference is explained:
    - Older live files did not add the delta1 seed (the two delta1 `Time_Delta`s,
      e.g. 36.838 + 59.672 = 96.51 s) to `Time (s)`, so they sit 97–120 s early.
      Current live code does add it.
    - Gaps: live time is shifted by the missing step (e.g. `-010`: 14,400 s); ours is not.
    - Failed live fits have a params row with NaN `Peak_Area`. Live carried the previous
      cumulative value forward; ours gives NaN area at the correct time.
    - Areas agree to 2e-15 everywhere else.
  - Refit areas built for `nn1120-3_pd_ceo2_004` → `_reprocess\`: 34 files, 0 gaps,
    26 `Peak_Name`s (24 peaks + 2 sums).
  - Note: the refit copies `Data_Integral` from the live rows too, so
    `Cumulative_Integral` lacks the step of any spectrum live never recorded.
    Kinetics does not read it.
  - Cleanup: `build_cluster_sum`/`build_monomer_sum` merged into `build_group_sum`.
    `get_peak_names`/`get_monomer_peak_names` were replaced by `group_peak_names`, which
    drops the `src.analysis.spectral_fitting` import.
- 2026-09-29, steps 3–4 (latch + harness):
  - `classification.latch_sweep` / `sorted_trajectory` are shared; `ever_fires` wraps them.
  - `run_validation` gains `input_subfolder`, `cluster_sum_peaks`, `folders`, and a `basis`
    breakdown. An errored file now scores wrong; before, it counted as a quiet `continuous`.
  - Source data still scores 285/288, with the same 3 mismatches (`003-109` FP, `004-014` miss, `004-031` FP).
- 2026-09-29: refit areas built for all 7 datasets → `_reprocess\` (296 files).
  - `003-072` has only delta1 spectra, so it gets no area rows and nothing is written.
  - Spectra without a fit: nn1120-2 `-004` delta8.0026 (file gone), nn1120-4 `-000`
    delta8.0130 (SVD failure), and 11 spectra of nn1120-4 `-041` (not refit).
- 2026-09-29: **classifier on refit areas, all 288 files** (`combined`, latch 3):

  | Input | Correct | Hit | Missed | FP |
  |---|---|---|---|---|
  | source, 9-peak | 285/288 | 47 | 1 | 2 |
  | refit, 9-peak | 275/288 | 40 | 8 | 5 |
  | refit, 15-peak | 257/288 | 21 | 27 | 4 |

  By folder (source9 / refit9 / refit15):

  | Folder | source9 | refit9 | refit15 |
  |---|---|---|---|
  | nn1120-3_003 | 116/117 | 111/117 | 107/117 |
  | nn1120-3_004 | 32/34 | 30/34 | 30/34 |
  | nn1120-4_000 | 33/33 | 30/33 | 16/33 |
  | the other 4 | all correct | all correct | all correct |

  Diagnostic on the missed files:
  - **nn1120-4:** the 9-peak sum keeps its rise-then-decay hump (rise ≈ 0.3, drawdown ≈ 0.15 au).
    The 6 low-band peaks grow steadily (+0.3 au net, mostly 1928/1913), fill in the drawdown,
    and remove the hump the drawdown rule keys on.
  - **nn1120-3_003** (`-091/-094/-098/-110`): these already miss with the refit 9-peak sum.
    The low band there is flat (about 0 net), so the refit's re-apportioned cluster areas are the cause.
  - The kinetics writer (step 5) is **paused** pending a decision on the classification trajectory.
- 2026-09-29: user decision: classification runs on the 15-peak `cluster_sum`, and 257/288 is
  accepted for now. Retuning the classifier is later, separate work.
- 2026-09-29, step 5 (new path, `writer.py` / `api.py` / `fit_cli.py`):
  - `REGIME_MODELS` is the `(group, regime) → model` table; the discontinuous entries are
    placeholders.
  - `classify_by_time`: the causal per-time label from `latch_sweep`.
  - `_fit_trajectory_rolling`, `prepare_measurement_rows`, `write_measurement`.
  - `api.build_areas` / `process_file` / `process_folder`. `_discover_area_csvs` takes
    `input_subfolder` and excludes `_reprocess` otherwise.
  - The fit CLI is rewritten around this path.
  - **Parity with live `kinetics_fitting`** (live area rows of `004-018`/`-019`, `voigt_fit`
    groups, no p0 carry-forward):
    - pfo parameters agree to about 7e-6 relative; r² to 1e-8.
    - secondary_pfo first matched on only ~80% of rows. Cause: `sorted_trajectory` used a
      stable sort while live uses pandas' default, so rows sharing a time reached the
      objective's sum in a different order. The last-bit differences steered L-BFGS on
      ill-conditioned rows.
    - After switching to live's sort, `monomer_sum` on `004-019` is bit-identical
      (30/30 rows, max diff 0). Each path is deterministic run to run; there were no
      ODE timeouts.
  - **Open (model, not this build):** secondary_pfo returns NaN for the whole trajectory when
    `monomer_sum` is all ≤ 0. `q_e`'s bound `(0, 2·max(y))` is inverted and `minimize` raises.
    Live does the same. This affects 14/296 refit files (15/295 live), e.g. `004-018`.
    It belongs to the model redesign.
- 2026-09-29, step 5 verified:
  - Full `004-019` parity against live `append_fit_results(latest_only=False)`: all 20 kinetic
    columns bit-identical over 453 rows (pfo 300, secondary_pfo 150, stderr included).
  - The classifier comparison is unchanged by the sort switch (285 / 275 / 257).
  - `--classify-only` over nn1120-3_004 → `_reprocess\_test\`: 34/34 files' final-row
    label equals the harness verdict (10 latched), and the label never reverts.
  - `pre_*`/`post_*` columns appear on latched files only, as in live.
- 2026-09-29, cleanup (step 7), as a separate pass after the new path was verified:
  - `writer.py` 704 → ~425 lines. Removed `prepare_model_fit_rows` (with `full_series`),
    `prepare_pfo_classification_rows`, `write_model_fit_params`,
    `write_sum_model_fit_params`, `write_pfo_classification`, `_classification_payload`,
    `_prepare_model_rows_for_file` and `remove_legacy_pfo_columns_file`.
  - `utils.py`: removed `write_fit_params_to_legacy` (the merge-onto-input and
    legacy-column drop list), `drop_columns_with_prefixes` and `write_plain_legacy_output`.
  - `api.py` / `__init__.py`: removed `fit_file`, `fit_folder`, `fit_folder_by_sum_models`,
    `classify_file`, `classify_folder`, `remove_legacy_pfo_columns_*` and the
    edit-constants `__main__`. Exports are now `build_areas`, `process_file`, `process_folder`.
  - `classification.py`: removed the sustained-rise detector. Thresholds are read from the
    yaml `kinetics_classification` block (same values; live reads the same block).
  - `classify_cli.py`: validation only; `--path`/`--folder` point to the fit CLI.
    `fit_cli.py` was rewritten.
  - `sys.path` bootstraps removed from non-entry modules (`api`, `utils`, `writer`,
    `classify_cli`). The `scripts\` entry points still set the path.
  - Docs: `spec.md` rewritten and condensed; CLAUDE.md kinetics sections updated;
    stale `docs/spec.md` / `docs/JOURNAL.md` references fixed.
  - Left alone: `monomer_features.py` (a research module), and the pre-existing lint in
    the detector and model code.
- 2026-09-29, post-cleanup: `--validate` on live data still gives 285/288, and the CLI smoke test
  (`004-019`, cluster_sum fit and `--classify-only`) passes. All-NaN metric summaries are
  now skipped.
- 2026-09-29, **cost of the full run (blocking)**: rolling secondary_pfo on `monomer_sum` alone
  for `004-008` (refit, 271 time points), at below-normal priority, took **4,808 s (80 min)**
  and hit **165 ODE timeouts** (0.1 s wall-clock each).
  - A full file has 4 secondary_pfo trajectories (3 monomer peaks + `monomer_sum`), so
    roughly 5 h per long file, about 2–3 days for nn1120-3_004, and weeks for all 296 files.
  - Under load the timeouts make results depend on machine load, not just the data.
    The bit-identical parity above held only because those runs had 0 timeouts.
- 2026-09-29, the user asked for parallel workers (the refit ran N=8 on this PC):
  - `process_folder(workers=N)` / `--workers N`: one process per measurement, spawn
    context, BLAS pinned to 1 thread, below-normal priority inherited (mirrors
    `ir_fitting.api._fit_parallel`).
  - The classifier is now passed by name (`writer.CLASSIFIERS`), so it pickles into workers.
  - Each file counts its secondary_pfo ODE timeouts and reports them (`N ODE timeouts`).
  - Smoke test: `--classify-only --workers 4` on nn1120-3_004, 34/34 files in 4 s.
  - Full fit of `004-019` + `004-035` with `--workers 2`: 8 min wall time, 0 ODE timeouts.
    `-035` rerun serially into `_test-serial\` is identical to the parallel output
    (1,378 × 29, max diff 0). Short files (~40–50 time points) take about 6.5 min serially.
- 2026-09-29: removed the unused user `p0` argument from `prepare_measurement_rows` /
  `_fit_trajectory_rolling` / `_select_secondary_p0_for_secondary` (no caller or flag used it).
  The secondary_pfo p0 search still starts fresh from its defaults, or from the carried-forward
  seed with `--use-prior-p0`. Check: `004-035` `monomer_sum` rerun matches the pre-change
  output to 1e-16, which is CSV round-trip precision.
