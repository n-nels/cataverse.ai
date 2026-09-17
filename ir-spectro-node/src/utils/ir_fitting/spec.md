# src/utils/ir_fitting — offline IR peak fitting and baseline EDA

**Status: implemented and in use.** Offline only — never invoked by the live
server path, never writes into source data.

Sibling in purpose to `src/utils/kinetics`, but deliberately *not* sibling in
architecture: this package wraps `src/analysis/spectral_fitting.py` instead of
re-implementing it (§2).

---

## 0. Where this stands — read first

Two workstreams live here. **The baseline one is active; the extra-peaks one is
dormant.**

| Workstream | State |
|---|---|
| **Baseline investigation** (§14) | Active. Parameter tuning ruled out, array truncation ruled out — including truncation at the isosbestic point (§14.6). The isosbestic point is now measured and exists; what to do with it is open. |
| **Two extra low-wavenumber peaks** (§4) | Dormant — `ir_fitting.extra_peaks_base` is `[]`, so nothing fits them. The machinery works; the peaks are simply not configured. |

### The open question — answered, and replaced by a harder one

**Is there an isosbestic point near 1940–1960 cm⁻¹ across
`nn1120-4_pd_ceo2_000`?** **Yes — at ~1957 cm⁻¹, in the lgRefl spectra, for 27
of 35 measurements.** Measured in §14.6. §14.4's load-bearing assumption
survives, with two corrections: the point sits at **1957**, not 1950, and the
**eight measurements that lack it there include the `...-022` regression
gate** — though §14.6 finding 6 shows the crossing *moves* rather than vanishing.

The question that replaces it: **a rule keyed to 1957 must detect the
measurements where no crossing exists there and fall back.** That is now the
blocking design problem, not the existence of the point.

### How to run things

```bash
# Baseline experiments — change settings and/or window, get figures + a CSV.
# Edit the `variants` list in the __main__ block; MODE = "baseline".
uv run python src\utils\ir_fitting\api.py

# Peak fitting. Same file, MODE = "fit".
uv run python src\utils\ir_fitting\api.py

# View saved baselines for one measurement (computes nothing new).
uv run python src\visualizations\plot_baseline.py

# View per-file fits.
uv run python src\visualizations\plot_individual_fit.py
```

Batch work follows the repo's edit-constants convention: change the constants in
an `if __name__ == "__main__":` block rather than adding argparse. There is no
CLI.

### Traps worth knowing before touching this code

- **Wavenumbers descend.** Index 0 is the *high* end. A narrower top edge drops
  samples from the **front** of the array, so any positional slice must come off
  the tail. This already caused one latent bug (§14.3).
- **`create_baseline` takes only `y`.** There is no x argument, so the
  wavenumber window *is* the array the algorithm sees, and its background
  classification is global. Changing the window changes the baseline
  everywhere, not just near the edge.
- **A degenerate baseline still returns an array.** `std_distribution` warns
  *"there were no baseline points found"* and hands back a plausible-looking
  curve. `BaselineVariant.compute` captures that warning into a `degenerate`
  flag; do not drop it.
- **Baseline quality cannot be scored automatically.** §14.3 finding 4 explains
  why every envelope-style metric gets it backwards.
- **Settings keys fail silently if misspelled.** `create_baseline` reads them
  with `.get(...)` and falls back to defaults, so `num_stds: 1.4` would run the
  *unmodified* baseline. `config.get_baseline_settings` therefore raises on
  unknown keys — keep that.

---

## 1. Purpose

Offline, programmatic entry points for exploratory analysis and reprocessing of
IR peak fits, with two jobs:

1. **Baseline experimentation** — try baseline recipes on chosen files and
   compare them visually (§14).
2. **Fitting extra peaks** not in the live `voigt_fit.peak_list_base`, appending
   them to an existing fit without re-solving it (§4–§8).

Both write only to non-source locations. The live pipeline re-reads
`*_CarbonylPeakFitParams.csv` as fit history, so overwriting it in place would
corrupt a dataset.

## 2. Architecture — wrap, don't duplicate

`src/utils/kinetics` is a full parallel re-implementation of
`src/analysis/kinetics_fitting.py`. `CLAUDE.md` calls that out as a standing
hazard: "A change to model or classification behavior usually has to land in
both, or the two paths silently disagree."

`ir_fitting` does **not** repeat that. It calls `src/analysis/spectral_fitting.py`
directly — `create_baseline`, `add_params`, `select_param_rule`,
`get_shifted_rules`, `voigt_model`, `peak_fit` — and adds only orchestration.
There is one Voigt implementation and one set of param rules in the repo.

```
src/utils/ir_fitting/
  __init__.py       re-exports the entry points
  spec.md           this file
  config.py         reads the ir_fitting: yaml block; applies the isotope shift
  api.py            fit_file / fit_folder / load_measurement / compare_baselines
  baseline.py       BaselineVariant — what "a baseline to try" means
  runner.py         per-file orchestration; calls analysis.spectral_fitting
  result_types.py   in-memory bundles the plots consume
  writer.py         merge + write into _test/
```

Three-layer split, worth preserving:

- **`baseline.py` is the extension point for baseline behaviour.** A new recipe
  gets a field on `BaselineVariant` and a branch in its `compute()`. The
  anchored / two-segment ideas of §14.4 belong there, not in a parallel module.
