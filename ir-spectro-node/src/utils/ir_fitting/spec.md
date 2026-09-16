# src/utils/ir_fitting — offline IR peak-fitting for EDA and reprocessing

**Status: implemented.** Verified against `nn1120-3_pd_ceo2_004` and
`nn1120-2_pd_ceo2_000`; see section 13 for what the first runs showed.

Sibling in purpose to `src/utils/kinetics`: an offline, programmatic wrapper used
for exploratory data analysis and reprocessing, never invoked by the live server
path and never writing into source data. It differs from `src/utils/kinetics` in
architecture — see §3.

---

## 1. Problem

`config/analysis.yaml`'s `voigt_fit.peak_list_base` currently declares 18 peaks.
Two additional low-wavenumber bands need to be fitted and studied offline before
they are promoted into the live list.

These are not new peaks. They were fitted historically and then dropped:

| Dataset | Fitted `Peak_Name` values present |
|---|---|
| `nn1120-2_pd_ceo2_000` (2024-11) | `Peak_1775`, `Peak_1795`, … **no** `Peak_2093`, `Peak_2176`, `Peak_2196` |
| `nn1120-3_pd_ceo2_004` (2026-03) | `Peak_2093`, `Peak_2176`, `Peak_2196`, … **no** `Peak_1775`, `Peak_1795` |
| `nn1120-4_pd_ceo2_000` (2026-06) | same as above |

Their `param_rules` were never removed — `config/analysis.yaml` lines 408–441 still
carry entries for `range_cm1: [1790, 1800]` and `[1770, 1780]`, tuned for these
bands specifically (`sigma.max: 26` vs. 6.37 elsewhere, no `gamma` max, center
offsets ±5 vs. ±1). No peak in the current `peak_list_base` maps into either
window, so those two rules are inert today.

Established facts to preserve:

- 12CO base values are **1845** and **1825**; at the default `13CO` isotope
  (`isotope_shift_cm1: -50`) they become **1795** and **1775**.
- `Peak_Name` strings are already established in historic CSVs as exactly
  `Peak_1795` and `Peak_1775` — integer-formatted, no decimals.
- Fitted `Amplitude` for these bands is **negative** (negative-going in log
  reflectance). Nothing may assume positive amplitude.

## 2. Core decision: append, don't refit

The two peaks sit ~180 cm⁻¹ below the lowest currently-fitted peak (`Peak_1975`
at 13CO). There is no meaningful Voigt overlap with the existing 18-peak set, so
the existing fit does not need to be re-solved to add them.

Default behavior is therefore: **read the existing
`*_CarbonylPeakFitParams.csv`, fit only the `ir_fitting` peaks, append those rows.**

A consequence worth using: the saved `*_CarbonylFitResidual.csv` currently
contains these two peaks *unmodeled*, because the original fit declared no peaks
below 1975. The residual in the 1750–1850 region is a direct sanity check on the
new fits.

**This premise is under strain in practice — see §13.** With 1845 / 1825 seeded,
`Peak_1795`'s sigma pins at its upper bound in 25/72 files, putting its tails
near 1900 cm⁻¹. The isolation argument still looks right, and the pinning is more
likely a bounds problem than a genuine overlap, but the premise should not be
read as validated until the `param_rules` are tuned and the bounds stop binding.

## 3. Architecture — wrap, don't duplicate

`src/utils/kinetics` is a full parallel re-implementation of
`src/analysis/kinetics_fitting.py`. `CLAUDE.md` calls that out as a standing
hazard: "A change to model or classification behavior usually has to land in
both, or the two paths silently disagree."

`ir_fitting` does **not** repeat that. It calls
`src/analysis/spectral_fitting.py` directly — `create_baseline`, `add_params`,
`select_param_rule`, `get_shifted_rules`, `voigt_model`, `peak_fit` — and adds
only orchestration. There is one Voigt implementation and one set of param rules
in the repo.

Layout:

```
src/utils/ir_fitting/
  __init__.py       re-exports fit_file / fit_folder
  spec.md           this file
  config.py         reads the ir_fitting: yaml block, applies isotope shift
  api.py            fit_file / fit_folder — the entry points
  runner.py         per-file orchestration; calls analysis.spectral_fitting
  result_types.py   in-memory bundle consumed by the plots
  writer.py         merge + write into _test/
```

