# ir_fitting — working spec: self-contained full refit on the anchored baseline

Status: implemented 2026-09-24 (parity gate: see §8). Supersedes the append-only / extra-peaks design in
`spec.md` and `context/2026-09-16-ir-fitting-package-and-extra-peaks.md` where
the two disagree.

## 0. Reading of the user's answers

| Question | Answer | Where it lands |
|---|---|---|
| Wire the new baseline into the fit? | Yes — `"recompute"` runs the default recipe from `baseline_cli.py` | §3 |
| Are new-baseline fits full refits? | Yes — full refit is the only mode. No append-only, no toggles | §7 |
| Existing peaks' starting values | Always seeded from `*_CarbonylPeakFitParams.csv` (no switch) | §6 |
| Rules for the six new peaks | Proposal accepted: one rule each, center ±2, standard widths. Revised 2026-09-25: free sign; 1928/1913 widened | §5 |
| Output format | Same schema as live, but no calls into live code | §4, §7 |
| Window | Unchanged (2250–1750) | — |
| 1845 / 1825 | Dropped; not part of this work | §2 |
| New peaks | 13CO 1938, 1928, 1913, 1877, 1849, 1838 → cluster | §2 |
| 2175 (12CO) | Moves monomer → unknown | §2 |

**Naming convention used throughout:** `Peak_Name` strings are 13CO
(`Peak_2125`); YAML peak lists are 12CO base (`2175`). They are the same peak:
12CO 2175 == 13CO `Peak_2125`.

## 1. Goal

Refit every peak — the current 18 plus six new cluster peaks — jointly on the
anchored two-segment baseline, entirely inside `src/utils/ir_fitting/`, writing
live-schema CSVs to a `_test` subfolder. The live server path
(`src/analysis/`, `voigt_fit` in yaml) is not touched.

## 2. Peak set

Peak lists are **12CO base** (shifted −50 at read time for 13CO).
`param_rules` are **13CO** (`param_rules_base_isotope: 13CO`). Both columns:

| 13CO (Peak_Name) | 12CO base | Group | Status |
|---|---|---|---|
| Peak_2196 … Peak_2136 | 2246, 2226, 2206, 2196, 2186 | unknown | existing |
| Peak_2125 | 2175 | **unknown** (was monomer) | existing, regrouped |
| Peak_2113, 2103, 2093 | 2163, 2153, 2143 | monomer | existing |
| Peak_2073 … Peak_1975 | 2123, 2112, 2100, 2090, 2080, 2065, 2050, 2038, 2025 | cluster | existing |
| **Peak_1938** | 1988 | cluster | new |
| **Peak_1928** | 1978 | cluster | new |
| **Peak_1913** | 1963 | cluster | new |
| **Peak_1877** | 1927 | cluster | new |
| **Peak_1849** | 1899 | cluster | new |
| **Peak_1838** | 1888 | cluster | new |

24 peaks total. Checked against
`C:\Data\peakFit\nn1120-4_pd_ceo2_000\20260630_141811_pd_ceo2_000-000_CarbonylPeakFitParams.csv`:
its 18 `Peak_Name` strings are integer-formatted and equal the current
`peak_list_base` − 50, so the `(File, Peak_Name)` seed join in §6 works as-is.

**Why the regroup is ir_fitting-only:** moving 2175 in `voigt_fit.monomer_peaks_base`
would change live `monomer_sum` membership in kinetics, which is part of the output
contract. Groups do not affect fitting. They are recorded here for promotion and
for offline kinetics.

## 3. Baseline

- `baseline="recompute"` (new **default**) runs the default recipe:
  - window 2250–1750
  - upper anchors `2240 2006 1955 1955 1955`
  - cut at 1955
  - lower anchors `1955 1800 1820`
  - the default anchor-guard constants
- `baseline="saved"` stays available (reads `*_CarbonylFitBaseline.csv`). It is
  needed for the parity gate in §8.
