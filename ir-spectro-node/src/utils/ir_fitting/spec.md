# src/utils/ir_fitting — offline IR peak fitting and baseline runs

**Status: implemented and in use.** Offline only — never invoked by the live
server path, never writes into source data.

Sibling in purpose to `src/utils/kinetics`, but deliberately *not* sibling in
architecture: this package wraps `src/analysis/spectral_fitting.py` instead of
re-implementing it (§2).

This file describes what the package does now. **The record of how the
baseline recipe was arrived at — what was tried, measured, rejected and why —
lives in `context/`** (`2026-09-16-*`, `2026-09-17-baseline-investigation.md`,
`2026-09-20-baseline-cleanup-and-cli.md`). The full historical spec is in git
at commit `c114eab`. Read the baseline-investigation note before proposing a
change to the baseline recipe; most obvious alternatives have been tried.

---

## 0. Read first

| Workstream | State |
|---|---|
| **Baseline runs** (§9) | One recipe, run on chosen files, one figure per file. Default recipe is the anchored, lower-split baseline of §9. Experiment-only: no production baseline, ROI or `config/analysis.yaml` default is changed by it. |
| **Two extra low-wavenumber peaks** (§4) | Dormant — `ir_fitting.extra_peaks_base` is `[]`, so nothing fits them. The machinery works; the peaks are simply not configured. |

### How to run things

```bash
# Baseline runs (argparse CLI, §11). No arguments = default recipe on the
# eight default files, run name "default".
uv run python scripts\run_baseline_experiment.py
uv run python scripts\run_baseline_experiment.py --help
uv run python scripts\run_baseline_experiment.py --anchors 2240 2006 1955 --run-name probe

# Peak fitting. Edit-constants, in api.py's __main__.
uv run python src\utils\ir_fitting\api.py

# View saved baselines for one measurement (computes nothing new).
uv run python src\visualizations\plot_baseline.py

# View per-file fits.
uv run python src\visualizations\plot_individual_fit.py
```

Batch **fitting** follows the repo's edit-constants convention. Batch
**baseline runs** have a CLI because the recipe is what gets varied. The split
mirrors `src/utils/kinetics`.

### Traps worth knowing before touching this code

- **Wavenumbers descend.** Index 0 is the *high* end. Split and select by
  wavenumber *value*, never by position.
- **`create_baseline` takes only `y`.** There is no x argument, so the
  wavenumber window *is* the array the algorithm sees, and its background
  classification is global. Changing the window changes the baseline
  everywhere, not just near the edge — by tens of percent of signal range on
  some files. `half_window` and friends are sample counts, not cm⁻¹.
- **A degenerate baseline still returns an array.** `std_distribution` warns
  *"there were no baseline points found"* and hands back a plausible-looking
  curve. `BaselineVariant` captures that warning into a `degenerate` flag; do
  not drop it.
- **Baseline quality cannot be scored automatically.** The low-wavenumber bands
  are negative-going, so the baseline is a centre-line estimator, not a lower
  envelope; envelope-style scores rank the best baseline worst. Judgement is
  visual, which is why a run produces figures and no metrics.
- **Anchor lists keep order and duplicates.** Each entry is one residual in a
  least-squares fit, so a repeat is an integer weight (`1955` three times in
  the default = triple weight). Never deduplicate or sort.
- **The anchor guard does not protect a low-wavenumber anchor.** Its threshold
  is a fraction of the *whole ROI* range (a local scale gates every file), and
  the bands below ~1900 are 2–9% of that range. A passing guard there means
  "not visible at ROI scale", not "background". This applies to the default
  lower anchors at 1800/1820.
- **`settings` reaches the upper curve only.** The lower segment always runs on
  the unmodified `voigt_fit.baseline` settings.
- **Settings keys fail silently if misspelled** in `create_baseline`, which
  reads them with `.get(...)`. `config.get_baseline_settings` therefore raises
  on unknown keys — keep that.

---

## 1. Purpose

Offline, programmatic entry points for exploratory analysis and reprocessing of
IR peak fits, with two jobs:

1. **Baseline runs** — compute a baseline recipe on chosen files and render it
   for visual judgement (§9).
