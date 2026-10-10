# src/utils/ir_fitting — offline full refit and baseline runs

**Status: implemented and in use.** Offline only. The live server never calls it,
and it never writes into source data.

This file describes what the package does now. How it got here (what was tried,
measured and rejected) is in `context/`:

- `2026-09-17-baseline-investigation.md`: the baseline recipe. Read it before
  changing the recipe, since most obvious alternatives have been tried.
- `2026-09-20-baseline-cleanup-and-cli.md`: the baseline CLI.
- `2026-09-25-full-refit-and-low-band-rules.md`: the refit, the parity gate and
  the low-band rules.

The older append-only spec is in git at `c114eab`. The working spec for the
refit, with its full validation tables, is at `ab4ca27:src/utils/ir_fitting/spec-working.md`.

---

## 0. Read first

```bash
# Refit (argparse CLI). No arguments means the 8 default files -> _test.
uv run python scripts\run_spectral_fit.py --help
uv run python scripts\run_spectral_fit.py --measurements "*-021" --plot --output-folder _test-1

# Baseline runs: one recipe, one figure per file, nothing else.
uv run python scripts\run_baseline_fit.py --help

# Whole-measurement / whole-folder refit: edit-constants in api.py's __main__.
uv run python src\utils\ir_fitting\api.py
```

### Traps

- **Wavenumbers descend.** Index 0 is the high end. Split and select by
  wavenumber *value*, never by position.
- **`create_baseline` takes only `y`.** The window *is* the array the algorithm
  sees, and its classification is global. Changing the window moves the
  baseline everywhere. `half_window` and the other settings are sample counts,
  not cm⁻¹.
- **A degenerate baseline still returns an array.** `BaselineVariant` turns the
  "no baseline points" warning into `degenerate`. The file is still fitted
  (parity-safe), and the flag becomes a file warning.
- **Baseline quality cannot be scored automatically.** The low bands go
  negative, so envelope-style scores rank the best baseline worst. Judge
  baselines visually.
- **Anchor lists keep order and duplicates.** A repeated anchor acts as a
  weight (`1955` ×3 in the default). Never dedupe or sort them.
- **The anchor guard does not protect low anchors.** Its threshold is a
  fraction of the *whole-ROI* range, and bands below ~1900 are only 2–9% of that.
- **Settings keys fail silently when misspelled** inside `create_baseline`, so
  `config.get_baseline_settings` raises on unknown keys. Keep that check.
- **`Peak_Name` is 13CO, while the yaml peak lists are 12CO base.** 12CO `2175`
  and `Peak_2125` are the same peak. Names are integer-formatted
  (`Peak_1913`, not `Peak_1913.0`).

## 1. Purpose and architecture

The package refits **every** peak in `ir_fitting.fit` jointly on the anchored
two-segment baseline and writes live-schema CSVs to a `_test`-style subfolder.
It is self-contained: `voigt.py` is a copy of the fit from
`src/analysis/spectral_fitting.py` (`voigt_model`, `peak_fit`, `add_params`,
rule selection, `create_baseline`, `manually_skip_files`), so that rule and peak
changes here cannot leak into the live server.
`grep -r "src.analysis" src/utils/ir_fitting/` must return nothing.

This deliberately diverges from live. The parity gate (§7) is what establishes
that the copy is faithful.

```
config.py        ir_fitting.fit block: get_fit_settings, get_peaks, get_group_peaks
voigt.py         vendored fit (+ seed clipping/nudging)
baseline.py      BaselineVariant: the recipe, guard, anchors, cut
runner.py        per-file fit: ROI -> baseline -> params (rules + seeds) -> fit -> rows
writer.py        params_frame + CSV writing into the output subfolder
api.py           fit_file / fit_folder / fit_files / load_measurement / run_baseline / subifg_files
refit_cli.py     argparse over api.fit_files
baseline_cli.py  argparse over api.run_baseline; add_recipe_arguments is shared
result_types.py  in-memory bundles the plots consume
```

`src/visualizations` only renders (`plot_individual_fit.py`, `plot_baseline.py`).

## 2. Configuration: `ir_fitting.fit` in `config/analysis.yaml`

The block has the same key names as `voigt_fit`, so the vendored `add_params`
reads it unchanged and promoting it to live is a copy of values.
`voigt_fit` itself is not touched.

- `peak_list_base`: 24 peaks (12CO), the live 18 plus six new cluster peaks.
- `cluster_peaks_base` / `monomer_peaks_base` / `unknown_peaks_base`: groups.
  2175 moves from monomer to **unknown** here only. Moving it in `voigt_fit`
  would change live `monomer_sum`. Groups do not affect the fit.
- `param_rules`: 13CO. The 18 existing rules are verbatim copies of `voigt_fit`
  plus the six new rules (§4). The staged `[1790,1800]` / `[1770,1780]` rules are
  **not** copied.
- `baseline`: the `std_distribution` settings for both baseline segments.