No CLI. Entry points are importable; batch runs follow the repo convention of an
editable `file_directory` / `name` constant in an `if __name__ == "__main__":`
block.

## 4. Configuration — new `ir_fitting:` block

A new top-level key in `config/analysis.yaml`, kept structurally parallel to
`voigt_fit` so that promoting these peaks to live is a copy of values between
two lists, not a rewrite:

```yaml
ir_fitting:
  # 12CO base wavenumbers, shifted by voigt_fit.isotope_shift_cm1 at read time.
  # Integers only — Peak_Name is formatted as Peak_<value> and must match the
  # historic strings exactly (Peak_1795, not Peak_1795.0).
  extra_peaks_base: []            # e.g. [1845, 1825]

  # Group membership, mirroring voigt_fit's *_peaks_base keys.
  extra_cluster_peaks_base: []    # e.g. [1845, 1825]
  extra_monomer_peaks_base: []
  extra_unknown_peaks_base: []
```

Rules:

- `voigt_fit.peak_list_base` and `voigt_fit.cluster_peaks_base` are **not
  modified**. The live server keeps its 18-peak list; existing
  `*_CarbonylPeakFitParams.csv` / `*_CarbonylPeakArea.csv` row sets are unchanged.
- `ir_fitting` peaks are isotope-shifted using the same `voigt_fit.isotope_shift_cm1`
  and `isotope_default`, so a single isotope switch moves both lists together.
- An empty `extra_peaks_base` is a valid no-op, not an error.

### Voigt bounds stay in `voigt_fit.param_rules`

Per your decision: the new peaks' bounds are hand-edited directly in
`voigt_fit.param_rules`. The staged `[1790, 1800]` / `[1770, 1780]` entries
already serve 1795 / 1775 and are inert for the live path, so editing them costs
nothing in production.

One guard is required. `select_param_rule` falls through to the `default: true`
rule when no `range_cm1` matches, and that default sets `sigma.max: 6.37` and
`gamma.max: 2.8` — far too narrow for these broad bands, and it fails silently.
So: **log a warning whenever an `ir_fitting` peak resolves to the default rule**,
naming the peak and the bounds it got.

The catch-all rule itself is **not changed here** — see §12. The warning is the
interim step that makes it visible when it fires, which is what you want before
deciding how to replace it.

### Fit window

The existing **1750–2250 cm⁻¹** ROI, unchanged. `io.py::import_data` already
clips to it and both new peaks fall inside. No new ROI key.

## 5. Per-file procedure

Input is a subIFG file path, as elsewhere in the repo — e.g.
`C:\Data\OpusConvert_subIFG_lgRfl\<folder>\<name>.<index>`.

1. Resolve paths. Reuse `DataAnalysisRunner._resolve_paths` semantics:
   `folder_name`, `file_name`, `file_index`, `delta_file`.
2. Honor `manually_skip_files` (`delta1` index > 2, and all of
   `delta2`/`delta3`/`delta4`) exactly as the live path does, so offline and live
   cover the same files.
3. Load the existing `*_CarbonylPeakFitParams.csv` for the dataset.
4. Load the subIFG array over 1750–2250.
5. Obtain a baseline (§6) and subtract it.
6. Build `lmfit.Parameters` for the `ir_fitting` peaks only, via `add_params` — so
   the peaks pick up `voigt_fit.param_rules` unchanged. All `ir_fitting` peaks go
   into **one** `Parameters` set and are fitted jointly: 1795 and 1775 are 20 cm⁻¹
   apart with `sigma.max: 26`, so they overlap each other substantially and
   cannot be solved independently.
7. Fit with `peak_fit`, evaluate each peak's `voigt_model`, integrate with
   `-trapezoid(y_fit, wavenumbers)` — sign convention identical to
   `peak_analysis`.
8. Build rows, merge, write to `_test/` (§7, §8).

### Guard: parameters pinned at their bounds

