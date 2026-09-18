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
| **Baseline investigation** (§14) | Active. Tuning and bare truncation ruled out (§14.3, §14.6). The isosbestic point is measured (~1957) and an **anchored baseline is built and calibrated** (§14.7). It recovers the halved bands on the post-crossing files and is a no-op on the pre-crossing ones. **Splitting at the crossing is built and rejected** (§14.8) — though the post-mortem shows it was tested in its worst form, and names the variant worth trying — **that variant is now built and measured (§14.9)**: it keeps all of the anchor's band recovery, verified, and replaces the anchored baseline's unconstrained 205 cm⁻¹ extrapolation below the lowest anchor, at the cost of a seam §14.7 does not have. **Whether to prefer it over §14.7 alone is open — the visual call has not been made.** A fourth anchor at 1854 was tried and removed (§14.7.1). **The lower segment now has anchors of its own — both its endpoints plus 1800 (§14.10), built and measured**: containment above the cut still verified at exactly zero, the seam cut by a third to three quarters on the four post-crossing files, and the `.0022` files' subtracted offset below the cut halved — the first measurement in §14 that moves that regime at all, though whether closer to zero is *better* there is exactly what §14.3 finding 4 says these numbers cannot say. Against it: a seam that *grows* on those same `.0022` files, the post-crossing four's offset pushed back out, and an anchor at 1800 the guard cannot police. **Also a trade; also a visual call not yet made.** |
| **Two extra low-wavenumber peaks** (§4) | Dormant — `ir_fitting.extra_peaks_base` is `[]`, so nothing fits them. The machinery works; the peaks are simply not configured. |

### The open question — answered, and replaced by a harder one

**Is there an isosbestic point near 1940–1960 cm⁻¹ across
`nn1120-4_pd_ceo2_000`?** **Yes — at ~1957 cm⁻¹, in the lgRefl spectra, for 27
of 35 measurements.** Measured in §14.6. §14.4's load-bearing assumption
survives, with two corrections: the point sits at **1957**, not 1950, and the
**eight measurements that lack it there include the `...-022` regression
gate** — though §14.6 finding 6 shows the crossing *moves* rather than vanishing.

The question that replaced it — how to handle a file whose crossing is
elsewhere — is **answered in §14.7**: a per-file prominence guard drops an
anchor with a band within ±25 cm⁻¹, and the baseline falls back to what it
already was. Built, calibrated, and clean on the judged files.

**The open question now:** the `.0022` / pre-crossing files (§14.3 finding 3)
are unchanged by anchoring, and §14.8's split does not reach them either. Half
the progression still has no fix **above 1955**. §14.10 finding 19 is the first
measurement that moves them at all; it moves them only below the cut, and the
direction of goodness there is unjudged.

**The current recommendation is the single anchored baseline of §14.7.** §14.8
tried the other reading of §14.4 step 3 — `ip` as a split point rather than a
pass-through point — and measured it as worse. §14.9 and §14.10 build the form
that is *not* worse and is not obviously better either; both are trades waiting
on a visual judgement, and neither has displaced §14.7 as the recommendation.

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
- **The anchor guard does not protect a low-wavenumber anchor.**
  `ANCHOR_PROMINENCE_FRAC` is a fraction of the *whole ROI* range — which §14.7
  finding 8 had to make it, or it gated every file — and the bands below 1900
  are 2–9% of that range. So an anchor at 1800 passes the guard with the 1795
  band 5 cm⁻¹ away, scoring 0.002–0.089 against a 0.5 threshold (§14.10 finding
  16). A passing guard there means "not visible at ROI scale", not "background".
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

The CSV carries what the guards did as well as what moved: `anchors` /
`anchors_gated`, `split` / `split_gated` / `split_form`, `seam_pct_of_range`,
and — for a `lower_split_cm1` variant — `upper_max_abs_diff` and
`lower_moved_pct` (§14.9). `split_form` is what distinguishes §14.8's truncating
cut from §14.9's lower-only one; both report a cut at the same wavenumber.

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
`(label, settings[, window[, anchors[, split_cm1[, lower_split_cm1[, lower_anchors]]]]])`
tuple; `window` is `(high, low)` cm⁻¹ and defaults to the 2250–1750 ROI.

The last four are the ways a baseline can be changed beyond its settings, and
they are not interchangeable:

| Slot | What it does | Section |
|---|---|---|
| `anchors` | Affine correction pulling the full-ROI baseline to the data at each surviving wavenumber. The array is never cut. | §14.7 |
| `split_cm1` | Cuts the ROI and recomputes **both** sides on their own truncated arrays. Measured and rejected; kept as a knob. | §14.8 |
| `lower_split_cm1` | Keeps the anchored full-ROI baseline above the cut untouched, replaces it only below. Recommended. | §14.9 |
| `lower_anchors` | A *second* affine correction, on the lower segment alone — its own line, its own residuals. Requires `lower_split_cm1`, and raises without it. | §14.10 |

The last two are mutually exclusive and raise if both are set — they cut at the
same wavenumber and mean different things. A comparison that includes either
should also include the plain `anchored` variant, so a change is attributable to
the cut rather than to the anchors; for `lower_split_cm1` that variant is also
what the `upper_max_abs_diff` check is measured against.

Variants with different windows produce different-length arrays, so they are
compared on their **overlap**, intersected by wavenumber *value* (see the
descending-wavenumber trap in §0). The compared region is reported per row.
Unknown settings keys, bad windows and non-overlapping windows raise at variant
construction, not partway through a batch.

The returned table reports `moved_pct_of_range` — how far each baseline sits
from the reference, as a percentage of that file's signal range. **It says the
baseline moved, not that moving it helped.** There is no quality score; see
§14.3 finding 4.

A `lower_split_cm1` variant adds two more: `upper_max_abs_diff`, which must be
**exactly 0.0** because above the cut the baseline is the anchored one by
construction, and `lower_moved_pct`, which carries the variant's actual effect.
The band-height columns cannot: 2040 and 1980 both sit above the cut, so they
are guaranteed to equal the anchored variant's (§14.9 finding 13).