- **`api.py` orchestrates.** It decides which files and variants to run.
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
  modified**. The live server keeps its 18-peak list; existing
  `*_CarbonylPeakFitParams.csv` / `*_CarbonylPeakArea.csv` row sets are unchanged.
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

Unknown keys raise (see the trap in §0). Valid keys: `half_window`,
`interp_half_window`, `fill_half_window`, `num_std`, `smooth_half_window`,
`weights`.

### Voigt bounds stay in `voigt_fit.param_rules`

Extra peaks' bounds are hand-edited directly in `voigt_fit.param_rules`. The
staged `[1790, 1800]` / `[1770, 1780]` entries already serve 1795 / 1775 and are
inert for the live path, so editing them costs nothing in production. No
`ir_fitting`-local rule set.

One guard: `select_param_rule` falls through to the `default: true` rule when no
`range_cm1` matches, and that default sets `sigma.max: 6.37` / `gamma.max: 2.8`
— far too narrow for broad bands, and silent. `_warn_on_default_rule` logs a
warning naming the peak and the bounds it got. Replacing the catch-all itself is
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

**Currently inactive: `extra_peaks_base` is `[]`.** Everything below describes
machinery that works and a decision record for when the peaks are seeded again.

### What they are

Two low-wavenumber bands that were fitted historically and then dropped:

| Dataset | Fitted `Peak_Name` values present |
|---|---|
| `nn1120-2_pd_ceo2_000` (2024-11) | `Peak_1775`, `Peak_1795`, … **no** `Peak_2093`, `Peak_2176`, `Peak_2196` |
| `nn1120-3_pd_ceo2_004` (2026-03) | `Peak_2093`, `Peak_2176`, `Peak_2196`, … **no** `Peak_1775`, `Peak_1795` |
| `nn1120-4_pd_ceo2_000` (2026-06) | same as above |

Facts to preserve:

- 12CO base values are **1845** and **1825**; at the default `13CO` isotope
  (`isotope_shift_cm1: -50`) they become **1795** and **1775**.
- `Peak_Name` strings are established in historic CSVs as exactly `Peak_1795`
  and `Peak_1775` — integer-formatted, no decimals.
- Fitted `Amplitude` for these bands is **negative** (negative-going in log
  reflectance). Nothing may assume positive amplitude. This is also why no
  envelope-based baseline score works (§14.3 finding 4).

### Append, don't refit

These two sit ~180 cm⁻¹ below the lowest currently-fitted peak (`Peak_1975` at
13CO), so there is no meaningful Voigt overlap with the existing 18 and the
existing fit need not be re-solved. Default: **read the existing
`*_CarbonylPeakFitParams.csv`, fit only the `ir_fitting` peaks, append those
rows** (`append_only=True`).

A consequence worth using: the saved `*_CarbonylFitResidual.csv` contains these
bands *unmodeled*, because the original fit declared no peaks below 1975. The
residual over 1750–1850 is a direct sanity check on a new fit.

### Known problem when they were last seeded

With 1845 / 1825 seeded, fitted parameters pinned at their rule bounds across 72
files of `nn1120-3_pd_ceo2_004`:

| Peak | Parameter | Pinned in |
|---|---|---|
| `Peak_1795` | `center` at min (1790) | 33/72 |
| `Peak_1795` | `center` at max (1800) | 17/72 |
| `Peak_1775` | `center` at max (1780) | 30/72 |
| `Peak_1775` | `center` at min (1770) | 8/72 |
| `Peak_1775` | `sigma` at min (2.55) | 42/72 |
| `Peak_1795` | `sigma` at max (26) | 25/72 |

Both centers hit a bound in ~70% of files, pushing *toward each other* — 1795
down to 1790, 1775 up to 1780 — while 1795's sigma pins wide and 1775's pins
narrow. That pattern says the two bands are competing to describe one feature
and the `[1790, 1800]` / `[1770, 1780]` windows are not where the data wants
them.

So: **`param_rules` need attention before these peak areas mean anything.** Any
areas produced before the bounds stop binding are provisional. Also note
`sigma.max: 26` is a Gaussian FWHM of ~61 cm⁻¹, with tails reaching ~1900 cm⁻¹
— which is where the isolation argument above starts to weaken.

## 5. Per-file fit procedure

Input is a subIFG file path, e.g.
`C:\Data\OpusConvert_subIFG_lgRfl\<folder>\<name>.<index>`.

1. Resolve paths, reusing `DataAnalysisRunner._resolve_paths` semantics:
   `folder_name`, `file_name`, `file_index`, `delta_file`.
2. Honor `manually_skip_files` (`delta1` index > 2, and all of
   `delta2`/`delta3`/`delta4`) exactly as the live path does, so offline and
   live cover the same files.
3. Load the existing `*_CarbonylPeakFitParams.csv` for the dataset.
4. Load the subIFG array over 1750–2250.
5. Obtain a baseline (§6) and subtract it.
6. Build `lmfit.Parameters` for the `ir_fitting` peaks only, via `add_params`, so
   they pick up `voigt_fit.param_rules` unchanged. All `ir_fitting` peaks go into
   **one** `Parameters` set and are fitted jointly: 1795 and 1775 are 20 cm⁻¹
   apart with `sigma.max: 26`, so they overlap each other substantially and
   cannot be solved independently.