- **The dataclass defaults are the recipe.** `BaselineVariant()` is built from
  `ANCHOR_POINTS_CM1`, `LOWER_SPLIT_POINT_CM1`, `LOWER_ANCHOR_POINTS_CM1`,
  `ANCHOR_GUARD_CM1` and `ANCHOR_PROMINENCE_FRAC`. The CLI's argparse defaults
  and the fitter both read it, so they cannot drift. (Earlier drafts had a
  separate `default_variant()` because the dataclass defaults were unanchored
  and uncut; the defaults were changed instead.) Turning the cut off takes
  `lower_split_cm1=None, lower_anchors=()` together.
- The fit kwarg `baseline_settings: dict` (the std_distribution override, which
  cannot express anchors or a cut) is replaced by `variant: BaselineVariant | None`.
  `None` means `BaselineVariant()`.
- A degenerate baseline (`outcome.degenerate`) is recorded as a file warning.
  The file is still fitted (parity-safe: no silent skip).

## 4. Vendored fit — reverses two earlier decisions

The 09-16 note marked "wrap `spectral_fitting.py`, don't re-implement" as
decided and "ir_fitting-local param rules" as rejected. **Both are reversed.**
This package now diverges from live *on purpose*, with a new baseline, six new
peaks and a regrouped 2175. Wrapping would mean any rule edit for this work
leaks into the live server. The divergence risk that CLAUDE.md warns about for
`src/utils/kinetics` is handled by the parity gate (§8), which must pass before
anything else changes.

New module `src/utils/ir_fitting/voigt.py`, copied from
`src/analysis/spectral_fitting.py`:

- `voigt_model`
- `combined_voigt`, `objective`, `peak_fit` (`combined_voigt` may call
  `voigt_model` directly rather than `Model(voigt_model).eval`; the math is the same)
- `select_param_rule`, `get_shifted_rules`
- `resolve_center_offsets`: simplified, since `temp_peak` is always `None` here
  and no rule uses `special_cases`
- `add_params`: plus seeding (§6)
- `manually_skip_files`
- `create_baseline` (currently imported by `baseline.py` from live)
- `voigt_fwhm` (already local in `runner.py`)

**Completion check:** `grep -r "src.analysis" src/utils/ir_fitting/` returns nothing.

## 5. Config — the ir_fitting block owns its settings

Default: stays a block in `config/analysis.yaml`, which uses the existing cached
loader (see §9 Q2 for a separate file). It is restructured as a full copy of
`voigt_fit`'s key names, so the vendored `add_params` reads it unchanged and
promoting to live means copying values:

```yaml
ir_fitting:
  fit:                                  # same keys as voigt_fit
    isotope_default: "13CO"
    param_rules_base_isotope: "13CO"
    monomer_peaks_base_isotope: "12CO"
    isotope_shift_cm1: {"12CO": 0, "13CO": -50}
    peak_list_base: [2246, 2226, 2206, 2196, 2186, 2175, 2163, 2153, 2143,
                     2123, 2112, 2100, 2090, 2080, 2065, 2050, 2038, 2025,
                     1988, 1978, 1963, 1927, 1899, 1888]
    cluster_peaks_base: [2123, 2112, 2100, 2090, 2080, 2065, 2050, 2038, 2025,
                         1988, 1978, 1963, 1927, 1899, 1888]
    monomer_peaks_base: [2163, 2153, 2143]
    unknown_peaks_base: [2246, 2226, 2206, 2196, 2186, 2175]
    param_rules:                        # full copy of voigt_fit.param_rules (13CO)
      ...                               # + the six new rules below
```

New rules, in 13CO, one per peak. Ranges are lower-inclusive and upper-exclusive,
matching `select_param_rule`, and none overlaps an existing rule (the lowest is
`[1970,1980]`).

**Revised 2026-09-25** (see §8 steps 7–8). The first version gave all six the
standard body with `amplitude.min: 0`. Now the sign is free on five of the six
(1838 keeps `min: 0`), and only 1928 and 1913 are wider. The data does not
determine the widths of 1877/1849/1838, so they keep the standard width limits.
That stops them turning into broad plateaus that trade area with the 1913 tail.
y0 is `{value: 0, min: 0, vary: false}` throughout.