A fitted parameter sitting exactly on one of its bounds means the optimizer
wanted to go further and the rule stopped it, so the value reflects the bound
rather than the data. `_warn_on_pinned_params` checks `center`, `amplitude`,
`sigma` and `gamma` against both bounds. Two cases carry extra meaning:

- **`sigma` at its max.** `sigma.max: 26` is a Gaussian FWHM of ~61 cm⁻¹, tails
  reaching ~1900 cm⁻¹ — still clear of `Peak_1975`, but only just. This is the
  condition under which the isolation assumption of §2 weakens and
  `append_only=True` stops being obviously safe.
- **`center` at either bound.** The band wants to sit outside the window its
  rule allows, i.e. the seeded wavenumber is probably wrong.

Individual messages are logged at DEBUG and collected on the result; `api.py`
aggregates them into one WARNING per distinct issue per run, because a
measurement holds dozens of files and a per-file warning repeats endlessly.

### FSD peak snapping — not performed, matching current live behavior

The live path calls `find_fsd_peaks` + `resolve_peak_lists` intending to snap
each nominal peak to a detected FSD peak within 5 cm⁻¹. That snapping does not
happen: `find_fsd_peaks` returns `peaks` — the **array indices** from
`scipy.signal.find_peaks` (`spectral_fitting.py:216`, which computes
`peak_wavenumbers` and then discards it) — while `resolve_peak_lists` compares
those against wavenumbers with `atol=5.0`. Indices run 0–258, wavenumbers
1750–2250, so nothing ever matches.

Confirmed in the data: `Peak_Value` differs from nominal only in
`nn1120-2_pd_ceo2_000` and `nn1120-3_pd_ceo2_000`, and is exactly nominal in
every dataset from `nn1120-3_pd_ceo2_001` onward.

`ir_fitting` therefore sets `Peak_Value` to the nominal shifted wavenumber and
does not load FSD data at all, which reproduces current live output exactly.
Fixing the live path is **out of scope** here — it would change `Peak_Value` in
new output, and output schemas are a public contract.

### Column derivation for appended rows

| Column | Source |
|---|---|
| `File` | `delta{N}.{index}`, e.g. `delta5.0007` — 4-digit index, matching existing rows |
| `Delta_Group` | `delta{N}` |
| `Peak_Name` | `Peak_<shifted integer>` — `Peak_1795`, `Peak_1775` |
| `Peak_Value` | FSD-snapped center, else the nominal shifted value |
| `Center`, `Amplitude`, `Sigma`, `Gamma`, `Y0` | from the fit |
| `fwhm` | Voigt pseudo-FWHM, same formula as `peak_analysis` |
| `Peak_Area` | `-trapezoid(y_fit, wavenumbers)` |
| `Data_Integral` | **copied** from an existing row for the same `File`. It is a whole-ROI integral, identical across every peak row in a file — recomputing it would be redundant and could drift. |
| `Time_Delta (s)` | **copied** from an existing row for the same `File`. Recomputing needs the subIFG log + exp params chain; copying is exact and cheaper. |
| `PdCO_mol`, `PdCO_mol_stderr` | **Left empty (NaN) on appended rows.** The column itself is preserved and every existing row keeps its historical value — the merge must not drop or blank it. The calibration slope is hardcoded to two folders in `io.py::import_calibration_data` and was derived in the carbonyl region; applying it at 1775-1795 is not justified. |

## 6. Baseline

**Correction to an earlier draft of this spec.** It claimed the saved baseline
may have "partly absorbed" the two new bands, so recomputing would give
different values. That is wrong, and the design does not need to correct for it.

`create_baseline` wraps
`pybaselines.classification.std_distribution(data, x_data, half_window,
interp_half_window, fill_half_window, num_std, smooth_half_window, weights)`.
It receives the intensity array and those settings and **nothing else — there is
no peak list argument**. The baseline has never known which peaks were declared,
so declaring two more cannot change it.

Verified on `20260304_145524_pd_ceo2_004-000_delta5.0007`: two `create_baseline`
runs over the same 1750–2250 ROI with the same settings return bit-identical
arrays. Same input file, same ROI, same settings ⇒ same baseline.

So the switch is not "saved vs. different". Its two real uses are:

| `baseline` | Purpose |
|---|---|
| `"saved"` (default) | Read the `delta{N}.{index}` column from the dataset's `*_CarbonylFitBaseline.csv`. Cheapest, and guarantees the appended peak areas sit on exactly the same baseline as the existing 18. |
| `"recompute"` | Needed when the saved CSV is missing or lacks a column for that file. Also the hook for EDA on baseline *settings* — the only thing that actually makes a recomputed baseline differ. |

A yaml settings override (`ir_fitting.baseline:`) is **deferred** — added only if
EDA shows the baseline is worth tuning. Until then `"recompute"` inherits
`voigt_fit.baseline` and therefore reproduces `"saved"` exactly, which is a
useful self-check rather than redundancy.

One real caveat, recorded so nobody trips on it later: `half_window` and friends
are counts of **samples**, not cm⁻¹, so they only stay meaningful while the
window is fixed. Narrowing the ROI to 1750–1900 shifts the baseline by up to
2.8e-5 in the overlap region against a signal range of 4.7e-3 (~0.6%). We are
**not** narrowing the window — the fit window stays 1750–2250 (§4) — so this
does not apply to the design as specified.

## 7. Collision handling — the case the design must not get wrong

`nn1120-2_pd_ceo2_000` **already has** `Peak_1795` and `Peak_1775` rows. Blindly
appending would produce duplicate rows for the same `File` / `Peak_Name`, which
then flow into `compute_cumulative_peak_area_df` as double-counted fit history.

Behavior when an `ir_fitting` peak already has a row for that `File` / `Delta_Group`,
controlled by `on_existing: {"skip", "overwrite", "error"}`:

| Value | Behavior |
|---|---|
| `"skip"` (default) | Leave the existing row untouched, do not fit, log at INFO with the file and peak name. Run summary reports counts of fitted / skipped. |
| `"overwrite"` | Drop the existing row and replace it with the new fit. For re-running after a param-rule change. |
| `"error"` | Raise. For reprocessing runs that must not silently no-op. |

### Backfilling peaks missing from a historic dataset

The churn runs both ways: `nn1120-2_pd_ceo2_000` also lacks `Peak_2093` /
`Peak_2176` / `Peak_2196`, which the current live `peak_list_base` does contain.

`append_only=True` does **not** backfill these, and cannot do so correctly.
Unlike the two new bands, those three sit *inside* the existing peak cluster
(2093 between 2103 and 2073, and so on), where Voigt profiles overlap
substantially. Adding one changes its neighbours' fitted amplitudes and widths,
so its parameters cannot be solved while the neighbours are held at saved values.

`append_only=False` handles it by construction: it discards the saved parameters
and refits every peak in `voigt_fit.peak_list_base` plus
`ir_fitting.extra_peaks_base` from the subIFG in a single joint fit. So
backfilling is not a missing feature — it is the full-refit path, and the reason
that flag exists beyond "future robustness".

A full refit therefore replaces **every row for every file it touched**, not just
the `(File, Peak_Name)` pairs it reproduces. The peak list has churned between
datasets, so a saved CSV can hold a peak the current list has dropped; keeping
such a row would mix two models' output within one file, and the per-peak curves
would no longer sum to the composite. Files the run did not touch — those
`manually_skip_files` excludes — keep their rows unchanged.

## 8. Outputs — `_test/` only

Never writes into the source folder. Follows
`src/utils/kinetics/utils.py::resolve_output_dir`: output is a subfolder of the
source dataset folder, `_test` by default, and an empty/`"."`/absolute
`output_folder` is rejected because it would collapse back onto the source.

```
C:\Data\peakFit\<dataset>\_test\
  <name>_CarbonylPeakFitParams.csv   existing rows + appended ir_fitting rows
  <name>_CarbonylFitBaseline.csv     baseline actually used, per file column
  <name>_CarbonylFitResidual.csv     residual after the ir_fitting peaks are modeled
```

- Column order and names match the live schema exactly — these are readable by
  the existing plotting and kinetics code without modification.
