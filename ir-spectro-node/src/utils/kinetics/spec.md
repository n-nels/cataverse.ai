# src/utils/kinetics — offline kinetics reprocessing

**Status: implemented. Verified on nn1120-3_pd_ceo2_004.** Offline only. The live
server never calls it, and it never writes into source data. Refit areas are built for
all 7 datasets. Full kinetic fits beyond the verification files are limited by
secondary_pfo cost (§5). Folders are run one at a time.

This file describes what the package does now. How it got here (what was tried,
measured and rejected) is in `context/2026-09-29-kinetics-reprocessing-on-refit.md`.
Classifier history: `docs/spec_nuc-clf.md` (the old cluster_sum rules) and
`docs/JOURNAL_nuc-clf-refit.md` (the current Peak_1988 detector).

**Purpose.** Rerun kinetics on the 24-peak refit (`src/utils/ir_fitting`, output in
`C:\Data\peakFit\<dataset>\_reprocess\`), with sums redefined from the refit's groups.
The output is live-schema, live-equivalent `*_CarbonylPeakArea.csv` files. This package
also holds the ground-truth harness for the nucleation classifier.

---

## 0. Read first

```bash
# 1. refit params -> area CSVs, then 2. classify + kinetic fits (live-equivalent)
uv run python scripts\run_kinetics_fit.py --folder nn1120-3_pd_ceo2_004 --build-areas
uv run python scripts\run_kinetics_fit.py --folder nn1120-3_pd_ceo2_004 --classify-only   # fast
uv run python scripts\run_kinetics_fit.py --folder nn1120-3_pd_ceo2_004 --measurements <base name>
uv run python scripts\run_kinetics_fit.py --folder nn1120-3_pd_ceo2_004 --workers 8   # one process per measurement

# Classification only (no fits) -> _reprocess\_test_classification\
uv run python scripts\run_kinetics_classification.py --folder nn1120-3_pd_ceo2_004

# Score the detector against ground_truth.json
uv run python scripts\run_kinetics_classification.py --validate --input-subfolder _reprocess
```

Other fit flags: `--peak-names` limits which rows are fitted, `--output-folder`
defaults to `_test`, `--use-prior-p0` seeds each p0 search from the previous point,
and `--normal-priority` turns off the below-normal default. Importable as
`from src.utils.kinetics import build_areas, process_file, process_folder`.

### Traps

- **Time never comes from params rows.** `Time (s)` is a running sum of
  `Time_Delta (s)`, so a missing or failed fit would shift every later time. The
  timeline (`timeline.py`) takes each spectrum's `Time_Delta` from the subIFG log
  instead. A spectrum with no fit keeps its time and gets NaN area. Its unknown area
  increment is simply missing from later cumulative values: no interpolation. Kinetics
  drops NaN-area rows before fitting.
- **Live area CSVs are not a clean reference for time.** In 14 measurements live never
  recorded some spectra, so their live times are shifted after the gap. Older live files
  also left the delta1 seed out of `Time (s)`, which puts them 97–120 s early. The
  ground truth was labeled on those live times.
- **The sums are fixed in the area CSV.** They come from the `ir_fitting.fit` groups
  (`_KineticUtilities.group_peak_names`): monomer = 2113/2103/2093, cluster = 15 peaks,
  including the six low-band peaks. There are no per-run sum flags. Rebuild the areas
  to change a sum. Live reads `voigt_fit` instead, so the two sides' sums differ by design.
- **`classification` is causal.** Each `cluster_sum` row carries the latch state as of
  that time (`classification.latch_sweep` of `classify_nucleation`: 3 consecutive
  fires, never reverts). The detector reads Peak_1988 and `monomer_sum`, not
  `cluster_sum` (§2a). The label is not a hindsight label, and it is the same sweep the
  ground-truth harness scores. Duplicate times take the state after their last row.
  `growth_onset_s` is the latch time. Unlike live, there are no `pre_*`/`post_*`
  columns.
- **Sort order is part of parity.** `sorted_trajectory` sorts exactly as live does.
  A stable sort changes floating-point sums enough to move ill-conditioned
  secondary_pfo fits.
- **secondary_pfo is slow**, and has a 0.1 s wall-clock ODE timeout per solve, so a
  heavily loaded machine can change results. Run at below-normal priority (the CLI
  default). `--workers N` runs N measurements at once, one process each, as the
  refit does. More load means more timeouts, which are reported per file
  (`N ODE timeouts`).
- **`Cumulative_Integral` is not rebuilt.** The refit copies `Data_Integral` from the
  live rows, so it lacks the step of any spectrum live never recorded. Kinetics does not
  read it.
- **Model changes land twice.** `models.py` duplicates live `kinetics_fitting`. A model
  change that lands on one side only makes the two disagree silently.

## 1. Pipeline

```
<dataset>\_reprocess\*_CarbonylPeakFitParams.csv         (refit output)
   │  timeline.build_timeline  (subIFG log + exp params → Time_Delta per spectrum)
   │  areas.build_peak_area_df (live compute_cumulative_peak_area_df on the full grid,
   ▼                            sums from ir_fitting.fit groups)
<dataset>\_reprocess\*_CarbonylPeakArea.csv
   │  writer.prepare_measurement_rows:
   │    classify_by_time   causal nucleation label on cluster_sum rows (latch_sweep)
   │    rolling fits       REGIME_MODELS[(group, regime)] per time point
   ▼
<dataset>\_reprocess\_test\*_CarbonylPeakArea.csv          (live schema)
```

Spectrum discovery matches the refit: isoX files excluded, `manually_skip_files`
applied. Each spectrum's time comes from the subIFG log, plus any extra file found on
disk. Outputs are built fresh per measurement, never merged onto an existing CSV.
`_discover_area_csvs` globs only `input_subfolder` when it is given, and otherwise
excludes `_reprocess`.

| Module | Role |
|---|---|
| `timeline.py` | One row per subIFG spectrum (from the log), with `Time_Delta (s)` from the live `io.py` loaders |
| `areas.py` | Params + timeline → area CSV. Logs one warning per missing params row |
| `classification.py` | `classify_nucleation` + `nucleation_trajectory`, `latch_sweep`, `sorted_trajectory`. Parameters come from yaml `kinetics_reprocess_classification` (offline only) |
| `models.py` | pfo and secondary_pfo (copies of live, same results) |
| `writer.py` | `REGIME_MODELS`, per-measurement classify + rolling fit + write; singletons |
| `api.py` | `build_areas`, `process_file`, `process_folder` (`workers=N`: spawn, BLAS pinned to 1 thread) |
| `validation.py` | Ground-truth harness (`run_validation`, `ever_fires`); an errored file scores wrong |
| `fit_cli.py` / `classify_cli.py` | The two CLIs (`scripts\run_kinetics_fit.py`, `scripts\run_kinetics_classification.py`: classification-only writes + `--validate`) |

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
Fits cover the 18 atomic group peaks (3 monomer + 15 cluster) and both sums. Peaks in
no group get areas but no fits.

## 2a. Classifier

`classify_nucleation` (from the nuc-clf-refit loop, `docs/JOURNAL_nuc-clf-refit.md`)
fires at a prefix when all three of these hold:

- **Rise.** For each `Delta_Group`, take the causal 3-point median of Peak_1988. Its
  newest value minus `max(0, min)` over the last 8 h is the group's rise. The median
  over groups must exceed 0.00275 au.
- **Monomer.** The median over groups of the newest smoothed `monomer_sum` is > 0.
- **Amplitude.** The median over groups of the smoothed prefix's max − min is
  ≥ 0.006 au. `zero_floor: false`, which is the round-3 form.

The values are in yaml `kinetics_reprocess_classification`. The legacy cluster_sum
detectors (flat-then-rise, drawdown, combined) were removed from this package on
2026-10-01. Live `kinetics_fitting.classify_trajectory` is unchanged.

## 3. Data notes (refit, all 7 datasets, 296 area files)

- 58 spectra were never recorded live. They now get real times from the timeline.
- Spectra with no refit fit (NaN area at the correct time):
  - nn1120-2 `-004` delta8.0026 (fitted live, but the file is gone from disk);
  - nn1120-4 `-000` delta8.0130 (SVD failure);
  - 11 spectra of nn1120-4 `-041` (not refit; probably still acquiring at refit time).
- nn1120-3_003 `-072` has only delta1 spectra, so it gets no area rows and no output.
- Live params hold 3 corrupted `File` values (`.638`, `99.548`, `146918916` in
  nn1120-3_003 `-027/-038/-106`).

## 4. Validation

| Check | Result |
|---|---|
| Timeline `Time_Delta` vs saved live params, all 7 datasets | 24,199/24,199 exact |
| Area builder vs live area CSVs (live params, `voigt_fit` groups), nn1120-3_004 | 34/34 identical (float rounding). Measurements with gaps differ only in time after the gap, as expected |
| Kinetic fits vs live `append_fit_results(latest_only=False)`, `004-019`, all peaks | all 20 kinetic columns bit-identical, 453 rows (0 ODE timeouts) |
| Written `classification` vs harness verdict, nn1120-3_004 | 34/34 agree, never reverts |
| Parallel (`--workers 2`) vs serial, `004-035` | identical |

Classifier (`classify_nucleation`, latch 3) against `ground_truth.json` (288 files,
65 discontinuous, labels as of 2026-09-30) on `_reprocess`: **286/288**. The two
mismatches are both in nn1120-3_003, and the user excused both: `-077` (FP, low S/N)
and `-102` (missed). Every other folder scores 100%. The written column agrees with the
harness on nn1120-3_004 (15/15 latched files), and `fit_cli --classify-only` writes
identical files.

The legacy `combined` detector scored 257/288 on the refit with the pre-relabel ground
truth (`docs/JOURNAL_nuc-clf-refit.md`). The ground truth is not edited without the
user.

## 5. Cost

Rolling secondary_pfo is the bottleneck. At below-normal priority, `monomer_sum` alone on
`004-008` (271 time points) took 80 min and hit 165 ODE timeouts. A file has 4
secondary_pfo trajectories, so a long file takes about 5 h serially. A short file
(40–50 points) takes about 6.5 min. `--classify-only` on a whole folder takes seconds.

## 6. Open

- Classifier: 286/288 (§4). As new data arrives, retune it in yaml and rescore with
  `--validate`.
- secondary_pfo returns NaN for the whole trajectory when `monomer_sum` is all ≤ 0: the
  `q_e` bound `(0, 2·max(y))` inverts and `minimize` raises. Live does the same. This
  affects 14/296 refit files. It belongs to the model redesign.
- Timeouts are wall-clock, so results under load are not reproducible bit for bit.

## 7. Out of scope

- The discontinuous-regime models (the four equations) and renaming the labels.
- `src/analysis/`, `voigt_fit`, and the live path. That includes porting the
  classifier to live (`docs/spec_nuc-clf.md` §8).
- Labeling the 6 unlabeled nn1120-4 files and the 3 refit-only measurements.