`lower_anchors` adds `lower_anchors` / `lower_anchors_gated`, reported apart from
`anchors` / `anchors_gated` because they are two least-squares lines on two
arrays and 1955 belongs to both. The column to judge a `lower_anchors` run on is
`seam_pct_of_range` — not the band heights, which are pinned to `anchored` by
finding 13, and not `lower_moved_pct`, which only says the lower baseline moved
(§14.10).

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
| Baseline window | A `BaselineVariant` field, applied at load. **Array truncation is rejected** as a fix — at the top edge (§14.3 finding 2) and at the isosbestic point (§14.6 finding 7). That covers truncation that *discards* the region below the cut; giving that region its own baseline is a different proposal, and is rejected separately in §14.8. |
| Anchor: split or pass-through | **Pass-through** (§14.7). The split form is built (`BaselineVariant.split_cm1`) and measured worse (§14.8), so it stays available as a knob but is not the recommendation. |
| Isosbestic point | Exists at **~1957 cm⁻¹** in lgRefl, 27/35 measurements; the other 8 cross elsewhere (~2052–2087) (§14.6). Measured, not assumed. |
| Anchored baseline | Built (§14.7). Affine correction through `(2240, 2006, 1955)`, array left at 1750–2250. The 2240 pin is required — without it the tilt extrapolates and breaks the flat high end. A fourth anchor at 1854 was tried and removed (§14.7.1). |
| Lower-only split | **Built and measured, not yet decided** (§14.9). `lower_split_cm1 = 1955`: the anchored full-ROI baseline stands unchanged above the cut, a second `create_baseline` replaces it below. Verified `max\|diff\|` above the cut = **0.0 exactly** on all 8 judged files. Whether to prefer it over §14.7 alone is the seam-vs-extrapolation trade and is open pending a visual call. |
| Anchor guard | Per-file: reject an anchor with an extremum of prominence ≥ 0.5 of **ROI signal range** within ±25 cm⁻¹. Local-scale prominence does not work — it gates every file (§14.7 finding 8). |
| Halved bands | **2040 and 1980** (`api.REPORTED_BANDS_CM1`), not 2050/1960 as earlier drafts said. |
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
| `lower_split_cm1` leaves the region above the cut untouched | max abs diff vs the `anchored` variant at and above 1955: **0.0e+00** on all 8 judged files, no tolerance applied (§14.9 finding 13). |
| `lower_split_cm1` falls back to §14.7 when the guard fires | `...-022`, both files: cut gated at 1955, result identical to `anchored` — `lower_moved_pct` 0.0, band heights and `moved_pct_of_range` unchanged. |
| `split_cm1` + `lower_split_cm1` together | rejected at variant construction with `ValueError`; they are different operations at the same wavenumber. |
| `lower_anchors` do not leak above the cut | with `LOWER_ANCHOR_POINTS_CM1` applied, `upper_max_abs_diff` is still **0.0e+00** on all 8 files, and the flat 2235–2250 means and both band heights are identical to `anchored` (§14.10 finding 17). `lower_anchors` is excluded from `_recipe_key` on purpose, so the `anchored` twin — and therefore the check — stays in place. |
| `lower_anchors` without `lower_split_cm1` | rejected at variant construction with `ValueError`; there is no lower segment to anchor. A `lower_anchors` entry above the cut is rejected the same way. |
| `lower_split_cm1` unchanged by the §14.10 branch | the unanchored `lower split 1955` variant reproduces §14.9's seams exactly in the same run (−2.87/−1.77/−5.64/+2.02/+0.85/−0.53) and its local-step ratios to the reported precision (2.2/1.2/5.3/10.7/9.8/0.4). |
| `lower_anchors` with the cut gated | `...-022`, both files: `lower_anchors_applied` empty, `lower_moved_pct` 0.0, result identical to `anchored` — the anchors go with the cut rather than being fitted to a segment that was never made. |
| `split_cm1` unchanged by the §14.9 branch | §14.8 finding 11's six seam values reproduced to the reported precision (−7.86/−2.53/−6.05/+1.86/+1.10/−0.61 against its −7.9/−2.5/−6.1/+1.9/+1.1/−0.6) after `split_form` was threaded through that path. |

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
   the peaks at **2040 and 1980 in half** — a large error in exactly the
   region the cluster peaks occupy. (Earlier drafts said 2050/1960; 2040/1980
   is the user's correction and is what the code measures, via
   `api.REPORTED_BANDS_CM1`.)

**Framing, as instructed:** the baseline is wrong and the peak areas come out
low as a result — but **the low areas are a symptom, and whether the baseline is
the whole story is not settled.** Do not treat "fix the baseline" as the agreed
problem statement.

### 14.2 The judged files

Encoded as `baseline.JUDGED_FILES`, and the default target of
`compare_baselines`. All from `nn1120-4_pd_ceo2_000`.

| File | Verdict |
|---|---|
| `20260715_094622_pd_ceo2_000-007_delta10.0042` | bad — peaks at 2040/1980 cut in half |
| `20260717_203829_pd_ceo2_000-008_delta10.0042` | bad — same |
| `20260728_032548_pd_ceo2_000-012_delta10.0052` | bad |
| `20260806_105210_pd_ceo2_000-017_delta10.0022` | bad |
| `20260811_072450_pd_ceo2_000-021_delta10.0022` | bad |
| `20260825_052349_pd_ceo2_000-027_delta10.0052` | bad |
| `20260813_195617_pd_ceo2_000-022_delta10.0022` | **guard** — band at 1942 |
| `20260813_195617_pd_ceo2_000-022_delta10.0042` | **guard** — band at 1938 |

`...-022` is in the list **because its spectrum has an extremum at the
wavenumber under test** — its raw subIFG minimum sits at 1942.0 cm⁻¹, inside the
1940–1960 window. It is the file that *defines the guard*, not a certified-good
baseline that disqualifies candidates. (An earlier draft of this section called
its baseline "perfect"; that was never measured, and §14.7's figures show its
subtracted trace sitting ~1e-3 off zero across 2150–2000.) Any anchor or
truncation rule needs a guard that detects "this window holds a band, not
background" and falls back — built and calibrated in §14.7.

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
2040 rises monotonically with index and crosses zero around index 0032–0042. The
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
3. ~~**Anchor as a split point or as a single pass-through point?**~~
   **Answered, in two stages.** §14.8: not as a *truncating* split — that was
   built and measured, and it keeps the anchors but loses most of the band
   recovery they produce, adding a seam of up to 7.9% of signal range. §14.9:
   but as a **lower-only** cut, it is viable — the pass-through baseline is kept
   intact above the crossing and a second baseline replaces it only below, which
   loses none of the recovery. It still carries a seam (up to 5.6%), which is the
   open part: seam against extrapolation is a judgement, not a measurement, and
   it has not been made.
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

### 14.7 Anchored baseline — built

The anchor reading of §14.4 step 3, implemented in `baseline.py` per §2: a field
on `BaselineVariant` and a branch in `compute()`, no parallel module. The array
stays at 1750–2250 — this is the alternative to truncation, not a variant of it.

```python
compare_baselines(
    [("current", {}), ("anchored", {}, DEFAULT_WINDOW, ANCHOR_POINTS_CM1)],
    folder_name="nn1120-4_pd_ceo2_000",
)
```

**How it works.** `create_baseline` runs unchanged, then an affine correction in
wavenumber is added, fitted to the data at each surviving anchor. The baseline
keeps the shape `std_distribution` gave it; only the shift and tilt change.

**The anchors are a pull, not a constraint.** With three of them the correction
is a least-squares line, so none is hit exactly. Measured residuals at the
anchors are **0.4–3.2% of signal range** (on `...-007`: 0.69% at 2240, 3.23% at
2006, 0.38% at 1955). The 2006 miss is about a third of the 2040 band's height
on that file, so it is not negligible — an anchor moves the baseline toward the
data there, it does not pin it. Two anchors give the unique line through both residuals
`d_i = data(wᵢ) − baseline(wᵢ)`; three or more, a least-squares line; one, a
constant shift (a tilt is not determined by one point); none, the baseline
unchanged — the deliberate fallback.

**The anchors are `(2240, 2006, 1955)`.** 1955 is the lgRefl crossing of §14.6.
2006 is the valley between the 2040 and 1980 bands. 2240 is not optional:

| Variant | flat 2250–2200 residual, mean \|·\| |
|---|---|
| current baseline | ~4e-5 |
| anchors `(2006, 1955)` | **1.5e-3** — ~30× too high |
| anchors `(2240, 2006, 1955)` | ~5e-5 |

Nothing absorbs in 2235–2250, so that region is an independent check: the
subtracted signal must sit at zero there. With only 2006 and 1955 the two
anchors are 50 cm⁻¹ apart, the correction's slope is barely determined, and it
extrapolates across the remaining 250 cm⁻¹ and lifts the whole high end off
zero. **This is the same lever-arm failure as truncation (finding 7), reached by
a different route** — the anchor form is not immune to it, it just has a fix:
pin the high end.

**Finding 8. The guard works, and it needed the right scale.** An anchor claims
"this is background", which is false if a band sits beside it. The guard rejects
an anchor with a prominent extremum within ±25 cm⁻¹.

Prominence must be measured against the **full ROI signal range**, not the local
excursion. A locally-scaled prominence gates *everything*: these spectra are
oscillatory, so there is a wiggle beside every anchor, and the first attempt
gated all six files the anchor exists to help. Against the ROI range the
separation is clean at 1955:

| | prominence / ROI range |
|---|---|
| `...-022` (band at 1942) | **0.75 – 0.82** — gated |
| all six bad files | **≤ 0.24** — passed |

Threshold `ANCHOR_PROMINENCE_FRAC = 0.5`. `...-022` loses its 1955 anchor and
keeps 2240/2006; every other judged file keeps all three.

**Finding 9. The anchor addresses half the progression, as §14.3 finding 3
predicts.** Band heights relative to the current baseline:

| File | index | height 2040 | height 1980 |
|---|---|---|---|
| `...-007` | .0042 | ×1.43 | ×1.71 |
| `...-008` | .0042 | ×1.23 | ×1.21 |
| `...-012` | .0052 | ×2.05 | (ref ≤ 0) |
| `...-027` | .0052 | ×1.66 | ×1.21 |
| `...-017` | .0022 | ×0.98 | ×0.44 |
| `...-021` | .0022 | ×0.99 | ×0.23 |

The `.0042`/`.0052` files — *after* the zero crossing of finding 3 — recover
1.2–2.1×, consistent with bands that were being halved. The `.0022` files —
*before* the crossing — come out unchanged. Anchoring helps the post-crossing
regime and is a no-op on the pre-crossing one. That is coherent with finding 3
describing one progression with a sign change, not a partial failure, but it
means **the `.0022` files still have no fix**.

A ratio is reported only where the reference height is positive. Where a band
sits *below* the current baseline the reference is negative and "×N" would read
as an improvement while meaning nothing; the raw `height_*` column carries those.

**What is still not settled.**

- The `.0022` / pre-crossing regime is untouched by this.
- 2006 was chosen as the valley between the two bands, by eye. Unlike 1955 it
  has no measurement behind it.
- Judgement remains visual (§14.3 finding 4). `height_2040` / `height_1980`
  measure two named bands the user identified; they are not a baseline quality
  score, and `baseline.band_height` says so where someone would reach for one.
- Everything here is still offline. No `voigt_fit.baseline` change.

#### 14.7.1 The fourth anchor at 1854 — tried and removed

**Outcome: `ANCHOR_POINTS_CM1` is `(2240, 2006, 1955)`.** A fourth anchor at
1854 was added, measured, judged not to work, and taken out again by the user.
This subsection is kept so it is not re-added on the same reasoning.

1854 sits below the carbonyl envelope; at the default 13CO isotope the low bands
are at 1795/1775 (§4), so it is ~59 cm-1 clear of the nearer one. The idea was
to extend the lever arm below the bands, the way 2240 extends it above.

**The guard agrees it is background.** Prominence at 1854 as a fraction of ROI
range is **0.01-0.26** across the judged files, against the 0.5 threshold, so
the anchor is never gated there. Placement is defensible; the question is what
it does.

**Finding 12. A fourth anchor is a brake, not an extra lever.** Adding it
*reduces* how far the correction moves the baseline on 6 of the 7 files
measured, and the band recovery falls with it:

| File | index | `moved_pct` 3 → 4 | 2040: 3 anchors → 4 | 1980: 3 anchors → 4 |
|---|---|---|---|---|
| `...-008` | .0042 | 7.7 → **9.4** | ×1.23 → **×1.26** | ×1.21 → **×1.25** |
| `...-012` | .0052 | 17.0 → 7.9 | ×2.05 → **×1.73** | raw 3.6e-4 → 1.6e-4 |
| `...-027` | .0052 | 6.9 → 5.6 | ×1.66 → ×1.60 | ×1.21 → ×1.18 |
| `...-017` | .0022 | 2.9 → 1.8 | ×0.98 → ×0.99 | raw 8.0e-5 → 1.2e-4 |
| `...-021` | .0022 | 3.2 → 2.2 | ×0.99 → ×1.00 | raw 2.2e-5 → 5.9e-5 |
| `...-022` | .0022 | 34.4 → 12.0 | raw 6.0e-4 → -0.7e-4 | raw -5.2e-4 → -13.5e-4 |
| `...-022` | .0042 | 13.9 → 3.2 | ×3.64 → ×2.07 | raw -1.5e-4 → -2.9e-4 |

Only `...-008` gains. The mechanism is visible in the figures: at 1854 the
current baseline already sits on the data, so the fourth residual is near zero
and the least-squares line is dragged back toward no correction at all —
undoing part of the lift the 2006 anchor was supplying at 2040.

**Do not read the 1980 column on the `.0022` files as an improvement.** The
ratios there move a lot (×0.44 → ×0.66 and ×0.23 → ×0.63) but the raw
heights are 2e-5 to 1.8e-4 against 2.1e-3 for the same file's 2040 band — the
1980 band is essentially absent in that regime, and a ratio of two near-zero
numbers is exactly the trap §14.3 finding 4 describes. The `.0022` regime is
still unfixed.

**It costs the high-end check on two files.** Mean `|subtracted|` over
2235-2250, 3 anchors → 4:

| File | 3 anchors | 4 anchors |
|---|---|---|
| `...-012` | 3.5e-5 | **1.3e-4** |
| `...-022_delta10.0022` | 2.5e-5 | **3.0e-4** |
| others | 6.9e-5 - 1.9e-4 | 5.0e-5 - 2.0e-4 |

Same lever-arm story as §14.7's 2240 pin, from the other end: where the
residuals are strongly curved (on `...-022_delta10.0022`, +3.5% at 2240, -8.9%
at 2006, +5.4% at 1854, with 1955 gated) one straight line cannot satisfy four
points, and what gives is the flat region the check watches.

**Why it was removed.** The measurement says three anchors recover more band on
the files this work exists to fix, and the visual judgement agreed. Recorded
because the counter-argument is real and someone will make it again: 1854 *is*
background, it is never gated, and on `...-022` it cuts the disturbance of a
file whose baseline may not need fixing from 34.4% to 12.0%. Damping is not
inherently wrong — it is only wrong if the files being damped are the ones that
need moving, which is a judgement about which files are wrong, and §14.2 says
that is known for six of thirty-five. The call went to band recovery.

