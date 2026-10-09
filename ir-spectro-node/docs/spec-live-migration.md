# spec-live-migration — move the reprocessing defaults into the live path

Working spec. Started 2026-10-09 on `feature/kinetics-live`. It records the decisions
and status as the work goes. The finished design moves into the package specs
(`src/utils/ir_fitting/spec.md`, `src/utils/kinetics/spec.md`) and `src/analysis/.spec.md`.

**Goal.** Live (`src/analysis/`) should produce what the offline defaults produce
(`run_spectral_fit.py` and `run_kinetics_fit.py` with no flags). The user treats
those defaults as the correct settings.

**Order.**

1. Correct the offline reference into `_reprocess-v2` (§2).
2. Migrate live (§3).
3. Validate live against `_reprocess-v2` (§4).

---

## 1. Decisions

| # | Date | Decision |
|---|---|---|
| L1 | 10-09 | Copy code into `src/analysis/`, don't import from `src/utils/`. `src/utils/kinetics` already imports `src.analysis` (`areas.py`, `timeline.py`), so the reverse import would be circular. The repo already runs two implementations side by side. |
| L2 | 10-09 | **Keep the live peak detector.** In `peak_analysis`, when `find_peaks` finds no positive or negative peak in the baseline-corrected ROI (`voigt_fit.find_peaks.subifg`), the fit is skipped: shape params are NaN and `Peak_Area = 0`. Reason (user): runs are very long, and fitting noise would build up a false cumulative area. The offline refit had no detector, so it is added there too (§2). |
| L3 | 10-09 | Live seeds every peak from its yaml rule `value:` (unseeded; confirmed by the user 10-09). Offline seeded from the saved live fit of the same file, which doesn't exist live. Test, 13 spectra, median \|Δ\| vs `_reprocess`: monomer_sum 4.7e-4 unseeded vs 4.5e-4 seeded from the previous spectrum; cluster_sum 2.7e-4 vs 7.9e-4; nfev 2.6k vs 5.3k. |
| L4 | 10-09 | Live kinetics are segments mode, rerun after every spectrum over the trajectory so far. The label is the causal label so far, so the results are provisional until the run ends. |
| L5 | 10-09 | The per-row rolling pfo/pfo-sec columns are removed from live `*_CarbonylPeakArea.csv`. |
| L6 | 10-09 | `plot_params` is not called by the migrated path. |
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

**Next.**
1. The user runs the full segments kinetics on `_reprocess-v2`:
   `run_kinetics_fit.py --folder <ds> --input-subfolder _reprocess-v2`.
2. Then the live migration (§3).

## 3. Live migration (not started)

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

## 5. Open

- **O1. FSD snapping is dead in live.** `find_fsd_peaks` returns array indices (0–258), but `resolve_peak_lists` (±5) and `resolve_temp_peak` (2169.5 ± 0.5) compare them to wavenumbers, so neither ever matches. Every peak keeps its nominal wavenumber. It's exposed in `ir_fitting` with `--fsd-snap`, comparing wavenumber to wavenumber; that is the intended behavior and is untested. Experiment before deciding: fix it in live, or remove it.
- **O2.** Why the partial-write fragments (§2.2) happened is unknown: `save_data` read-concat-writes the whole CSV each time. Possibly two writers at once.
- **O3. Resolved 10-09.** The refit reproduces `_reprocess` to 1e-16 (areas and baseline, 000-007 delta10.0042/delta5.0047), but only with BLAS pinned to one thread (`OMP/OPENBLAS/MKL_NUM_THREADS=1`), as `--workers` sets. Unpinned, BLAS thread rounding moves this ill-conditioned joint fit by ≤ 1e-3 au in area. So the current `ir_fitting.fit` rules are the ones that produced `_reprocess`, and porting them is correct. For §4, pin threads in the validation runs. Live will not be pinned, so expect ~1e-3 au agreement there, not bit-identity.
- **O4.** `_reprocess-v2` has params, areas and features only. It has no baseline or residual CSVs; those are still in `_reprocess`.