2. **Fitting extra peaks** not in the live `voigt_fit.peak_list_base`, appending
   them to an existing fit without re-solving it (§4–§8).

Both write only to non-source locations. The live pipeline re-reads
`*_CarbonylPeakFitParams.csv` as fit history, so overwriting it in place would
corrupt a dataset.

## 2. Architecture — wrap, don't duplicate

`src/utils/kinetics` is a full parallel re-implementation of
`src/analysis/kinetics_fitting.py`, and the two can silently disagree.
`ir_fitting` does **not** repeat that. It calls `src/analysis/spectral_fitting.py`
directly — `create_baseline`, `add_params`, `select_param_rule`,
`get_shifted_rules`, `voigt_model`, `peak_fit` — and adds only orchestration.
There is one Voigt implementation and one set of param rules in the repo.

```
src/utils/ir_fitting/
  __init__.py       re-exports the entry points
  spec.md           this file
  config.py         reads the ir_fitting: yaml block; applies the isotope shift
  api.py            fit_file / fit_folder / load_measurement / run_baseline / subifg_files
  baseline.py       BaselineVariant — one baseline recipe; the guard and anchor correction
  baseline_cli.py   argparse CLI over api.run_baseline
  runner.py         per-file fit orchestration; calls analysis.spectral_fitting
  result_types.py   in-memory bundles the plots consume
  writer.py         merge + write into _test/
```

Three-layer split, worth preserving:

- **`baseline.py` is the extension point for baseline behaviour.** A new recipe
  gets a field on `BaselineVariant` and a branch in its `compute()`.
- **`api.py` orchestrates.** It decides which files to run.
- **`src/visualizations` only renders.** `plot_baseline.py` computes nothing.

## 3. Configuration

All of it in `config/analysis.yaml` and `config/paths.yaml`, read through
`src/core/config.py`. No hardcoded paths, peak wavenumbers or fit bounds.

### `ir_fitting:` block

Kept structurally parallel to `voigt_fit` so promoting a peak to live is a copy
of values between two lists, not a rewrite:

```yaml
ir_fitting:
  # 12CO base wavenumbers, shifted by voigt_fit.isotope_shift_cm1 at read time.
  # Integers only — Peak_Name is formatted Peak_<value> and must match the
  # historic strings exactly (Peak_1795, not Peak_1795.0).
  extra_peaks_base: []            # e.g. [1845, 1825]

  # Group membership, mirroring voigt_fit's *_peaks_base keys. Recorded for
  # later promotion into the live config; does not affect fitting.
  extra_cluster_peaks_base: []
  extra_monomer_peaks_base: []
  extra_unknown_peaks_base: []

  # Optional. Overrides voigt_fit.baseline for offline runs only.
  # baseline:
  #   num_std: 1.4
```

- `voigt_fit.peak_list_base` and `voigt_fit.cluster_peaks_base` are **not
  modified**. The live server keeps its 18-peak list.
- `ir_fitting` peaks are isotope-shifted with the same
  `voigt_fit.isotope_shift_cm1` and `isotope_default`, so one isotope switch
  moves both lists together.
- An empty `extra_peaks_base` is a valid no-op, not an error.

### Baseline settings precedence

`config.get_baseline_settings(voigt_settings, override=...)` layers, lowest
first:

1. `voigt_fit.baseline` — what the live path uses
2. the `ir_fitting.baseline` yaml block — an offline default
3. the per-call `override` — the experiment knob

Unknown keys raise. Valid keys: `half_window`, `interp_half_window`,
`fill_half_window`, `num_std`, `smooth_half_window`, `weights`.

### Voigt bounds stay in `voigt_fit.param_rules`

Extra peaks' bounds are hand-edited directly in `voigt_fit.param_rules`. The
staged `[1790, 1800]` / `[1770, 1780]` entries serve 1795 / 1775 and are inert
for the live path. No `ir_fitting`-local rule set.

`select_param_rule` falls through to the `default: true` rule when no
`range_cm1` matches, and that default sets `sigma.max: 6.37` / `gamma.max: 2.8`
— far too narrow for broad bands, and silent. `_warn_on_default_rule` logs a
warning naming the peak and the bounds it got. Replacing the catch-all is
deferred (§12).

### Figure paths