A peak that matches no `range_cm1` falls through to the `default: true` rule
(sigma ≤ 6.37, gamma ≤ 2.8), and `_warn_on_default_rule` logs it.

## 3. Per-file fit (`runner.fit_subifg_file`)

1. `manually_skip_files` → no rows, as in live. Folder discovery also skips
   `isoX` files, which live sends to iso-exchange, not the carbonyl fit.
2. Load the ROI (2250–1750) and resolve the baseline:
   - `"recompute"` (default) runs `BaselineVariant()` (§5).
   - `"saved"` reads `*_CarbonylFitBaseline.csv`. It exists for the parity gate
     and for inspecting the old fit, and falls back to the recipe with a warning.
3. **Skip detector** (`voigt.has_peaks`, a copy of live's, added 2026-10-09).
   It runs `find_peaks` on `raw − baseline` and on its negative, with
   `ir_fitting.fit.find_peaks.subifg`. If neither finds a peak, nothing is fitted:
   every peak gets live's skip row (shape params NaN, `Peak_Area` 0) and the
   residual is 0. Reason (user): runs are long, and fitted noise would build up a
   false cumulative area. `api.apply_peak_detector` applies it to an existing
   refit without refitting (`docs/spec-live-migration.md` §2).
4. Build `Parameters` for all peaks. Bounds come from the rule around the
   **nominal** wavenumber (with `--fsd-snap`, around the snapped FSD peak, below).
   Initial values are seeded from the saved
   `*_CarbonylPeakFitParams.csv`:
   - Lookup is by `(File, Peak_Name)`, and all shape columns must be finite.
   - A seed outside its bounds is clipped, and the clip is counted.
   - A seed within 1% of a bound is nudged inside (`voigt.SEED_NUDGE_FRAC`) and
     counted. On the bound, lmfit's transform has zero derivative and the fit
     never moves.
   - Fixed params (`y0`) always take the rule value.
   - A missing row, a NaN, or a new peak falls back to the rule `value`.
   - Saved rows for peaks not in the list are ignored.
5. `peak_fit` with **`least_squares`**. `method="leastsq"` reproduces live, for
   the parity check. `_warn_on_pinned_params` flags parameters left on a bound.
6. One row per peak in the live `PARAM_COLUMNS`:
   - `Peak_Value` is the nominal wavenumber. Live FSD snapping is a no-op
     because of an index-vs-wavenumber bug, and by default it is not reproduced
     here. **`--fsd-snap`** (`fsd_snap=True`, opt-in, untested) does what live
     intends:
     - load the paired FSD (`<fsd_output>\<dataset>\<base name>.<index>`);
     - find its peaks in wavenumbers (`voigt.find_fsd_peaks`, `find_peaks.fsd`);
     - center each window on an FSD peak within 5 cm⁻¹ (`voigt.snap_peaks`, live's
       loop: the last unused match wins);
     - write that center as `Peak_Value`.
     The rule is still chosen by the nominal wavenumber.
   - `Peak_Area` = `−trapezoid`.
   - `Data_Integral` and `Time_Delta (s)` are copied from the saved rows.
   - `PdCO_mol` is left empty.
   - `is_new` marks peaks with no saved row. No plot reads it now.

## 4. Peaks and the low-band rules

| 13CO `Peak_Name` | Group | Rule notes |
|---|---|---|
| 2196, 2176, 2156, 2146, 2136, **2125** | unknown | 2125 was monomer |
| 2113, 2103, 2093 | monomer | |
| 2073 … 1975 (9 peaks) | cluster | existing width cap pins often (out of scope) |
| 1938 | cluster | center ±2, standard widths, free sign |
| 1928 | cluster | center ±2, sigma ≤ 9, gamma ≤ 4, free sign |
| 1913 | cluster | center −3/+1, sigma 8–14, gamma ≤ 3, free sign |
| 1877 | cluster | center −3/+2, standard widths, free sign |
| 1849 | cluster | center −2/+6, standard widths, free sign |
| 1838 | cluster | center −2/+6, standard widths, `amplitude.min: 0` |

The rules were tuned by a shared-shape fit on `-000` delta10.0042–0072
(context note). 1877/1849/1838 are kept narrow because, when wide, they turn
into plateaus that trade area with the 1913 tail.

**Not yet validated:** the center offsets for 1877/1849/1838 and 1838's `min: 0`
are hand edits made after the last validation run.

## 5. The baseline recipe (`BaselineVariant`)

`BaselineVariant()` **is** the default recipe. The CLI defaults and the fitter
both read it, so the two cannot drift.

| Field | Default |
|---|---|
| `window` | `(2250, 1750)`, which must equal the fit ROI |
| `anchors` | `(2240, 2006, 1955, 1955, 1955)` |
| `lower_split_cm1` | `1955` |
| `lower_anchors` | `(1955, 1800, 1820)` |
| `anchor_guard_cm1` / `anchor_prominence_frac` | `25.0` / `0.5` |
| `settings` | `{}`, overrides for the full-ROI curve only |

To turn off the cut, set `lower_split_cm1=None, lower_anchors=()` together.

`compute()` works in four steps:

1. Compute the full-ROI `create_baseline` curve.
2. Apply the anchor correction. It is affine in wavenumber, fit by least
   squares through the residual `data − baseline` at each anchor the guard
   passes. `data` is a ±10 cm⁻¹ local line fit at each anchor.
3. Below the cut, a second `create_baseline` runs on the lower samples, using
   `ir_fitting.fit.baseline` without the variant's `settings`. It gets its own
   affine correction from `lower_anchors`. Above the cut the curve is bit-for-bit
   unchanged.
4. Splice the two segments.

**The guard** gates each anchor, each lower anchor and the cut with one test:
it drops the point when there is an extremum within ±25 cm⁻¹ whose prominence
is ≥ 0.5 × the whole-ROI range. A gated cut means there is no lower segment. On
the `-022` files, 1955 is gated both as an anchor and as the cut.

`__post_init__` validates the window, the settings keys, anchor positions, and
lower anchors without a cut.

## 6. Outputs

- **Fit output:** written to `C:\Data\peakFit\<dataset>\<output_folder>\`
  (default `_test`). The folder is reused and overwritten, so pass `_test-1`
  etc. to keep a run. An empty or absolute `output_folder` is rejected.
  - `*_CarbonylPeakFitParams.csv` holds **only this run's rows**. A failed or
    skipped file gets none.
  - `*_CarbonylFitBaseline.csv` holds the baseline actually used.
  - `*_CarbonylFitResidual.csv` holds `model − data`.
  - `refit_<YYYYMMDD_HHMMSS>.log` has a settings header, one line per file
    (converged, nfev, seeded/nudged/clipped counts, seconds), the aggregated
    warnings, and tracebacks.
- **Refit figures** (`--plot`): one full-range figure per file, with the
  legend data / fit / peak. `--plot-window` adds zooms.
- **Baseline runs:** `C:\Figures\<dataset>\baseline_experiments\<run_name>\`,
  one PNG per file.

`*_CarbonylPeakArea.csv` and kinetics are out of scope.

### Runtime on the lab machine

`run_spectral_fit` drops to below-normal priority by default (`--normal-priority`
turns this off). `--workers N` fits N measurements in parallel, one process
each. Large batches still belong on another machine, because this one hosts
OPUS, the ZMQ server and the LN2 loop.

## 7. Validation

No test suite. Check against real data. Headline results:

| Check | Result |
|---|---|
| **Parity gate:** live `peak_fit` vs the copy, same start | Δmodel 0.0, Δparams 0.0 (60,339 nfev each) |
| Seeded + nudged vs unseeded, 18 pk, saved baseline | same RSS, 9,142 vs 60,339 nfev |
| `least_squares` vs `leastsq`, 24 pk, seeded | equal or better RSS, 25–90× faster, all converge |
| End-to-end `fit_file` on a scratch copy of five files | columns identical to the saved CSV, 24 rows per file |
| Cut leaves the region above it untouched | max diff 0.0 on the 8 default files |
| Low-band rules, 8 default files (`_test-lowband-A8`) | all converge in 3–7 s |

Rerun the parity gate by passing live `voigt_fit` as `fit_settings` with
`method="leastsq"`. For the unseeded variant, blank the saved shape columns
first. The test script may call live code, but the package must not.

## 8. Open

- **-022 lower baseline:** the lower anchors (1955/1820/1800) don't follow
  delta10.0022/0042. The low band fits negative there. This is a baseline
  problem, not a rules problem.
- **Low-band rules:**
  - 1913's gamma cap could go from 3 to about 4.
  - 1849 flips sign between files.
  - The 1877/1849/1838 centers often end on their bounds.
  - The hand edits in §4 need a validation run.
- **Existing width cap** (6.37 / 2.8) pins on 1975, 2000, 2015, 2156 and others.
- **FSD snapping** (`--fsd-snap`): exposed, not yet tested. Open item O1 in
  `docs/spec-live-migration.md`.
- **Reproducibility depends on BLAS threads.** With `OMP/OPENBLAS/MKL_NUM_THREADS=1`
  (what `--workers` sets) a refit reproduces `_reprocess` to 1e-16. Serial and
  unpinned, areas move by ≤ 1e-3 au and some shape params by up to 0.5 (checked on
  000-007 delta10.0042/delta5.0047, 2026-10-09). Pin the threads for parity checks.
- **Offline kinetics** (`src/utils/kinetics`) still reads the
  `voigt_fit.*_peaks_base` groups, not the ones in `ir_fitting.fit`.

## 9. Out of scope

- Changes to `src/analysis/` and the live server from this package. Since
  2026-10-09, `voigt_fit` holds a copy of this block's values and live runs a port
  of the default baseline recipe (`docs/spec-live-migration.md`). A change to the
  peaks, rules or recipe meant for both has to land in both.
- Changing the ROI window.
- Fixing live FSD snapping.