7. Fit with `peak_fit`, evaluate each peak's `voigt_model`, integrate with
   `-trapezoid(y_fit, wavenumbers)` — sign convention identical to
   `peak_analysis`.
8. Build rows, merge, write to `_test/` (§7, §8).

### Guard: parameters pinned at their bounds

A fitted parameter sitting exactly on a bound means the optimizer wanted to go
further and the rule stopped it, so the value reflects the bound, not the data.
`_warn_on_pinned_params` checks `center`, `amplitude`, `sigma`, `gamma` against
both bounds. Two cases carry extra meaning:

- **`sigma` at max** — the band is wider than the rule allows and its tails may
  reach the existing cluster, which is when `append_only=True` stops being
  obviously safe.
- **`center` at either bound** — the band wants to sit outside its rule's
  window, i.e. the seeded wavenumber is probably wrong.

Individual messages log at DEBUG and collect on the result; `api.py` aggregates
them into one WARNING per distinct issue per run, because a measurement holds
dozens of files and a per-file warning repeats endlessly.

### FSD peak snapping — not performed, matching current live behavior

The live path calls `find_fsd_peaks` + `resolve_peak_lists` intending to snap
each nominal peak to a detected FSD peak within 5 cm⁻¹. That snapping does not
happen: `find_fsd_peaks` returns `peaks` — the **array indices** from
`scipy.signal.find_peaks` (`spectral_fitting.py:216`, which computes
`peak_wavenumbers` then discards it) — while `resolve_peak_lists` compares those
against wavenumbers with `atol=5.0`. Indices run 0–258, wavenumbers 1750–2250,
so nothing ever matches.

Confirmed in the data: `Peak_Value` differs from nominal only in
`nn1120-2_pd_ceo2_000` and `nn1120-3_pd_ceo2_000`, and is exactly nominal from
`nn1120-3_pd_ceo2_001` onward.

`ir_fitting` therefore sets `Peak_Value` to the nominal shifted wavenumber and
does not load FSD data at all, reproducing current live output exactly. Fixing
the live path is **out of scope** — it would change `Peak_Value` in new output,
and output schemas are a public contract.

### Column derivation for appended rows

| Column | Source |
|---|---|
| `File` | `delta{N}.{index}`, e.g. `delta5.0007` — 4-digit index, matching existing rows |
| `Delta_Group` | `delta{N}` |
| `Peak_Name` | `Peak_<shifted integer>` — `Peak_1795`, `Peak_1775` |
| `Peak_Value` | the nominal shifted value (see FSD note above) |
| `Center`, `Amplitude`, `Sigma`, `Gamma`, `Y0` | from the fit |
| `fwhm` | Voigt pseudo-FWHM, same formula as `peak_analysis` |
| `Peak_Area` | `-trapezoid(y_fit, wavenumbers)` |
| `Data_Integral` | **copied** from an existing row for the same `File`. A whole-ROI integral, identical across every peak row in a file — recomputing would be redundant and could drift. |
| `Time_Delta (s)` | **copied** from an existing row for the same `File`. Recomputing needs the subIFG log + exp-params chain; copying is exact and cheaper. |
| `PdCO_mol`, `PdCO_mol_stderr` | **Left empty (NaN) on appended rows.** The column is preserved and every existing row keeps its historical value — the merge must not drop or blank it. The calibration slope is hardcoded to two folders in `io.py::import_calibration_data` and was derived in the carbonyl region; applying it at 1775–1795 is not justified. |

## 6. Baseline in the fit path

`create_baseline` wraps
`pybaselines.classification.std_distribution(data, x_data, half_window,
interp_half_window, fill_half_window, num_std, smooth_half_window, weights)`.
It receives the intensity array and those settings and **nothing else — there is
no peak list argument**. The baseline has never known which peaks were declared,
so declaring more cannot change it. Verified: two `create_baseline` runs over the
same ROI with the same settings return bit-identical arrays.

So the `baseline=` switch is not "saved vs. different":

| `baseline` | Purpose |
|---|---|
| `"saved"` (default) | Read the `delta{N}.{index}` column from the dataset's `*_CarbonylFitBaseline.csv`. Cheapest, and guarantees appended peak areas sit on exactly the same baseline as the existing 18. |
| `"recompute"` | Needed when the saved CSV is missing or lacks a column for that file. Also the hook for settings-level EDA. |

Passing `baseline_settings=` forces `"recompute"`, since a stored column would
ignore the override. With no override the two agree to 1e-16, which is a useful
self-check rather than redundancy.

**`half_window` and friends are counts of samples, not cm⁻¹**, so they only stay
meaningful while the window is fixed. Changing the array extent changes the
baseline globally — sometimes by tens of percent (§14.3 finding 2), not the
fraction of a percent an earlier draft of this spec estimated.

## 7. Collision handling

`nn1120-2_pd_ceo2_000` **already has** `Peak_1795` and `Peak_1775` rows. Blindly
appending would duplicate rows for the same `File` / `Peak_Name`, which then flow
into `compute_cumulative_peak_area_df` as double-counted fit history.

Controlled by `on_existing`:

| Value | Behavior |
|---|---|
| `"skip"` (default) | Leave the existing row untouched, do not fit, log at INFO. Run summary reports fitted / skipped counts. |
| `"overwrite"` | Drop the existing row and replace it with the new fit. For re-running after a param-rule change. |
| `"error"` | Raise `ExistingPeakRowsError`. For reprocessing runs that must not silently no-op. |

### Backfilling peaks missing from a historic dataset

The churn runs both ways: `nn1120-2_pd_ceo2_000` also lacks `Peak_2093` /
`Peak_2176` / `Peak_2196`, which the current live `peak_list_base` contains.

`append_only=True` does **not** backfill these and cannot do so correctly.
Unlike the two low bands, those three sit *inside* the existing cluster (2093
between 2103 and 2073, and so on), where Voigt profiles overlap substantially.
Adding one changes its neighbours' fitted amplitudes and widths, so its
parameters cannot be solved while the neighbours are held at saved values.

`append_only=False` handles it by construction: it discards the saved parameters
and refits every peak in `voigt_fit.peak_list_base` plus
`ir_fitting.extra_peaks_base` jointly from the subIFG. Backfilling is not a
missing feature — it is the full-refit path, and the reason that flag exists.

A full refit replaces **every row for every file it touched**, not just the
`(File, Peak_Name)` pairs it reproduces. A saved CSV can hold a peak the current
list has dropped; keeping such a row would mix two models' output within one
file, and the per-peak curves would no longer sum to the composite. Files the
run did not touch — those `manually_skip_files` excludes — keep their rows.

## 8. Outputs

Never writes into a source folder. Two destinations, by purpose.

**Fit output** — `writer.resolve_output_dir`, a subfolder of the source dataset
folder, `_test` by default. An empty / `"."` / absolute `output_folder` is
rejected because it would collapse back onto the source.

```
C:\Data\peakFit\<dataset>\_test\
  <name>_CarbonylPeakFitParams.csv   existing rows + appended ir_fitting rows
  <name>_CarbonylFitBaseline.csv     baseline actually used, per file column
  <name>_CarbonylFitResidual.csv     residual after the ir_fitting peaks are modeled
```

- Column order and names match the live schema exactly, so this output is
  readable by existing plotting and kinetics code unmodified.
- `*_CarbonylPeakArea.csv` (cumulative areas, `cluster_sum`, kinetics columns) is
  **out of scope**. Grouping the new peaks as cluster peaks would change
  `cluster_sum`; that belongs in a separate deliberate step.
- The residual is **full-ROI**. Under `append_only=True` the existing 18 peaks
  are reconstructed from their saved `Center`/`Amplitude`/`Sigma`/`Gamma`/`Y0` —
  the same reconstruction `plot_spectrum_fit.py::_build_delta_group_fit`
  performs — and the new peaks added to that composite before differencing.
  Outside the new-peak region it reproduces the live path's saved residual,
  which is a free regression check.
- Residual sign convention is `model - data`, inherited from
  `spectral_fitting.py::objective`. Stated because it is easy to plot inverted.

**Baseline-experiment output** — `api.baseline_experiment_dir`, under the figures
tree:

```
C:\Figures\<dataset>\baseline_experiments\<run_name>\
  <subifg filename>.png          one per file, all variants overlaid
  baseline_comparison.csv        one row per (file, variant)
```

Figures rather than `data.peak_fit` because this is an experiment log to look
at, not pipeline data, and nothing downstream reads it. That also keeps it clear
of `resolve_output_dir`, whose job is protecting the params CSV from in-place
overwrite — a hazard figures do not have. Use a distinct `run_name` per
experiment so runs do not overwrite each other.

## 9. Visualizations — `src/visualizations/`

These render; they do not compute. `plot_spectrum_fit.py` is left alone: it sums
every file within a delta group into one trace and draws individual curves only
for monomer peaks, which is a different question from per-fit inspection.

### `plot_individual_fit.py` — one figure per file

Unit is one subIFG file (one delta group, one index).

```
  black   data (baseline-subtracted)
  red     composite fit
  dashed  each peak, one line per peak, labeled by Peak_Name
  blue    residual
```

Individual curves for **all** peaks present, not just monomer; `ir_fitting`
peaks visually distinguished from the pre-existing 18; residual offset below the
data so it stays readable at its own amplitude, or `stacked=True` for a
shared-x two-panel layout; x inverted, 2250 → 1750.

### `plot_baseline.py` — viewing and comparing baselines

- `plot_baselines(folder, name)` / `plot_file_baseline` — raw subIFG, its
  baseline, and the subtracted signal for saved or recomputed baselines. When
  recomputing, the saved baseline is overlaid with a printed
  `max |recompute - saved|`.
- `plot_baseline_comparison` — the renderer for `api.compare_baselines`. Draws
  variant against variant, which the functions above cannot: they compare only
  against the stored CSV column. Display limits are the **union** of every
  variant's window, so a narrower variant's trace visibly *stops* instead of
  being cropped out of view. Legend carries each variant's shift, its window
  when it differs from the reference, and a `DEGENERATE` marker.

## 10. Entry points

```python
from src.utils.ir_fitting import (
    BaselineVariant, compare_baselines, fit_file, fit_folder, load_measurement,
)
```

### Baseline experimentation