```yaml
data:
  plot_individual_fit: "plot_individual_fit"
  plot_baseline: "plot_baseline"
  baseline_experiments: "baseline_experiments"
```

Resolved via `config.get_path("data.figures", folder_name, ...)`.

## 4. The two extra peaks — dormant

**Currently inactive: `extra_peaks_base` is `[]`.** The machinery works; this
section is what to know when the peaks are seeded again.

Two low-wavenumber bands that were fitted historically and then dropped:

| Dataset | Fitted `Peak_Name` values present |
|---|---|
| `nn1120-2_pd_ceo2_000` (2024-11) | `Peak_1775`, `Peak_1795`, … **no** `Peak_2093`, `Peak_2176`, `Peak_2196` |
| `nn1120-3_pd_ceo2_004` (2026-03) | `Peak_2093`, `Peak_2176`, `Peak_2196`, … **no** `Peak_1775`, `Peak_1795` |
| `nn1120-4_pd_ceo2_000` (2026-06) | same as above |

- 12CO base values are **1845** and **1825**; at the default `13CO` isotope
  (`isotope_shift_cm1: -50`) they become **1795** and **1775**.
- `Peak_Name` strings are established in historic CSVs as exactly `Peak_1795`
  and `Peak_1775` — integer-formatted, no decimals.
- Fitted `Amplitude` for these bands is **negative**. Nothing may assume
  positive amplitude.

**Append, don't refit.** These two sit ~180 cm⁻¹ below the lowest
currently-fitted peak (`Peak_1975` at 13CO), so there is no meaningful Voigt
overlap with the existing 18 and the existing fit need not be re-solved.
Default: read the existing `*_CarbonylPeakFitParams.csv`, fit only the
`ir_fitting` peaks, append those rows (`append_only=True`). The saved
`*_CarbonylFitResidual.csv` contains these bands *unmodeled*, so the residual
over 1750–1850 is a direct sanity check on a new fit.

**Known problem when they were last seeded.** Across 72 files of
`nn1120-3_pd_ceo2_004`, both centers hit a rule bound in ~70% of files, pushing
*toward each other* (1795 down to 1790, 1775 up to 1780), while 1795's sigma
pinned wide (26) and 1775's pinned narrow (2.55). The two bands appear to be
competing for one feature. **`param_rules` need attention before these peak
areas mean anything.** `sigma.max: 26` is a Gaussian FWHM of ~61 cm⁻¹, with
tails reaching ~1900 cm⁻¹ — where the no-overlap argument above weakens.

## 5. Per-file fit procedure

Input is a subIFG file path, e.g.
`C:\Data\OpusConvert_subIFG_lgRfl\<folder>\<name>.<index>`.

1. Resolve paths with `DataAnalysisRunner._resolve_paths` semantics:
   `folder_name`, `file_name`, `file_index`, `delta_file`.
2. Honor `manually_skip_files` (`delta1` index > 2, and all of
   `delta2`/`delta3`/`delta4`) exactly as the live path does.
3. Load the existing `*_CarbonylPeakFitParams.csv` for the dataset.
4. Load the subIFG array over 1750–2250.
5. Obtain a baseline (§6) and subtract it.
6. Build `lmfit.Parameters` for the `ir_fitting` peaks only, via `add_params`,
   so they pick up `voigt_fit.param_rules` unchanged. All `ir_fitting` peaks
   are fitted **jointly** — 1795 and 1775 are 20 cm⁻¹ apart and overlap.
7. Fit with `peak_fit`, evaluate each peak's `voigt_model`, integrate with
   `-trapezoid(y_fit, wavenumbers)` — sign convention identical to
   `peak_analysis`.
8. Build rows, merge, write to `_test/` (§7, §8).

### Guard: parameters pinned at their bounds

A fitted parameter sitting exactly on a bound reflects the bound, not the data.
`_warn_on_pinned_params` checks `center`, `amplitude`, `sigma`, `gamma` against
both bounds. `sigma` at max means the band's tails may reach the existing
cluster, which is when `append_only=True` stops being obviously safe; `center`
at either bound means the seeded wavenumber is probably wrong. Messages collect
on the result; `api.py` aggregates them into one WARNING per distinct issue per
run.