**What would make a low-end anchor work**, if it is revisited: the problem is
not the wavenumber, it is that one straight line cannot satisfy four points
spread over 400 cm-1 when the residuals are curved. A low anchor needs either a
non-affine correction or per-anchor weights, both of which are larger changes
than adding a number to a tuple.

**Coverage caveat: n=7, not 8.** `...-007_delta10.0042` was locked by another
process for the whole of this run (`PermissionError` on every read), so it is
absent from every number in this subsection. It is the file §14.8's edge
analysis is built on, and it is one of the two that responded best to anchoring,
so the numbers above are the seven readable files only. That does not change
the outcome — the removal was decided on them plus the figures — but a re-run
would be needed before any of it is cited as complete.

**Retained, not implemented: the noise / duration / pinch-point correlation.**
§14.6 finding 6 records that the eight measurements crossing away from 1957 have
noise floors ~4× lower and are mostly the short ones (median 58 spectra vs 130).
That is a real observation worth keeping, and it may explain which measurements
the guard fires on. It is deliberately **not** built into the guard — the
prominence test above is per-file and needs no measurement-level statistics.
Revisit it only if the per-file guard proves insufficient.
### 14.8 Split baseline at the crossing — built, and rejected

The *other* reading of §14.4 step 3: use 1955 as a split point rather than a
pass-through point. The array is cut there, the upper segment (2250-1955) gets
the default anchors `(2240, 2006, 1955)`, and the lower segment (1955-1750) —
which a bare truncation would simply discard (§14.6 finding 7) — gets its own
`create_baseline` run with the **unmodified** `voigt_fit.baseline` settings.

Implemented per §2 as one more field, `BaselineVariant.split_cm1`, and a branch
in `compute()`. `SPLIT_POINT_CM1 = 1955.0`.

```python
compare_baselines(
    [
        ("current", {}),
        ("anchored", {}, DEFAULT_WINDOW, ANCHOR_POINTS_CM1),
        ("split 1955", {}, DEFAULT_WINDOW, ANCHOR_POINTS_CM1, SPLIT_POINT_CM1),
    ],
    folder_name="nn1120-4_pd_ceo2_000",
)
```

The middle variant is not optional. Without §14.7's anchored baseline as a
middle term, a change cannot be attributed to *the split* rather than to *the
anchors*, which are already known to work.

**The guard gates the split and the anchor independently.** One
`gating_extremum` call, two consequences: a gated anchor is dropped while the
others stand (§14.7), and a gated split falls back to a single segment while
the surviving anchors are still applied. That decomposition is what makes
`...-022` a bit-for-bit regression check rather than a judgement call — it keeps
2240/2006, loses 1955, is not split, and comes out **max |split - anchored| =
0.0e+00** on both its files.

Its `moved_pct_of_range` of 34.4% / 13.9% is therefore §14.7's anchored move,
inherited unchanged — the split adds nothing to it. Not to be read against
§14.6 finding 7's 74% / 52.7%, which was bare truncation moving the baseline
*at the cut edge*; here the guard stops the cut from happening at all.

**Finding 10. The split keeps the anchors and loses most of what they
recovered.** `height_2040` / `height_1980` as ratios to the current baseline:

| File | index | 2040 anchored | 2040 split | 1980 anchored | 1980 split |
|---|---|---|---|---|---|
| `...-007` | .0042 | ×1.43 | **×1.00** | ×1.71 | **×1.08** |
| `...-008` | .0042 | ×1.23 | **×0.63** | ×1.21 | ×1.22 |
| `...-012` | .0052 | ×2.05 | ×1.97 | 3.6e-4 (raw) | 3.5e-4 (raw) |
| `...-027` | .0052 | ×1.66 | **×1.30** | ×1.21 | ×1.19 |
| `...-017` | .0022 | ×0.98 | ×0.97 | ×0.44 | ×0.45 |
| `...-021` | .0022 | ×0.99 | ×1.06 | ×0.23 | ×0.24 |

`...-012`'s 1980 reference height is negative (-1.3e-4), so no ratio is defined
there and the raw heights carry it, as §14.7 finding 9 requires: current
-1.3e-4, anchored 3.6e-4, split 3.5e-4 — the split keeps that one.

Two of the four post-crossing files lose the recovery outright — `...-007` falls
back to the current baseline's height and `...-008` goes **below** it — one
loses half of it, and only `...-012` keeps it. The `.0022` files are unchanged,
the same no-op §14.7 finding 9 reports; the split does not reach the
pre-crossing regime either.

**Why. Two mechanisms, and which one dominates is per file.** The starting
point is §14.3 finding 2: `create_baseline` receives only `y`, so the truncated
2250-1955 array is a *different array*, `std_distribution` classifies background
over it differently, and the affine correction can then only shift and tilt
whatever shape came out. But "different" splits into an edge effect and a global
reshape, and they are not the same problem. Comparing `create_baseline` on the
truncated array against the full-ROI one over 2250-1955, **before any
anchoring**, as % of signal range:

| File | whole upper segment | excluding 20 cm-1 at the cut | after removing the offset |
|---|---|---|---|
| `...-007` | 8.8% | 3.5% | **2.1%** |
| `...-012` | 9.6% | 8.2% | 4.8% |
| `...-008` | 7.0% | 7.0% | **5.6%** |

- **`...-007` is edge-dominated.** Away from the cut the two baselines agree to
  ~3.5%, and only ~2% of that survives removing a constant offset — which is
  what anchoring would have absorbed. The user's expectation that the two should
  differ by little more than a bias is **correct for this file, away from the
  cut**. The 8.8% is concentrated at 1955 itself.
- **`...-008` is a genuine global reshape.** 7.0% everywhere, 5.6% of it shape.
  Its upper baseline arches upward over 2150-2000, riding above both the current
  and the anchored baseline, which is why its 2040 band comes out *shorter* than
  with no correction at all.

**The chain that actually loses the band on `...-007`: the 1955 anchor sits on
the corrupted edge.** Its residual is measured against a baseline that is wrong
by ~8.8% right there, that residual tilts the least-squares line, and the 2006
anchor then lands **-8.2%** off instead of the -2.1% the unsplit anchored
baseline achieves. Misses at each anchor, % of range:

| anchor | anchored | split |
|---|---|---|
| 2240 | +0.38% | +1.47% |
| 2006 | **-2.12%** | **-8.21%** |
| 1955 | +1.74% | +4.76% |

8% of range is about 40% of the 2040 band's height on that file. So the loss is
not "truncation reshaped the baseline" so much as "truncation corrupted the
sample the lowest anchor reads, and one bad residual tilts the whole line."

**This means the split was not given a clean test**, and the rejection in
§14.5 item 3 should be read as "this form of it is worse", not "splitting cannot
work". See the untried variant below.

**Finding 11. The seam is a real discontinuity, and it is not small.**
Reported as `seam_pct_of_range`, the jump across the cut as a percentage of the
file's signal range (the 2040 band is ~20% of range for scale):

| File | seam |
|---|---|
| `...-007_delta10.0042` | **-7.9%** |
| `...-012_delta10.0052` | **-6.1%** |
| `...-008_delta10.0042` | -2.5% |
| `...-017_delta10.0022` | +1.9% |
| `...-021_delta10.0022` | +1.1% |
| `...-027_delta10.0052` | -0.6% |