```python
compare_baselines(
    [
        ("current",        {}),                       # first = the reference
        ("num_std 1.4",    {"num_std": 1.4}),         # settings change
        ("window 2200",    {}, (2200.0, 1750.0)),     # window change
    ],
    folder_name="nn1120-4_pd_ceo2_000",
    files=None,          # None -> baseline.JUDGED_FILES
    run_name="sweep",
)
```

Every variant is measured against the **first**, so put the baseline being
compared to at the front. A variant is a `BaselineVariant` or a
`(label, settings[, window])` tuple; `window` is `(high, low)` cm⁻¹ and defaults
to the 2250–1750 ROI.

Variants with different windows produce different-length arrays, so they are
compared on their **overlap**, intersected by wavenumber *value* (see the
descending-wavenumber trap in §0). The compared region is reported per row.
Unknown settings keys, bad windows and non-overlapping windows raise at variant
construction, not partway through a batch.

The returned table reports `moved_pct_of_range` — how far each baseline sits
from the reference, as a percentage of that file's signal range. **It says the
baseline moved, not that moving it helped.** There is no quality score; see
§14.3 finding 4.

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

The unit is one **measurement** (a base name), not one subIFG file: `fit_file`
iterates every delta group / index sharing that base name, matching the
granularity of the params CSV, and writes one merged CSV. `fit_folder` does every
measurement in a dataset.

`load_measurement` loads and reconstructs the saved fit without fitting or
writing anything — the inspection path, and it does not depend on
`extra_peaks_base` being seeded.

All return in-memory bundles (wavenumbers, per-peak curves, composite, residual,
baseline, rows) that the plot modules consume directly, so an EDA session can
compute and plot without a round trip through disk.

## 11. Decisions settled

| Item | Decision |
|---|---|
| Architecture | Wrap `src/analysis/spectral_fitting.py`; do not re-implement it (§2). |
| Naming | `ir_fitting` for both the package and the `config/analysis.yaml` key. |
| Append/refit | `append_only: bool = True`. `True` reuses saved params and fits only the `ir_fitting` peaks; `False` refits every peak jointly (§7). |
| Fit unit | `fit_file(base_name)` = one measurement; `fit_folder(folder)` = a dataset. Mirrors `src/utils/kinetics`. |
| Peak values | `extra_peaks_base` ships empty and is seeded by hand. 1845 / 1825 reproduce the historic `Peak_1795` / `Peak_1775` (§4). |
| Param rules | Hand-edited in `voigt_fit.param_rules`. No `ir_fitting`-local rules; only a warning when a peak falls through to the catch-all (§3). |
| `PdCO_mol` | Not populated on appended rows; existing rows retain historical values. |
| Baseline default | `"saved"`. `"recompute"` is for a missing column and for settings EDA, not because the two differ by default (§6). |
| Baseline override | Implemented as a yaml block *and* a per-call kwarg; unknown keys raise (§3). |
| Baseline window | A `BaselineVariant` field, applied at load. **Array truncation is rejected** as a fix — at the top edge (§14.3 finding 2) and at the isosbestic point (§14.6 finding 7). |
| Isosbestic point | Exists at **~1957 cm⁻¹** in lgRefl, 27/35 measurements; the other 8 cross elsewhere (~2052–2087), including the `...-022` regression gate (§14.6). Measured, not assumed. |
| Baseline scoring | None. Judgement is visual (§14.3 finding 4). |
| Experiment output | Figures tree, one folder per `run_name` (§8). |

## 12. Out of scope, and deferred

Out of scope:

- Promoting the extra peaks into `voigt_fit.peak_list_base` / `cluster_peaks_base`.
- Regenerating `*_CarbonylPeakArea.csv`, `cluster_sum`, or any kinetics output.
- Backfilling peaks missing from historic datasets (§7 — use `append_only=False`).
- Any change to `src/analysis/`, the ZMQ server, or live output schemas.
- Fixing the live FSD snapping bug (§5).
- A CLI. Added only if the workflow needs A/B flags, as `src/utils/kinetics` did.

Deferred, to revisit:

- **The catch-all param rule.** `voigt_fit.param_rules`' final entry
  (`range_cm1: [0, 0]`, `default: true`) silently supplies narrow bounds to any
  peak matching no explicit window. Flagged for replacement; for now only a
  warning fires (§3).
- **Threading `window` into the fit path.** `runner.load_subifg_roi` accepts it;
  the fit path does not pass it. Changing the ROI that *peaks* are fitted over
  would put `Peak_2196` (13CO) ~4 cm⁻¹ from a window edge and would invalidate
  §13's residual regression check.

## 13. Verification log

`nn1120-3_pd_ceo2_004` / `20260304_145524_pd_ceo2_004-000` (72 files after
`manually_skip_files`) and `nn1120-2_pd_ceo2_000`, with
`extra_peaks_base: [1845, 1825]` where peaks were needed.