### FSD peak snapping — not performed, matching current live behavior

The live path intends to snap each nominal peak to a detected FSD peak within
5 cm⁻¹, but `find_fsd_peaks` returns **array indices** while
`resolve_peak_lists` compares them against wavenumbers, so nothing ever
matches. `Peak_Value` is exactly nominal from `nn1120-3_pd_ceo2_001` onward.
`ir_fitting` therefore sets `Peak_Value` to the nominal shifted wavenumber and
does not load FSD data, reproducing live output exactly. Fixing the live path is
out of scope (§12) — it would change `Peak_Value` in new output.

### Column derivation for appended rows

| Column | Source |
|---|---|
| `File` | `delta{N}.{index}`, e.g. `delta5.0007` — 4-digit index |
| `Delta_Group` | `delta{N}` |
| `Peak_Name` | `Peak_<shifted integer>` — `Peak_1795`, `Peak_1775` |
| `Peak_Value` | the nominal shifted value (see FSD note) |
| `Center`, `Amplitude`, `Sigma`, `Gamma`, `Y0` | from the fit |
| `fwhm` | Voigt pseudo-FWHM, same formula as `peak_analysis` |
| `Peak_Area` | `-trapezoid(y_fit, wavenumbers)` |
| `Data_Integral` | **copied** from an existing row for the same `File` (whole-ROI, identical across peak rows) |
| `Time_Delta (s)` | **copied** from an existing row for the same `File` |
| `PdCO_mol`, `PdCO_mol_stderr` | **Left NaN on appended rows**; existing rows keep their historical values. The calibration was derived in the carbonyl region and is not justified at 1775–1795. |

## 6. Baseline in the fit path

`create_baseline` wraps `pybaselines.classification.std_distribution` and
receives the intensity array and settings — **no peak list**. Declaring more
peaks cannot change the baseline.

| `baseline=` | Purpose |
|---|---|
| `"saved"` (default) | Read the `delta{N}.{index}` column from the dataset's `*_CarbonylFitBaseline.csv`. Guarantees appended peak areas sit on exactly the same baseline as the existing 18. |
| `"recompute"` | When the saved CSV is missing or lacks the column, or for settings-level EDA. |

Passing `baseline_settings=` forces `"recompute"`. With no override the two
agree to 1e-16 — a self-check. The fit path uses the plain `create_baseline`
curve, **not** the anchored recipe of §9.

## 7. Collision handling

`nn1120-2_pd_ceo2_000` **already has** `Peak_1795` / `Peak_1775` rows; blind
appending would double-count fit history in `compute_cumulative_peak_area_df`.

| `on_existing` | Behavior |
|---|---|
| `"skip"` (default) | Leave the existing row, do not fit, log at INFO; fitted / skipped counts in the summary. |
| `"overwrite"` | Drop the existing row and replace it. For re-running after a param-rule change. |
| `"error"` | Raise `ExistingPeakRowsError`. |

**Backfilling peaks missing from a historic dataset** (e.g. `Peak_2093` /
`2176` / `2196` in `nn1120-2`) is `append_only=False`, never append: those sit
*inside* the existing cluster, where adding one changes its neighbours' fit.
`append_only=False` refits every peak in `voigt_fit.peak_list_base` plus
`extra_peaks_base` jointly, and replaces **every row for every file it
touched** — keeping a row for a dropped peak would mix two models within one
file. Files it did not touch (`manually_skip_files`) keep their rows.

## 8. Outputs

Never writes into a source folder. Two destinations.

**Fit output** — `writer.resolve_output_dir`, a subfolder of the source dataset
folder, `_test` by default. An empty / `"."` / absolute `output_folder` is
rejected.

```
C:\Data\peakFit\<dataset>\_test\
  <name>_CarbonylPeakFitParams.csv   existing rows + appended ir_fitting rows
  <name>_CarbonylFitBaseline.csv     baseline actually used, per file column
  <name>_CarbonylFitResidual.csv     residual after the ir_fitting peaks are modeled
```

- Column order and names match the live schema exactly.
- `*_CarbonylPeakArea.csv` (cumulative areas, `cluster_sum`, kinetics) is
  **out of scope**.
