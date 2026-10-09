# src/utils/kinetics — offline kinetics reprocessing

**Status: implemented. Verified on nn1120-3_pd_ceo2_004.** Offline only. The live
server never calls it, and it never writes into source data. Refit areas are built for
all 7 datasets. Full rolling fits beyond the verification files are limited by
secondary_pfo cost (§5); segments fits take seconds to minutes per file. Folders are
run one at a time.

There are two fit modes. `--mode segments` (the `fit_cli` default) fits once per
peak and segment over the whole trajectory (§8). `--mode rolling` is the
live-equivalent path (§1–§2). This file describes what the package does now. How it
got here (what was tried, measured and rejected) is in
`context/2026-09-29-kinetics-reprocessing-on-refit.md` (rolling) and
`spec-working.md` (segments: decisions D1–D27, surveys, the Q12 start-of-trajectory
test).
Classifier history: `docs/spec_nuc-clf.md` (the old cluster_sum rules) and
`docs/JOURNAL_nuc-clf-refit.md` (the current Peak_1988 detector).

**Purpose.** Rerun kinetics on the 24-peak refit (`src/utils/ir_fitting`, output in
`C:\Data\peakFit\<dataset>\_reprocess\`), with sums redefined from the refit's groups.
The output is per-segment `*_CarbonylKineticParams.csv` / `*_CarbonylKineticFeatures.csv`
(segments mode, §8) or live-schema, live-equivalent `*_CarbonylPeakArea.csv` files
(rolling mode). This package also holds the ground-truth harness for the nucleation
classifier.

---

## 0. Read first

```bash
# 1. refit params -> area CSVs, then 2. classify + kinetic fits (live-equivalent).
# --mode rolling is required here: the CLI default is --mode segments (§8).
uv run python scripts\run_kinetics_fit.py --folder nn1120-3_pd_ceo2_004 --build-areas --mode rolling
uv run python scripts\run_kinetics_fit.py --folder nn1120-3_pd_ceo2_004 --classify-only --mode rolling   # fast
uv run python scripts\run_kinetics_fit.py --folder nn1120-3_pd_ceo2_004 --measurements <base name> --mode rolling
uv run python scripts\run_kinetics_fit.py --folder nn1120-3_pd_ceo2_004 --workers 8 --mode rolling   # one process per measurement

# Classification only (no fits) -> _reprocess\_test_classification\
uv run python scripts\run_kinetics_classification.py --folder nn1120-3_pd_ceo2_004

# Score the detector against ground_truth.json
uv run python scripts\run_kinetics_classification.py --validate --input-subfolder _reprocess

# Segments mode (default): per-segment fits -> *_CarbonylKineticParams/Features.csv (§8)
uv run python scripts\run_kinetics_fit.py --folder nn1120-3_pd_ceo2_004
uv run python scripts\run_kinetics_fit.py --folder nn1120-3_pd_ceo2_004 --classify-only   # features only
uv run python scripts\run_kinetics_classification.py --validate-spikes   # spike detector vs ground_truth.json
```

`--folder` (or `--path`) is required. `--measurements` takes base names, exact or
glob (e.g. `"*-043"`).

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
  Latched rows carry `latch_time_s` (the time of the first latched row) and
  `growth_onset_s` (`classification.growth_onset`: the first row of pooled,
  unsmoothed Peak_1988 up to the latch that passes the gates with
  `growth_onset_amplitude_min`; the sweep's first fire if none does). Unlike live, there
  are no `pre_*`/`post_*` columns.
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
- **Segments pfo is on a different clock.** Segments mode runs pfo on `t − t_ref_s`
  (the segment's first row, §8.2); rolling and live run it on absolute time. Segments
  pfo `k` and `q_e` are not comparable to rolling or live values. `exp_decay` is
  offline only and has no live twin.

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
| `models.py` | pfo and secondary_pfo (copies of live, same results); `exp_decay` (offline only, §8) |
| `writer.py` | `REGIME_MODELS`, per-measurement classify + rolling fit + write; singletons |
| `segments.py` | Segments mode (§8): `smoothed`, `detect_spike`, `plan_segments`, `depletion_start`, `segment_curve` (evaluate a params row, for plots), `SegmentWriter` / `SEGMENT_WRITER` |
| `api.py` | `build_areas`, `process_file(mode=...)` (`MODES`; the API default is `rolling`), `process_folder` (`workers=N`: spawn, BLAS pinned to 1 thread) |
| `validation.py` | Ground-truth harness (`run_validation`, `ever_fires`, `run_spike_validation`); an errored file scores wrong |
| `fit_cli.py` / `classify_cli.py` | The two CLIs (`scripts\run_kinetics_fit.py`: `--mode {segments, rolling}`, default `segments`; `scripts\run_kinetics_classification.py`: classification-only writes + `--validate` / `--validate-spikes`) |

Figures: `src/visualizations/plot_kinetics_fit.py` draws the segments outputs (§8).

## 2. Models

`REGIME_MODELS` maps `(group, regime)` to a model. The regime at a time point is the
cluster_sum latch state at that time.

| Group (rows fitted) | continuous | discontinuous |
|---|---|---|
| monomer peaks + `monomer_sum` | secondary_pfo | secondary_pfo (placeholder) |
| cluster peaks + `cluster_sum` | pfo | pfo (placeholder) |

The discontinuous entries are placeholders until the before/after-detection models
exist (four equations: two sums × two regimes). Segments mode (§8) fits separate
per-segment models; the rolling placeholders are unchanged. Fits are rolling (an expanding window
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

With the 000-041 entry added on 2026-10-03 (`spike: true`, it scores correct) the
same run gives **287/289**, with the same two misses. Every commit from `654f3bb` to
`9ce4dfb` scores 286/288 on `_reprocess`, so the detector has not drifted. Pitfall:
plain `--validate` (no `--input-subfolder`) scores the **live** area CSVs, not the
refit areas the detector was tuned on, and gives other misses (286/289: 003-098,
003-102, 004-016). That is not drift.

The legacy `combined` detector scored 257/288 on the refit with the pre-relabel ground
truth (`docs/JOURNAL_nuc-clf-refit.md`). The ground truth is not edited without the
user.

## 5. Cost

Rolling secondary_pfo is the bottleneck. At below-normal priority, `monomer_sum` alone on
`004-008` (271 time points) took 80 min and hit 165 ODE timeouts. A file has 4
secondary_pfo trajectories, so a long file takes about 5 h serially. A short file
(40–50 points) takes about 6.5 min. `--classify-only` on a whole folder takes seconds.

Segments mode fits each trajectory once per segment: 5–90 s per file with all peaks
(~2 min per test folder), against up to ~5 h rolling.

## 6. Open

- Classifier: 287/289 (§4). As new data arrives, retune it in yaml and rescore with
  `--validate`.
- secondary_pfo returns NaN for the whole trajectory when `monomer_sum` is all ≤ 0: the
  `q_e` bound `(0, 2·max(y))` inverts and `minimize` raises. Live does the same. This
  affects 14/296 refit files. It belongs to the model redesign.
- Timeouts are wall-clock, so results under load are not reproducible bit for bit.
- Segments mode (§8):
  - Kinetics are to be redone on all datasets (`run_kinetics_fit.py --folder
    <dataset>`, started by the user; `--build-areas` first if a dataset's refit
    params changed). Only the 8 test files have D24 fits; every other kinetics output
    predates it.
  - Models for the cluster spike segments (`burst_nucleation`, `diffusion_growth`),
    left blank on purpose.
  - The post-onset hump (003-097): a monotone pfo cannot follow it (§8.6).
  - Short first segments (000-002): `pre_nucleation`'s k is not slow kinetics (§8.6).
  - Constituent fits: 49/144 have R² < 0.5, because pfo's `q_e ≥ 0` cannot follow
    falling or flat constituents. Left as is (no signed `q_e`, no amplitude skip).

## 7. Out of scope

- The discontinuous-regime models (the four equations) and renaming the labels.
- `src/analysis/`, `voigt_fit`, and the live path. That includes porting the
  classifier to live (`docs/spec_nuc-clf.md` §8).
- Labeling the 6 unlabeled nn1120-4 files and the 3 refit-only measurements.

## 8. Segments mode (`--mode segments`, the `fit_cli` default)

Each peak trajectory is fitted **once over its whole length, per segment**, instead
of at every row (rolling, §2). Segments are named after the physics: continuous =
adsorption; discontinuous = LaMer, with `monomer_sum` as the monomer's view and
`cluster_sum` as the cluster's view. Offline only. Rolling mode and live are
unchanged by it.

### 8.1 Segment rules

The regime is the measurement's **final** label (whether the latch ever engaged).
Boundaries come from the **sum** trajectory, and its constituents use the same
boundaries. A boundary row belongs to **both** adjacent segments.

| Rows | Regime | Spike | Segments (model) |
|---|---|---|---|
| monomer_sum + 3 constituents | continuous | — | `adsorption` (secondary_pfo), one fit over the whole run, even when it peaks and decays |
| | discontinuous | — | `supersaturation`: t0 → `t_b` (secondary_pfo); `depletion`: `t_b` → end (exp_decay). `t_b = max(monomer max, growth onset)` |
| cluster_sum + 15 constituents | continuous | — | `adsorption` (pfo) |
| | discontinuous | no | `pre_nucleation`: t0 → growth onset (pfo); `ripening`: growth onset → end (pfo). One `ripening` if the onset is NaN (no file today) |
| | discontinuous | yes | `pre_nucleation`: t0 → spike base (pfo); `burst_nucleation`: base → cluster max (none); `diffusion_growth`: cluster max → end (none) |

- An unclassified file (too few points) gets the continuous segments, with
  `regime = unclassified`.
- `pre_nucleation` is CO adsorption onto pre-existing clusters; the spike is CO
  adsorption onto emergent, new clusters.
- The monomer segments are contiguous: when the growth onset comes after the monomer
  max (50/70 discontinuous files), supersaturation runs on to the onset.
- The spike segments are written with `model = none` and no fit, until a model is
  chosen.
- A segment with fewer than `--min-points` rows (default 4) gets NaN parameters, and
  its row is still written. There is no other point minimum: short supersaturation
  segments (9–15 points in about half of nn1120-4_000's discontinuous files) still get
  the 5-parameter secondary_pfo.

### 8.2 Clock and models

**Every segment's model clock starts at its own first row, `t_ref_s`**, and `q0`
(exp_decay: `y_b`) is set there. The first area row is at ~420 s, not 0; it is
treated as (0, y₁), and the time before it is ignored. Reason: the analysis targets
the **slow** kinetics. The fast admission phase (0–420 s, seen only in the delta1
seed spectra) is out of scope; to study it, look at the first ~400 s directly.

- **pfo** runs on `t − t_ref_s` (the segment layer shifts it; `models.py` is
  unchanged). This differs from rolling and live, which keep absolute-time pfo.
- **secondary_pfo** already integrates its ODE from the first row (`q = y₁`,
  `p = 0` there), unchanged.
- **exp_decay** (`models._ExpDecayModel`, offline only):
  `y = y_inf + (y_b − y_inf)·exp(−k·(t − t_b))`, solved with `curve_fit`.
  - `t_b` is the segment's first time. `y_b` is fixed to the **smoothed** trajectory
    at `t_b` (passed as `p0[2]`; without it, the raw first value).
  - Fitted: `k ∈ [0, 0.01]`, `y_inf ∈ [min − span, max + span]`.
- `segment_curve` evaluates a params row with the same shift, for plots.

Rejected: a free `q0`. On cluster pfo it raises R² slightly, but on 000-026 and
004-008 it acts as a free offset, not an admission step. On monomer it lifts the
curve 0.03–0.20 au above the early data. Fitting from (0, 0) with the seed rows
fails on every file: one pfo or secondary_pfo cannot do the fast step and the slow
rise together. The test tables are in `spec-working.md` §7 Q12.

### 8.3 Outputs

Files go to `<dataset>\_reprocess\<output-folder>\` (default `_test`). The suffixes
are in `config/paths.yaml` (`kinetic_params_suffix`, `kinetic_features_suffix`).
`--classify-only` writes only the features file.

**`<base>_CarbonylKineticParams.csv`**, one row per `(Peak_Name, segment)`:
- `Measurement, Peak_Name, group, regime, segment, model, t_start_s, t_end_s,
  t_ref_s, n_points, r^2, rmse`. `t_ref_s` is the model clock's zero.
- Then `pfo_*` and `pfo-sec_*` (live schema), and `exp_k_s-1, exp_k_stderr,
  exp_y_inf_au, exp_y_inf_stderr, exp_y_b_au`. Columns of other models are NaN.
- Rows written before 2026-10-08 (D24) hold `t_ref_s = 0` for segments that start
  the trajectory: absolute-time pfo then.

**`<base>_CarbonylKineticFeatures.csv`**, one row:
- `Measurement`, `n_points`, `classification`, `growth_onset_s`, `latch_time_s`;
- `monomer_max_s`, `monomer_max_au`, `depletion_start_s` (`t_b`; NaN unless
  discontinuous);
- `spike_detected`, `spike_base_s`, `cluster_max_s`, `cluster_max_au`,
  `cluster_plateau_au`, `cluster_noise_au`, `spike_prominence`, `spike_rise`,
  `spike_note`. Evaluated for discontinuous files only; `spike_detected` is empty
  for continuous files.
- The `_au` maxima are smoothed values.

### 8.4 Boundaries and the spike (yaml `kinetics_reprocess_segments`)

- **Smoothing:** a centered running median of `smooth_n = 5` points over the
  **pooled**, time-sorted sum trajectory (all `Delta_Group`s together).
- **Monomer max:** the argmax of smoothed monomer_sum.
- **Spike** (discontinuous only), on smoothed cluster_sum:
  - candidate max: the argmax within [monomer max − 2 h, monomer max + 8 h];
  - noise: `1.4826·MAD(raw − smoothed)`;
  - prominence: (max − plateau) / noise, plateau = median smoothed value from 4 h
    after the max (at least 3 points);
  - rise: (max − smoothed value at the base) / noise;
  - base: `growth_onset_s`;
  - detected when prominence ≥ 5, rise ≥ 5 and base < max.

Why (survey of 296 files, 70 discontinuous, 2026-10-03):
- **Pooled, not per-group.** A Delta_Group has ~17 points in a 52 h run, so a
  per-group window of 5 spans ~15 h and puts the max early (000-026: 3.0 h vs.
  10.1 h pooled; the plot shows ~10 h). Group offsets in the sums (~0.05 au) are
  small next to the monomer_sum range (~0.8 au). Windows 3–9 agree within ~1–2 h.
- **The spike score separates with a gap.** Detected: 000-034 25.7, 000-032 17.4,
  000-026 15.3, 000-041 8.8, 000-000 6.0, 000-029 5.3 (all nn1120-4_pd_ceo2_000).
  Next: 001-034 4.9 (rise 2.7, tiny amplitude) and 003-097 3.9; all others < 2.
- **Base = growth onset.** A walk-left / windowed-minimum base landed too early
  (000-026: 6.6 h vs. a visible start at ~11.5 h). The growth onset matched the
  visible start on all six spikes.

Spike labels are an optional boolean `spike` per `ground_truth.json` entry (user
labels; continuous entries left unlabeled, since only discontinuous files are
scored). `--validate-spikes` scores the detector against them and reads
`_reprocess` by default.

### 8.5 Figures

`src/visualizations/plot_kinetics_fit.py`: per measurement, monomer_sum and
cluster_sum panels (raw points, shaded segments, fitted curves via
`segment_curve`), plus one panel per optional `extra_peaks` entry (e.g.
Peak_1988). Output: `<data.figures>\<folder>\plot_kinetics_fit\*_kinetics_fit.png`
with a `kinetics_fit.csv` catalog. There is no `--plot` flag on the CLI.

### 8.6 Validation (8 test files, all peaks)

Test files: nn1120-4_pd_ceo2_000 -000, -002, -014, -026, -028; nn1120-3_pd_ceo2_003
-097; nn1120-3_pd_ceo2_004 -008, -013.

| Check | Result |
|---|---|
| Rolling mode unchanged (`--mode rolling --classify-only`, 000-026) | byte-identical to `_test_classification` |
| `--classify-only` (segments), all 7 datasets | 296/296 files, 0 failures, 226 continuous / 70 discontinuous; `spike_detected` = exactly the 6 spikes |
| `--validate-spikes` | 66/66 labeled files correct (6 spike) |
| Curves start on the data (D24) | in all 176 pfo rows, `segment_curve` at the first row = `q0` = the first row (44 rows share the first time across two Delta_Groups; `q0` is the first of them) |
| A rule change leaks into other segments (iteration 2, before D24) | no: unchanged segments match to ≤ 4e-14 (secondary_pfo moves only by ODE-timeout noise) |

Fit quality (sums):
- monomer_sum supersaturation R² 0.95–1.00, depletion 0.81–0.99 (003-097's 0.81:
  the run ends while the decay is still nearly linear).
- cluster_sum `pre_nucleation` / `adsorption`, on the D24 clock: 000-000 0.937,
  000-002 0.796, 000-014 0.171, 000-026 0.948, 000-028 0.953. 000-014 is continuous
  and its cluster_sum is flat noise (0.42–0.48 au), not a bad fit.
- cluster_sum `ripening` is weaker: 003-097 0.326, 004-008 0.448, 000-028 0.698
  (000-002 is the exception, 0.913). The clock is not the cause (the curve starts on the data). 004-008
  is a fast rise then a long noisy plateau; 000-028's scatter grows after ~30 h.
  **003-097 has a sub-threshold hump**: cluster_sum rises to ~0.35 at 21.6 h and
  falls to ~0.25 by 32 h (prominence 3.9, just under the cutoff), which a monotone
  pfo cannot follow.
- **Short first segments:** on 000-002 the onset is at 0.5 h, so `pre_nucleation` is
  8 rows of the tail of the admission rise; its k (9.0e-4) is not slow kinetics and
  is not comparable across files.
- **Continuous monomer that peaks and decays** (61/226 files): the single
  secondary_pfo still fits (004-013: 1.29 → 0.19 au over 150 h, R² 0.976), with
  systematic residuals (overshoots the max by ~0.08 au, under the data at 40–70 h).
- ODE timeouts: 0 on most files; 004-013 had 20–41, from its long constituent
  secondary_pfo fits under machine load.