- `*_CarbonylPeakArea.csv` (cumulative areas, `cluster_sum`, kinetics columns) is
  **out of scope** for this iteration. Grouping the new peaks as cluster peaks
  would change `cluster_sum`, and that belongs in a separate, deliberate step
  once the fits have been inspected.
- The residual is **full-ROI**, not a 150 cm⁻¹ window. Under `append_only=True`
  the existing 18 peaks are reconstructed from their saved
  `Center`/`Amplitude`/`Sigma`/`Gamma`/`Y0` — the same reconstruction
  `plot_spectrum_fit.py::_build_delta_group_fit` already performs — and the new
  peaks are added to that composite before differencing. This keeps the residual
  plot meaningful across the whole spectrum, and outside the new-peak region it
  should reproduce the live path's saved residual, which is a free regression check.
- Residual sign convention is `model - data`, inherited from
  `spectral_fitting.py::objective` (`combined_voigt(...) - y_baseline`). Stated
  here because it is easy to plot with the wrong sign.

## 9. Visualizations — `src/visualizations/`

Two new modules. Existing `plot_spectrum_fit.py` is not extended: it *sums every
file within a delta group* into a single trace and draws individual peak curves
only for monomer peaks, which is a different question from the per-fit inspection
needed here. It is left alone.

### 9.1 `plot_individual_fit.py` — one figure per file

The unit is **one subIFG file** (one delta group, one index), e.g.
`..._004-005_delta5.0007`:

```
fig: <name>_delta5.0007
─────────────────────────────────────
  black   data (baseline-subtracted)
  red     composite fit
  dashed  each peak, one line per peak, labeled by Peak_Name
  blue    residual
```

- Individual curves for **all** peaks present, not just monomer.
- `ir_fitting` peaks visually distinguished from the pre-existing 18.
- Residual drawn offset below the data so it stays readable at its own
  amplitude; a `stacked=True` option gives a shared-x two-panel layout instead.
- x inverted, limits 2250 → 1750, matching repo convention.

### 9.2 `plot_baseline.py` — raw / baseline / subtracted

Same per-file unit:

- raw subIFG over the ROI,
- the baseline drawn on top of it,
- the baseline-subtracted signal,
- when `baseline="recompute"` with an `ir_fitting.baseline` settings override,
  both baselines and both subtracted traces overlaid, so a settings change is
  judged visually rather than by number. With no override the two coincide
  exactly (§6), which is itself the check that nothing drifted.

### Figure paths

New subfolder keys in `config/paths.yaml` alongside `plot_spectrum_fit` etc.:

```yaml
data:
  plot_individual_fit: "plot_individual_fit"
  plot_baseline: "plot_baseline"
```

Resolved via `config.get_path("data.figures", folder_name, ...)`. No hardcoded
figure paths.

## 10. API sketch

```python
from src.utils.ir_fitting import fit_file, fit_folder

# The unit is one MEASUREMENT (a base name), not one subIFG file. fit_file
# iterates every delta group / index sharing that base name, matching the
# granularity of the params CSV, and writes one merged CSV.
fit_file(
    r"C:\Data\OpusConvert_subIFG_lgRfl\nn1120-3_pd_ceo2_004\20260304_145524_pd_ceo2_004-000",
    append_only=True,  # False -> joint refit of every peak (see §7)
    baseline="saved",  # or "recompute"
    on_existing="skip",  # or "overwrite" / "error"
    output_folder="_test",
    save=True,
)
```

Returns an in-memory result bundle (wavenumbers, per-peak curves, composite,
residual, baseline, rows) that the plot modules consume directly, so an EDA
session can fit and plot without a round trip through disk.

## 11. Decisions settled