| Check | Result |
|---|---|
| Residual vs. live saved residual above 1900 cm⁻¹ | max abs diff **7e-16**. Reconstructing the existing 18 peaks from saved parameters reproduces the live path, which is what makes append-only sound. |
| `baseline="recompute"` vs `"saved"`, no override | max abs diff **1e-16** across all 72 files — confirming §6. Re-run after any change here. |
| `baseline_settings=` passed | forces `baseline_source == "recompute"`; `num_std: 1.4` moves the baseline by 2.1e-4. |
| `on_existing="skip"` on `nn1120-2` (peaks already present) | 0 fitted, 238 skipped, row count unchanged at 2023. |
| `on_existing="overwrite"` | 238 refitted, row count still 2023 — replaced, not added. |
| `on_existing="error"` | raises `ExistingPeakRowsError`, which the per-file guard re-raises rather than logging. |
| `PdCO_mol` on `nn1120-2` | 1785/1785 historical rows retain their value; 0/238 new rows carry one. |
| Empty `extra_peaks_base` | no-op with a warning. |
| Invalid `on_existing` / `baseline` / `output_folder` / settings key / window | rejected up front with `ValueError`. |
| Degenerate baseline (`num_std: 0.8`) | flagged on the trace, in the legend and in the CSV — not silently plotted. |

## 14. Baseline investigation

Active workstream. Dataset `nn1120-4_pd_ceo2_000` (35 measurements).

### 14.1 The problem and its constraints

The current settings (`voigt_fit.baseline`: `half_window: 10`,
`interp_half_window: 5`, `fill_half_window: 6`, `num_std: 1.1`) were **tuned for
the no-nucleation regime — "Regime 1"**. They do not generalise to spectra where
nucleation has occurred and the carbonyl envelope has changed shape.

1. **The current baseline is good overall.** Only a handful of files are wrong.
   Whatever replaces it must *retain* the baselines that already work — this is
   a fix for a minority of files, not a wholesale replacement.
2. **Where it fails, it fails large.** On the `.0042` files the baseline cuts
   the peaks near **2050 and 1960 in half** — a large error in exactly the
   region the cluster peaks occupy.

**Framing, as instructed:** the baseline is wrong and the peak areas come out
low as a result — but **the low areas are a symptom, and whether the baseline is
the whole story is not settled.** Do not treat "fix the baseline" as the agreed
problem statement.

### 14.2 The judged files

Encoded as `baseline.JUDGED_FILES`, and the default target of
`compare_baselines`. All from `nn1120-4_pd_ceo2_000`.

| File | Verdict |
|---|---|
| `20260715_094622_pd_ceo2_000-007_delta10.0042` | bad — peaks near 2050/1960 cut in half |
| `20260717_203829_pd_ceo2_000-008_delta10.0042` | bad — same |
| `20260728_032548_pd_ceo2_000-012_delta10.0052` | bad |
| `20260806_105210_pd_ceo2_000-017_delta10.0022` | bad |
| `20260811_072450_pd_ceo2_000-021_delta10.0022` | bad |
| `20260825_052349_pd_ceo2_000-027_delta10.0052` | bad |
| `20260813_195617_pd_ceo2_000-022_delta10.0022` | **good** |
| `20260813_195617_pd_ceo2_000-022_delta10.0042` | **good** |

`...-022` is the regression gate: its spectrum is substantially different and its
current baseline is *perfect*, so a candidate that degrades it is disqualified
regardless of what it does for the other six. It also constrains the isosbestic
idea directly — **in some of its files the 1940–1960 window is where the maximum
sits**, so an anchor there would be anchoring to a peak. Any anchor rule needs a
guard that detects "this window holds a maximum, not background" and falls back.

**Evidence quality — read before relying on any conclusion below:**

- **One measurement is certified good**, so "this does not break what works"
  rests on **n=1**. `...-022` is also *short* — indices 0012–0052 only — so it
  never reaches the high-index regime where the failures are worst.
- Every other file in the dataset is **unlabelled, not known-good**. Six files
  were looked at; they are not necessarily the only wrong ones.

### 14.3 Findings

Numbers are percentages of a file's signal range (`max(y) - min(y)` over the
ROI), because raw log-reflectance differences are ~1e-4 and unreadable alone.
For scale: **the 2040 cm⁻¹ peak is about 20% of signal range**, so a 10%
baseline shift is half that peak's height.

**1. Tuning the existing parameters does not fix these files.** All five exposed
settings swept, 12 combinations, over the eight judged files.

On the bad files every candidate produces nearly the **same** near-linear
baseline. The reason is structural: those spectra swing so hard (on
`...-007 delta10.0042`, a peak at ~2145 and a trough at ~2098, excursions of
±0.004 about a ~0.004 level) that `std_distribution` finds almost no stretch it
can classify as background, and falls back to interpolating between the ROI
edges. The parameters have nothing to grip.

Magnitude agrees: restoring a halved peak needs a **6–14%** correction, and the
largest local move any candidate achieved on any bad file was **8%** — by a
setting that disturbed the good file more. Strong evidence, not proof: 12
combinations of many possible. `smooth_half_window` moves the bad files by
exactly zero.

**2. Do not truncate the array to 2200–1750.** Note this *narrows* the current
ROI (1750–2250) at the top edge; an earlier draft called it a widening to
2200–1700.

Because the window *is* the array the algorithm sees (§0), dropping 2200–2250
moves the baseline by up to **13%** of range on the good file, worst at
2030–2150 where the cluster peaks sit — up to 48% across a 30-file unlabelled
sample. **It disturbs the good files more than the bad ones**, the opposite of
what constraint 1 requires.