- The residual is **full-ROI**: under `append_only=True` the existing 18 peaks
  are reconstructed from saved parameters (as
  `plot_spectrum_fit.py::_build_delta_group_fit` does) and the new peaks added
  before differencing. Outside the new-peak region it reproduces the live
  residual — a free regression check.
- Residual sign convention is `model - data`, from
  `spectral_fitting.py::objective`.

**Baseline-run output** — `api.baseline_experiment_dir`, under the figures tree:

```
C:\Figures\<dataset>\baseline_experiments\<run_name>\
  <subifg filename>.png          one per file
```

Nothing else is written. The directory is reused: a second run under the same
`run_name` overwrites the first. Use a distinct `run_name` per recipe.

## 9. The baseline recipe — `BaselineVariant`

`baseline.BaselineVariant` is one recipe. `compute(intensity, voigt_settings,
wavenumbers)` returns a `BaselineOutcome` (`values`, `degenerate`,
`anchors_applied`, `lower_anchors_applied`, `split_applied`).

| Field | Default (CLI) | What it does |
|---|---|---|
| `label` | `"default"` | Legend name |
| `settings` | `{}` | `std_distribution` overrides, **full-ROI curve only**. Not a CLI flag. |
| `window` | `DEFAULT_WINDOW = (2250, 1750)` | Extent handed to `create_baseline` |
| `anchors` | `ANCHOR_POINTS_CM1 = (2240, 2006, 1955, 1955, 1955)` | Full-ROI affine correction points |
| `lower_split_cm1` | `LOWER_SPLIT_POINT_CM1 = 1955` | Cut; below it a second baseline replaces the first |
| `lower_anchors` | `LOWER_ANCHOR_POINTS_CM1 = (1955, 1800, 1820)` | The lower segment's own correction points |
| `anchor_guard_cm1` | `ANCHOR_GUARD_CM1 = 25.0` | Guard half-width |
| `anchor_prominence_frac` | `ANCHOR_PROMINENCE_FRAC = 0.5` | Guard threshold, fraction of whole-ROI range |

The class defaults for `anchors`, `lower_split_cm1` and `lower_anchors` are
empty/`None` (a plain `create_baseline` curve); the CLI supplies the constants
above. `DEFAULT_FOLDER` / `DEFAULT_FILES` are the eight `nn1120-4_pd_ceo2_000`
files the recipe was developed on: six where the stock baseline is wrong
(`-007`, `-008`, `-012`, `-017`, `-021`, `-027`) and the two `-022` files, which
have a band at ~1940 and exist to exercise the guard.

### How a baseline is computed

1. **Full-ROI curve.** `create_baseline` over `window`, with the layered
   settings (§3). The "no baseline points" warning sets `degenerate`.
2. **Anchor correction** (`apply_anchors`). For each anchor the guard lets
   through, the residual `data(w) − baseline(w)` is taken, where `data(w)` is a
   local straight-line fit over ±10 cm⁻¹ (`anchor_data_value`). The correction
   is affine in wavenumber: ≥3 distinct points → least-squares line (no anchor
   hit exactly); 2 → exact line through both; 1 → constant shift; 0 → no
   change. It is added to the whole curve. The array is never truncated.
3. **Cut** (if `lower_split_cm1` is set and the guard lets it through). Samples
   are split by wavenumber **value**: `>= cut` keeps the anchored full-ROI curve
   unchanged — bit-for-bit — and `< cut` is replaced by a second
   `create_baseline` computed on the lower samples alone, with the
   **unmodified** `voigt_fit.baseline` settings. Each segment needs ≥2 samples.
4. **Lower anchors.** The lower segment gets its own affine correction from
   `lower_anchors`. Guard and data estimate read the **full-ROI** arrays (the
   threshold is a fraction of the whole ROI range; an anchor on the cut would
   otherwise get a one-sided fit). One grid step of tolerance keeps an anchor
   exactly on a segment edge (1955 under a cut at 1955).
5. **Splice.** The result has a seam at the cut; `degenerate` is set if either
   segment was.

### The guard