| Item | Decision |
|---|---|
| Append/refit flag | `append_only: bool = True`. `True` reuses saved fit params and fits only the `ir_fitting` peaks; `False` refits every peak jointly from the subIFG (§7). |
| Naming | `ir_fitting` for both the package (`src/utils/ir_fitting`) and the `config/analysis.yaml` key. `ir_eda` dropped. |
| Peak values | `extra_peaks_base` ships empty; you seed it. §1 records that 1845 / 1825 reproduce the historic `Peak_1795` / `Peak_1775`. |
| `PdCO_mol` | Not populated on appended rows. Existing rows retain their historical values through the merge. |
| Param rules | Hand-edited in `voigt_fit.param_rules`. No `ir_fitting`-local rules. The only code change is a warning when a peak falls through to the `range_cm1: [0, 0]` default rule (§4). |
| Fit unit | `fit_file(base_name)` = one measurement, iterating its subIFG files; `fit_folder(folder)` = every measurement in a dataset. Mirrors `src/utils/kinetics`. |
| First target | `__main__` constants point at `nn1120-3_pd_ceo2_004`. |
| Baseline | Default `"saved"`. `"recompute"` exists for a missing saved column and for settings-level EDA, not because the two differ by default (§6). |

## 12. Out of scope

- Promoting the peaks into `voigt_fit.peak_list_base` / `cluster_peaks_base`.
- Regenerating `*_CarbonylPeakArea.csv`, `cluster_sum`, or any kinetics output.
- Backfilling peaks missing from historic datasets (§7).
- Any change to `src/analysis/`, the ZMQ server, or live output schemas.
- A CLI. Added later only if the workflow proves to need A/B flags, as
  `src/utils/kinetics` did.

### Deferred, to revisit

- **The catch-all param rule.** `voigt_fit.param_rules`' final entry
  (`range_cm1: [0, 0]`, `default: true`) silently supplies narrow bounds to any
  peak matching no explicit window. Flagged for replacement; unchanged for now,
  with only a warning added when it fires (§4).
- **`ir_fitting.baseline:` settings override** — added if EDA warrants it (§6).

## 13. What the first runs showed

Verified against `nn1120-3_pd_ceo2_004` / `20260304_145524_pd_ceo2_004-000`
(72 files after `manually_skip_files`) and `nn1120-2_pd_ceo2_000` unless noted,
with `extra_peaks_base: [1845, 1825]`.

### Correctness checks

| Check | Result |
|---|---|
| Residual vs. live saved residual above 1900 cm⁻¹ | max abs diff **7e-16**. Reconstructing the existing 18 peaks from their saved parameters reproduces the live path exactly, which is what makes append-only sound. |
| `baseline="recompute"` vs `"saved"`, no override | max abs diff **1e-16** across all 72 files -- confirming §6: the baseline cannot depend on which peaks are declared. |
| `on_existing="skip"` on `nn1120-2` (peaks already present) | 0 fitted, 238 skipped, row count unchanged at 2023. |
| `on_existing="overwrite"` | 238 refitted, row count still 2023 -- replaced, not added. |
| `on_existing="error"` | raises `ExistingPeakRowsError`, which the per-file error guard re-raises rather than logging. |
| `PdCO_mol` on `nn1120-2` | 1785/1785 historical rows retain their value; 0/238 new rows carry one. |
| Empty `extra_peaks_base` | no-op with a warning, no files processed. |
| Invalid `on_existing` / `baseline` / `output_folder` | rejected up front with `ValueError`. |

### The finding that matters for the next step

With 1845 / 1825 seeded, **the fitted parameters are frequently pinned at their
rule bounds**, across 72 files:

| Peak | Parameter | Pinned in |
|---|---|---|
| `Peak_1795` | `center` at min (1790) | 33/72 |
| `Peak_1795` | `center` at max (1800) | 17/72 |
| `Peak_1775` | `center` at max (1780) | 30/72 |
| `Peak_1775` | `center` at min (1770) | 8/72 |
| `Peak_1775` | `sigma` at min (2.55) | 42/72 |
| `Peak_1795` | `sigma` at max (26) | 25/72 |

Both centers hit a bound in ~70% of files, and they are pushing *toward each
other* -- 1795 down to 1790, 1775 up to 1780. Combined with `Peak_1795`'s sigma
pinning wide while `Peak_1775`'s pins narrow, this says the two bands are
competing to describe the same feature, and the `[1790, 1800]` / `[1770, 1780]`
windows are not where the data wants them.

So the `param_rules` need real attention before these areas mean anything --
which is the hand-editing already planned (§4), now with specific evidence of
what to change. The peak areas produced by this run should be treated as
provisional until the bounds stop binding.