If 2200 is used, the safe form is an **anchor** the baseline must pass through,
with the array left at 1750–2250. The anchor-vs-truncate choice is **not
settled** — it was raised once before the terms were explained.

**3. The six flagged files are one progression, not two failure modes.** Across
each failing measurement's whole `delta10` group, `max(baseline - data)` near
2050 rises monotonically with index and crosses zero around index 0032–0042. The
`.0022` files sit just *before* that crossing and the `.0042`/`.0052` files just
*after* — the same curve, opposite sign. A regime change through the run, not
two bugs. (That quantity is a rough proxy for how far the envelope has grown,
**not** a measure of badness — see finding 4.)

**4. There is no automatable quality score.** The obvious metric — baseline
rising above the data, violating a lower envelope — is wrong here. The
low-wavenumber bands are negative-going (§4), so these spectra carry features of
both signs and the baseline is a **centre-line estimator**, not a lower
envelope. Scored that way the **good** file comes out worst of all eight judged
files. Any envelope-style score would rank the one certified-good baseline as
the most broken.

So the tooling renders comparisons and reports how far a baseline moved; it does
not judge. **Judgement is visual.**

### 14.4 Proposed approach — isosbestic anchor (not built)

Unblocked by 14.3 but gated on the open question in §0.

1. **Normalise y at 2200 cm⁻¹.** Shift each spectrum by a constant `y0` so they
   all share the same value at 2200, making spectra comparable so an isosbestic
   point can be located across them. The array extent stays 1750–2250 —
   truncation is rejected (finding 2).
2. **Find the isosbestic point `ip`** within an adjustable tolerance window;
   candidate lookup range **1940–1960 cm⁻¹**, chosen by eye. (1900 was
   considered and is less preferred.)
3. **Use `ip`** either as a split point for two baselines, or as a single anchor
   the one baseline must pass through.

The framing worth keeping: **the isosbestic point is a flag within an otherwise
unknown background estimation.** It is not itself the background — it is the one
place the spectra agree, so it is the one defensible place to anchor or split.

A supporting observation from the figures, *(inferred, unconfirmed)*: the bad
spectra are **oscillatory / derivative-like** while the good one is smooth with
a single broad negative band. A derivative lineshape crosses zero, which is a
genuine anchor, whereas `std_distribution`'s variance test has nothing to grip.
That would be what a subIFG — a difference of two interferograms — produces when
a band *shifts* between them rather than simply growing.

**The segment interface is the weak point** if `ip` is used as a split. Two
baselines meeting at `ip` may show a slope discontinuity or visible kink even
when each segment is individually reasonable. Options, none evaluated:

- enforce continuity of value at `ip` only, accepting a slope break;
- blend the two segments over a narrow window around `ip`;
- fit both segments jointly with a continuity constraint;
- **use `ip` only as an anchor point, never splitting the curve** — this
  deserves attention precisely because it removes the problem rather than
  managing it.

### 14.5 What to settle next

1. ~~Does an isosbestic point exist at 1940–1960 across the folder?~~
   **Answered in §14.6: yes, at ~1957, in 27/35 measurements.**
2. **Where is the crossing, per measurement?** Promoted to *the* blocking
   question by §14.6. The eight measurements without a crossing at 1957 have one
   *elsewhere* (`...-022` at ~2052), so the job is to locate it per measurement,
   not to detect its absence and give up. A fallback is still needed for the
   case where nothing is found.
   §14.6's `spread / noise_floor` ratio is only a **candidate** detector — it
   separates the two groups cleanly (≤2.5 vs ≥11.6) but the denominator is
   confounded (finding 6), so it needs a noise-floor-independent form first.
3. **Anchor as a split point or as a single pass-through point?** Still open,
   but §14.6 rules out the third reading — the point may not be used as a
   *truncation* edge.
4. **Does any of this reach the live path?** Changing `voigt_fit.baseline`
   changes what the instrument computes live; an `ir_fitting.baseline` override
   or a per-call kwarg does not. Default assumption: **offline only** until
   proven otherwise. Everything built so far is offline.

### 14.6 Isosbestic probe — measured

Two throwaway scans over `nn1120-4_pd_ceo2_000`, plus one run of
`compare_baselines`. No new module: §2's extension point earns code only once a
rule survives, and nothing here has yet.

**The right place to look is lgRefl, not subIFG.** The first scan tested the
subIFG files directly — if the lgRefl curves share a crossing at `ip`, every
subIFG passes through zero there, needing no normalisation. It came back
negative (best median `|y|/range` anywhere in the ROI was 24%, at 2088; 1950 was
41%). **That test is confounded and its negative result should not be trusted:**
`|y|/range` reached **102%** on `...-022_delta10.0022`, i.e. the difference
spectrum is offset bodily away from zero, which baseline drift between the two
members of a delta-10 pair does. The offset inflates `|y|` at every wavenumber
and buries any crossing.

The lgRefl test is immune to that by construction — shift each spectrum in a
measurement to zero at 2200 cm⁻¹ (§14.4 step 1) and measure the spread
(`max - min`) across them at each wavenumber.

**Finding 5. The isosbestic point is real, and it is at ~1957 cm⁻¹.**