| Peak | `range_cm1` | center offset | amplitude value [min] | sigma value [min, max] | gamma value [min, max] | FWHM max |
|---|---|---|---|---|---|---|
| Peak_1938 | [1933, 1943] | ±2 | 0.01 [none] | 5 [2.55, 6.37] | 2 [0, 2.8] | ≈18 |
| Peak_1928 | [1923, 1933] | ±2 | 0.05 [none] | 7 [2.55, 9.0] | 3 [0, 4.0] | ≈26 |
| Peak_1913 | [1908, 1918] | −3 / +1 | 0.03 [none] | 12 [8, 14] | 1 [0, 3] | ≈36 (min ≈19) |
| Peak_1877 | [1872, 1882] | −3 / +2 | 0.01 [none] | 5 [2.55, 6.37] | 2 [0, 2.8] | ≈18 |
| Peak_1849 | [1844, 1854] | −2 / +6 | 0.01 [none] | 5 [2.55, 6.37] | 2 [0, 2.8] | ≈18 |
| Peak_1838 | [1833, 1844] | −2 / +6 | 0.01 [0] | 5 [2.55, 6.37] | 2 [0, 2.8] | ≈18 |

The new peaks have no saved row to seed from, so these `value`s are their
actual starting points.

**Not yet validated.** The 1877/1849/1838 center offsets and the 1838
`amplitude.min: 0` were edited by hand after §8 steps 7–8. Those runs
(`_test-lowband-A`, `_test-lowband-A8`) used ±2 centers and a free sign on all
three, so their numbers describe that earlier version. With the new offsets the
center windows are 1874–1879 (1877), 1847–1855 (1849) and 1836–1844 (1838). They
do not overlap, but 1849 can now reach the ~1852–1856 dip.

Removed:
- `extra_peaks_base` and the `extra_*_peaks_base` group lists: the fitter always
  fits the full list.
- The commented `ir_fitting.baseline` std_distribution override: superseded by §3.

`config.py` changes:
- `get_voigt_settings()` reads `ir_fitting.fit` (rename to `get_fit_settings()`).
- `get_live_peaks` / `get_extra_peaks` collapse to `get_peaks()`.
- `get_group_peaks(group)` reads the three `*_peaks_base` keys.
- The integer / Peak_Name validation is kept.
- `BASELINE_KEYS` and `get_baseline_settings` go if nothing else uses them.

The staged `[1790,1800]` and `[1770,1780]` rules were removed from
`ir_fitting.fit.param_rules` (2026-09-25); no peak sits there. They remain in
live `voigt_fit.param_rules`. Whether to remove them there is a separate cleanup.

## 6. Seeding existing peaks from the CSV

Always on; there is no switch. For each file and each peak in the fit list:

1. Look up the row `(File, Peak_Name)` in the measurement's saved
   `*_CarbonylPeakFitParams.csv`.
2. If found and `Center/Amplitude/Sigma/Gamma/Y0` are all finite, use them as
   **initial values**.
3. **Bounds always come from the rule around the nominal wavenumber**, never
   around the seeded center. Otherwise centers walk across repeated refits.
4. A seed outside its bounds is clipped explicitly to the nearest bound. The
   clips are counted and reported in a file warning (lmfit would otherwise clamp
   silently).