§14.4 named the segment interface as the weak point of a split and listed four
ways to manage it. The jump is **reported, not blended**: two baselines with the
settings asked for is the thing being judged, and smoothing the seam would
change it into a different proposal.

**It survives into the subtracted signal.** The seam falls between the samples
at 1955.5 and 1953.6 cm-1, and the subtracted trace steps across that one
sample gap by **+7.8%** of range on `...-007` and **+4.8%** on `...-012`,
against a median sample-to-sample change of 1.3% / 0.9% over 1946-1966. So it is
a ~6x local discontinuity, not a cosmetic kink — though it sits at 1955, about
25 cm-1 clear of the 1980 band, so what it corrupts is the region between the
bands rather than either band's own integral.

**What did *not* break.** Worth recording, because it was the expected failure
mode and it is not what happened:

- **The flat 2235-2250 check passes.** Mean `|subtracted|` there: current
  1.5e-5 - 2.6e-4, anchored 2.5e-5 - 1.9e-4, split 2.5e-5 - 1.6e-4. The split
  is within a factor of ~1.6 of the anchored baseline on every file and better
  than it on three. Truncating at 1955 does not break the high end the way
  dropping the 2240 anchor does (§14.7) — the lever-arm failure and the
  shape-change failure are separate.
- **No degenerate segments.** The lower segment is ~106 samples against the
  ROI's ~259, so `half_window: 10` and friends are ~2.4× larger relative to the
  array than the values they were tuned at, and `std_distribution` finding no
  background points there was the obvious risk. It did not fire on any judged
  file. The lower baseline is still *not* the current baseline over 1750-1955 —
  same recipe, shorter array — so it should not be reported as unchanged.

**Untried, and the obvious next form: do not truncate the upper segment at
all.** Every failure above traces to the upper segment being computed on a
shortened array. The alternative keeps the full-ROI `create_baseline` above the
cut — identical to §14.7's anchored baseline by construction, so the 2250-1955
region provably does not move — and adds a second baseline only *below* 1955.
The cut then changes exactly the region it was meant to change, no anchor ever
reads a truncation edge, and the seam is the only thing left to judge.

This is **not what `split_cm1` currently does** and would be a second branch in
`compute()`, not a parameter change. It is recorded here rather than built
because the case for it came out of reading the measurements above, and
§14.7's anchored baseline remains the recommendation until something beats it.

> **Built, as `lower_split_cm1` — see §14.9.** It is a second branch in
> `compute()`, as predicted. Every number in §14.9 is measured against the
> `anchored` variant, not against this section's split, and the region above
> the cut is verified equal to it bit for bit.

**Conclusion.** Keep §14.7's single anchored baseline. `split_cm1` stays in
`baseline.py` as a documented knob with its guard wired up, because the
measurement above is only over the judged files and a different split point
(2006, say, or a per-measurement crossing per §14.6 finding 6) is a different
experiment. But as a candidate for the halved bands it is worse than the anchor
alone, and the `.0022` regime remains untouched by either.