| | |
|---|---|
| Measurements whose tightest spread falls in 1942–1961 | **27 of 35**, clustering at 1955–1959 |
| Median spread profile | local minimum at **1959.3** (3.4e-3), flanked by 7.1e-3 at 2000 and 9.9e-3 at 1940 — a factor of 2–3 on both sides |
| Absolute spread there vs. the 2235–2250 noise floor | ratio **0.17–2.5** for those 27 — at or below the noise |

A local minimum flanked on both sides, sitting at the noise floor in absolute
log-reflectance units, is a crossing. Reporting spread only as a percentage of
each measurement's own maximum would not have shown this — a measurement that
grew a large feature near 2100 inflates its own denominator — so the absolute
units and the noise-floor comparison are what make the claim, not the
percentages.

**1950 is not the point; 1957 is.** ~7 cm⁻¹ / ~4 grid steps off. Median spread
at 1950 is 4.2e-3 against 3.4e-3 at 1959, ~24% worse.

**Finding 6. Eight measurements cross somewhere else — including the
regression gate — but the crossing moves, it does not vanish.** `...-006`,
`-013`, `-014`, `-016`, `-018`, `-019`, `-020` and `-022` put their tightest
spread at **2052–2087** instead. For `...-022` the spread at 1950 is 2.5e-2, a
ratio of **20.2** to its noise floor: 1940–1960 is where its curves fan out
*widest*. This is §14.2's warning — "in some of its files the 1940–1960 window
is where the maximum sits" — confirmed quantitatively, from the offset-immune
measurement.

But `...-022` has a perfectly good crossing of its own at **2051.9 cm⁻¹**
(spread 2.2e-3, ratio **1.8** — inside the range the other 27 show at 1957). So
the useful statement is not "eight lack a crossing" but **"the crossing sits at
1957 in one regime and near 2052 in another."** A rule that *locates* the
crossing per measurement handles `...-022` correctly; a rule that hardcodes 1957
does not. This is what §14.5 item 2 now asks.

Two caveats on the split, both of which weaken it:

- **The ratio's denominator is confounded.** The eight have systematically
  *lower* noise floors (median 7.2e-4) than the 27 (median 3.1e-3), a factor of
  ~4. Absolute spread at 1950 alone does **not** separate the groups — they
  overlap (27-group max 8.8e-3, 8-group min 4.6e-3). So the clean bimodality in
  the ratio is partly manufactured by the denominator, and the ratio is a
  candidate detector, not a validated one.
- **Six of the eight are the short measurements** (n = 50–95 spectra, median 58,
  against a median of 130 for the 27). Fewer spectra spanning less of the run
  means less opportunity to cross anywhere. §14.2 already flags `...-022` as
  short. So part of "crosses elsewhere" may be "was sampled too briefly", which
  changes what the fallback has to handle.

**Finding 7. Truncating the array at the isosbestic point is rejected**, on the
same grounds as finding 2 and more decisively. `compare_baselines` with
`(2250.0, 1950.0)` and `(2250.0, 1957.0)` against the eight judged files:

| Files | `moved_pct_of_range`, truncate 1950 / 1957 |
|---|---|
| the six bad | 0.5–8.3 / 0.4–9.6 |
| **`...-022_delta10.0022` (good)** | **74.0 / 66.5** |
| **`...-022_delta10.0042` (good)** | **52.7 / 54.3** |

It moves `...-022` by 5–10× what it moves the files the change is meant to fix.
**Read this as the gate requirement, not as a disqualification.** `...-022` is
in `JUDGED_FILES` precisely *because* it has an extremum at the wavenumber under
test — its raw subIFG minimum sits at **1942.0 cm⁻¹**, 8 cm⁻¹ from the 1950 cut,
and the 74% move occurs at **1951.6 cm⁻¹**, right at the cut edge. Cutting the
array on the shoulder of a large excursion makes the baseline terminate where
the data is swinging hardest, and it swings with it.

So a bare truncation at a constant wavenumber is out, but truncation *behind a
guard* is not tested: **if a local extremum lies within ±25 cm⁻¹ of the
candidate point, do not cut — keep the whole 1750–2250 array.** That guard is
the next thing to try, and `...-022` is the file that defines it. Figures:
`C:\Figures\nn1120-4_pd_ceo2_000\baseline_experiments\truncate_1950\`.

Worth noting on the other side: the bad files move 7–9.6%, against the 6–14%
correction finding 1 says is needed and the 8% ceiling any settings sweep
reached. Something in this direction has the right magnitude — truncation is
just the wrong mechanism, because it also deletes the baseline below 1950
entirely.

**What this leaves standing.** The anchor reading of §14.4 step 3 — `ip` as a
single point the one baseline must pass through, array left at 1750–2250 — is
untouched by finding 7 and is the only remaining form. It now needs the crossing
**located per measurement** rather than fixed at a constant (finding 6), a
noise-floor-independent "nothing found here" guard, and the current baseline as
the fallback when the guard fires.

Scripts are throwaway, in the session scratchpad, not the repo. The probe figure
is at
`C:\Figures\nn1120-4_pd_ceo2_000\baseline_experiments\isosbestic_probe\isosbestic_probe.png`
— panel 2 (`...-034`) shows the pinch at 1957; panel 3 (`...-022`) shows the
curves at their widest there.