5. Missing row, NaN or new peak → rule `value`s, i.e. today's `add_params` behavior.
6. `vary` flags come from the rule (`y0` stays fixed at 0).
7. Saved rows for peaks **not** in the current list (e.g. nn1120-2's churned peaks)
   are ignored, and dropped by the merge (§7).

Seeds fitted on the old baseline are only starting points. A full refit on the
new baseline moves them.

## 7. runner / api / writer changes

`runner.fit_subifg_file(subifg_path, df_saved_params, df_saved_baseline, *, fit_settings, baseline="recompute", variant=None)`:

1. `manually_skip_files` → `None` (unchanged).
2. Load the ROI, then resolve the baseline (§3).
3. Build `Parameters` for all 24 peaks: rule bounds plus seeds (§6).
   `_warn_on_default_rule` is kept.
4. `peak_fit` jointly against `raw − baseline`. `_warn_on_pinned_params` is kept.
5. One row per peak in `PARAM_COLUMNS`, carried over unchanged:
   - `Peak_Value` = nominal
   - `Peak_Area` = −trapz
   - `Data_Integral` / `Time_Delta (s)` copied from the saved rows
6. `is_new` marks the six new peaks (see §9a). The plots no longer use it
   (2026-09-25):
   - `plot_individual_fit` draws every peak in one style.
   - The legend is just data / fit / peak.
   - `run_refit --plot` writes one full-range (2250–1750) figure per file.
   - Zooms are opt-in via `--plot-window`.

Removed:
- `append_only` and the live-curve reconstruct-and-subtract path in the fitter.
  `reconstruct_live_curves` stays, because `load_measurement` uses it for inspection.
- `on_existing`, `ExistingPeakRowsError`, `skipped_peaks`, `n_skipped`: a full
  refit has nothing to append onto.
- `writer.merge_params` is replaced by `writer.params_frame`: **the output
  params CSV holds only this run's rows** (decided 2026-09-24). Nothing is
  carried over from the saved CSV. A file that fails gets no rows, and its
  traceback goes to the log. Skipped files never had rows: live skips the same
  files, and `-021`'s saved CSV holds exactly its 107 non-skipped files.
- **Run log** (decided 2026-09-24): with `save`, each `fit_file` writes
  `refit_<YYYYMMDD_HHMMSS>.log` into its output folder, and `fit_folder` writes
  one log for the whole batch. The log holds a settings header (dataset,
  baseline recipe, optimizer, peaks), one line per file (converged or not,
  nfev, seeded, nudged and clipped counts, seconds), the aggregated warnings,
  and full tracebacks. Timestamped, so rerunning into the same folder keeps
  earlier logs.
- **Output folder**: `output_folder="_test"` by default, reused and overwritten
  each run. Pass another name (e.g. `"_test-1"`) to keep a run. Both ways
  are intended.
- **Optimizer** (decided 2026-09-24): `least_squares` (scipy trust-region
  reflective, native bounds) replaces live's `leastsq`. `method="leastsq"`
  still reproduces live exactly for the parity gate.

Call sites to update:
- `api.py` (`fit_file`, `fit_folder`, `_run_measurement`, `load_measurement`, `__main__`)
- `result_types.py`, `writer.py`, `config.py`, `baseline.py`, `baseline_cli.py`, `__init__.py`
- `src/visualizations/plot_individual_fit.py`, `plot_baseline.py`, `_axes.py`
  (docstrings referencing `extra_peaks_base`; `is_new` colouring)

Output is unchanged in location and names: `_test` subfolder,
`*_CarbonylPeakFitParams.csv`, `*_CarbonylFitBaseline.csv` (now the anchored
baseline) and `*_CarbonylFitResidual.csv`.

## 8. Validation

1. **Parity gate — passed 2026-09-24.** The gate as first written (seeded refit
   vs saved CSV) was replaced after it proved uninformative. What was measured:
   - **Seeded vs saved CSV (original gate):** matched to about 5e-13, but only
     because the fit never moved. 37 of about 72 free parameters were seeded
     exactly on a bound (the saved fits pin them). lmfit's bound transform has
     zero derivative there, so `leastsq` stopped after one Jacobian (`ier=2`).
     This also froze the six new peaks at their rule values. Fixed by
     nudging: a seed within 1% of a bound's range is moved that far inside
     (`voigt.SEED_NUDGE_FRAC`) and counted as `n_nudged`.
   - **Unseeded vs saved CSV** (40 files): amplitude and area differed by up to
     about 4.5× relative. Starting from rule values, `leastsq` often hits its
     evaluation cap (2000·(n+1) = 194k) without converging, so its endpoint is
     path-dependent. The large relative differences sit on near-zero or
     degenerate amplitudes. Not a copy defect; see the next two bullets.
   - **The actual gate — live `peak_fit` vs the copy from the same start:**
     identical, with model difference 0.0 and parameter difference 0.0, both
     after 3000 evaluations and run to convergence (60,339 evaluations each,
     `ier=1`). The copy is faithful. (This test script calls the live code;
     the package does not.)
   - **Live-now vs saved CSV, one file run to convergence:** RSS
     3.256646e-5 vs 3.256646e-5 and amplitude difference about 0.3%, so the
     saved CSV sits at the same optimum today's live code finds.
   - **Seeded and nudged, 18 peaks, saved baseline:** RSS 3.256640e-5 in 9,142
     evaluations, vs 60,339 unseeded, so seeding pays for itself.
2. **End-to-end `fit_file` — passed 2026-09-24.** Scratch copy of five
   `-021` files (three fitted; delta1.0005 and delta3.0005 skipped), written to
   `C:\Data\peakFit\nn1120-4_pd_ceo2_000\_test_refit\`:
   - Columns identical to the saved CSV; 24 rows per refitted file.
   - 1944 rows = 1926 saved − 3×18 + 3×24.
   - The 1872 untouched rows match on keys and NaN pattern. Values differ only
     at the last float digit from the CSV round trip (max 5e-13).
   - Baseline and residual CSVs hold one column per refitted file.
3. **`load_measurement` and plots — passed.** `plot_measurement_fits` and
   `plot_measurement_baselines` (saved and recomputed baselines) render.
   Figures are in `C:\Figures\nn1120-4_pd_ceo2_000\_refit_test\`.
4. **New baseline, 18 peaks (8 default files) — done, results provisional.**
   - Per-peak median area change is about 1e-3 to 6e-3, the same order as
     the peaks themselves, so the baseline change materially moves areas.
   - The summed area of the 18 peaks changes by about +1% to +3% on the two
     high-signal files. It changes by several-fold, with sign flips, on files
     whose net area is near zero.
   - **4 of 8 fits hit the evaluation cap without converging.**
5. **New baseline, 24 peaks (8 default files) — done, results provisional.**
   Figures are in `..._refit_test\individual_fit_24pk\`.
   - **5 of 8 fits hit the evaluation cap without converging.** Each file
     takes 2–6 min on one core.
   - The new peaks pin often, out of 8 files:
     - 1913: sigma@max 6, center@min 5, gamma@max 5
     - 1928: center@min 6
     - 1877: sigma@max 4, center at either edge 7
     - 1849 / 1838: amplitude@min 4 / 3, center@max 3 / 4
   - Per file, some of the six carry most of the area and others go to about
     1e-12, and which ones varies between files.
   - Visual check (`-012 delta10.0052`): the 1945–1905 band is fitted. There is
     an unfitted shoulder near 1898, and a negative dip near 1852 that the
     `amplitude.min: 0` rules cannot fit.

6. **Optimizer switch — `least_squares` vs `leastsq`** (same inputs;
   single process at below-normal priority):

   | Case | `leastsq` | `least_squares` |
   |---|---|---|
   | 18 pk, saved baseline, seeded, `-021 delta10.0022` | RSS 3.256640e-5, 9,142 nfev | RSS 3.256639e-5, 659 nfev, 1 s |
   | 24 pk, new baseline, seeded, `-021 delta10.0022` | RSS 1.808786e-5, 164k nfev, 248 s | RSS 1.808358e-5, 10 s, converged |
   | 24 pk, new baseline, seeded, `-017 delta10.0022` | hit 194k cap, not converged, 358 s | RSS 1.176497e-5, 4 s, converged |
   | 18 pk, saved baseline, rule start, `-021 delta10.0022` | RSS 3.256646e-5, 60k nfev | RSS 3.260119e-5, 2 s (0.1% worse) |

   Seeded fits come out equal or better, 25–90× faster, and all converge. The
   step 4/5 numbers above used `leastsq` and should be rerun.

7. **Low-band rules: shared-shape fit on `-000` — done 2026-09-25.**
   - **Data:** `20260630_141811_pd_ceo2_000-000`, delta10.0042/0052/0062/0072, fitted
     below the 1955 cut (1965–1790).
   - **Model:**
     - The six low-band peaks share one center, sigma and gamma across all four files, with one amplitude per peak per file.
     - The sign is free.
     - 1975/1988 are free per file, within their rules.
     - Peaks ≥2000 are fixed at the `_test` refit values.
     - Optimizer: `least_squares`, run from 5 starting points.
     - The script is scratch only, not in the repo.
   - **Result:** all 5 starts converge (with a raised evaluation cap), but to different minima, RSS 6.0e-6 to 7.6e-6.
     - **Consistent across starts:**
       - 1928: center 1927–1929, FWHM 18–25.
       - 1913: center 1910–1912, FWHM 29–30.
       - 1938: center ~1938, but with near-zero amplitude whose sign flips.
     - **Not consistent:**
       - 1877: FWHM 21–42.
       - 1849: center 1844–1850.
       - 1838: FWHM 10–33.
     - With free sign, neighbours partly cancel.
   - **Band shape:** one broad, lopsided band peaking near 1928, with a tail to about 1890. Below 1880 there are only small, narrow features, at about 1870 (+), 1855 (−), 1845 (+) and 1810 (−).
   - **Anchors:** the fitted low-band signal at the 1955/1820/1800 anchors is 1–8% of the band height, so the baseline is not absorbing the band.
   - **Rules:** these results set the §5 rules (2026-09-25).
   - **Validation**, same seeds and baseline for both. Old rules → `_test-lowband-0`, new rules → `_test-lowband-A`:

   | `-000` | 0042 | 0052 | 0062 | 0072 |
   |---|---|---|---|---|
   | RSS 1955–1800, old → new | 1.05e-5 → 3.2e-6 | 5.7e-6 → 1.6e-6 | 2.0e-6 → 3.8e-7 | 8.5e-7 → 6.0e-7 |
   | converged, old → new | **no (194k cap)** → yes (52k) | yes → yes | yes → yes | yes → yes |
   | low-band total area, new | +0.179 | +0.114 | +0.074 | +0.030 |

   - **Pins and time:** low-band pins go from 1 to 0, and the four fits take about 1.5 min instead of about 5.
   - **Shape stability across the four files:**
     - 1928 sits at 1927.8–1928.3, FWHM ≈20.
     - 1913 sits at 1912.8–1913.1, FWHM ≈30–31.
   - **Figures:** the 1898 shoulder is now fitted. The old rules put a false dip near 1900 in 0042.
   - **Area:** the low-band total is within 6% of the old rules', but more of it now sits in 1913 than in 1938.
   - **Still weak:** 1849 changes sign between files, following the ~1852 feature.

8. **Low-band rules on the 8 default files — done 2026-09-25**, output in `_test-lowband-A8`.
   - **Convergence:** all 8 converge, in 3–7 s each (3.1k–6.6k evaluations). There is no old-rules `least_squares` run on these 8 to compare against; step 5 used `leastsq`.
   - **Shapes, 6 of 8 files** (all but -022):
     - 1928: center 1926.0–1928.8, FWHM 15–24.
     - 1913: center 1910.0–1914.0, FWHM 26–36.
     - In -007 delta10.0042 the 1945–1880 band is fitted closely, and 1849 goes negative to follow the ~1850 dip.
   - **Pins over 8 files:**

     | Peak | Pins | Notes |
     |---|---|---|
     | 1938 | 4 | |
     | 1928 | 2 | both on center |
     | 1913 | 8 | center at both edges; gamma at its 3.0 cap 3× |
     | 1877 | 8 | mostly center |
     | 1849 | 8 | mostly center |
     | 1838 | 6 | mostly center |

     The width-cap pins on 1877/1849/1838 occur mainly in -022. The existing 18 peaks pin far more often, for example 2000, 2015 and 2156 on 6–8 files each (the old width cap, untouched here).
   - **-022 fails, and it is a baseline problem:**
     - In delta10.0022 and delta10.0042 the band comes out negative.
     - The corrected spectrum rises to about +0.0025 below 1850.
     - 1938 fits to −0.141 while 1877/1849/1838 go strongly positive to follow the slope.
     - The low-band total area is therefore negative: −0.069 and −0.034.
     - The lower baseline segment is the cause, not the rules.

### Open after validation

- **Throughput**: fits are serial. Large batches go on a different machine
  (decided 2026-09-24). This one hosts OPUS, the ZMQ server and the LN2 pump loop.
- **Rules for 1948–1838**: revised 2026-09-25 (§5, §8 steps 7–8). Remaining:
  - 1913's gamma cap (3.0) could go to about 4.
  - 1849 changes sign between files.
  - 1877/1849/1838 centers often end on their bounds.
- **-022 lower baseline**: the 1955/1820/1800 lower anchors do not follow
  -022 (delta10.0022, delta10.0042), and the low band fits negative there
  (§8 step 8). This belongs to the baseline work, not the rules.
- **Existing peaks' width cap** (sigma 6.37 / gamma 2.8): 1975, 2000, 2015,
  2156 and others pin on most files. Out of scope for the low-band work.
- Out of scope (decided 2026-09-24): `*_CarbonylPeakArea.csv` / kinetics from
  refit output, and a diagnostics CSV.

## 9. Decisions log

- 2026-09-23: full refit is the only mode, with seeding always on. The six
  new-peak rules are as proposed (§5).
- 2026-09-24: `PdCO_mol` is left empty on refitted rows. Config stays a block in
  `analysis.yaml` (`ir_fitting.fit`).
- 2026-09-25, low-band rules (§5, §8 step 7):
  - The rules are tuned on `-000` delta10.0042–0072 with a shared-shape fit.
  - Peak_1856 is **not** in the set; the six peaks stay.
  - Amplitude sign is free on all six. Later the same day, 1838 was set back to `min: 0` (below).
  - No merging of close pairs (1938/1928, 1849/1838).
  - Nominal wavenumbers are kept, with the 1913 center offset widened to −3/+1 rather than renaming it.
  - 1877/1849/1838 stay narrow.
  - 1938 stays narrow.
- 2026-09-25, later, hand edits after §8 steps 7–8, not yet validated by a run:
  - Center offsets: 1877 −3/+2, 1849 −2/+6, 1838 −2/+6.
  - 1838 back to `amplitude.min: 0`.
  - The staged 1790/1770 rules were removed from `ir_fitting.fit`.
  - Refit figures: full range only, with the legend reduced to data / fit / peak.
- Baseline recipe (anchors, cut, lower anchors, guard): stays as constants in
  `baseline.py`, as the `BaselineVariant()` defaults. The per-segment std_distribution
  settings live in `ir_fitting.fit.baseline`. Moving the anchors into yaml
  later is a small change if wanted.

## 9a. As built

- The parity gate needs no switch in the code. It passes the live `voigt_fit`
  dict as `fit_settings` (a config read, not a live-code call). For the
  unseeded variant it blanks the saved shape columns, so every peak starts
  from its rule exactly as live does. `Data_Integral` / `Time_Delta (s)` are
  still carried over.
- A fixed parameter (`y0`, `vary: false`) always takes the rule value, never
  a seed. Otherwise a rule edit would silently do nothing on refit.
- `is_new` marks peaks the saved fit had no row for, i.e. the six new peaks.
  It needs no config lookup. No plot reads it any more; it stays on
  `PeakCurve` for callers.
- `load_measurement` (inspection) uses `runner.load_subifg_file`, which fits
  nothing and rebuilds the saved curves.
- The `ir_fitting.fit.param_rules` copy no longer carries the staged
  `[1790,1800]` / `[1770,1780]` rules (removed 2026-09-25). It is therefore not
  a verbatim superset of `voigt_fit.param_rules`; the other 18 rules are still
  verbatim copies.

## 10. Out of scope

- Any change to `src/analysis/`, `voigt_fit` in yaml, or the live server.
- Promoting peaks or groups to live.
- Offline kinetics on the refit output (`src/utils/kinetics` reads
  `voigt_fit.*_peaks_base`, not `ir_fitting.fit`). Pointing it at the new groups
  is a follow-up.
- Changing the ROI window.