`gating_extremum(wavenumbers, intensity, anchor, guard_cm1, prominence_frac)`
returns the most prominent extremum (either sign) within ±`guard_cm1` whose
prominence is ≥ `prominence_frac` of the file's **whole-ROI** signal range, or
`None`. A gated anchor is dropped from its correction. **One test, three
sites**: the same thresholds gate each full-ROI anchor, each lower anchor and
the cut. A gated cut means no lower segment, so lower anchors are neither
applied nor considered — on the two `-022` files 1955 fails both as anchor and
as cut, and the result is the uncut, anchored curve without 1955.

### Validation at construction

`BaselineVariant.__post_init__` raises `ValueError` for: `window` not
`(high, low)` with high > low; unknown `settings` keys; non-finite guard values,
negative `anchor_guard_cm1` or non-positive `anchor_prominence_frac`; an anchor
outside the window; `lower_anchors` without a cut; a cut not strictly inside
the window; a lower anchor outside `[window floor, cut]`. `compute` raises if
anchors or a cut are set and `wavenumbers` is not passed.

## 10. Visualizations — `src/visualizations/`

These render; they do not compute. `plot_spectrum_fit.py` is left alone: it
sums a delta group into one trace, a different question from per-fit inspection.

**`plot_individual_fit.py`** — one figure per subIFG file: data
(baseline-subtracted, black), composite fit (red), each peak dashed and labeled
by `Peak_Name` (`ir_fitting` peaks visually distinguished), residual (blue)
offset below or, with `stacked=True`, in a second panel. x inverted, 2250 → 1750.

**`plot_baseline.py`**
- `plot_baseline_run_file` — the renderer for `api.run_baseline`. Top panel:
  raw subIFG, the baseline, applied anchors (circles for full-ROI, squares for
  lower) and the cut. Bottom panel: the baseline-subtracted signal.
- `plot_baselines(folder, name)` / `plot_file_baseline` — raw subIFG, saved or
  recomputed baseline, and the subtracted signal. When recomputing, the saved
  baseline is overlaid with a printed `max |recompute - saved|`.
- Figures carry a reference grid (`_axes.apply_reference_grid`, 50/10 cm⁻¹
  major/minor over the full ROI), because judgement is visual.

## 11. Entry points

```python
from src.utils.ir_fitting import (
    BaselineVariant, run_baseline, subifg_files,
    fit_file, fit_folder, load_measurement,
)
```

### Baseline runs

CLI: `scripts\run_baseline_experiment.py` → `baseline_cli.py` →
`api.run_baseline`. Builds one `BaselineVariant` from the flags.

| Group | Flags |
|---|---|
| Data | `--folder` (default `DEFAULT_FOLDER`), `--measurements`, `--delta-groups`, `--limit` (default 60), `--run-name` (default `default`) |
| Recipe | `--label`, `--window HIGH LOW`, `--anchors …` / `--no-anchors`, `--lower-split CM1` / `--no-lower-split`, `--lower-anchors …` / `--no-lower-anchors` |
| Guard | `--anchor-guard-cm1`, `--anchor-prominence-frac` |
| Output | `--no-plot`, `--no-save`, `--dpi`, `--dry-run` |

With neither `--measurements` nor `--delta-groups`, the run uses
`DEFAULT_FILES`. It prints the recipe, the selected files and the destination
before computing (`--dry-run` stops there), then a one-line summary: files,
figures, degenerate baselines. `--no-lower-split` drops the lower anchors.
`--anchors` preserves order and duplicates.

Programmatic:

```python
run = run_baseline(
    BaselineVariant(label="probe", anchors=(2240, 2006, 1955),
                    lower_split_cm1=1955, lower_anchors=(1955, 1800, 1820)),
    folder_name="nn1120-3_pd_ceo2_004",
    files=subifg_files("nn1120-3_pd_ceo2_004",
                       measurements=["*-000"], file_keys=["delta10"]),
    run_name="probe",
)
```

`run_baseline` returns a `BaselineRun` (`files: list[FileBaseline]`,
`figure_paths`, `warnings`). A missing or unreadable file is a warning, not an
abort.

`subifg_files(folder, measurements=, file_keys=, limit=60)` selects stems.
`measurements` is an exact base name or glob; `file_keys` uses the same matcher
as `plot_baselines` (`result_types.matches_file_key`): `"delta10"`,
`"delta10.0042"`, or a glob. `None` means all on that axis. It raises when
nothing matches (listing the delta groups that exist) and when more than
`limit` files match — a dataset holds ~12k subIFG files, and a delta group
spans every measurement. `DEFAULT_FILES` belong to `nn1120-4_pd_ceo2_000`, so
any other folder needs an explicit selection.