Figures: `C:\Figures\nn1120-4_pd_ceo2_000\baseline_experiments\split_1955\`.

### 14.9 Lower-only split — built and measured; the call is open

The variant §14.8 named and did not build: **do not truncate the upper segment
at all.** `create_baseline` runs once on the full 1750–2250 ROI, the anchors
`(2240, 2006, 1955)` are fitted to *that* result, and only below 1955 is a
second baseline substituted. The cut changes exactly the region it was meant to
change and nothing else.

Implemented per §2 as `BaselineVariant.lower_split_cm1` and a branch in
`compute()` — a separate field from `split_cm1`, not a mode of it, and the two
are mutually exclusive. `LOWER_SPLIT_POINT_CM1 = 1955.0`. Keeping `split_cm1`
intact keeps §14.8 reproducible; the two cut at the same wavenumber and mean
different things, so `split_form` (`"truncate"` / `"lower_only"`) labels every
trace, legend and CSV row.

```python
compare_baselines(
    [
        ("current", {}),
        ("anchored", {}, DEFAULT_WINDOW, ANCHOR_POINTS_CM1),
        ("lower split 1955", {}, DEFAULT_WINDOW, ANCHOR_POINTS_CM1,
         None, LOWER_SPLIT_POINT_CM1),
    ],
    folder_name="nn1120-4_pd_ceo2_000",
)
```

The `anchored` variant is **not optional** here, for the reason §14.8 gives and
one more: it is the twin the zero-diff check is measured against. Drop it and
`upper_max_abs_diff` silently reports `nan`.

**Order of operations is the whole design.** Anchor *before* splicing. Fitting
the least-squares line to an already-spliced curve would mix two baselines into
one correction, which is precisely the failure §14.8 finding 10 traced.

**Coverage: n=8.** `...-007_delta10.0042` — locked by another process
throughout the §14.7.1 run, and the file §14.8's edge analysis is built on — was
readable for this one. Every table below is all eight judged files.

**Finding 13. The region above the cut does not move — verified, not argued.**
`upper_max_abs_diff`, the largest `|lower-split − anchored|` at and above 1955:
**0.0e+00 on all eight files.** Not "small": exactly zero, checked with no
tolerance, because a tolerance would hide the one bug the check exists to catch
(a truncated array reaching `create_baseline`). Two things follow for free —
`height_2040` and `height_1980` are *identical* to `anchored` on every file, so
all of §14.7 finding 9's band recovery is kept intact; and the flat 2235–2250
check is inherited unchanged rather than re-measured.

The corollary matters when reading the comparison table: **the band-height
columns cannot score this variant.** Both reported bands sit above the cut, so
they are guaranteed to match `anchored` and say nothing about whether the cut
helped. `lower_moved_pct` was added to carry the result instead.

**Finding 14. What the cut does is undo the anchored baseline's extrapolation.**
`argmax |anchored − current|` is at **1751 cm⁻¹ on every one of the eight
files** — the bottom edge of the ROI, 205 cm⁻¹ below the lowest anchor. The
affine correction is fitted to three points all at ≥1955 and then extrapolated
across a quarter of the ROI where nothing constrains it, and that extrapolation
is its single largest excursion. As % of signal range:

| File | index | \|anc−cur\| at 1955 | at 1751 | max \|lower-split − cur\| below cut |
|---|---|---|---|---|
| `...-007` | .0042 | 6.74 | **10.96** | 3.94 |
| `...-008` | .0042 | 4.78 | **7.67** | 5.15 |
| `...-012` | .0052 | 10.30 | **16.95** | 4.78 |
| `...-027` | .0052 | 4.39 | **6.93** | 5.24 |
| `...-017` | .0022 | 1.33 | **2.89** | 0.71 |
| `...-021` | .0022 | 1.12 | **3.21** | 0.31 |

The correction is ~1.5–2.9× larger at the bottom edge than at the lowest anchor
it was fitted to. Replacing that region with its own `create_baseline` cuts the
deviation from the current baseline to roughly a third on four of the six.

**This is the same lever-arm failure as §14.7's 2240 pin, on the other end.**
§14.7 fixed the high end by pinning it; §14.7.1 tried to fix the low end the
same way, with a fourth anchor at 1854, and it cost band recovery because one
straight line cannot satisfy four points across 400 cm⁻¹ of curved residuals.
This form fixes it without a fourth anchor — by not extrapolating at all.
§14.7.1's closing note asked for "a non-affine correction or per-anchor
weights"; a second baseline below the cut is a third answer it did not list.

**Finding 15. The seam is smaller than §14.8's, but §14.7 has no seam at all.**
The comparison that matters for "should this replace §14.7" is against §14.7,
and there the seam is a pure cost: the anchored baseline is one continuous
curve, this one is not. §14.8 is the weaker comparison and is given second.

`seam_pct_of_range`, lower-only against the truncating split (§14.8's numbers
reproduced exactly in this run — −7.86 against its −7.9, and so on — so the two
columns are comparable):

| File | index | §14.8 truncate | §14.9 lower-only | seam / median local step |
|---|---|---|---|---|
| `...-007` | .0042 | −7.86 | **−2.87** | 2.2× |
| `...-012` | .0052 | −6.05 | **−5.64** | 5.3× |
| `...-008` | .0042 | −2.53 | **−1.77** | 1.2× |
| `...-021` | .0022 | +1.10 | **+0.85** | 9.8× |
| `...-027` | .0052 | −0.61 | **−0.53** | 0.4× |
| `...-017` | .0022 | +1.86 | +2.02 | 10.7× |

**It is not a halving.** Ratios lower-only / truncate are 0.37, 0.70, 0.77,
0.87, 0.93 and 1.09 — median ~0.82. Only `...-007` halves, and it halves hard:
seam −7.9% → −2.9%, local discontinuity ~6× the median sample-to-sample step →
2.2×. That is the predicted result on exactly the file §14.8 finding 10
diagnosed, because the upper side of its seam is now the undisturbed anchored
value instead of a corrupted truncation edge. `...-017` is marginally worse and
is the only one. The other four improve by 7–30%.

**The seam has not gone away.** It is still a real step on `...-012` (5.3×) and,
in local terms, on the two `.0022` files — whose median step is only 0.15–0.20%
of range, so even a 1–2% seam reads as ~10×. As in §14.8 it is **reported, not
blended**: `seam_jump` / `segment_edges` carry it and `plot_baseline` draws it.
It sits at 1955, ~25 cm⁻¹ clear of the 1980 band, so what it corrupts is the
region between the bands rather than either band's integral.

**The `...-022` regression gate holds.** The guard gates the cut at 1955 on both
its files, and a gated lower-only split returns the plain anchored full-ROI
baseline — which is steps 1–2 alone, so the fallback *is* the §14.7 path rather
than a re-derivation of it. Both files come out identical to `anchored`:
`moved_pct_of_range` 34.41 / 13.93 inherited unchanged, `lower_moved_pct` 0.0,
band heights equal.

**What is still not settled.**

- **The `.0022` / pre-crossing regime is still untouched.** Third section
  running. Its band heights are inherited from `anchored`, which was already a
  no-op there, and its `lower_moved_pct` is 0.3–0.7% — the smallest of any
  group. Nothing in §14.7, §14.8 or §14.9 reaches it.
- **Nothing here measures the region below 1955 against ground truth.** Findings
  14 and 15 say the baseline moved and that the seam shrank. Neither says the
  new lower baseline is *right* — §14.3 finding 4 still applies, and the low
  bands are negative-going so `band_height` cannot score them. The two extra
  low-wavenumber peaks of §4 are the obvious instrument for this and are still
  dormant (`extra_peaks_base` is `[]`). **Judge the figures.**
- 2006 still has no measurement behind it (§14.7).
- ~~The lower segment takes the unmodified `voigt_fit.baseline` settings and no
  anchors, matching `split_cm1`'s precedent. Giving it its own high-end pin at
  1955 is untried and is the §14.7.1 "what would make a low-end anchor work"
  thread.~~ **Built and measured — §14.10.** It still takes the unmodified
  settings; it now takes three anchors of its own, including that 1955 pin.
- Everything here is still offline. No `voigt_fit.baseline` change.

**Conclusion — a trade, and the call has not been made.** Above the cut this is
§14.7 exactly, verified, so it cannot lose any of that section's band recovery.
Below the cut it removes an unconstrained 205 cm⁻¹ extrapolation that was the
anchored baseline's single largest excursion. Against that it introduces a
discontinuity at 1955 where §14.7 had none — 0% → up to 5.6% of range, and up to
10.7× the local sample step. **That is a trade, not an improvement**, and which
side wins is the kind of judgement §14.3 finding 4 says the measurements here
cannot make. §14.7.1 and §14.8 both record who decided and on what; this section
cannot, yet.

What the figures show, as read by the author of this section and **not** as a
user judgement:

- `...-007` (.0042) and `...-012` (.0052): a clear gain below the cut. The
  anchored baseline leaves the subtracted trace floating +0.0005 to +0.0009
  above zero across 1900–1750; the lower-only split brings it back to ~0 and
  rides the data. `...-012`'s seam is visible as a kink at 1955 but is small
  beside the 1930 band it sits next to.
- `...-017` (.0022): the lower-only split is visually indistinguishable from the
  *current* baseline over the whole ROI. On the pre-crossing files the cut
  reverts the only thing anchoring did there, so the variant is close to a
  no-op — consistent with its `lower_moved_pct` of 0.71%, the smallest measured.
- The 10.7× local-step ratio on `...-017` reads alarming and is not: its median
  sample-to-sample step is only 0.20% of range, so a visually negligible seam
  scores a large ratio. Read the local ratio next to the raw seam %, never
  alone.

Figures: `C:\Figures\nn1120-4_pd_ceo2_000\baseline_experiments\lower_split_1955\`.
### 14.10 Anchors on the lower half — built and measured; the call is open

The thread §14.9 left open and §14.7.1 asked for. §14.9's lower segment ran with
the unmodified `voigt_fit.baseline` settings and **no anchors**, matching
`split_cm1`'s precedent; it now gets three of its own — **both endpoints of its
own segment plus 1800 cm⁻¹**, `LOWER_ANCHOR_POINTS_CM1 = (1955, 1800, 1750)`.

Implemented per §2 as `BaselineVariant.lower_anchors` plus a step in
`_compute_lower_split`, not a parallel module. It **requires** `lower_split_cm1`
and raises without it: there is no lower segment to anchor without a cut, and a
silently ignored anchor list is the same failure as a misspelled settings key.

```python
compare_baselines(
    [
        ("current", {}),
        ("anchored", {}, DEFAULT_WINDOW, ANCHOR_POINTS_CM1),
        ("lower split 1955", {}, DEFAULT_WINDOW, ANCHOR_POINTS_CM1,
         None, LOWER_SPLIT_POINT_CM1),
        ("lower split 1955 + lower anchors", {}, DEFAULT_WINDOW, ANCHOR_POINTS_CM1,
         None, LOWER_SPLIT_POINT_CM1, LOWER_ANCHOR_POINTS_CM1),
    ],
    folder_name="nn1120-4_pd_ceo2_000",
)
```

**Both middle variants are load-bearing.** `anchored` for §14.8's reason and as
the zero-diff twin; the *unanchored* `lower split 1955` one level deeper —
without it a change cannot be attributed to the lower anchors rather than to the
cut.

**This is structurally not §14.7.1.** That subsection removed a *fourth* anchor
at 1854 because one least-squares line cannot satisfy four points across
400 cm⁻¹ of curved residuals, and the brake it applied cost 2040 band recovery.
Here the lower segment carries its own line, fitted to its own three points, over
its own 205 cm⁻¹; the full-ROI correction above the cut is untouched and provably
so. It is the third answer to §14.7.1's closing "a non-affine correction or
per-anchor weights" — a separate line on a separate segment. Order of operations
is still the whole design: the lower correction is fitted to the lower segment's
own baseline **before** the splice, never to the spliced curve.

**Coverage: n=8**, all judged files, `...-007_delta10.0042` included.

#### Finding 16. The guard passes 1800 on every file, and that is the thing to know about this anchor

1800 is ~5 cm⁻¹ from the 1795 band (at the default ¹³CO isotope the low peaks sit
at 1795/1775, §4) — well inside `ANCHOR_GUARD_CM1 = 25`. It is **never gated**.
Prominence of the most prominent extremum within ±25 cm⁻¹, as a fraction of
full-ROI range, against the 0.5 threshold:

| File | index | prominence @1800 | where | 1795 band, peak-to-peak | as % of ROI range |
|---|---|---|---|---|---|
| `...-007` | .0042 | 0.019 | 1793 | 2.0e-4 | 2.6 |
| `...-008` | .0042 | 0.031 | 1793 | 1.9e-4 | 3.6 |
| `...-012` | .0052 | 0.029 | 1799 | 1.5e-4 | 2.9 |
| `...-017` | .0022 | 0.002 | 1822 | 3.4e-4 | 3.7 |
| `...-021` | .0022 | 0.089 | 1820 | 3.9e-4 | 4.0 |
| `...-027` | .0052 | 0.015 | 1793 | 1.3e-4 | 2.1 |
| `...-022` † | .0022 | 0.032 | 1793 | 2.7e-4 | 3.2 |
| `...-022` † | .0042 | 0.088 | 1815 | 2.8e-4 | 9.3 |

† **The anchor never runs on these two.** Their cut at 1955 is gated, so no lower
segment is built and `lower_anchors` go with it (finding 17's fallback). The rows
are listed because they are part of the eight and the prominence is measurable on
any file, not because 1800 was exercised there. Six files, not eight, carry every
other number in this section.

On five of the eight the extremum the guard finds near 1800 **is** the 1795 band
— and it scores 0.015–0.032, twenty times under the threshold. **Passing is not
reassurance.** It means the anchor reads a region where a small band lives, and
the guard as calibrated cannot object: `ANCHOR_PROMINENCE_FRAC` is a fraction of
the *whole ROI* range, which §14.7 finding 8 required (a locally-scaled
prominence gated all six files the anchor exists to help), and against a range
set by the 2040/1980 bands the low bands are 2–9% and invisible. The guard is
doing what it was calibrated to do; it simply does not protect a low-wavenumber
anchor.

So 1800's defence is not the guard — it is that the band it sits beside is small
in absolute terms, and that the residual measured there (finding 20) is what the
correction actually acts on. **The nearest clearly clear alternative is ≥1820**,
and nothing here has measured it. 1800 was the user's choice and is what was
built; it is not a wavenumber with a measurement behind it, the same caveat 2006
carries (§14.7).

#### Finding 17. Containment holds with the lower anchors on — verified

`upper_max_abs_diff` is **0.0e+00 on all eight files**, exactly, unchanged from
§14.9 finding 13. The lower correction is fitted to the lower segment's array, so
it cannot reach above the cut — and the check was left able to catch it if it did:
`lower_anchors` is deliberately **not** part of `_recipe_key`, so the `anchored`
variant stays the twin. Two things follow without re-measuring: `height_2040` /
`height_1980` are identical to `anchored` on every file, so all of §14.7 finding
9's band recovery is intact; and the flat 2235–2250 check is inherited unchanged
(5.9e-5 to 1.9e-4, identical to the `anchored` column).

**The corollary from §14.9 applies with more force here.** Both reported bands sit
above the cut. They cannot score this variant. `seam_pct_of_range` can.

#### Finding 18. The seam halves on the post-crossing files and grows on the pre-crossing ones

This is the trade §14.9 left open, moved. 1955 is in *both* anchor sets, so both
sides of the cut are pulled toward the same data value there.
`seam_pct_of_range`:

| File | index | §14.8 truncate | §14.9 lower-only | §14.10 + lower anchors | ratio to §14.9 |
|---|---|---|---|---|---|
| `...-007` | .0042 | −7.86 | −2.87 | **−1.58** | 0.55 |
| `...-008` | .0042 | −2.53 | −1.77 | **−0.42** | 0.24 |
| `...-012` | .0052 | −6.05 | −5.64 | **−2.52** | 0.45 |
| `...-027` | .0052 | −0.61 | −0.53 | **−0.36** | 0.68 |
| `...-017` | .0022 | +1.86 | +2.02 | **+2.86** | 1.41 |
| `...-021` | .0022 | +0.85 | +0.85 | **+2.61** | 3.09 |

The four post-crossing files improve by 32–76%; the two pre-crossing ones get
worse, `...-021` by 3×. Same split by regime as findings 9, 10 and 15 — a fourth
section running.

In local terms — the seam step in the *subtracted* trace over the median
sample-to-sample step across 1946–1966, §14.9's method, which this run reproduces
exactly on the lower-only column (2.2 / 1.2 / 5.3 / 10.7 / 9.8 / 0.4):

| File | index | §14.9 | §14.10 |
|---|---|---|---|
| `...-007` | .0042 | 2.2× | **1.2×** |
| `...-008` | .0042 | 1.2× | **0.1×** |
| `...-012` | .0052 | 5.3× | **1.6×** |
| `...-027` | .0052 | 0.4× | **0.2×** |
| `...-017` | .0022 | 10.7× | 14.9× |
| `...-021` | .0022 | 9.8× | 21.9× |

On `...-008` the seam drops to a tenth of the local noise step — below the point
where it is visible at all. Read the `.0022` ratios next to their raw seam (+2.9%,
+2.6% of range) and §14.9's warning: their median local step is only 0.15–0.20% of
range, so a 20× ratio there is a 2.6% seam, not a 20% one.

**Pulled, not pinned** (`ANCHOR_POINTS_CM1`'s most-misread property). With three
anchors each correction is least-squares, so neither side is forced to the data
value at 1955 and the seam cannot reach zero by construction. Pinning it exactly
would mean anchoring the lower baseline to the *upper baseline's value* at the cut
rather than to the data — a continuity constraint, not an anchor. Untried, and a
different proposal: it would guarantee a seam of 0 and give up the property that
both segments are fitted to the data alone.

#### Finding 19. Below the cut, this is the first thing that moves the `.0022` regime

**Mean signed `raw − baseline` over 1750–1900, raw units** — the quantity §14.9
read off the figures ("the anchored baseline leaves the subtracted trace floating
+0.0005 to +0.0009 above zero across 1900–1750"). A signed offset is a baseline
error; zero is the target:

| File | index | current | anchored | lower-only | **+ lower anchors** |
|---|---|---|---|---|---|
| `...-007` | .0042 | −1.04e-4 | +6.05e-4 | **−1.6e-5** | −4.0e-5 |
| `...-008` | .0042 | −2.24e-4 | +2.54e-4 | **−3.3e-5** | −1.43e-4 |
| `...-012` | .0052 | −3.4e-6 | +7.23e-4 | +2.3e-6 | **−3.3e-6** |
| `...-027` | .0052 | −8.19e-5 | +3.08e-4 | **−7.7e-5** | −1.64e-4 |
| `...-017` | .0022 | −3.33e-4 | −5.45e-4 | −3.51e-4 | **−1.46e-4** |
| `...-021` | .0022 | −3.98e-4 | −6.41e-4 | −4.13e-4 | **−1.99e-4** |

Two results, in opposite directions:

- **The `.0022` files' offset is halved** — −3.3e-4 → −1.5e-4 and −4.0e-4 →
  −2.0e-4 against the unanchored split, and better than 2× against the current
  baseline. Three sections running have been a no-op there (findings 9, 10, 15);
  this is the first measurement in §14 that moves the pre-crossing regime at all.
  It moves it only **below 1955** — above the cut those files are still
  `anchored`, which finding 9 measured as unchanged from current. So this is not
  "the `.0022` regime is fixed"; it is "a quarter of the ROI on those files
  stopped being ignored."
- **The four post-crossing files give some ground back.** The unanchored lower
  split had brought them to −1.6e-5 to −7.7e-5; the anchors move them to −4.0e-5
  to −1.6e-4, so two of the four end up further from zero than the *current*
  baseline as well. All four remain far inside `anchored`'s +2.5e-4 to +7.2e-4,
  which is the excursion §14.9 was built to remove.

Mean `|raw − baseline|` over the same region tells the same story and is kept only
as a secondary reading, because it cannot distinguish a baseline offset from band
content: current 1.62–4.53, `anchored` 4.24–14.47, lower-only 1.70–4.64, and with
lower anchors 2.10–3.34, all as % of signal range. A baseline that "tracks the
data more closely" below 1955 is also a baseline that eats more of the bands
there, and the bands below the cut are negative-going. **That is the trap §14.3
finding 4 describes**, which is why the signed table leads and this one does not.

Neither table is a quality score. They say where the subtracted trace sits, not
that where it sits is right. The instrument that could settle it is §4's two
low-wavenumber peaks — still dormant, `extra_peaks_base` is `[]`. **Judge the
figures.**

#### Finding 20. The `.0022` files' lower residuals are curved, and one line cannot hold them

Miss at each surviving lower anchor, as % of signal range (`data(w) − spliced
baseline(w)`, so the sign says which way the line ended up off):

| File | index | @1955 | @1800 | @1750 |
|---|---|---|---|---|
| `...-007` | .0042 | +1.35 | −0.76 | +0.58 |
| `...-008` | .0042 | +0.62 | −1.36 | +1.05 |
| `...-012` | .0052 | +2.07 | −0.93 | +0.73 |
| `...-027` | .0052 | +0.62 | −1.50 | +1.15 |
| `...-017` | .0022 | −0.78 | **−5.50** | **+4.14** |
| `...-021` | .0022 | −0.49 | **−5.99** | **+4.53** |

The post-crossing files' residuals are nearly collinear and all three anchors land
within 2.1%. On the two `.0022` files the pattern is the signature of curvature —
ends high, middle low, by 4–6% of range — and it is exactly §14.7.1's mechanism at
segment scale: one straight line, three points, curved residuals. That is also
why their seam grew in finding 18 while their 1750–1900 tracking improved in
finding 19: the line is tilted to split the difference, which helps the bulk of
the segment and costs the end that touches the cut.

A fourth lower anchor would not fix this, for §14.7.1's reason. What would is a
non-affine lower correction (quadratic, or per-anchor weights) — the two options
§14.7.1 named and neither section has built.

Note on the anchor at the cut: 1955 sits ~1.4 cm⁻¹ above the lower segment's top
sample (1953.6), inside `apply_anchors`' one-grid-step coverage tolerance, so it
is kept rather than reported outside the segment. The residual there is therefore
read at the data estimate for 1955 against the baseline interpolated at the
segment edge. Sub-sample, but it is the first thing to check if the seam ever
looks stubborn.

At 1750 the data estimate is one-sided — there is no data below the ROI floor — so
that residual is the noisiest of the three, and for the same reason
`gating_extremum` cannot see an extremum peaking at the array's own edge.

#### What is still not settled

- **1800 has no measurement behind it.** Finding 16 says the guard cannot object
  to it; it does not say 1800 is the right wavenumber. ≥1820 is the nearest point
  clear of the 1795 band and is unmeasured.
- **The `.0022` regime is improved below the cut, not fixed.** Above 1955 it is
  still `anchored`, still a no-op (finding 9). Four sections in.
- **Nothing here scores the region below 1955 against ground truth.** Findings 18,
  19 and 20 say the seam shrank on four files and grew on two, that tracking
  improved on two and slightly worsened on four, and that two files' residuals are
  curved. None of that says the new lower baseline is *right*. **Judge the
  figures.**
- The lower segment still takes the unmodified `voigt_fit.baseline` settings; only
  its correction changed.
- A continuity constraint at the cut (anchor the lower baseline to the upper
  baseline's value rather than to the data) would zero the seam and is untried —
  finding 18.
- Everything here is still offline. No `voigt_fit.baseline` change.

**Conclusion — a trade again, and the call is the user's.** Containment is
verified: above the cut this is §14.7 exactly, so no band recovery is at risk
(finding 17). Below the cut it cuts the seam by a third to three quarters on the
four post-crossing files — removing §14.9's only cost over §14.7 on the files
that section was built for — and it halves the `.0022` files' subtracted offset
below 1955, the first movement in that regime anywhere in §14 (finding 19).
Against that it grows the seam on those same `.0022` files (2.0 → 2.9%,
0.9 → 2.6% of range), moves the post-crossing four's offset back out by 2–5x
(from −1.6e-5..−7.7e-5 to −4.0e-5..−1.6e-4, though still far inside
`anchored`'s), and does all of it through an anchor at 1800
that the guard passes without being able to see the band beside it. **Which side
wins is the judgement §14.3 finding 4 says these measurements cannot make.**

What the figures show, as read by the author of this section and **not** as a
user judgement:

- `...-007` (.0042): below the cut the lower-anchored curve sits between the
  unanchored split and the data, and the kink at 1955 that §14.9 left visible is
  noticeably flatter — the −2.9% → −1.6% of finding 18 is the visible change.
  The anchored baseline's float above zero across 1900–1750 stays corrected.
- `...-021` (.0022): the change is real and it is below 1955 only. The subtracted
  trace over 1900–1750 sits at roughly −0.0010 under both `current` and the
  unanchored split and is lifted to roughly −0.0005 here — the first visible
  movement on a pre-crossing file anywhere in §14. Closer to zero; whether that
  region *should* sit at zero is the part no measurement here settles. Its larger seam is a small
  step at 1955 against a locally quiet trace, which is the reading finding 18's
  ratio column warns about.
- The green squares mark the lower anchors and the black circles the full-ROI
  ones; at 1955 they coincide, which is the point — two lines pulled toward the
  same data value from opposite sides.

Figures: `C:\Figures\nn1120-4_pd_ceo2_000\baseline_experiments\lower_anchored_1955\`.
