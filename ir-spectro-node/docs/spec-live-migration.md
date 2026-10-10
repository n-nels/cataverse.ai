# spec-live-migration — move the reprocessing defaults into the live path

Working spec. Started 2026-10-09 on `feature/kinetics-live`. It records the decisions
and status as the work goes. The finished design moves into the package specs
(`src/utils/ir_fitting/spec.md`, `src/utils/kinetics/spec.md`) and `src/analysis/.spec.md`.

**Goal.** Live (`src/analysis/`) should produce what the offline defaults produce
(`run_spectral_fit.py` and `run_kinetics_fit.py` with no flags). The user treats
those defaults as the correct settings.

> **Naming, 2026-10-10.** The user consolidated each dataset to one flat
> `<dataset>\_reprocess\`: what this spec calls `_reprocess-v2` is now `_reprocess`.
> The old `_reprocess` and every `_test*` / `_reprocess-v2` subfolder are gone. It
> holds params, `peak_detector.csv`, areas, KineticParams and KineticFeatures; the
> full segments kinetics was rerun on it. The utils CLIs now read `_reprocess` and
> write derived files back into it in place; the refit still defaults to `_test`.
> `apply_peak_detector` (the one-off v2 builder) is removed. In the history below,
> "`_reprocess`" before this date means the old, pre-detector folder.

**Order.**

1. Correct the offline reference into `_reprocess-v2` (§2).
2. Migrate live (§3).
3. Validate live against `_reprocess-v2` (§4).

> [!WARNING]
> **`_reprocess` (formerly `_reprocess-v2`) and live do NOT fit spectra the same way. Do not mix them
> without accounting for this.**
>
> - **Live (deployed <TBD>)** starts every spectrum's fit from the yaml rule
>   `value:` (L3). That is the rule from now on.
> - **`_reprocess`, formerly `_reprocess-v2`** (= the old `_reprocess` params + the peak-detector zeroing, §2.1;
>   no refit) started each spectrum's fit from that file's old 18-peak live fit.
>   That start can't be reproduced live or in a future run.
>
> The 24-peak fit has several near-equal solutions, so the two can land on different
> area splits. On 000-000 (the only measurement compared, 148 / 24,583 spectra),
> 4 early spectra differ by 2–10% in monomer area. Cumulative areas carry that
> forward as a constant offset: −0.09 au on delta10, which is 100% of the late-run
> value there (§4.1, V2). Kinetics move by ~5% (k_a) to ~12% (depletion y_inf).
> How widespread this is across all datasets is unknown.
>
> **Consequences.**
> - Results from `_reprocess` and from live runs after <TBD> are not directly
>   comparable at the few-percent level.
> - Classification, onset, latch and segment boundaries matched on 000-000, so the
>   labels are not affected there.
>
> **Resolution (O7, not now):** refit all spectra with rule-value starts, so
> offline matches live.

---

## 1. Decisions

| # | Date | Decision |
|---|---|---|
| L1 | 10-09 | Copy code into `src/analysis/`, don't import from `src/utils/`. `src/utils/kinetics` already imports `src.analysis` (`areas.py`, `timeline.py`), so the reverse import would be circular. The repo already runs two implementations side by side. |
| L2 | 10-09 | **Keep the live peak detector.** In `peak_analysis`, when `find_peaks` finds no positive or negative peak in the baseline-corrected ROI (`voigt_fit.find_peaks.subifg`), the fit is skipped: shape params are NaN and `Peak_Area = 0`. Reason (user): runs are very long, and fitting noise would build up a false cumulative area. The offline refit had no detector, so it is added there too (§2). |
| L3 | 10-09 | Live seeds every peak from its yaml rule `value:` (unseeded; confirmed by the user 10-09). Offline seeded from the saved live fit of the same file, which doesn't exist live. Test, 13 spectra, median \|Δ\| vs `_reprocess`: monomer_sum 4.7e-4 unseeded vs 4.5e-4 seeded from the previous spectrum; cluster_sum 2.7e-4 vs 7.9e-4; nfev 2.6k vs 5.3k. On a full run (V2, §4.1) areas diverge more (cumulative monomer_sum up to 0.092), but the unseeded fits have equal or lower RSS: median ratio 0.98 vs `_reprocess`; lower in 76/148 spectra, higher in 18; 0.82 on the most divergent. Seeding would buy agreement with `_reprocess`, not better fits. |
| L4 | 10-09 | Live kinetics are segments mode, rerun after every spectrum over the trajectory so far. The label is the causal label so far, so the results are provisional until the run ends. |
| L5 | 10-09 | The per-row rolling pfo/pfo-sec columns are removed from live `*_CarbonylPeakArea.csv`. |
| L6 | 10-09 | `plot_params` is not called by the migrated path; `src/visualizations/plot_params.py` and its `paths.yaml` keys are deleted. |
| L7 | 10-09 | FSD snapping stays as it is in live for now (see O1). It is exposed in `ir_fitting` behind an opt-in flag (`--fsd-snap`), so it can be tested. |
| L8 | 10-09 | Drop the three corrupted live params rows (§2.2) from the source CSVs, with backups. |

## 2. Correcting the reference: `_reprocess` → `_reprocess-v2`

### 2.1 Peak detector

- `voigt.has_peaks` is a copy of the live detector. `ir_fitting.fit.find_peaks` is a copy of `voigt_fit.find_peaks`.
- `runner.fit_subifg_file` runs the detector on `raw − baseline` (the default recipe) before fitting. When nothing is found it writes live's skip rows: shape params NaN, `Peak_Area = 0`, residual 0. From now on a refit applies it by default.
- `api.apply_peak_detector(folder, input_subfolder="_reprocess", output_folder="_reprocess-v2")` runs the detector on every spectrum of an existing refit **without refitting**. Rows where it fires are zeroed. All other rows are copied unchanged. It writes the params CSV only.
- The detector runs on the *new* baseline, so the files it fires on are not the same as live's 91. Live's detector ran on the old baseline.

### 2.2 Corrupted live params rows

Three rows in nn1120-3_pd_ceo2_003's live `*_CarbonylPeakFitParams.csv` have a garbage `File`. Each is the tail of the row above it, on a line of its own (a partial write). They hold no data. `_reprocess` has none, because the refit is keyed by subIFG file.

| Measurement | Line | Content | Tail of |
|---|---|---|---|
| `20250916_120524_pd_ceo2_003-027` | 1280 | `.638,0.0058402021489837,,,…` | a `16199.638` row |
| `20251008_152546_pd_ceo2_003-038` | 1280 | `99.548,0.0014077622857566,,,…` | line 1278 (`…16199.548,0.0014077622857566`) |
| `20260129_070735_pd_ceo2_003-106` | 2 | `146918916,16199.655,0.0070001968487913,,,…` | a `16199.655` row |

Fix: delete those lines byte-exact. The originals are kept under `<dataset>\_backup_corrupt_rows\`. Derived live outputs don't change, since the rows have no `Peak_Name`.

### 2.3 Rebuild and rescore

For each dataset:

1. Run `apply_peak_detector`.
2. Run `run_kinetics_fit.py --folder <ds> --input-subfolder _reprocess-v2 --build-areas --classify-only`.
3. Run `run_kinetics_classification.py --validate --input-subfolder _reprocess-v2` (baseline: 287/289 on `_reprocess`).
4. Run the full segments kinetics. This is slow, so it is started by the user (kinetics spec D16).

### 2.4 Status (2026-10-09): steps 1–3 done; step 4 not started

**Corrupted rows (§2.2).** Removed. Backups are in
`nn1120-3_pd_ceo2_003\_backup_corrupt_rows\`. A rescan of all 299 live params CSVs
finds 0 bad `File` values.

**Detector pass** (`apply_peak_detector`, all 7 datasets, ~20 min at below-normal
priority). It zeroed **299 / 24,583 spectra**, and no subIFG file was missing.
The per-spectrum record is `<dataset>\_reprocess-v2\peak_detector.csv`.

| Dataset | Spectra | Zeroed |
|---|---|---|
| nn1120-2_000 | 2573 | 37 |
| nn1120-3_000 | 672 | 11 |
| nn1120-3_001 | 3663 | 73 |
| nn1120-3_002 | 288 | 0 |
| nn1120-3_003 | 8705 | 30 |
| nn1120-3_004 | 4695 | 28 |
| nn1120-4_000 | 3987 | 120 |

Overlap with live's own skips, which used the old baseline: live skipped 161,
v2 zeroed 299, and both include 124. The baseline change moves the set, as
expected.

**Areas and features.** Built for 299 measurements: `--build-areas --classify-only`
into `_reprocess-v2\_test`. Three more than §3 of the kinetics spec, because
nn1120-4_000 has new runs.

**Rescore.**
- Nucleation `--validate --input-subfolder _reprocess-v2`: **287/289**. These are
  the same two misses as `_reprocess` (003-077 FP, 003-102 missed).
- `--validate-spikes`: 66/66.

**Features changed, v2 vs `_reprocess`.** No `classification` and no
`spike_detected` changed. Out of 296 files, 10 have other changes:

- `growth_onset_s`: 003 `20260223_215629`, 480 → 1200 s.
- `monomer_max_s` in 9 files. Three of them move off the first row (≈420 s) to
  40–100 ks: 004 `20260505_063850`, 000 `20260804_234155`, 000 `20260813_195617`.

All 9 `monomer_max_s` files are continuous. Continuous files get one `adsorption` segment, so their segment fits don't change. The only discontinuous change is 003-119 (`20260223_215629`), whose growth onset moves from 480 s to 1200 s, which moves its segment boundary.

**Segments on the 8 D24 test files** (`_reprocess-v2\_test` vs `_reprocess\_test`, 10-09):
- Segment boundaries are identical in all 8.
- 003-097, 004-008 and 004-013 are bit-identical: no spectra were zeroed there.
- Sum R² moved only in 000-028 (cluster `ripening` 0.698 → 0.736, monomer
  `depletion` 0.990 → 0.982; 3 spectra zeroed) and 000-014 (monomer `adsorption`
  0.947 → 0.942; 5 zeroed).
- The large constituent ΔR² are on fits that were already poor (R² < 0, e.g.
  000-028 Peak_1849 ripening −3.1 → −5.3).
- 000-026 had nothing zeroed but still moved by ≤ 7e-3 in R². That is
  secondary_pfo ODE-timeout noise.

**Done 10-10.** The user ran the full segments kinetics on all datasets, then
consolidated the folders (see the naming note at the top).

## 3. Live migration (implemented 2026-10-09, not yet deployed)

| Area | Change |
|---|---|
| `scripts/run_server.py` | BLAS pinned to one thread (`OMP/OPENBLAS/MKL_NUM_THREADS=1`), so a refit is reproducible (O3) |
| `config/analysis.yaml` | `voigt_fit` = `ir_fitting.fit` values + `baseline_recipe` (anchors, cut, guard). `kinetics_classification` = `kinetics_reprocess_classification` values. New `kinetics_segments` = `kinetics_reprocess_segments` values. The voigt_fit rules for 1790–1800 / 1770–1780 had no peak and are gone. Peak_1988's center window is now −4/+1 (was −1/+1), as offline |
| `src/analysis/baseline.py` (new) | Port of `BaselineVariant()` (`compute_baseline`) |
| `spectral_fitting.py` | `least_squares` (`FIT_METHOD`); `combined_voigt` calls `voigt_model` directly. Detector and FSD unchanged |
| `classification.py` (new) | Port of the offline detector + `classify_by_time` (verbatim apart from the yaml key) |
| `segments.py` (new) | Port of `SegmentWriter`: `kinetic_features`, `plan_segments`, `detect_spike`, `fit_segment`, `compute_segment_kinetics` |
| `kinetics_fitting.py` | Removed: old `classify_trajectory` and helpers, rolling `_prepare_*_fit_rows`, `append_fit_results`. Added: `exp_decay`, `fit_exp_decay_with_errors`, `classify_area_rows`. pfo `maxfev` 20000 → 500, offline's value |
| `output.py` | `compute_kinetics_outputs` → `KineticsOutputs` (peak area + params + features); `save_kinetic_params_df` / `save_kinetic_features_df` (suffixes from `paths.yaml`) |
| `main.py` | New baseline; kinetics recomputed whole every spectrum, writing all three files; `run_kinetics_fit(path_or_df, measurement)` returns `KineticsOutputs` |
| `src/instrument/server.py` | `end_experiment` no longer calls `plot_params_folder` / `plot_params_all` (L6) |
| `scripts/run_analysis.py` | Batch writer updated for `KineticsOutputs` |

**Deploy.** Restart `run_server.py` only between measurements: a running process
keeps the old code and the cached yaml, and a params CSV mixing 18- and 24-peak rows
breaks the cumulative history.


- **Config.** `ir_fitting.fit` values go into `voigt_fit`: 24 peaks, the groups (2175 → unknown, 6 new cluster peaks), rules, baseline. The live classification gets the `kinetics_reprocess_classification` values. The offline blocks are left as they are.
- **Spectral fit.**
  - Baseline: the `BaselineVariant()` recipe.
  - Optimizer: `least_squares`.
  - Fit: the direct `combined_voigt`.
  - Kept as they are: the peak detector, `Data_Integral`/`Time_Delta`/`PdCO_mol`, and FSD (L7).
- **Kinetics.** The `classify_nucleation` + latch classifier: `classification`, `growth_onset_s` and `latch_time_s` on `cluster_sum` rows, with no `pre_`/`post_` columns. Segments write `*_CarbonylKineticParams.csv` / `*_CarbonylKineticFeatures.csv` next to the PeakArea file. Time stays a running sum over params rows: live has no log-based timeline, because the log lists spectra not yet fitted.
- **Cutover.** Switch between measurements. A params CSV that mixes 18- and 24-peak rows breaks the cumulative history.

## 4. Validation plan (live vs `_reprocess-v2`)

- **Baseline:** identical to `_reprocess` `*_CarbonylFitBaseline.csv` on the 8 default files.
- **Fit:** compare live unseeded with `_reprocess-v2`. Expect differences at the L3 level, plus `Data_Integral`, which `_reprocess` copied from live old-baseline rows.
- **Areas, classifier, segments:** run on `_reprocess-v2` params through the live code; the result should match `_reprocess-v2` areas, `classification` and segment params.
- Write to a scratch `data.peak_fit` (config shim), never to `C:\Data\peakFit\<dataset>`.

### 4.1 Results (2026-10-09, BLAS pinned, below-normal priority, scratch output)

| Check | Result |
|---|---|
| V1 baseline, 8 default files: live `compute_baseline` vs `_reprocess` | max \|Δ\| 1e-16 |
| V3a classification: live `classify_by_time` vs offline, on every `_reprocess-v2` area CSV | 299/299 identical |
| V3b segments, 8 D24 test files: live `compute_kinetics_outputs` on v2 areas vs `_reprocess-v2\_test` | same rows and segments; features identical (one value 1 ulp from the CSV round trip); params ≤ 3.7e-9, except secondary_pfo on 004-013 at 1.2e-4 (its known ODE timeouts) |
| V2 full live fit, 000-000 (148 spectra, ~4 s each): `DataAnalysisRunner.run_spectral_fit` vs `_reprocess-v2` | see below |
| V4 incremental live path with kinetics, 000-000 | see below |

**V2 detail.**

Matches:
- `Time_Delta` and area `Time (s)` are identical.
- The skipped spectra are identical (delta5.0087, delta5.0152).
- Live also fits delta8.0130, which the refit lost to an SVD failure (kinetics spec §3).
- Classification, growth onset, latch time, monomer max, depletion start, spike flag
  and every segment boundary are identical.

Differences:
- **Peak areas follow L3, the unseeded start.** Median \|Δ\| per peak is 2e-4, but the
  max is 0.045, concentrated in a few early high-signal spectra (delta10.0032,
  delta9.0029). There the unseeded fit stops with parameters on their bounds
  (sigma 6.37, center 2114.0), where the seeded fit found interior values.
- Cumulative monomer_sum differs by up to 0.092; cluster_sum by up to 0.015. The
  "range 0.09–1.57" first given here understated it. The monomer offset is set by 4
  early spectra (Δ monomer area: delta10.0032 −0.066, delta7.0030 −0.028,
  delta9.0029 −0.013, delta6.0032 −0.012, each ~2–10% of that spectrum's monomer
  area; the other 144 spectra are within 0.01). A cumulative sum carries each one
  forward, so it is a constant offset for the rest of the run: −0.09 on delta10,
  −0.03 on delta6/7/8, −0.015 on delta9, −0.004 on delta5. Late in the run,
  cumulative monomer has fallen to 0.09–0.19, so the offset is 2–23% of the value,
  and 100% on delta10 (live −0.002 vs v2 0.087). Those 4 spectra have RSS 0.81–0.85×
  `_reprocess`. Kinetics on monomer_sum: supersaturation k_a 2.29e-4 vs 2.18e-4,
  q_e 2.12 vs 2.20; depletion y_inf 0.197 vs 0.224, k 5.59e-5 vs 5.52e-5.
- Spike prominence is 9.7 vs 10.7 (still detected). Monomer depletion R² is 0.937 vs
  0.952; cluster pre_nucleation 0.934 vs 0.937.

**V4 found a bug, now fixed.** At the third spectrum each trajectory has one point.
`segments.smoothed_max` got an all-NaN smoothed array and `nanargmax` raised. That
happened after the params CSV was written and before the area, residual and baseline
files, so a spectrum's outputs would have been dropped.

Fixes:
- `smoothed_max` and `detect_spike` return NaN / a note when nothing is smoothable.
  This is applied to the offline `segments.py` too; no result that worked before
  changes.
- `main.run_spectral_fit` catches a kinetics failure, prints it, and still writes
  the areas (without the label), residual and baseline.

After the fix, V4 on the first 200 files of 000-000 (56 spectra fitted, kinetics
after every one, ~11 s per spectrum by the end): no kinetics failure. The label
latches `discontinuous` with the same onset (2700 s) and latch time (14,701 s) as
the full run. All three kinetics files are rewritten each spectrum.

## 5. Open

- **O1. FSD snapping is dead in live.** `find_fsd_peaks` returns array indices (0–258), but `resolve_peak_lists` (±5) and `resolve_temp_peak` (2169.5 ± 0.5) compare them to wavenumbers, so neither ever matches. Every peak keeps its nominal wavenumber. It's exposed in `ir_fitting` with `--fsd-snap`, comparing wavenumber to wavenumber; that is the intended behavior and is untested. Experiment before deciding: fix it in live, or remove it.
- **O2. Partial writes: detection and a live fix in place (10-10); cause likely, not confirmed.**
  - **Likely cause: two overlapping writers.** A plain `to_csv` truncates and rewrites in place. If two
    processes rewrite the same CSV at once, the shorter write can land over the longer one, leaving the
    longer one's tail after its end. The next `save_data` reads that tail back as a row and rewrites it
    full width, which is the nn1120-3_003 signature (§2.2). This was reproduced in scratch with two file
    handles. A single writer that crashes leaves a truncated file, not a tail. Which second writer it
    was (a manual rerun during live? two servers?) is unknown.
  - **Detection:** `scripts/run_csv_check.py` (`src/utils/csv_integrity.py`), read-only. It checks
    `*_Carbonyl*.csv` for lines whose field count differs from the header, a missing trailing newline,
    blank lines, invalid `File` / `Delta_Group` / `Peak_Name` / `Measurement` keys, bad wide-file
    columns or wavenumbers, and duplicate `(File, Peak_Name)` rows. It exits 1 if anything is found.
    Example: `--all --subfolder _reprocess`.
  - **Scan, 10-10.**
    - `_reprocess-v2`, recursive: 983 files, 0 issues.
    - Live dataset folders: 1197 files, 6 files flagged, none of them a params CSV:
      - 003-106 PeakArea: 2 rows with an empty `File` (delta8, t = 3899.7 s). The file is stale (09-10),
        derived before the fragment fix.
      - 003-002 PeakArea: 43 duplicate `monomer_sum` rows, equal to 1e-16. That looks like sums computed
        twice, not a tear.
      - 000-014 residual: 134 rows with no wavenumber, which looks like a misaligned column concat.
      - 001-037 baseline and residual, and 003-004 residual: one trailing blank line each.
    - None was changed.
  - **Prevention (live, `output.write_csv`):** each CSV is written to a temp file next to it, then
    `os.replace`d. A reader or a second writer sees one writer's whole file, never a splice. If the
    replace keeps failing (a Windows reader holding the file), it retries 10 × 0.2 s, then falls back
    to the plain write so no output is dropped. `save_data` also keeps a copy
    (`<file>.unreadable-<timestamp>`) when the existing file can't be read, instead of silently
    replacing the history with the new rows only.
  - **Not covered:** two writers can still lose one of their updates (last one wins). Peak-heights and
    iso-exchange writers and the offline writers still write in place.
- **O3. Resolved 10-09.** The refit reproduces `_reprocess` to 1e-16 (areas and baseline, 000-007 delta10.0042/delta5.0047), but only with BLAS pinned to one thread (`OMP/OPENBLAS/MKL_NUM_THREADS=1`), as `--workers` sets. Unpinned, BLAS thread rounding moves this ill-conditioned joint fit by ≤ 1e-3 au in area. So the current `ir_fitting.fit` rules are the ones that produced `_reprocess`, and porting them is correct. For §4, pin threads in the validation runs. `run_server.py` now pins them too (§3), from its next start.
- **O5. Deploy blocker: graph-node reads per-row pfo columns.** `graph-node/src/graph_node/data/fits.py` takes the last-time row per peak of `*_CarbonylPeakArea.csv` and maps `pfo-sec_*` (and `knowledge/data_file_types.yaml` documents `pfo_*`, `pre_*`, `post_*`). It reads with `row.get`, so it won't crash, but AdsParams for runs under the new code would get None. Decided 10-10: graph-node will read only `*_CarbonylKineticParams.csv`. The user does that work separately; it is noted in `graph-node/spec.md` §7.8, and nothing is changed here.
- **O6. Deploy timing.** Measurement nn1120-4_000 `-046` was last written 2026-10-09 06:36. Restart `run_server.py` only after the measurement in progress ends.
- **O7. Refit all spectra with rule-value starts (deferred by the user 10-10).** This
  resolves the warning at the top. Add a rule-value start to `ir_fitting` (today
  `runner.saved_seeds` always seeds from the saved params) and make it the default.
  Then refit all 24,583 spectra into `_reprocess-v3`, with the detector and pinned
  BLAS, and rebuild areas, classification and kinetics.
  - Cost: likely about a day at below-normal priority on the lab machine; the user
    starts it.
  - It also measures how widespread the V2 discrepancy is.
- **O4.** `_reprocess-v2` has params, areas and features only. Its baseline and residual CSVs would be identical to `_reprocess`'s (no refit), so the user will copy them over later.