### Fitting

```python
fit_file(
    r"C:\Data\OpusConvert_subIFG_lgRfl\nn1120-3_pd_ceo2_004\20260304_145524_pd_ceo2_004-000",
    append_only=True,       # False -> joint refit of every peak (§7)
    baseline="saved",       # or "recompute"
    baseline_settings=None, # dict -> forces recompute
    on_existing="skip",     # or "overwrite" / "error"
    output_folder="_test",
    save=True,
)
```

The unit is one **measurement** (a base name): `fit_file` iterates every delta
group / index sharing it and writes one merged CSV. `fit_folder` does every
measurement in a dataset. `load_measurement` reconstructs the saved fit without
fitting or writing — the inspection path. All return in-memory bundles
(wavenumbers, per-peak curves, composite, residual, baseline, rows) that the
plot modules consume directly.

## 12. Out of scope, and deferred

Out of scope:

- Promoting the extra peaks into `voigt_fit.peak_list_base` / `cluster_peaks_base`.
- Regenerating `*_CarbonylPeakArea.csv`, `cluster_sum`, or any kinetics output.
- Any change to `src/analysis/`, the ZMQ server, or live output schemas —
  including using §9's recipe in the live or fit path.
- Fixing the live FSD snapping bug (§5).
- A CLI for batch fitting (edit-constants, as in `src/utils/kinetics`).

Deferred, to revisit:

- **The catch-all param rule** (`range_cm1: [0, 0]`, `default: true`) silently
  supplies narrow bounds; only a warning fires (§3).
- **Threading `window` into the fit path.** `runner.load_subifg_roi` accepts it;
  the fit path does not pass it. Changing the fitted ROI would put `Peak_2196`
  ~4 cm⁻¹ from a window edge and invalidate the residual regression check.
- **The §9 default recipe is unmeasured against its predecessor**, and the guard
  thresholds (25 cm⁻¹, 0.5) were calibrated once and never swept. See
  `context/2026-09-20-baseline-cleanup-and-cli.md`.

## 13. Verification

No test suite; per `CLAUDE.md`, run against real data and diff. Datasets:
`nn1120-3_pd_ceo2_004` / `20260304_145524_pd_ceo2_004-000` (72 files after
`manually_skip_files`), `nn1120-2_pd_ceo2_000`, and the eight `DEFAULT_FILES`.

| Check | Result |
|---|---|
| Residual vs. live saved residual above 1900 cm⁻¹ | max abs diff **7e-16** — reconstruction from saved params reproduces the live path, which is what makes append-only sound |
| `baseline="recompute"` vs `"saved"`, no override | max abs diff **1e-16** across 72 files. Re-run after any change here |
| `on_existing="skip"` on `nn1120-2` | 0 fitted, 238 skipped, row count unchanged at 2023 |
| `on_existing="overwrite"` | 238 refitted, row count still 2023 |
| `on_existing="error"` | raises `ExistingPeakRowsError`, re-raised by the per-file guard |
| `PdCO_mol` on `nn1120-2` | 1785/1785 historical rows keep their value; 0/238 new rows carry one |
| Empty `extra_peaks_base` | no-op with a warning |
| Invalid `on_existing` / `baseline` / `output_folder` / settings key / window | `ValueError` up front |
| Cut leaves the region at and above it untouched | max abs diff vs the unsplit anchored curve **0.0** on all 8 default files |
| Guard on the `-022` files | anchor 1955 and cut 1955 both gated; result identical to the uncut anchored curve |
| Degenerate flag | forced with `num_std: 0.8` on `-008_delta10.0042`: `degenerate` True |
| `run_baseline` vs the pre-cleanup implementation | 5 recipes × 8 files: baseline arrays and applied-anchor lists `np.array_equal`, 80/80 |

The cut-containment check is no longer in code; to repeat it, run the same
`BaselineVariant` with and without `lower_split_cm1` and compare the arrays at
and above the cut.
