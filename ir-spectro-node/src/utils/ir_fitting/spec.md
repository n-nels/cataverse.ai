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
| **Baseline investigation** (§14) | Active. Tuning and bare truncation ruled out (§14.3, §14.6). The isosbestic point is measured (~1957) and an **anchored baseline is built and calibrated** (§14.7). It recovers the halved bands on the post-crossing files and is a no-op on the pre-crossing ones. **Splitting at the crossing is built and rejected** (§14.8) — though the post-mortem shows it was tested in its worst form, and names the variant worth trying — **that variant is now built and measured (§14.9)**: it keeps all of the anchor's band recovery, verified, and replaces the anchored baseline's unconstrained 205 cm⁻¹ extrapolation below the lowest anchor, at the cost of a seam §14.7 does not have. **Whether to prefer it over §14.7 alone is open — the visual call has not been made.** A fourth anchor at 1854 was tried and removed (§14.7.1). **The lower segment now has anchors of its own — both its endpoints, `(1955, 1750)` (§14.10, §14.10.1)**: containment above the cut still verified at exactly zero, and the seam improved against the unanchored split on five of six files. An interior third anchor at 1800 was built, measured and **removed by the user on the figures** (§14.10.1); with two anchors the correction is exact at both ends, so the seam is now *predicted* by the upper anchor's residual at 1955 and confirmed to 0.05% of range. The `.0022` regime is still unfixed — §14.10's apparent movement there was measured on a proxy that §14.10.1 finding 24 withdraws. `lower_settings` now exposes the lower segment's own `std_distribution` parameters (no default changed). **The settings are now re-swept under the anchor (§14.11)**: the three anchor residuals are one scalar, `lower_settings` provably cannot move the seam, and tuning the *upper* side halves both that scalar and the seam — while making the 2040 recovery slightly worse and ranking differently on a 60-file sample. **Then the algorithm itself was changed (§14.12), which is the knob no earlier section turned**: below the cut, with `lower_anchors` removed on the user's instruction, `pspline_arpls` at its defaults is the only one of 44 `pybaselines` methods that hits all three targets the user stated this session — baseline through the midpoint of the dispersive ~1850 feature on post-crossing files, under the base of the 1850/1870-1880 bands on pre-crossing ones, near-zero mean residual over 1838-1750. **It is the first thing in §14 to fix the `.0022` regime.** Containment above the cut is still exactly 0.0 and the `...-022` gate still a no-op; the cost is a seam ~1.5x the two-anchor form. **The user judged that form's lower segment no good on the figures, and named the fix: tie the second baseline off at 1800 rather than 1750 (§14.13)** — built and measured. Over the region it now fits, the artefact is gone: `...-012`'s residual drops from +1.11 to +0.19 and all six judged files land inside ±0.22, `und` improves on every one, and the 1955 seam improves on five of six. The 44-method ranking was re-derived on the shortened array and does not move. **The cost moved rather than went away** — below 1800 the anchored baseline stands, and the jump there is 6.5–16.6% of range, the largest discontinuity in §14. **The user then removed the floored form, and the splice with it, from consideration on the figures (§14.13.1)** — the comparison is back to four traces and nothing below 1955 is recommended. **§14.14 then resolves what §14.13.1 could not: *"the splice"* meant `pspline_arpls`, not the 1955 cut.** The cut stays, its seam is tolerated, and `lower split 1955` is the preferred form. `pspline_arpls` is rejected on a third ground (*"caused major problems elsewhere"*), a full-ROI algorithm swap is out of scope (historical datasets), and a cross-file/stack estimate is shelved. Three new measurements say why the region below the cut is wrong and what will not fix it: `weights` — the sixth setting §14.3 finding 1 never swept — is **bit-for-bit a no-op** on the `.0022` files (finding 41), because `std_distribution` classified **0 of 17** samples in 1870–1836 as background and, on `…-021`, only **3 of 106** in the whole lower segment (finding 42); it is neither degenerate nor an endpoint line (finding 43). So the band is not being mistaken for background — the curve is **under-constrained**, which retires every mask-style fix and points at a **C¹ continuation** of the anchored baseline below the cut. **That continuation is now built — as the continuation **plus** `num_std: 3.0` on the lower classifier, which is load-bearing and is the one knob the rest of §14 leaves alone — swept and checked on both samples (§14.15), and it is the best-measured form in §14.** Everything §14.14 required is exact — containment 0.0 over 688 rows, band heights bit-identical, the `…-022` gate a no-op — and the property §14.14 called a prediction holds: one construction serves both regimes, **the first time without `pspline_arpls`**. Post `mid` 0.25 and pre `und` 0.54 beat every earlier form including the rejected one; the seam, measured properly for the first time as `seam_excess`, is **0.36 against the splice's 5.58**. Two things make it work that §14.14 did not foresee: finding 44 — the classified points are not sparse but **confined above ~1910** on the pre-crossing files, so the `int` window has *nothing* in it and no `lam` over seven decades can help — and finding 45, that `lower_settings` under a continuation configures the **classifier**, which is the one lever that fixes it (`num_std` 3.0 reaches to ~1807). The 60-file breadth sample **agrees with the judged six** for once (51/53), where §14.11 finding 30 warned it would not. Costs: pre `int` +3.3/+3.7, unfixed; and `num_std` 3.0 works through a **regime coincidence** in where the threshold falls, which is the section's largest risk. **The visual call has not been made and nothing is recommended.** **§14.16 then goes back to §14.7's form — three anchors, no split, no continuation — on an array truncated to 2250–1800, at the user's instruction.** It moves the pre-crossing `.0022` regime **without a cut**: against `anchored`, `mid` crosses to the correct side of zero on both files, `und` falls from +5.2/+6.2 to +2.4/+2.5, and `int_shared` improves by 7.4/7.5 points — with no seam, no second curve and no `num_std` change, so none of §14.15's classifier risk. **It is nonetheless a clear third: §14.12's `pspline_arpls` and §14.15's continuation beat it on all three targets on both pre-crossing files** (finding 50, whose first draft claimed the opposite before the comparison had been run). On the post-crossing regime it is very nearly a **no-op**: band heights bit-identical on three of four files, `mid`/`und` identical on three of four (finding 49). The denominator confound truncation could have introduced is measured and **confined to the two guard files** (finding 48), which do degrade (finding 51). `int_shared` is a new column because plain `int` is **not comparable across a window change**. **Breadth has not been checked and the visual call has not been made; no default is changed and the production ROI is untouched.**|
| **Two extra low-wavenumber peaks** (§4) | Dormant — `ir_fitting.extra_peaks_base` is `[]`, so nothing fits them. The machinery works; the peaks are simply not configured. |

**Current experiment status:** §14.21/§14.22 record the selected
configuration, and it is now the **default of the CLI** (§16) rather than a
variants list in `api.py`. It retains the full `(2250, 1750)` ROI and the
lower-only cut at 1955; the selected trace uses the three established anchors
plus the dense upper set `2011–2000`, and the five lower anchors
`(1955, 1790, 1800, 1810, 1820)`. The lower experiment's range is 1955–1750
cm⁻¹. `run_baseline_experiment.py` with no arguments is that form, and
`--compare` restores §14.21's other three traces. §14.19 and §14.20 remain the
preceding measured iterations; no production recommendation or default changed.

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

**The open question now — answered for the region below the cut.** The `.0022` /
pre-crossing files (§14.3 finding 3) were unchanged by anchoring, and §14.8's
split did not reach them; §14.10 finding 19 looked like the first measurement to
move them and §14.10.1 finding 24 withdrew it. **§14.12 moves them for real**, by
changing the lower segment's *algorithm* rather than its parameters or its
anchors: on `...-021` the 1850 and ~1876 bands go from being cut into by 4% of
range to standing above a baseline touching their feet, and the 1838–1750
residual goes from −6.0% to +0.2%. Below 1955 there are now three proxies rather
than none, but they are the **user's stated targets**, not discovered ones, and
finding 33 shows any one of them alone still ranks a wrong baseline first. What
remains open is the seam — 1.5× the two-anchor form, since removing the anchor at
the cut gave up the only thing holding it (§14.12 finding 36) — and whether the
`.0022` depression below 1838 was baseline error at all, which the `int ≈ 0`
target asserts rather than measures.

**Superseded again by §14.15 — read that first.** §14.14's proposal is built.
The region below the cut now has a form that satisfies `mid` and `und` on both
regimes at once, is continuous at the cut to 0.36% of range, changes nothing at
or above it, and does not use the rejected algorithm. What it does not fix is
`int` on the two pre-crossing files (+3.3, +3.7), and finding 44 bounds how much
more classification can do there. The two paragraphs below are what stood before
it.

**Superseded by §14.14 decision 1.** *"The splice"* meant
`pspline_arpls`, not §14.9's cut: the cut **stays**, its seam is tolerated, and
the user's preferred form is now **`lower split 1955`** (§14.9), not §14.7 alone.
`pspline_arpls` is rejected on a third, independent ground — *"it caused major
problems elsewhere"* — and replacing the full-ROI algorithm is out of scope
because the historical datasets would need refitting. The next thing to try is
§14.14's C¹ continuation. The paragraph below is what stood before that.

**The recommendation through §14.13.1 was the single anchored baseline of §14.7, and
below 1955 there was nothing recommended.** §14.12's `pspline_arpls` and
§14.13's floor at 1800 met the three stated targets and were **removed from
consideration by the user** (§14.13.1); they remain built, measured, and off. §14.8
tried the other reading of §14.4 step 3 — `ip` as a split point rather than a
pass-through point — and measured it as worse. §14.9, §14.10 and §14.10.1 build
the form that is *not* worse and is not obviously better either; it is a trade
waiting on a visual judgement, and it has not displaced §14.7 as the
recommendation.

### How to run things

```bash
# Baseline experiments. With NO arguments this is the selected form of §14.22
# on the eight judged files — what api.py's __main__ block used to do.
uv run python scripts\run_baseline_experiment.py
uv run python scripts\run_baseline_experiment.py --help

# The flags are the knobs §14 actually introduced (§16): --window, --anchors,
# --lower-split, --lower-anchors, and the two guard thresholds. --with-twin
# adds the uncut twin that turns upper_max_abs_diff from NOT CHECKED into a
# real check; --compare restores §14.21's four traces.
uv run python scripts\run_baseline_experiment.py --with-twin
uv run python scripts\run_baseline_experiment.py --anchor-prominence-frac 0.9

# Peak fitting. Still edit-constants, in api.py's __main__ (MODE is gone —
# the baseline branch moved to the CLI, so what remains is the fit path).
uv run python src\utils\ir_fitting\api.py

# The baseline CLI prints one compact row per file per variant (gated, seam,
# mid/pre/und/int/n, band heights), the upper-check verdict, and the CSV path;
# everything else is in baseline_comparison.csv (§16.4).

# View saved baselines for one measurement (computes nothing new).
uv run python src\visualizations\plot_baseline.py

# View per-file fits.
uv run python src\visualizations\plot_individual_fit.py
```

Batch **fitting** follows the repo's edit-constants convention: change the
constants in an `if __name__ == "__main__":` block. Batch **baseline
experiments** have an argparse CLI (§16), added on the condition §12 named —
the recipe is what gets swept, and re-typing a variant list is how a sweep goes
wrong. The split mirrors `src/utils/kinetics`, where the algorithm under active
iteration got a CLI and batch fitting did not.

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
  That anchor is gone (§14.10.1), but the limit is not — it applies to any anchor
  placed below ~1900.
- **Below 1955 the only proxies are the three the user stated, and each is
  gameable alone.** Every "distance from the data" measure invented in-house got
  it backwards, because the bands there are negative-going and a baseline pulled
  down onto them scores *better* — §14.10.1 finding 24 has the worked case.
  §14.12 uses `mid` / `und` / `int` instead, which come from the user rather than
  from the data, and reports all three together: `irsqr` is best of 44 methods on
  `int` and is a strict lower envelope sitting 9% of range below where it belongs
  (finding 33). Never sum them, never quote one. §14.13 finding 38 re-ran the
  sweep on a shorter array and `irsqr` failed the same way, so the floor does not
  retire this.
- **Under a floor, `int` over 1838-1750 straddles two baselines.** The lower
  segment stops at `lower_floor_cm1` and the anchored full-ROI baseline stands
  below it, so the user's own `int` window covers one fitted curve and one
  inherited one. Score the fitted segment over 1838-1800 (`int>fl`) and read the
  full-window number as what it is: mostly a measurement of the anchored
  baseline down there (§14.13 findings 37 and 40).
- **A floored variant has two interfaces, not one.** `seam_jump` is the cut's and
  `floor_seam_jump` is the floor's; they are different kinds of join — two
  fitted curves at the cut, one fitted and one inherited at the floor — so they
  are reported separately and never summed. The floor's is the larger by 3-5x.
- **A seam is not a discontinuity.** Adjacent samples of a *continuous* curve
  differ by ~slope x the 1.9 cm-1 grid step, so §14.15's continuation reports a
  non-zero `seam_jump` while having no discontinuity at all. Compare forms on
  `seam_excess_pct_of_range`, which subtracts what the unsplit anchored curve
  does across the same sample pair. `seam_jump` is still the right column for
  two independently computed segments, where the two are nearly equal anyway.
- **Below 1955 the classifier does not reach the bottom of the array on the
  pre-crossing files.** Not "few points" — *none* below ~1910, which is the
  whole 1838-1750 `int` window (§14.15 finding 44). Any form that fits
  `std_distribution`'s classified points there is extrapolating the last
  ~160 cm-1 whatever its parameters say, and `lam` over seven decades does not
  move it. This is also why `pspline_arpls`, which classifies nothing, could
  reach where nothing else could.
- **`num_std` is not a mask, and a larger value is not a stricter one.** It
  raises the tolerance for calling a sample background, so 3.0 classifies *more*
  of the spectrum than 1.1, not less. §14.15 finding 45 uses that direction
  deliberately; §14.14 finding 41's `weights` family fails in the other.
- **The three anchor residuals are one number.** A least-squares line through
  three points leaves a 1-D residual, so `(r2240, r2006, r1955)` is always
  proportional to `(+0.218, −1.218, +1)` — measured std 0.000000 over 174 rows
  (§14.11 finding 25). Reporting them as three independent misses reads as more
  information than there is.
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
  when it differs from the reference, the anchors applied and gated on each side
  of a cut, the seam, and a `DEGENERATE` marker. It is drawn **below** the
  figure: those annotations make the labels wide enough that an in-axes box
  covered the top of both panels, which is where the flat 2235≐2250 check is
  read from.
- Both figures carry a reference grid — `_axes.apply_reference_grid`, major and
  minor ticks on both axes, 50/10 cm⁻¹ over the full ROI and finer on a zoom.
  Judgement here is visual (§14.3 finding 4), and reading a value off a 500 cm⁻¹
  span with five ticks is guesswork. `plot_individual_fit` shares `_axes` and
  could take it too; it has not been changed.

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

#### Choosing which files to run on — `subifg_files`

`files=None` means `JUDGED_FILES`, and those eight stems live **only** in
`nn1120-4_pd_ceo2_000`. So `folder_name` alone never changed which data was
looked at: point it at another dataset with `files=None` and every file is
reported missing. `files` wanted fully qualified stems typed by hand
(`20260304_145524_pd_ceo2_004-000_delta10.0012`), which is why sampling an
arbitrary folder had effectively stopped being available.

`api.subifg_files` is the bridge. It takes the folder and the two things a
person actually picks — which measurement, which delta group — and returns the
stems:

```python
compare_baselines(
    variants,
    folder_name="nn1120-3_pd_ceo2_004",
    files=subifg_files(
        "nn1120-3_pd_ceo2_004",
        measurements=["20260304_145524_pd_ceo2_004-000"],  # or ["*-000"], or None
        file_keys=["delta10"],           # or ["delta10.0042"], ["delta10.00*"], None
    ),
    run_name="my_run",
)
```

`file_keys` is the **same vocabulary** `plot_baselines` already used —
`result_types.matches_file_key`, now public, is the one matcher behind both, so
`["delta10"]` selects the same thing on either path. `measurements` is an exact
base name or a glob against it. `None` on either axis means "all", and `None` on
both means every subIFG file in the folder.

That last case is the reason for `limit`, defaulting to
`DEFAULT_FIGURE_BUDGET = 40`. A dataset folder holds ~12k subIFG files and a
delta group spans every measurement in it: `file_keys=["delta10"]` on
`nn1120-4_pd_ceo2_000` matches **385 files**, one figure each per variant. Over
the limit the helper raises and says how many matched and how many measurements
the folder has, rather than starting the run. Raise `limit` deliberately.
A pattern matching nothing also raises, listing the delta groups that do exist —
a typo would otherwise produce a silent empty run.

A stem that is one of the judged eight keeps its `bad` / `guard` verdict when
named explicitly, so a hand-built or `subifg_files`-built list of them produces
the same figure titles and `verdict` column as `files=None`.

On the CLI (§16) this is `--measurements`, `--delta-groups` and `--limit`
beside `--folder`; both selectors omitted falls back to `JUDGED_FILES`. The run
prints the selected stems, the resolved variants and the destination directory
**before** computing, because `baseline_experiment_dir` reuses a directory — a
second run under an unchanged `--run-name` overwrites the first run's figures
and CSV. `--dry-run` stops after that print.

*(Historical: these were the `MEASUREMENTS` / `DELTA_GROUPS` / `FILE_LIMIT`
constants in `api.py`'s `__main__` block, which §16 replaced.)*

Every variant is measured against the **first**, so put the baseline being
compared to at the front. A variant is a `BaselineVariant` or a
`(label, settings[, window[, anchors[, split_cm1[, lower_split_cm1[, lower_anchors[, lower_settings]]]]]])`
tuple; `window` is `(high, low)` cm⁻¹ and defaults to the 2250–1750 ROI.

The last five are the ways a baseline can be changed beyond its settings, and
they are not interchangeable:

| Slot | What it does | Section |
|---|---|---|
| `anchors` | Affine correction pulling the full-ROI baseline to the data at each surviving wavenumber. The array is never cut. | §14.7 |
| `split_cm1` | Cuts the ROI and recomputes **both** sides on their own truncated arrays. Measured and rejected; kept as a knob. | §14.8 |
| `lower_split_cm1` | Keeps the anchored full-ROI baseline above the cut untouched, replaces it only below. Recommended. | §14.9 |
| `lower_anchors` | A *second* affine correction, on the lower segment alone — its own line, its own residuals. Requires `lower_split_cm1`, and raises without it. Two by default, so both are hit exactly. | §14.10.1 |
| `lower_settings` | `std_distribution` overrides for the lower segment only. Requires a cut of either kind. `None` keeps the current baseline's parameters, which is what every measurement used. | §14.10.1 |
| `lower_method` | Replaces the lower segment's **algorithm** — any `pybaselines.Baseline` method instead of `std_distribution`. Requires `lower_split_cm1`; mutually exclusive with `lower_settings`, whose keys belong to `std_distribution`. Arguments go in `lower_method_kwargs`. | §14.12 |
| `lower_floor_cm1` | Ties the lower segment off **above** the ROI floor, so its algorithm never sees the array edge. Requires `lower_split_cm1`, and must sit strictly between the window floor and the cut. Below it the anchored full-ROI baseline stands, at the price of a second seam. | §14.13 |

`split_cm1` and `lower_split_cm1` are mutually exclusive and raise if both are
set — they cut at the same wavenumber and mean different things. A comparison that includes either
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

`lower_method` adds `lower_method`, saying which algorithm actually ran below
the cut — blank on a gated cut, where none did. `lower_floor_cm1` adds
`lower_floor` and `floor_seam_pct_of_range`; read the latter next to
`seam_pct_of_range` rather than merged with it, and read `int`-style residuals
over 1838-1800 rather than the full 1838-1750 window, which under a floor spans
two different baselines (§14.13 finding 37).

A `lower_split_cm1` variant adds two more: `upper_max_abs_diff`, which must be
**exactly 0.0** because above the cut the baseline is the anchored one by
construction, and `lower_moved_pct`, which carries the variant's actual effect.
The band-height columns cannot: 2040 and 1980 both sit above the cut, so they
are guaranteed to equal the anchored variant's (§14.9 finding 13).

`lower_anchors` adds `lower_anchors` / `lower_anchors_gated`, reported apart from
`anchors` / `anchors_gated` because they are two corrections on two arrays and
1955 belongs to both. The column to judge a `lower_anchors` run on is
`seam_pct_of_range` — not the band heights, which are pinned to `anchored` by
finding 13, and not `lower_moved_pct`, which only says the lower baseline moved.
With the default two anchors the seam is *predictable* before the run — it is
minus the anchored baseline's residual at the cut — and `__main__` prints
predicted against actual as a check (§14.10.1 finding 21).

Past the fifth slot, declare variants with the **keyword** form,
`BaselineVariant(label=..., lower_split_cm1=..., lower_anchors=...)`. The
positional tuple exists to keep `("current", {})` short; at eight slots with two
`None`s in the middle it no longer does. `coerce` still accepts both.

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
| Active offline experiment | `api.py`'s selected comparison uses `DEFAULT_WINDOW = (2250, 1750)`, a lower-only cut at `1955`, upper anchors `(*ANCHOR_POINTS_CM1, 2011, 2010, ..., 2000)`, and lower anchors `(1955, 1790, 1800, 1810, 1820)`. This is experiment-only; `ANCHOR_POINTS_CM1` and production defaults remain unchanged. |
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

**No longer out of scope:** *"A CLI. Added only if the workflow needs A/B flags,
as `src/utils/kinetics` did."* The workflow now does, and the CLI is built —
§16. It covers baseline experiments only; batch fitting stays on the
edit-constants convention, exactly as in `src/utils/kinetics`.

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
| `lower_anchors` do not leak above the cut | with `LOWER_ANCHOR_POINTS_CM1` applied (re-checked for both the three- and the two-anchor set), `upper_max_abs_diff` is still **0.0e+00** on all 8 files, and the flat 2235–2250 means and both band heights are identical to `anchored` (§14.10 finding 17). `lower_anchors` is excluded from `_recipe_key` on purpose, so the `anchored` twin — and therefore the check — stays in place. |
| Two lower anchors are hit exactly, so the seam is predictable | predicted `-(anchored residual at 1955)` against the measured seam, per file: gap **0.013-0.056% of signal range** on all six un-gated files — the sub-sample interpolation gap and nothing more (§14.10.1 finding 21). Printed by `api.py`'s `__main__`. |
| `lower_settings` without a cut, or with an unknown key | rejected at variant construction with `ValueError`, on `settings`' precedent. |
| `lower_settings` is confined to the lower segment | `lower_settings=None` against `lower_settings=` the current resolved settings: max abs diff **0.0**, so the default is bit-for-bit §14.8-§14.10. `{"half_window": 4}` moves the baseline by 2.2e-4 below the cut and by **0.0 at and above it**. Honoured by `split_cm1`'s lower segment as well (1.9e-4). |
| `lower_anchors` without `lower_split_cm1` | rejected at variant construction with `ValueError`; there is no lower segment to anchor. A `lower_anchors` entry above the cut is rejected the same way. |
| `lower_split_cm1` unchanged by the §14.10 branch | the unanchored `lower split 1955` variant reproduces §14.9's seams exactly in the same run (−2.87/−1.77/−5.64/+2.02/+0.85/−0.53) and its local-step ratios to the reported precision (2.2/1.2/5.3/10.7/9.8/0.4). |
| `lower_anchors` with the cut gated | `...-022`, both files: `lower_anchors_applied` empty, `lower_moved_pct` 0.0, result identical to `anchored` — the anchors go with the cut rather than being fitted to a segment that was never made. |
| `lower_floor_cm1` confines the lower method to `[floor, cut)` | with `pspline_arpls` floored at 1800: `upper_max_abs_diff` **0.0e+00** on all 8 judged files, and max abs diff vs `anchored` **below** 1800 is **0.0e+00** as well — asserted per file in `floor_per_file_table.py`, not inferred (§14.13 finding 39). |
| `lower_floor_cm1` goes with the cut when the guard fires | `...-022`, both files: cut gated at 1955, `lower_floor` blank in the CSV, `lower_moved_pct` 0.0, result identical to `anchored` — as for `lower_method` and `lower_anchors`. |
| `lower_floor_cm1` without `lower_split_cm1`, at the window floor, or at/above the cut | rejected at variant construction with `ValueError`; a floor at the ROI floor is the unfloored form written as a setting. A `lower_anchors` entry below the floor is rejected the same way. |
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
`split_cm1`'s precedent; it now gets anchors of its own — as first built, three
of them: **both endpoints of its own segment plus 1800 cm⁻¹**.

> **Read §14.10.1 first. `LOWER_ANCHOR_POINTS_CM1` is now `(1955, 1750)`** — the
> 1800 anchor was removed by the user on the figures. Every table in this section
> measures the **three**-anchor set and is kept as the record of it, not as a
> description of the default. Findings 21–24 supersede findings 18–20 where they
> overlap; finding 19's reading is **withdrawn** by finding 24, and finding 16 is
> now about a wavenumber that is only a probe.

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

#### Finding 16. The guard passes 1800 on every file — a standing limit of the guard, not a fact about 1800

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

> **Withdrawn by finding 24.** The numbers are right; the reading is not. Below
> 1955 the bands are negative-going, so "the subtracted trace sits nearer zero"
> and "the baseline has been pulled onto the band" are the same movement, and this
> metric rewards the form the user rejected. Kept intact because §14.10.1 argues
> against it and an edited-away claim cannot be argued against.

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

(The 1800 column is the removed anchor; §14.10.1 finding 23 re-reads it against
the *current* baseline's own miss at 1800, which changes what it means.)

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
below 1955 — which finding 24 later shows is not a result in the direction it
appears to be (finding 19, withdrawn).
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
#### 14.10.1 The 1800 anchor — tried and removed

**Outcome: `LOWER_ANCHOR_POINTS_CM1` is `(1955, 1750)`.** The interior anchor at
1800 was built, measured (§14.10), judged on the figures and taken out again by
the user — *"that did not work well"*. The lower segment keeps both its endpoints
and nothing between them. This subsection is kept so it is not re-added on the
same reasoning, and because removing it changes the mechanics, not just the
count.

**Two anchors are hit exactly. Three were not.** `apply_anchors` fits a
least-squares line to three or more residuals and the unique line through two —
so the lower baseline now passes through the data estimate at the cut and at the
ROI floor, instead of being pulled toward three points and satisfying none. Every
number below follows from that.

##### Finding 21. The seam is now predictable, and it is fixed by the upper side alone

If the lower baseline hits `anchor_data_value(1955)` exactly while the upper side
still misses by its own least-squares residual, then

> **seam = −(the anchored baseline's residual at 1955)**

up to the ~1.4 cm⁻¹ between the anchor and the lower segment's top sample. That is
a prediction, not a description, so it was checked before the run was read. As %
of signal range:

| File | index | predicted | actual | gap |
|---|---|---|---|---|
| `...-007` | .0042 | −1.742 | −1.770 | −0.028 |
| `...-008` | .0042 | −0.704 | −0.760 | −0.056 |
| `...-012` | .0052 | −2.694 | −2.748 | −0.054 |
| `...-017` | .0022 | +1.507 | +1.495 | −0.013 |
| `...-021` | .0022 | +1.165 | +1.129 | −0.036 |
| `...-027` | .0052 | −0.689 | −0.729 | −0.041 |

Agreement to 0.013–0.056% of range, which is the sub-sample gap and nothing else.
The predicted column is §14.7's own anchor residual at 1955 — `...-007`'s +1.74%
is the number §14.8's miss table already reported — so this is the two sections
meeting where they should.

**This retires a thread.** With the endpoint anchor exact, *nothing done below the
cut can change the seam*: it is bounded by the quality of the full-ROI anchor at
1955 and by that alone. A smaller seam now needs a better upper anchor, a
continuity constraint (§14.10 finding 18), or a different cut point — not more
lower anchors.

##### Finding 22. The seam against the other two forms: better where §14.10 was worse

`seam_pct_of_range`, and the local ratio (seam step in the subtracted trace over
the median sample-to-sample step across 1946–1966):

| File | index | §14.9 none | §14.10 three | **§14.10.1 two** | local: none / three / **two** |
|---|---|---|---|---|---|
| `...-007` | .0042 | −2.87 | **−1.58** | −1.77 | 2.2 / **1.2** / 1.3 |
| `...-008` | .0042 | −1.77 | **−0.42** | −0.76 | 1.2 / **0.1** / 0.5 |
| `...-012` | .0052 | −5.64 | **−2.52** | −2.75 | 5.3 / **1.6** / 1.9 |
| `...-027` | .0052 | −0.53 | **−0.36** | −0.73 | 0.4 / **0.2** / 0.6 |
| `...-017` | .0022 | +2.02 | +2.86 | **+1.50** | 10.7 / 14.9 / **8.0** |
| `...-021` | .0022 | +0.85 | +2.61 | **+1.13** | 9.8 / 21.9 / **11.8** |

Two anchors are a little worse than three on the post-crossing four (by 0.2–0.4
points, all still well inside the unanchored form) and **clearly better on the two
`.0022` files**, which is where three anchors had made the seam worse than doing
nothing. On `...-017` the two-anchor seam is the smallest of the three forms
outright. The regime split that has run through findings 9, 10, 15, 18 and 19
reverses here.

##### Finding 23. What two anchors give up is the middle, and on the `.0022` files the middle is the question

With no interior constraint, the lower correction is a straight line between the
endpoints and the segment's curvature is unopposed. `data(1800) − baseline(1800)`,
as % of signal range — a **probe, not an anchor** (`LOWER_MID_PROBE_CM1`):

| File | index | current | anchored | lower-only | three anchors | **two anchors** |
|---|---|---|---|---|---|---|
| `...-007` | .0042 | −0.13 | +9.82 | −0.12 | −0.76 | −1.23 |
| `...-008` | .0042 | −0.31 | +6.67 | +0.72 | −1.36 | −2.22 |
| `...-012` | .0052 | −0.18 | +15.18 | −0.18 | −0.93 | −1.52 |
| `...-027` | .0052 | +0.16 | +6.48 | +0.14 | −1.50 | −2.45 |
| `...-017` | .0022 | **−7.89** | −10.40 | −8.02 | −5.50 | −8.96 |
| `...-021` | .0022 | **−8.12** | −10.83 | −8.23 | −5.99 | −9.78 |

On the post-crossing four the cost is small: the two-anchor baseline sits 1.2–2.5%
of range above the data at 1800, against ~0% for the current baseline.

**The `.0022` column is the whole argument, and it is not what §14.10 finding 20
made it sound like.** Read the `current` column first: the existing baseline
*already* sits 7.9–8.1% of range above the data at 1800 on those files. The low
region there is a broad depression, deeper than the 1795 band's own 3.7–4.0%
peak-to-peak (§14.10 finding 16). So the three-anchor set's −5.50/−5.99 was not
"the anchor holding the middle in place" — it was the anchor pulling the baseline
**down into that depression** by ~2.4 points, on the assumption that the
depression is baseline error. The two-anchor set takes no position and leaves the
baseline ~1 point further above the data than current.

Which of those is right is unresolved and is exactly §14.3 finding 4: nothing here
distinguishes "the baseline is too high at 1800" from "there is unfitted band
intensity at 1800". §4's two low-wavenumber peaks are still the instrument that
could, and are still dormant. **The user judged the figures and the answer was
that pulling it down did not work.**

##### Finding 24. The signed-offset proxy of §14.10 finding 19 points the wrong way here, and is retired

Mean signed `raw − baseline` over 1750–1900, raw units, with the removed form
included:

| File | index | current | anchored | lower-only | three anchors | **two anchors** |
|---|---|---|---|---|---|---|
| `...-007` | .0042 | −1.04e-4 | +6.05e-4 | −1.6e-5 | −4.0e-5 | −7.2e-5 |
| `...-008` | .0042 | −2.24e-4 | +2.54e-4 | −3.3e-5 | −1.43e-4 | −1.98e-4 |
| `...-012` | .0052 | −3.4e-6 | +7.23e-4 | +2.3e-6 | −3.3e-6 | −2.98e-5 |
| `...-017` | .0022 | −3.33e-4 | −5.45e-4 | −3.51e-4 | **−1.46e-4** | −4.31e-4 |
| `...-021` | .0022 | −3.98e-4 | −6.41e-4 | −4.13e-4 | **−1.99e-4** | −5.37e-4 |
| `...-027` | .0052 | −8.19e-5 | +3.08e-4 | −7.71e-5 | −1.64e-4 | −2.19e-4 |

**On this metric the three-anchor set wins on every file, and it is the form the
user rejected.** That is not a contradiction to explain away — it is the metric
failing, and finding 23 says how. Below 1955 the bands are negative-going, so
"the subtracted trace sits nearer zero" and "the baseline has been pulled down
onto the band intensity" are *the same movement*. The metric cannot tell them
apart, and on the `.0022` files it rewards precisely the movement that was judged
wrong.

§14.10 finding 19 introduced this table as "a metric whose direction of goodness
is defensible" and read its `.0022` improvement as the first real movement in that
regime. **That reading does not survive.** The measurement stands — the offset did
halve — but it is not evidence the baseline got better, and §14.10's conclusion
and the §0 status row are corrected accordingly. Mean `|subtracted|`, which
finding 19 had already demoted, fails for the same reason and more obviously.

What this leaves: below 1955 there is **no proxy**, signed or absolute. The seam
(findings 21–22) is measurable and means what it says because it is a
discontinuity in something that should be continuous. Everything else in that
region is for the figures and for §4's peaks when they are configured.

##### Unchanged

- **Containment.** `upper_max_abs_diff` is **0.0e+00 on all eight files** with the
  two-anchor set, `height_2040` / `height_1980` identical to `anchored`, flat
  2235–2250 inherited. §14.10 finding 17 holds unchanged; the anchor count below
  the cut cannot reach above it.
- **The `...-022` gate.** Both files: cut gated at 1955, `lower_anchors_applied`
  empty, result identical to `anchored`.
- `lower_moved_pct` with two anchors: 12.78 / 11.88 / 19.64 / 10.27 on the
  post-crossing four, and **1.81 / 1.52** on the `.0022` pair — against 5.95 /
  5.60 with three. Below the cut the two-anchor baseline stays much closer to the
  full-ROI anchored one on the pre-crossing files, which is the same fact
  finding 23 reports from the other side.

##### `lower_settings` — the lower segment's parameters are now exposed

Separate change, same run. `BaselineVariant.lower_settings` overrides
`std_distribution` for the **lower segment only**; `None` — the default — keeps
the unmodified `voigt_fit.baseline` settings that every measurement in §14.8–§14.10
used, so nothing here is re-based. It requires a cut and raises without one, and an
unknown key raises at variant construction, both on `settings`' precedent.

It is exposed because that segment has a specific reason to want different values:
it is ~106 samples against the full ROI's ~259, so `half_window` and the other
sample-count settings are **~2.4× larger relative to the array** than the values
they were tuned at (§14.8's "no degenerate segments" note). Those are the knobs to
reach for first. **No value is recommended and no default is changed** — this is
the instrument, not a tuning. A commented template variant sits in `api.py`'s
`__main__`.

##### Reading the figures

`plot_baseline` now draws a reference grid — major and minor ticks on both axes,
50/10 cm⁻¹ over the full ROI and finer on a zoom (`_axes.apply_reference_grid`) —
and the legend moved below the figure, because the anchor and seam annotations had
made it wide enough to cover the top of both panels, including the flat 2235–2250
region the high-end check is read from. Judgement here is visual (§14.3 finding 4);
the figures should at least be readable.

Figures: `C:\Figures\nn1120-4_pd_ceo2_000\baseline_experiments\lower_anchored_2pt\`.

### 14.11 `std_distribution` settings, re-swept under the anchor — measured; nothing recommended

§14.3 finding 1 swept the five exposed settings and ruled tuning out. That sweep
was of the **bare** baseline: no anchors, no cut, no lower segment. Two
instruments have been built since that finding 1 could not have used — the
full-ROI anchor set (§14.7) and `lower_settings` (§14.10.1) — so the sweep was
run again on both. The headline is unchanged (**tuning does not un-halve the
bands**), but the re-run produces a quantity that does move, and a measurement
of its limit.

Runs: `C:\Figures\nn1120-4_pd_ceo2_000\baseline_experiments\std_sweep_upper\`,
`...\std_sweep_lower\`, `...\std_sweep_anchor_consistency\`. The last folder
also holds `anchor_inconsistency_sweep.{py,csv}` (28 settings × 8 judged files)
and `anchor_inconsistency_breadth.{py,csv}` (4 settings × 60 unlabelled files);
both are throwaway probes in §14.6's sense, kept beside their output rather than
promoted into the package.

#### Finding 25. The three-anchor residual is a single scalar, exactly

`apply_anchors` fits a least-squares **line** to three residuals, so the leftover
residual vector lives in the 1-dimensional orthogonal complement of a
2-parameter fit on 3 points. Its *direction* is fixed by the anchor wavenumbers
alone; only its magnitude varies with the file and the settings. Normalised to
the residual at 1955, that direction is

> `(r2240, r2006, r1955) ∝ (+0.217949, −1.217949, +1)`

analytically, from `(2240, 2006, 1955)`. Measured across 174 (file, settings)
pairs the two ratios have standard deviation **0.000000** — the same to machine
precision in every row. The "0.4–3.2% of signal range" spread §14.7 reports as
three numbers is therefore one number seen three times.

Call it the **anchor inconsistency**, reported as `r1955`: the part of the
baseline's error at the three anchors that is *not* affine, and so is the part
anchoring cannot remove. It is zero exactly when the three residuals are
collinear in wavenumber.

**It is not a quality score.** §14.3 finding 4 applies to it directly: a
baseline whose error happens to be collinear at three chosen points can be wrong
everywhere between them. What it is defensibly a measure of is (a) anchor
self-consistency and (b), via §14.10.1 finding 21, the seam.

#### Finding 26. `lower_settings` cannot move the seam — predicted, then confirmed

Stated before the run, from finding 21: with two lower anchors the lower
baseline hits `anchor_data_value(1955)` exactly whatever the lower segment's
parameters are, so `seam_pct_of_range` must be invariant under `lower_settings`.
Eight variants (`half_window` 4/6/15, all three sample-count knobs ×0.4,
`num_std` 1.4/2.0, against the §14.10.1 reference), `std_sweep_lower`:

| file | index | ref | spread across all 8 |
|---|---|---|---|
| `...-007` | .0042 | −1.770 | −1.748 … −1.774 |
| `...-008` | .0042 | −0.760 | −0.728 … −0.762 |
| `...-012` | .0052 | −2.748 | −2.718 … −2.753 |
| `...-017` | .0022 | +1.495 | +1.494 … +1.498 |
| `...-021` | .0022 | +1.129 | +1.129 … +1.140 |
| `...-027` | .0052 | −0.729 | −0.711 … −0.727 |

Spread ≤ 0.035% of range — the ~1.4 cm⁻¹ sub-sample term, not the parameters.
`upper_max_abs_diff` is **0.0e+00 on all 8 files × all 8 variants**, and no
variant went degenerate, including `half_window 4` on the ~106-sample segment.
So `lower_settings` is confirmed as an instrument that reaches only the interior
of the lower segment — the region §14.10.1 finding 24 left with no proxy at all.
**Nothing in this sweep can be scored, and none of it is recommended.**

The one visible movement is the 1800 probe on the `.0022` pair, where
`lower_settings={"half_window": 15}` takes it from −8.96/−9.78 to **−2.88/−3.68**
% of range. That is the largest movement anything has produced in that regime —
and it is the *same direction* as the three-anchor set of §14.10, i.e. pulling
the baseline down onto the low-wavenumber depression, which is what the user
judged wrong. Finding 24 already says why the number cannot tell the two apart.
Recorded so it is not rediscovered as a result.

#### Finding 27. Under the anchor, tuning halves the anchor inconsistency

28 settings combinations, judged files, `anchor_inconsistency_sweep.csv`. Mean
|`r1955`| over the six bad files (the `...-022` pair is excluded — 1955 is gated
there, so the number is a miss, not a residual):

| settings | mean \|r1955\|, % of range |
|---|---|
| current (`num_std` 1.1, `half_window` 10) | 1.417 |
| `num_std` 2.5 + `half_window` 20 | **0.690** |
| `num_std` 2.5 + `half_window` 15 | 0.715 |
| `num_std` 2.0 + `half_window` 20 | 0.798 |
| `num_std` 2.5 | 0.970 |
| `half_window` 20 alone | 1.611 |
| `half_window` 30 alone | 1.778 |

`num_std` upward and `half_window` upward only help **together**; each alone is
neutral-to-worse. `interp_half_window`, `fill_half_window` and
`smooth_half_window` move it by <0.05 and are as inert here as finding 1 found
them. `num_std 0.8` produced a degenerate baseline on `...-008` and is out.

#### Finding 28. The seam halves — and then hits a floor the inconsistency does not

Measured end to end in `std_sweep_anchor_consistency`: the §14.10.1 form with
`settings={"num_std": 2.5, "half_window": 20}` on the **upper** side.
`seam_pct_of_range`, and finding 21's prediction beside it:

| file | index | seam ref | seam new | predicted new | gap |
|---|---|---|---|---|---|
| `...-007` | .0042 | −1.770 | **+0.116** | +0.249 | −0.133 |
| `...-008` | .0042 | −0.760 | **−0.378** | −0.294 | −0.084 |
| `...-012` | .0052 | −2.748 | **−0.661** | −0.480 | −0.181 |
| `...-017` | .0022 | +1.495 | **+1.074** | +1.067 | +0.007 |
| `...-021` | .0022 | +1.129 | **+1.013** | +1.034 | −0.022 |
| `...-027` | .0052 | −0.729 | −0.987 | −1.016 | +0.029 |

Mean |seam| **1.439 → 0.705**; smaller on five of six, larger on `...-027`.
`upper_max_abs_diff` stays 0.0e+00 everywhere and nothing went degenerate.

**But read the gap column.** Under the current settings it was 0.013–0.056
(§14.10.1 finding 21). Here it reaches **0.181**, and the three files where it
blew out are exactly the three where the inconsistency got smallest. That term
is the sub-sample slope difference across the ~1.4 cm⁻¹ between the anchor and
the segment's top sample, and **it does not shrink with `r1955`**. So the seam
does not go to zero as the inconsistency does — it floors at ~0.03–0.18% of
range, and `...-007`'s −1.770 → +0.116 is partly the sign passing through zero,
not a clean 15× scaling. That floor is the limit on what upper-side tuning can
buy, and it is the honest form of "the seam halves".

#### Finding 29. The primary symptom is slightly worse, and the movement roughly doubles

§14.1 constraint 2 names the halved 2040 and 1980 bands as the failure, and
`height_*_x_ref` is the arm where "better" is defensible. Under `ns2.5 hw20`
(unsplit anchored form; the lower-split twin is identical above the cut):

| file | index | 2040 anchored → new | 1980 anchored → new | moved_pct anchored → new |
|---|---|---|---|---|
| `...-007` | .0042 | 1.43 → 1.40 | 1.71 → **2.33** | 11.0 → 18.2 |
| `...-008` | .0042 | 1.23 → 1.17 | 1.21 → **1.44** | 7.7 → 20.7 |
| `...-012` | .0052 | 2.05 → 1.85 | (ref ≤ 0) | 17.0 → 12.8 |
| `...-027` | .0052 | 1.66 → **2.17** | 1.21 → 1.27 | 6.9 → 14.2 |
| `...-017` | .0022 | 0.98 → 0.93 | 0.44 → 0.50 | 2.9 → 5.9 |
| `...-021` | .0022 | 0.99 → 1.01 | 0.23 → **0.08** | 3.2 → 5.9 |

2040 recovery goes **down** on three of the four post-crossing files and up only
on `...-027`; 1980 improves on three and collapses on `...-021`. The baseline
also moves 1.5–2.7× further from `current` than the anchored form does, on files
nobody has looked at yet. **The metric §14.1 makes primary argues against the
candidate the inconsistency sweep found.** That is not resolved by promoting the
metric that agrees — it is finding 4 again, wearing a new hat.

Noted without a claim: on the `...-022` gate `moved_pct` drops 34.4 → 18.6
(.0022) and 13.9 → 13.3 (.0042). "Moves less from current" only counts if
current is right there, and §14.2 withdrew that label.

#### Finding 30. The breadth check disagrees with the judged six, and prefers the other candidate

60 unlabelled `delta10` files from the same dataset, 51 with 1955 ungated
(`anchor_inconsistency_breadth_60files.csv`):

| settings | mean \|r1955\| | median | max | smaller than current on |
|---|---|---|---|---|
| current | 2.421 | 2.147 | 9.651 | — |
| `ns2.5 hw15` | **1.607** | 1.201 | 9.586 | **37/51** |
| `ns2.5 hw20` | 1.700 | **1.079** | 9.611 | 32/51 |
| `ns2.0 hw20` | 1.795 | 1.355 | 9.548 | 31/51 |

The judged-six argmin (`hw20`) has the **weaker** independent evidence: 32/51 is
not distinguishable from chance, 37/51 is. That is what picking an argmin over
28 candidates on 6 files is expected to do. `ns2.5 hw15` also leaves the
2235–2250 flat check slightly *better* than current (mean 5.98e-5 vs 6.77e-5;
`hw20` ≈ current at 6.81e-5, worst file 4.6e-4 against current's 4.2e-4 — same
order, 20× below §14.7's 1.5e-3 failure). No degenerate baseline in 240 rows.

And the **max is unchanged** across all four settings, 9.65 → 9.55–9.61: whatever
makes the worst files worst is not a `std_distribution` parameter.

#### What this settles, and what it does not

- **Settled:** the three anchor residuals are one scalar (25); `lower_settings`
  cannot reach the seam (26); tuning under the anchor halves that scalar on the
  judged files (27) and improves it on a majority, not all, of a wider sample
  (30).
- **Settled against:** finding 1's headline survives — no setting un-halves the
  bands, and the best candidate on the inconsistency makes 2040 slightly worse
  (29).
- **Not settled:** whether any of this is an improvement. The seam is real and
  smaller; the band heights are real and slightly worse; the two samples rank the
  candidates differently. **Judgement is visual (§14.3 finding 4) and has not
  been made.** No value is recommended, no default is changed, `voigt_fit.baseline`
  is untouched, and everything here is offline.
- **Next, if this is picked up:** the seam floor of finding 28 says upper-side
  tuning is nearly spent as a way to shrink the seam; a continuity constraint at
  the cut (§14.10 finding 18) is the remaining lever. And `r1955` is cheap enough
  to promote to a column on the comparison table if it is going to be used — it
  is currently computed only in the scratch scripts beside the run output.

### 14.12 A different algorithm below the cut — built, measured, and the first thing to satisfy all three stated targets

Everything in §14.3 through §14.11 varied `std_distribution`'s *parameters*, the
anchors, or where the cut goes. **None of it varied the algorithm.** This
section does, on the lower segment only, and it is the first form in §14 that
moves the pre-crossing `.0022` regime in a direction the figures accept.

**The scope is the user's, this session**, and is narrower than it looks:

- The full-ROI three-anchor baseline of §14.7 **stays** — *"the upper baseline
  regime is fine, the one with 3 anchor points."* Nothing here touches it.
- The 1955 cut **stays**; `lower_anchors` **go**. Below the cut the baseline is
  whatever the algorithm produces, with no affine correction on top — *"no rules
  or guardrail tricks. Strictly pybaselines and other methods."* That rules out
  a fix built from anchors, offsets or clamps below 1955, and finding 31
  explains why the data itself already ruled them out.
- **Do not overfit**: acceptance is the judged eight *and* the 60-file breadth
  sample of §14.11, not the two files named.

#### The three targets, and the proxy §14.10.1 finding 24 said did not exist

Finding 24 retired every metric below 1955 and left only the seam. The user's
three statements restore three, because they are statements about where the
baseline should *be*, not inferences from where it ended up:

| column | definition | target | applies to |
|---|---|---|---|
| `mid` | `baseline(1850) − (data(trough) + data(peak))/2`, where trough/peak are the extrema in 1866–1838; % of range | **0** on post-crossing files | the dispersive ~1850 feature |

**`mid` is interpolated, not sampled.** The grid step is ~1.93 cm⁻¹ and no sample
lands on 1850 — the nearest are 1851.3 and 1849.4 — so `baseline(1850)` is a
linear interpolation between them, on the steepest part of a dispersive feature.
Same sub-sample caveat §14.10 finding 20 raised for the anchor at 1955, and the
first thing to check if the post-crossing `mid` column ever looks stubborn. The
trough and peak themselves are sampled, so the target is exact.
| `und` | `max(baseline − data)` over 1885–1840, % of range | **0**, from below | the 1850 and 1870–1880 bands |
| `int` | `mean(data − baseline)` over **1838–1750**, % of range | **0** | every file |

`mid`'s target comes from *"[the baseline at 1850] should be as close [as
possible to] the halfway point between the trough at around 1855 and the peak at
1845"* on `...-007_delta10.0042`. `und`'s from *"[`...-021_delta10.0022`] has a
nice peak centered at 1850 and 1870-1880. The baseline should run under the base
of those peaks."* `int`'s from *"I do not see many features beyond 1850 to the
terminal 1750, so the integral from 1860 or so to 1750 should be close to zero."*

**Two readings had to be fixed before these were usable**, both confirmed with
the user:

1. **The window is 1838–1750, and the ¹³CO bands are counted in, not masked.**
   The user picked "1838–1750, bands excluded" and then wrote *"Include the bands
   at 1795/1775. There is a reason these are no longer in production.
   Unnecessary. They will get deleted later."* Read as: exclude the 1850 feature
   at the top of the window (hence 1838, not 1860), and do **not** treat
   1795/1775 as signal to be preserved. §4's two dormant peaks are, on that
   reading, not coming back.
2. **`mid` at 1850 is a diagnostic, not a rule about what is baseline.** The user
   chose *"it is a real band, centre is coincidence"* and added *"there is a
   physical reason they have opposite signs."* So do **not** generalise it to
   "the baseline passes through the centre of any dispersive feature".

**This window is not §14.10.1 finding 24's trap.** That metric was signed over
1900–1750, which contains the 1850 feature, so pulling the baseline down onto a
negative-going band improved it. 1838–1750 excludes that feature, and the
candidate below lands **positive** (+0.04 to +1.11), i.e. sitting *above* the
data — so it is not eating the bands there. The metric can still be gamed by any
baseline that simply hugs the data; see finding 33.

#### Finding 31. The two named files want opposite signs at 1850, which is what rules the families out

Read off the raw spectra before anything was fitted, as % of signal range:

| file | regime | features in 1866–1838 | data @1850 | user's target | target − data |
|---|---|---|---|---|---|
| `...-007` `.0042` | post | trough 1853.3 = 57.3, peak 1843.6 = 65.8 | 58.4 | midpoint **61.5** | **+3.1** |
| `...-021` `.0022` | pre | peak 1849.4 = 18.9, flanks 1864.8 = 9.4 / 1834 = 10.1 | 18.9 | under the base **≈9.5** | **−9.4** |

Same wavenumber, opposite sign, 12.5 points apart — and the amplitudes do not
discriminate, 8.5% peak-to-peak against 9.5%. The discriminator is **local
shape**: dispersive/antisymmetric on the post-crossing file, a symmetric
positive band on the pre-crossing one.

Three consequences, and they are the whole design:

- **No fixed anchor, offset, tilt or line below 1955 can satisfy both.** This is
  the measurement behind "no guardrail tricks", not a preference.
- **A pure lower-envelope method fails the post-crossing files**, because it
  settles on the 1853 trough rather than the midpoint ~4.5% above it.
- **A pure centre-line method fails the pre-crossing files**, because it runs
  through the middle of the 1850 band instead of under it.

Both predictions were checked, not assumed — see finding 33's `irsqr` row.

On `...-021` the base is a real line, not an idea: the data at 1888 (8.03%),
1864.8 (9.41%) and 1838 (11.09%) are collinear to 0.04 points, so "under the
base of those peaks" names a baseline that touches at three places.

#### Finding 32. 44 methods at their defaults; `pspline_arpls` is the only one that clears all three

Every `pybaselines.Baseline` method that runs on a 106-sample segment was tried
on the lower segment with the upper side held at §14.7's anchored baseline —
classification, Whittaker, polynomial, morphological, smoothing, spline and
misc families. Judged six (the two `...-022` files are gated, finding 34):

| form | post \|mid\| mean | pre \|mid − target\| mean | pre `und` max | \|int\| max | \|int\| mean | \|seam\| max |
|---|---|---|---|---|---|---|
| `anchored`, no cut (§14.7) | 5.34 | 7.32 | 6.15 | 14.51 | 8.46 | — |
| lower split, no anchors (§14.9) | 1.43 | 5.40 | 4.33 | 6.10 | 2.55 | 5.64 |
| + lower anchors (§14.10.1, today's default) | 2.38 | 6.28 | 5.13 | 7.71 | 4.38 | **2.75** |
| **`pspline_arpls`, defaults** | **0.54** | **0.27** | **0.79** | **1.11** | **0.43** | 4.26 |

(`pre target` is `−(peak − trough)/2`: what `mid` reads when the baseline sits on
the flanking trough, which is what "under the base" means in `mid`'s units.)

Per file, the forms that matter:

| file | form | `mid` | target | `und` | `int` | `seam` |
|---|---|---|---|---|---|---|
| `...-007` `.0042` | current | +3.93 | 0 | +8.07 | −1.15 | — |
| | + lower anchors | +1.42 | 0 | +5.46 | −2.01 | −1.77 |
| | **`pspline_arpls`** | **−0.17** | 0 | +3.82 | **+0.14** | −2.41 |
| `...-008` `.0042` | current | +5.96 | 0 | +11.52 | −2.06 | — |
| | + lower anchors | +2.63 | 0 | +8.04 | −3.72 | −0.76 |
| | **`pspline_arpls`** | **−1.24** | 0 | +4.14 | **+0.37** | −1.92 |
| `...-012` `.0052` | current | +0.76 | 0 | +4.16 | −1.03 | — |
| | + lower anchors | +0.72 | 0 | +4.03 | −2.52 | −2.75 |
| | **`pspline_arpls`** | **+0.26** | 0 | +3.69 | **+1.11** | −4.26 |
| `...-017` `.0022` | current | +0.35 | −4.23 | +3.17 | −5.57 | — |
| | + lower anchors | +1.42 | −4.23 | +4.24 | −6.65 | +1.49 |
| | **`pspline_arpls`** | **−4.41** | −4.23 | **+0.79** | **+0.04** | +1.74 |
| `...-021` `.0022` | current | +0.97 | −4.76 | +4.08 | −6.00 | — |
| | + lower anchors | +2.14 | −4.76 | +5.13 | −7.71 | +1.13 |
| | **`pspline_arpls`** | **−4.41** | −4.76 | **+0.21** | **+0.18** | +1.03 |
| `...-027` `.0052` | current | +2.60 | 0 | +6.89 | −0.94 | — |
| | + lower anchors | +4.76 | 0 | +9.01 | −3.69 | −0.73 |
| | **`pspline_arpls`** | **−0.50** | 0 | +3.72 | **+0.76** | −1.33 |

**The `.0022` files are the result.** Four sections have been a no-op there
(findings 9, 10, 15) or moved them the wrong way (finding 23). `und` goes from
+4.1/+3.2 — the baseline cutting 3–4% of range *into* the 1850 band — to
+0.2/+0.8, which is touching its foot. `int` goes from −6.0/−5.6 to +0.2/+0.0.
`mid` lands at −4.41 against targets of −4.76 and −4.23, i.e. within 0.35 points
of sitting exactly on the flanking trough.

**Every parameter variant tried was worse on at least one target.** `lam` 1e2,
3e2, 3e3, 1e4, 1e5; `num_knots` 25, 50, 200; `diff_order` 2, 3. `lam=1e2` halves
the seam and doubles the post `mid` error; `num_knots=200` wins the breadth
column and quadruples post `mid`. Nothing here is at a tuned point — the
defaults *are* the argmin over the parameters tried, which is the
anti-overfitting evidence §14.11 finding 30 says to look for, and not a reason
to stop looking.

The near-misses, worth knowing because they say what the shape discriminator is
made of: `dietrich` and `fabc lam1e3` get post `mid` to 0.25/0.27 — better than
`pspline_arpls` — and fail the pre-crossing files at `und` +3.40/+2.72, cutting
straight through the 1850 band. `loess` is the seam's best showing (max 2.00)
and is second on everything else. `rolling_ball` is close on `mid` and `und` and
fails `int` at 6.07.

#### Finding 33. `int` alone is not a quality score — `irsqr` is the worked case

`irsqr` scores `int` 0.02 mean, 0.08 max on the judged six — the best of the 44,
20× better than `pspline_arpls` — and its `und` is 0.00 on both `.0022` files.
It is also **wrong**: it is a strict lower envelope, so its pre `|mid − target|`
is **8.94**, meaning it sits ~9% of range *below* the base it should be touching,
and its post `|mid|` is 2.78. `corner_cutting`, `pspline_derpsalsa` and
`pspline_mpls` fail the same way.

This is finding 31's prediction landing exactly where it was pointed, and it is
why the three columns are reported together and never summed. Any baseline that
hugs the data from below tops the `int` and `und` columns; only `mid` objects.

#### Finding 34. Containment and the gate are unchanged — verified, not inherited

- `upper_max_abs_diff` is **0.0e+00** on all eight judged files and on all 51
  ungated breadth files. Above the cut this is §14.7 bit for bit, so
  `height_2040` / `height_1980` are identical to `anchored` on every file and all
  of §14.7 finding 9's band recovery is intact. The check can still fail:
  `lower_method` is deliberately **not** part of `_recipe_key`, exactly as
  `lower_anchors` is not, so `anchored` stays the zero-diff twin.
- **Both `...-022` files are gated at 1955** (bands at 1942 and 1969), so no
  lower segment is built, no method runs, `lower_method` comes back blank and the
  result is `anchored` exactly. Nothing in this section reaches them, by design.
- `lower_moved_pct` on the `.0022` pair is **10.6 / 11.2**, against 1.8 / 1.5 for
  the two-anchor form. That is the size of the change below the cut on the regime
  four sections could not move.

#### Finding 35. Breadth on the 60-file sample — a non-regression check, and only that

Same sample as §14.11, 51 ungated. Only `int` and the seam are defined without a
regime label, so `mid` and `und` are not reported here.

| form | mean \|int\| | median | max | \|seam\| max | smaller \|int\| than today's default on |
|---|---|---|---|---|---|
| `anchored`, no cut | 20.40 | 9.42 | 74.29 | — | 13/51 |
| lower split, no anchors | 2.13 | 1.32 | 7.36 | 15.50 | 39/51 |
| + lower anchors (today) | 3.38 | 2.33 | 10.98 | 9.60 | — |
| **`pspline_arpls`** | **0.95** | **0.45** | **4.48** | 12.02 | **45/51** |
| `loess` | 1.29 | 0.38 | 17.65 | 11.22 | 43/51 |

**Read this as constraint 1 (§14.1) and nothing more** — "this does not break the
files that already work". It is *not* evidence that `pspline_arpls` is the best
method, because finding 33 shows `int` on its own ranks a wrong baseline first,
and on unlabelled files there is no `mid` to object. §14.10 finding 19 was
over-read in exactly this way; this row is the same shape of number.

No non-finite or constant baseline in 204 rows, and no method failure. **That is
a weaker statement than the identically-shaped sentence in §14.11**, which rested
on `std_distribution`'s own *"no baseline points found"* verdict; a direct
`pybaselines` call emits no such warning, so this is the structural check only
(see the last bullet below).

#### Finding 36. The cost is the seam, which no longer has anything holding it

| form | judged six \|seam\| max | breadth 51 \|seam\| max |
|---|---|---|
| + lower anchors (today's default) | 2.75 | 9.60 |
| **`pspline_arpls`** | **4.26** | **12.02** |
| lower split, no anchors (§14.9) | 5.64 | 15.50 |

~1.5× the two-anchor form on both samples, consistently, and this is the one
quantity §14.10.1 finding 24 kept — it is a discontinuity in something that
should be continuous, so it means what it says. It lands **between** the two
existing forms rather than outside them, and it is the direct and expected price
of "anchors go": §14.10.1 finding 21 proved the seam is fixed by the anchor at
the cut, so removing that anchor gives the control up.

The remaining lever is the one §14.10 finding 18 named and nobody has built: a
**continuity constraint** pinning the lower baseline to the *upper baseline's
value* at 1955 rather than to the data. That is not an anchor — it constrains the
lower curve against the upper curve, not against the spectrum — so it survives
"no guardrail tricks" on a reading that should be confirmed before it is built.
It would zero the seam by construction and give up the property that both
segments are fitted to the data alone.

#### What the figures show

As read by the author of this section, **not** as a user judgement. Run
`lower_pspline_arpls`, five variants, all eight judged files.

- `...-007` (.0042): below 1955 the baseline passes through the middle of the
  1853/1843 kink rather than under it, and the subtracted trace over 1838–1750
  sits on zero where `anchored` had it floating at +0.0008. No new wiggle appears
  elsewhere in the segment.
- `...-021` (.0022): the change is the whole point. The bands at 1850 and
  ~1876 now stand **above** a baseline running under their feet — in the
  subtracted trace they read +0.0009 and +0.0004 against a flat zero — where
  every other form runs through them and leaves 1838–1750 sitting at −0.0010.
- `...-012` (.0052) is where to look for the cost: below ~1790 the spline
  flattens while the data rises to the ROI floor, leaving the subtracted trace
  at +0.0005 at 1750. That is this file's `int` of +1.11, the largest of the six,
  and it is the end behaviour of an unanchored spline at the array edge.

#### What this settles, and what it does not

- **Settled:** the two regimes want opposite signs at 1850, so no fixed
  correction below 1955 can serve both (31); `pspline_arpls` at its defaults is
  the only method of 44 that clears all three stated targets, and its parameter
  variants are all worse (32); `int` alone ranks a wrong baseline first (33);
  containment above the cut and the `...-022` gate are untouched (34).
- **Settled against:** the lower segment's problem was never a
  `std_distribution` parameter — §14.3 finding 1 and §14.11 both looked in the
  only place they could, and the algorithm was the knob.
- **Not settled:** whether the seam cost is acceptable (36); whether the
  continuity constraint should be built; and **whether the `.0022` depression
  below 1838 was baseline error at all** — the `int ≈ 0` answer asserts it was,
  and §4's dormant peaks, the instrument that could have tested it
  independently, are on their way out by the same answer.
- **Unchanged:** no default moved. `lower_method` is `None` unless a variant asks
  for it, `LOWER_ANCHOR_POINTS_CM1` is still `(1955, 1750)`, `voigt_fit.baseline`
  is untouched, and everything here is offline.
- **The degenerate flag is weaker under `lower_method`.** `std_distribution`'s
  *"no baseline points found"* warning has no analogue in a direct `pybaselines`
  call, so the `"lower"` entry rests on a structural check (non-finite or
  constant) and `BaselineOutcome.lower_method_degeneracy_checked` comes back
  False to say so. A flag that is clean for want of anyone asking reads exactly
  like one that was checked.

Figures: `C:\Figures\nn1120-4_pd_ceo2_000\baseline_experiments\lower_pspline_arpls\`. That folder also holds the
throwaway probes the tables come from -- `method_sweep_44.py` (finding 32's
44 methods), `method_sweep_judged.py` (the parameter sweep),
`method_breadth_60files.py` with `breadth_files.txt` (finding 35), and
`per_file_table.py` -- kept beside their output rather than promoted into the
package, on section 14.11's precedent.

### 14.13 The lower segment tied off at 1800 — built and measured; the cost moved rather than went away

Section 14.12's figures faulted one thing and it was not the method: on
`...-012_delta10.0052` the spline flattened below ~1790 while the data climbed
to the ROI floor. That is **end behaviour at an array edge**, not a statement
about the spectrum — `create_baseline` and a `pybaselines` method alike see only
the array handed to them (§0) — and the lower segment's lowest wavenumber had
been 1750 in every section since 14.9 because nobody had chosen it.

**The scope is the user's:** *"tighten the data range. Tie it off at 1800, not
1750, for the second baseline only."* The full-ROI anchored baseline of §14.7 is
untouched, the 1955 cut is untouched, and the ROI itself is still 2250–1750 —
only the second baseline's own array is shortened, to 1955–1800.

`BaselineVariant.lower_floor_cm1` (default `None` — nothing here moved a
default; see `LOWER_FLOOR_POINT_CM1`). Below the floor **the anchored full-ROI
baseline stands**, because the splice simply stops reaching there. That is not a
fill rule invented for this section — it is the same curve a gated cut falls
back to, the one already in the array, which is the only option that survives
*"no rules or guardrail tricks"*. Its price is a second interface, at the floor,
reported separately as `floor_seam_pct_of_range`.

#### Finding 37. Over the region it fits, the floor removes the artefact outright

`int` is the mean residual `data − baseline`, % of range. It is reported twice
because under a floor the user's window 1838–1750 **straddles two baselines**:
`int` over 1838–1750 is no longer a statement about the fitted segment, and
`int>fl` over 1838–1800 is.

| file | form | `mid` | target | `und` | `int` 1838–1750 | `int>fl` 1838–1800 | seam @1955 | seam @1800 |
|---|---|---|---|---|---|---|---|---|
| `...-007` `.0042` | pspline 1750 | −0.17 | 0 | +3.82 | +0.14 | +0.52 | −2.41 | — |
| | **floor 1800** | −0.92 | 0 | **+3.03** | +5.11 | **+0.18** | **−1.78** | +10.62 |
| `...-008` `.0042` | pspline 1750 | −1.24 | 0 | +4.14 | +0.37 | +0.46 | −1.92 | — |
| | **floor 1800** | −2.07 | 0 | **+3.26** | +3.15 | **+0.22** | **−1.28** | +6.58 |
| `...-012` `.0052` | pspline 1750 | +0.26 | 0 | +3.69 | +1.11 | +0.45 | −4.26 | — |
| | **floor 1800** | −0.54 | 0 | **+2.89** | +8.12 | **+0.19** | **−3.54** | +16.62 |
| `...-017` `.0022` | pspline 1750 | −4.41 | −4.23 | +0.79 | +0.04 | +0.12 | +1.74 | — |
| | **floor 1800** | **−4.12** | −4.23 | **+0.71** | −3.90 | **+0.06** | +1.86 | −11.25 |
| `...-021` `.0022` | pspline 1750 | −4.41 | −4.76 | +0.21 | +0.18 | +0.09 | +1.03 | — |
| | **floor 1800** | **−4.40** | −4.76 | **+0.08** | −4.20 | **+0.21** | **+0.97** | −12.21 |
| `...-027` `.0052` | pspline 1750 | −0.50 | 0 | +3.72 | +0.76 | +0.35 | −1.33 | — |
| | **floor 1800** | −1.03 | 0 | **+3.17** | +3.03 | **+0.20** | **−0.47** | +6.50 |

| form | post \|mid\| | pre \|mid − target\| | `und` max | \|`int>fl`\| max | \|seam\| max |
|---|---|---|---|---|---|
| `anchored`, no cut (§14.7) | 5.34 | 7.32 | 6.15 | 8.94 | — |
| pspline_arpls to 1750 (§14.12) | **0.54** | 0.27 | 4.14 | 0.52 | 4.26 |
| **pspline_arpls, floor 1800** | 1.14 | **0.23** | **3.26** | **0.22** | **3.54** |

`int>fl` more than halves and its spread collapses — 0.06 to 0.22 across all six
against 0.09 to 0.52 — which is the artefact leaving: the largest residual of the
judged six was `...-012`'s +1.11, and over the region now fitted it is +0.19.
`und` improves on every file and the cut seam on five of six. **The one column
that gets worse is post `mid`**, 0.54 → 1.14, because dropping 26 samples of
lever arm lets the spline sit a little lower at 1850; it is still an order below
`anchored`'s 5.34, and the pre-crossing side improves slightly.

#### Finding 38. The method ranking was re-derived, not inherited — and does not move

The same 44 methods of finding 32, re-run on the floored segment (80 samples,
not 106) and scored on all six ungated judged files rather than the two named
ones. `pspline_arpls` still clears all three stated targets, and **two methods
that did not clear them at 1750 now do**:

| method (floor 1800) | post \|mid\| | pre \|d\| | `und` max | \|`int>fl`\| max | \|seam\| max |
|---|---|---|---|---|---|
| `mixture_model` | 1.07 | 0.38 | 3.40 | 0.36 | **2.05** |
| `cwt_br` | 1.09 | 0.98 | 3.32 | 0.50 | 6.48 |
| **`pspline_arpls`** | 1.14 | **0.23** | **3.26** | **0.22** | 3.54 |
| `std_distribution` (the incumbent) | 1.43 | 0.48 | 7.25 | 0.54 | 5.64 |
| `irsqr` | 2.77 | **8.94** | 0.00 | 0.00 | 2.45 |

Three things worth reading off it. `irsqr` fails exactly as finding 33 predicted,
on a floored segment as on an unfloored one — near-perfect `int` and `und`, 8.94
on `mid`, the strict lower envelope again — so **the floor did not retire finding
33's warning**. `std_distribution`, the thing all of §14.3–§14.11 was tuning,
improves markedly under the floor alone and still does not clear `und` at 7.25.
And `mixture_model` is now the seam's best showing among the three that clear,
2.05 against `pspline_arpls`'s 3.54 — it is left commented out in `api.py`'s
variant list rather than recommended, because the visual call on it has not been
made.

#### Finding 39. Containment, the gate and the anchor path are unchanged — verified

- `upper_max_abs_diff` is **0.0e+00** on all eight judged files. The floor is
  below the cut, so it cannot reach above it, and the `anchored` twin is still
  bit-for-bit — `height_2040` / `height_1980` are untouched and all of §14.7
  finding 9's band recovery is intact.
- **Below the floor is 0.0 against `anchored` too**, asserted per file in the
  probe rather than argued: the splice does not write there.
- **Both `...-022` files are still gated at 1955**, so no lower segment exists,
  no floor is applied, `lower_floor` comes back blank and `lower_moved_pct` is
  0.000000. Nothing here reaches them, as in 14.12.
- `lower_floor_cm1` is **not** part of `_recipe_key`, on `lower_method`'s and
  `lower_anchors`' precedent, so `anchored` stays the zero-diff twin.
- A lower anchor below the floor now raises rather than being silently fitted on
  an array that stops above it. `LOWER_ANCHOR_POINTS_CM1` ends at the ROI floor,
  so the default pair and a floor are deliberately incompatible.

#### Finding 40. The cost did not go away — it moved to 1800, and it is the largest in §14

| file | seam @1955 | **seam @1800** |
|---|---|---|
| `...-007` `.0042` | −1.78 | **+10.62** |
| `...-008` `.0042` | −1.28 | **+6.58** |
| `...-012` `.0052` | −3.54 | **+16.62** |
| `...-017` `.0022` | +1.86 | **−11.25** |
| `...-021` `.0022` | +0.97 | **−12.21** |
| `...-027` `.0052` | −0.47 | **+6.50** |

6.5 to 16.6% of range, against 2.75 for the two-anchor form and 4.26 for §14.12
— **bigger than any seam measured anywhere in §14** — and it is the reason `int`
over the user's own 1838–1750 window gets *worse* (+0.14 → +5.11 on `...-007`,
+1.11 → +8.12 on `...-012`).

**This is not a property of the method.** The sweep's floor-jump column sits at
11.6–17.5% for nearly all 44 methods, because the jump measures the gap between
whatever was fitted above 1800 and the **anchored baseline below it** — and
§14.12 finding 32 already measured that curve as 6 to 14% off down there. The
floor did not create the error; it made it visible by removing the curve that
was papering over it.

Two ways to close it, neither built and neither free:

1. **Take 1750–1800 out of the ROI**, so there is nothing below the floor to
   disagree with. Clean, and it is where the user's own reading points — the
   1795/1775 bands *are* below the floor, and *"there is a reason these are no
   longer in production"*. It is **not** a no-op on the rest, though:
   `create_baseline` classifies globally, so a window of 2250–1800 changes the
   full-ROI baseline **everywhere, including above 1955** (§0's second trap), and
   §14.7's containment guarantee would have to be re-established rather than
   inherited.
2. **Run the lower method over the full 1955–1750 and use it only above the
   floor** — the fit sees the ROI edge again, which is the artefact this section
   removed, so this trades finding 37 back for finding 40.

#### What the figures show

Author's read, not a user judgement. `lower_floor_1800`, six variants, all eight
judged files.

- `...-012` (.0052), the file this was for: the flattening is gone. The baseline
  tracks the data down to 1800 and the subtracted trace sits on zero from ~1900
  to the floor, where §14.12 had it drifting to +0.0005. At 1800 it steps to
  +0.0008 and follows the anchored curve to 1750.
- `...-021` (.0022): everything §14.12 won is kept — the 1850 and ~1876 bands
  still stand above a baseline running under their feet, +0.0009 and +0.0004
  against a flat zero — and 1838–1800 is now flat on zero rather than drifting
  low. The step at 1800 is −1.2e-03, the largest of the six in raw units.
- The floor is drawn as a dotted purple line and the cut as dash-dot, on both
  panels of every figure, so the two interfaces are not read as one.

#### What this settles, and what it does not

- **Settled:** the `...-012` residual was the array edge and not the spectrum —
  over the fitted region it drops from +1.11 to +0.19, and every file's
  `int>fl` lands inside ±0.22 (37); the method ranking survives the change of
  array, with two additions (38); containment, the `...-022` gate and the
  `anchored` twin are untouched, asserted rather than assumed (39).
- **Not settled — and this is the open question now:** what happens below 1800.
  The anchored baseline standing there is the only choice that adds no rule, and
  it costs the largest discontinuity in §14 (40). **Whether that matters is a
  question about the analysis, not about the baseline**: if 1750–1800 is leaving
  the ROI along with the 1795/1775 bands, the jump sits in a region nobody reads
  and the answer is option 1. That call has not been made.
- **Also not settled:** `mixture_model` vs `pspline_arpls` under the floor (38)
  — the former has a 40% smaller cut seam and is marginally worse on `mid` and
  `int`; and everything §14.12 left open, including the continuity constraint of
  its finding 36, which this section does not touch.
- **Unchanged:** no default moved. `lower_floor_cm1` is `None` unless a variant
  asks for it, `LOWER_METHOD_CANDIDATE` is still `pspline_arpls`,
  `LOWER_ANCHOR_POINTS_CM1` is still `(1955, 1750)`, `voigt_fit.baseline` is
  untouched, and everything here is offline.

Figures: `C:\Figures\nn1120-4_pd_ceo2_000\baseline_experiments\lower_floor_1800\`,
with the probes beside them — `floor_per_file_table.py` (findings 37 and 40) and
`method_sweep_floored.py` (finding 38, which imports finding 32's own
`CANDIDATES` list rather than restating it).

#### 14.13.1 Removed on the figures — the user's call

*"i don't want the splice. remove it from consideration. only plot the black,
blue, green, orange."* Read against the figure those colours are in: raw,
`current`, `anchored`, `lower split 1955`. So the variants now **off** in
`api.py`'s `__main__` are the lower anchors of §14.10.1, the `pspline_arpls` of
§14.12 and the 1800 floor of this section — commented out with their comments
intact rather than deleted, and every number above still stands as measured.
Figures: `four_trace`.

**What this decides and what it does not.** It ends the §14.12/§14.13 line: the
three stated targets were met, the cost was a discontinuity, and the
discontinuity was judged the worse of the two. It does **not** retire §14.9's own
cut — `lower split 1955` is still drawn, is still a spliced baseline and still
carries a seam (−2.8e−4 on `...-012`) — so if *"the splice"* was meant to cover
that one too, the comparison drops to three traces. That reading was not taken
here, because the colour named includes it.

**What survives, and is what a next attempt builds on:** §14.7's anchored
full-ROI baseline, untouched by any of this, and the measurement underneath the
whole line — finding 31, that the two regimes want opposite signs at 1850, so no
fixed correction below 1955 can serve both. That still has to be answered, and
now without a second segment to answer it in.

### 14.14 A C¹ continuation below 1955 — proposed, not built

**Everything after finding 43 is a proposal.** Findings 41–43 and the table in
decision 3 are measured; the design that follows them is not implemented, and no
field, default or config value has changed.

#### What this session decided

Four calls, all the user's. Three of them close things §14.13.1 left open.

**1. *"The splice"* meant `pspline_arpls`, not the cut at 1955.** §14.13.1 could
not tell which was meant and said so; it guessed, from the colour named, that
the cut was included. That was the wrong way round: *"i didn't want the
pspline_arpls. That is what i thought splice meant. The discontinuity at 1955
may be ok."* So **§14.9's cut stays, and its seam is tolerated** rather than
merely unresolved. `lower split 1955` is the standing preferred form — *"the
last iteration (the green one) is the best so far"* — and the comparison stays
at the four traces of §14.13.1.

**2. `pspline_arpls` is rejected on its own terms.** This is a **third** reason,
separate from the 1750 edge (§14.13's opening) and from the floor seam
(§14.13.1): *"I don't like pspline_arpls b/c it caused major problems elsewhere.
Its not just about 1850, b/c then we would have problems elsewhere."* §14.12 and
§14.13 are closed. Their measurements stand as measurements; the recipe does not
come back.

**3. Replacing the algorithm on the full ROI is out of scope.** Proposed this
session as the seam-free form of §14.12 — a `method` / `method_kwargs` field on
`BaselineVariant`, the full-ROI sibling of `lower_method`, with
`ANCHOR_POINTS_CM1` applied on top and **no cut anywhere**, so neither a seam nor
a floor exists to object to. Declined: *"No, I do not like redefining the
baseline. The current baseline works for the other historical data and I do not
want to refit everything."*

The measurement is recorded so this is not re-proposed as though untried. Eight
of finding 32's methods, at their defaults, over the full 259-sample array with
the three anchors on top:

| form | `und` (…-017 / …-021) | `int` (…-017 / …-021) | `height_2040` (…-021) |
|---|---|---|---|
| `lower split 1955` (green, today) | +3.48 / +4.33 | −5.69 / −6.10 | 2.07e−03 |
| full-ROI `pspline_arpls` | +1.32 / +2.29 | +0.05 / +0.91 | 2.49e−03 |
| full-ROI `arpls` | +0.07 / +1.99 | +1.51 / +1.80 | 2.34e−03 |
| full-ROI `loess` | −0.86 / −0.51 | +2.96 / +2.02 | 1.85e−03 |

It clears the `.0022` complaint, and `height_2040` **rises** rather than falls.
It also overshoots the post-crossing regime at defaults (`…-008` `mid` −12.05,
`…-027` `mid` −6.96, `…-012` `int` +6.04), degrades the flat 2235–2250 mean by
~1.5×, carries §14.12's 1750 edge exposure with no floor available to tie off,
and would be the first form in §14 to change `…-022` — with no cut the split
gate never fires, so the method runs on that file like any other. **None of that
is why it was declined.** The reason is the historical datasets, and it holds
whatever the figures show.

**4. A cross-file / stack background estimate is shelved.** Proposed as the one
family that never has to classify background *inside* a single spectrum — a
pre-nucleation reference index, or a low-rank decomposition over a measurement's
`delta10` stack. *"Sounds complicated. Let's shelve it."* One correction to the
figures quoted when proposing it: the folder holds **36** measurements and
**11 921** subIFG files, median 370 per measurement. The *`delta10` group alone*
is 384 files, ~10–11 per measurement — that is the number that was quoted
without its qualifier.

#### Finding 41. `weights` is the sixth setting, and here it is a measured no-op

§14.3 finding 1 swept "all five exposed settings". There are **six** valid keys
(§3), and `weights` is the one it did not turn — it is an array rather than a
scalar, so it does not fit a scalar sweep. `create_baseline` already forwards it.

Its semantics are the reverse of the intuitive reading: *"Only elements with 0 or
False values will have an effect; all non-zero values are considered baseline
points."* A zero therefore **excludes** a point from the background — it declares
it peak, which is exactly the "tell the classifier where not to look" knob.

Run on the lower segment of the `lower split 1955` recipe with three masks —
1870–1836, 1875–1830, and 1875–1830 plus 1805–1765 — the result on **both
`.0022` files is bit-identical to the unmasked green baseline.** On the
post-crossing files it does move them, and the wrong way: `und` +5.11 → +6.60 on
`…-007`, +4.16 → +6.99 on `…-012`.

#### Finding 42. The lower segment on `…-021` rests on three classified points

`std_distribution` returns its own background mask. Read on the lower segment
(106 samples), against the 17 samples in 1870–1836:

| file | regime | classified background | of those, in 1870–1836 |
|---|---|---|---|
| `…-007` `.0042` | post | 24 / 106 | 4 / 17 |
| `…-008` `.0042` | post | 30 / 106 | 4 / 17 |
| `…-012` `.0052` | post | 26 / 106 | 9 / 17 |
| `…-017` `.0022` | **pre** | 24 / 106 | **0 / 17** |
| `…-021` `.0022` | **pre** | **3 / 106** | **0 / 17** |
| `…-027` `.0052` | post | 21 / 106 | 0 / 17 |

Two things follow, and together they are why this section exists.

**Finding 41's no-op is explained, and the explanation retires a whole family.**
On both `.0022` files *no* sample in the 1850 window was classified background,
so removing those candidates cannot change anything. The algorithm is **not
mistaking the band for background.** Every fix of the shape "detect the bands
better and mask them" — `weights`, a curvature or CWT mask, a peak-list mask — is
therefore dead on these files, and dead for a measured reason rather than by
trial.

**The defect is an under-determined curve, not a misclassification.** On `…-021`
the baseline over 1955–1750, a 205 cm⁻¹ span, is interpolated from **three**
samples. That is also the mechanism behind §14.3 finding 1 and §14.11: every
`std_distribution` knob adjusts *which* samples get classified, and on this file
there are three of them to adjust.

#### Finding 43. Not degenerate, and not a straight line between the segment's ends

Both simpler explanations are ruled out, because each would call for a different
fix.

- **No degeneracy.** Re-run inside `warnings.catch_warnings(record=True)` —
  which a probe must do explicitly, since calling `create_baseline` directly
  swallows the warning (§0's trap list) — `DEGENERATE_WARNING` fires on **no**
  lower segment of the judged six, and on no full-ROI baseline either.
- **Not the endpoint line.** `max |lower segment − the straight line through its
  two end values|` is **2.00%** of range on `…-017` and **2.72%** on `…-021`
  (5.14–10.12% on the post-crossing four). So it is a real interpolation
  following the broad shape, not §14.3 finding 1's "falls back to interpolating
  between the ROI edges" reappearing at segment scale.

The curve is **under-constrained, not broken.** The correction needed at 1850 is
4–6% of range (§14.12 finding 32); the freedom the current curve is using is
2–3%.

#### The proposal

Replace the lower segment's **construction** — not its algorithm (§14.12), not
its parameters (§14.11), not its anchors (§14.10.1).

Today (§14.9) the region below the cut gets a second, independent
`create_baseline` on its own 106-sample array, spliced on. Instead, **continue
the anchored full-ROI baseline downward from the cut**: a smooth curve pinned to
that baseline's own value *and* slope at 1955, fitted to whatever the classifier
does supply below there, with an explicit curvature penalty as the one free knob.

Three properties, in the order they matter:

1. **It supplies exactly what finding 42 says is missing.** A starting value, a
   starting slope, and a stated amount of allowed bend, in place of three
   classified samples over 205 cm⁻¹. This is the load-bearing property.
2. **It is shape-adaptive, which finding 31 requires and no fixed correction can
   be.** A smooth curve fitted to flanks passes near the midpoint of an
   antisymmetric feature and near the base of a symmetric one — the opposite
   signs at 1850 that §14.13.1 leaves standing as the unanswered question. This
   is a **prediction, not a measurement**, and is the first thing to check.
3. **The seam goes to zero by construction, and the slope break with it.** Not
   shrunk — absent, because the continuation does not *meet* the upper curve, it
   *starts from* it. §14.10.1 finding 21 showed the seam is fixed by the upper
   side alone and that nothing below the cut can improve it; a continuation is
   the one form not subject to that. Listed third because decision 1 above
   tolerates the seam, so this is now a bonus rather than the requirement — and
   it answers §14.12 finding 36's open item on the way past.

#### What it must preserve

- **`upper_max_abs_diff == 0.0` exactly**, on all eight judged files. The
  continuation touches nothing at or above the cut, so §14.7 stands bit-for-bit
  there. The `anchored` twin must stay in the run or the check silently reports
  `nan` (§14.9 finding 13).
- **`height_2040` / `height_1980` identical to `anchored`** on every file, for
  finding 13's reason: both bands sit above the cut.
- **The gate.** A cut gated at 1955 leaves no lower segment and therefore no
  continuation, so both `…-022` files return `anchored` unchanged — as under
  every form since §14.9, and unlike decision 3's rejected full-ROI swap.
- **No default changed.** A new `BaselineVariant` field, `None` unless a variant
  asks for it, on `lower_method`'s precedent — and mutually exclusive with
  `lower_method` and `lower_settings`, which configure a second independent
  baseline that this form does not create.

#### The objection to answer before building it

This is a **constraint**, and §14.12's scope said *"no rules or guardrail tricks.
Strictly pybaselines and other methods."* Read narrowly, that rules this out.

The reading taken here is that the instruction was aimed at corrections applied
*to a finished curve* below 1955 — anchors, offsets, clamps, the things finding
31 shows cannot serve both regimes — and that a continuity condition on how the
curve is **constructed** is a different object: it adds no per-file rule, no
threshold and no regime label, and it is the opposite of the splice that decision
1 identifies as the actual objection. **This has not been confirmed with the
user, and should be before the field is built.**

#### What is not settled

- **Which smooth family.** A penalised spline, a low-order polynomial in the
  continuation variable, and a Whittaker-type smoother with the endpoint pinned
  are all candidates; none has been tried. The curvature penalty is then the one
  parameter, and it needs §14.11 finding 30's anti-overfitting treatment — the
  judged eight *and* the 60-file breadth sample, not the two named files.
- **Whether it reaches.** Finding 42 says the freedom is there to be had. It does
  not say a curvature-penalised fit to 3–24 classified samples will find the
  right level. `int` −6.10 → ≈0 and `und` +4.33 → ≤0 on `…-021` are the targets,
  and both are unmeasured.
- **The 1750 edge.** A continuation still ends at the array's bottom. §14.13's
  floor is not available in the same form — there is no independent segment to
  tie off — but the endpoint hazard is the same one, and it should be checked
  before the sweep rather than discovered in it.
- **Finding 31 itself.** Property 2 is the first claim in §14 that a single
  construction could serve both regimes. If it fails, what remains is §14.13.1's
  closing position unchanged.

#### The probes behind findings 41–43

`weights_probe.py`, `weights_lower.py`, `degen.py`, `mask.py` and
`fullroi_probe.py`, written to the session scratchpad rather than the repository
and not preserved. Findings 41–43 and decision 3's table are what they produced;
each is a few minutes' work to re-derive against `JUDGED_FILES`.

---

### 14.15 The C¹ continuation — built and measured; the first form to serve both regimes without `pspline_arpls`

§14.14 proposed it and did not build it. It is now built, swept and checked on
both samples. **Everything §14.14 said it must preserve, it preserves exactly.
Its load-bearing property — the one §14.14 called "a prediction, not a
measurement, and the first thing to check" — holds.** The cost is an `int`
error on the two pre-crossing files that is real, is smaller than every form
before §14.12, and has a measured cause that is *not* the continuation.

The scope question §14.14 said to settle first was put to the user and answered:
a continuity condition on how the curve is **constructed** is allowed under
§14.12's *"no rules or guardrail tricks"*, which was aimed at corrections
applied to a finished curve.

**Say this before the numbers, because it is not what §14.14 proposed.** The
form measured here is the continuation **plus `num_std: 3.0` on the lower
segment's classifier**, and that second half is load-bearing rather than
incidental — §14.14's literal proposal, with the classifier left alone, is a
**breadth regression** (finding 47). `num_std` is the knob §14.3 finding 1 and
§14.11 both swept and recommended nothing from, and every form in §14 until now
has left it at 1.1. Finding 44 is why it has to move and finding 45 is what
moves it; the last bullet of "what is not settled" is why to distrust it. A
reader comparing this section against the rest of §14 should carry that from
here, not discover it three findings in.

#### What was built

`BaselineVariant.lower_continuation_lam` (`None` by default, nothing in
`config/analysis.yaml` touched), and `_segment_continuation` beside
`_segment_baseline` and `_segment_pybaselines` — the third sibling, and the one
that is **not** a second baseline.

**The pin is two grid nodes, not a value and a derivative.** The node array is
the two lowest-wavenumber samples *above* the cut followed by every sample below
it: one contiguous run of the original grid. The first two nodes are held at the
anchored baseline's own values there. Holding two adjacent nodes fixes the
curve's value *and* its slope at the join exactly, on the grid the seam is
measured on — so nothing in the implementation has to reason about the sign of a
derivative on a descending axis, which is §0's first trap and the likeliest way
this would have gone quietly wrong.

With `b` the node values, `m` the samples the classifier called background below
the cut, and `D2` the second-difference operator on the node grid:

```
minimise  Σ_m (b − y)²  +  lam · ‖D2 b‖²      subject to  b[0], b[1] pinned
```

solved as one small dense least-squares problem in the `n − 2` free nodes
(`n ≈ 108`). `D2` uses the exact non-uniform three-point weights scaled by the
mean spacing squared, so on a uniform grid it is exactly `[1, −2, 1]` and `lam`
reads as it does in `pybaselines`' Whittaker methods.

**With no classified samples at all the system is still determined** — the
constrained `D2` block alone is square and triangular, and the answer is the
straight line continuing the anchored slope. That is the honest degenerate case
rather than a failure, and `BaselineOutcome.lower_continuation_points` reports
it rather than leaving it to be inferred: a curve carried entirely by its
penalty looks fitted and is not.

Three things had to be added to measure any of this:

- **`lower_target_metrics` — `mid` / `und` / `int` as real columns.** §14.12,
  §14.13 and §14.14 each re-derived them in a scratchpad probe that was not
  kept. They now live in `baseline.py` beside `band_height`, and the run prints
  all three per file per variant. Verified against the spec's own numbers before
  being used: `anchored` `und` +6.15 on `…-021` and `lower split` `und` +4.33 /
  `int` −6.10 reproduce §14.12 finding 32 exactly.
- **`seam_excess_jump`.** `seam_jump` alone cannot compare these forms. Adjacent
  samples of a *continuous* curve differ by ~slope × the 1.9 cm⁻¹ step, so a
  continuation reports a non-zero seam while having no discontinuity at all.
  `seam_excess_jump` subtracts what the unsplit anchored curve does across the
  same sample pair, leaving the part that is one. It is populated for every
  lower-split form, not just this one, so the comparison is fair in both
  directions.
- **`lower_continuation_points`** — finding 42's number, as a per-run column.

`lower_method`, `lower_anchors` and `lower_floor_cm1` each raise when combined
with a continuation, on the fields' own precedent. `lower_settings` does **not**
— see finding 45.

#### Finding 44. The classified samples are not sparse, they are confined to the top of the segment

This is the sharper form of finding 42, and it changes what that finding means.

Classified background below the cut, at the unmodified settings:

| file | regime | n / 106 | lowest classified | of those, in 1838–1750 |
|---|---|---|---|---|
| `…-007` `.0042` | post | 24 | 1789.6 | 17 |
| `…-008` `.0042` | post | 30 | 1785.8 | 19 |
| `…-012` `.0052` | post | 26 | 1789.6 | 15 |
| `…-017` `.0022` | **pre** | 24 | **1909.2** | **0** |
| `…-021` `.0022` | **pre** | **3** | **1911.1** | **0** |
| `…-027` `.0052` | post | 21 | 1787.7 | 17 |

Finding 42 read `…-017` as 24/106 and therefore unremarkable; the count is not
the problem. **On both pre-crossing files the classifier supplies nothing below
~1910 — zero samples in the entire 1838–1750 window `int` is measured over.**
`…-017` classifies 24 points and every one of them sits in 1954–1909.

Two consequences:

- **The continuation extrapolates the last ~160 cm⁻¹ of those files under its
  curvature penalty alone.** `int` therefore misses by +5.6 to +6.6% of range at
  **every** `lam` from 1e1 to 1e8 — seven decades, and the miss does not move.
  It is not a tuning failure.
- **It is not a failure of the continuation either.** Any method that fits
  `std_distribution`'s classified points on that segment inherits it. §14.12's
  `pspline_arpls` reached the bottom of those files precisely *because* it does
  no classification — which is also why it overshot the post-crossing regime.

#### Finding 45. The one lever inside the form is the classifier, and it works

Under a continuation there is no second baseline for `lower_settings` to
configure, so it configures the **classifier** — which samples below the cut
count as background. That is the same object those keys always named, reached
one step earlier, and it is why `lower_settings` is the one companion field not
rejected. Finding 44 makes it the interesting lever rather than a leftover.

`num_std` raises the tolerance for calling a sample background, so a *larger*
value classifies more — the opposite direction from a mask, and the reason the
mask family (finding 41) had nothing to give here.

Lowest classified wavenumber on the two pre-crossing files:

| setting | `…-017` lowest / in 1838–1750 | `…-021` lowest / in 1838–1750 |
|---|---|---|
| default (`num_std` 1.1) | 1909.2 / **0** | 1911.1 / **0** |
| `num_std` 2.0 | 1889.9 / 0 | 1907.3 / 0 |
| **`num_std` 3.0** | **1807.0 / 5** | **1808.9 / 3** |
| `num_std` 5.0 | 1797.3 / 22 | 1803.1 / 9 |

At 3.0 the classifier reaches the `int` window on both, and `int` comes back.

#### Finding 46. The result, on the judged six

`lower_continuation_lam=1e3` with `num_std: 3.0`, against every form §14 has
measured. `mid` targets 0 on post-crossing files; on pre-crossing ones the
target is `−(peak − trough)/2`, so the column is the distance from that.

| form | post \|mid\| mean | pre \|mid − target\| mean | pre `und` max | \|int\| max | \|int\| mean | \|seam\| max | \|seam excess\| max |
|---|---|---|---|---|---|---|---|
| `anchored`, no cut (§14.7) | 5.34 | 7.32 | 6.15 | 14.51 | 8.46 | — | — |
| lower split, no anchors (§14.9) | 1.43 | 5.40 | 4.33 | 6.10 | 2.55 | 5.64 | 5.58 |
| + lower anchors (§14.10.1) | 2.38 | 6.28 | 5.13 | 7.71 | 4.38 | 2.75 | — |
| `pspline_arpls` (§14.12, rejected) | 0.54 | 0.27 | 0.79 | **1.11** | **0.43** | 4.26 | — |
| **continuation, `lam` 1e3 + `ns3`** | **0.25** | 0.52 | **0.54** | 3.70 | 1.20 | **0.43** | **0.36** |

Per file:

| file | regime | `mid` | target | `mid − target` | `und` | `int` | excess | pts |
|---|---|---|---|---|---|---|---|---|
| `…-007` | post | −0.17 | 0 | −0.17 | +3.75 | **+0.06** | −0.16 | 87 |
| `…-008` | post | −0.73 | 0 | −0.73 | +4.51 | **+0.02** | −0.36 | 106 |
| `…-012` | post | +0.06 | 0 | +0.06 | +3.45 | **+0.07** | −0.17 | 85 |
| `…-017` | **pre** | −4.96 | −4.23 | **−0.73** | +0.54 | +3.34 | +0.04 | 41 |
| `…-021` | **pre** | −5.08 | −4.76 | **−0.32** | **−0.19** | +3.70 | +0.03 | 38 |
| `…-027` | post | −0.05 | 0 | −0.05 | +4.09 | **+0.03** | −0.06 | 106 |

**`mid − target` is signed here, and the sign matters more than the magnitude.**
The summary table above reports it as an absolute mean, which makes an overshoot
and an undershoot look like the same kind of miss. They are not: *"under the base
of those peaks"* has a good side to err on. **The continuation errs low on both
pre-crossing files** — 0.73 and 0.32% of range *below* the flanking trough — where
`split` reads +0.62 and +1.19, i.e. **4.9 and 6.0 above** it, cutting into the
band. Erring low is the better direction and `…-021`'s negative `und` agrees.
But it is still an error, and on the figures a baseline sitting under the trough
rather than touching it could read as sagging. That is a visual call, and it is
the one the pre-crossing files turn on.

**Property 2 holds — this is the headline.** §14.14 listed shape-adaptivity
first and called it a prediction: *"A smooth curve fitted to flanks passes near
the midpoint of an antisymmetric feature and near the base of a symmetric one."*
It does. Post-crossing `mid` lands inside ±0.73 on all four, pre-crossing `mid`
lands within 0.73 of "on the flanking trough", and `…-021`'s `und` goes
**negative** — the first form in §14 whose baseline is genuinely *under* the
base of those bands rather than less far into them. Finding 31's opposite signs
at 1850 are served by one construction, and **for the first time without
`pspline_arpls`**, which is the question §14.13.1 left standing.

**Property 3 holds, and is now measurable.** `|seam excess|` max **0.36**
against the splice's **5.58** — 15×, and the one column §14.10.1 finding 24 kept.
§14.12 finding 36's open item is answered: the seam is not a price this form
pays.

**Everything §14.14 said it must preserve is preserved, checked and exact:**

- `upper_max_abs_diff` **0.0 exactly** over 88 rows on the judged eight, 600 on
  the breadth sample.
- `height_2040` / `height_1980` bit-identical to `anchored` on every file and
  every `lam` — 0 mismatches in either run.
- **The gate.** Both `…-022` files gate at 1955, build no continuation
  (`pts` = −1), and come back `anchored` to 0.000e+00.
- No default changed, no config value touched, nothing in the live path.

**What it costs.** `int` on the two pre-crossing files, +3.34 and +3.70. That is
worse than `pspline_arpls`'s 1.11 max and better than every form before it
(`split` −5.69/−6.10, `anchored` −8.13/−8.77). Finding 44 says why: even at
`ns3` those files supply only 5 and 3 classified samples in that window, so most
of it is still carried by the penalty.

**The interior of the segment is held, by nothing.** §14.10.1 removed the third
lower anchor at 1800 and `LOWER_MID_PROBE_CM1` has measured what that cost ever
since: with two anchors the correction is exact at both ends and the middle
drifts. The continuation lands **+0.76 to +1.46% of range on all six**, where
`split` sits at −8.0 / −8.2 on the pre-crossing files and `anchored` at
−10.4 / −10.8. Nothing anchors it there — the value comes from the curvature
penalty carrying the pin across the segment, which is the same mechanism as
property 1 and the clearest evidence that finding 42's diagnosis was right.

One more result worth keeping:

- **The 1750 edge, which §14.14 said to check before the sweep rather than
  discover in it.** Checked: at the unmodified classifier the continuation ends
  +17 to +19% of range off the data on the pre files. At `ns3` that is what
  finding 45 fixes. The exposure is real and there is no floor available to tie
  it off — `lower_floor_cm1` raises here, deliberately.

#### Finding 47. Breadth — and this time the wider sample agrees

60 `delta10` files from the same dataset, 53 ungated. The original
`breadth_files.txt` was a scratchpad file and is gone, so the sample is
re-derived deterministically: every `delta10` file sorted by name, taken at an
even stride. Only `int` and the seam are defined without a regime label, so
`mid` and `und` are not reported — finding 35's shape exactly.

| form | mean \|int\| | median | max | \|seam\| max | \|excess\| max | smaller \|int\| than `split` on |
|---|---|---|---|---|---|---|
| `anchored`, no cut | 23.76 | 11.26 | 66.01 | — | — | 1/53 |
| lower split (§14.9) | 1.94 | 1.35 | 12.01 | 14.96 | 15.22 | — |
| `pspline_arpls` (§14.12 finding 35) | 0.95 | 0.45 | **4.48** | 12.02 | — | 45/51 |
| continuation, classifier unchanged | 6.35 | 3.97 | 44.13 | 1.14 | 0.33 | 16/53 |
| **continuation, `lam` 1e3 + `ns3`** | **0.58** | **0.13** | 9.51 | **1.07** | **0.82** | **51/53** |

Read as constraint 1 (§14.1) and nothing more — *"this does not break the files
that already work"*. On those terms it passes, and **the breadth sample ranks it
the same way the judged six do**, which is the thing §14.11 finding 30 warned
would not happen: 51/53 and 50/53 are not chance, where finding 30's 32/51 was.
It beats `pspline_arpls` on mean, median and win rate, and loses on the max.

The unmodified-classifier row is finding 44 measured on 53 files rather than 2:
mean `|int|` 6.35 against 0.58, and better than `split` on only 16/53. **That
row is the literal form §14.14 proposed**, and on its own it is a regression.

No degenerate or constant baseline in 720 rows, and the degeneracy verdict here
is `std_distribution`'s own — the continuation reads the classifier's warning
directly, so unlike finding 35 this is the strong check, not the structural one.

#### What is not settled — and one thing to distrust

- **The judgement is visual and has not been made** (§14.3 finding 4). Nothing
  is recommended, no default changed. The figures are the four traces the user
  asked for plus this one.
- **`num_std: 3.0` works for a reason that is a coincidence.** At 3.0 the
  classifier calls **all 17** samples of the 1870–1836 band window background on
  four of the six judged files — exactly the "pure centre-line method" finding 31
  predicts should fail the pre-crossing regime. It does not fail, because on both
  pre-crossing files it still classifies **0 of 17** there, as at 1.1. The
  threshold happens to fall on opposite sides of the same window in the two
  regimes. **Nothing guarantees that on a file neither regime describes**, and at
  `num_std` 5.0 it already breaks: `…-017` flips to 17/17 and its `mid` error
  triples. This is the single largest risk in the section and it is a property of
  the classifier, not of the continuation.
- **`int` on the pre-crossing files is unfixed**, at +3.3 to +3.7. Finding 44
  bounds what more classification can do there: 5 and 3 samples.
- **Whether the `.0022` depression below 1838 was baseline error at all** is
  still asserted by the `int ≈ 0` target rather than measured — §14.12's open
  item, untouched here.
- **`lam` is not a sharp optimum.** 3e2 and 1e4 are close; 1e3 wins most columns
  and loses two. Swept 1e1–1e8 on both samples.

#### Where the figures are

`run_name` moved from `four_trace` to `continuation`, so
`...\baseline_experiments\four_trace` still holds the four-trace figures the
user judged §14.14 on, unchanged, beside the five-trace set this section is
read from.

#### Probes

The sweep, the breadth check and the classifier-reach probe were written to the
session scratchpad and not preserved, on §14.14's precedent. What they produced
is above; `mid` / `und` / `int`, `seam_excess_jump` and
`lower_continuation_points` are now table columns, so findings 46 and 47 are
re-derivable from `uv run python src\utils\ir_fitting\api.py` alone.

---

### 14.16 The anchored baseline truncated at 1800 — built and measured; a near-no-op on one regime, a real but third-place move on the other

The user's instruction was exact: *"Let's go back to 3 anchor points, no split
(the orange trace). But this time, let's truncate at 1800. So 2250-1800. Yes, I
know that will cause reprocessing, but just do it."*

So: **§14.7's form, unchanged, on a shorter array.** No cut, no second baseline,
no continuation, no seam. The split forms of §14.9 and §14.15 are commented out
of the figures — still built, still measured above, out of the comparison.

**"The orange trace" is `anchored`.** Worth stating because a comment in
`api.py` had the colours wrong and would have sent a reader to the split form:
`plot_baseline_comparison` draws raw in black and then the variants in `tab10`
*list order*, so `traces[0]` = `current` is blue and `traces[1]` = `anchored` is
orange. The comment is corrected.

#### What was built

`TRUNCATED_WINDOW_1800 = (2250.0, 1800.0)` — a value for the existing `window`
field, not a new mechanism. The variant is one line:

```python
("anchored 1800", {}, TRUNCATED_WINDOW_1800, ANCHOR_POINTS_CM1),
```

`DEFAULT_WINDOW` is **not** changed: `("current", {})` reads it, and truncating
the reference would move `reference_range` and make every
`moved_pct_of_range` in the table meaningless. Untruncated `anchored` stays in
the run for the same reason it stays in for the split forms — it is the middle
term that attributes a change to the *truncation* rather than to the anchors.

All three anchors (2240 / 2006 / 1955) sit above 1800, so `__post_init__`'s
anchor-in-window check passes and the `…-022` gate behaves exactly as in §14.7.

**This is not §14.13's floor and not §14.6 finding 7's truncation.** Three
things in §14 sit at 1800 or at truncation and this is none of them:

- §14.13's `lower_floor_cm1` is also 1800, but is a floor on a *split* form: the
  second baseline stops there and the anchored full-ROI curve — computed over
  the whole 2250–1750 array — stands below it. Here nothing is computed below
  1800 at all.
- `LOWER_MID_PROBE_CM1` is also 1800. Under this window it lands on the array
  edge, so that probe's number is no longer an interior measurement **for this
  variant**; read it accordingly.
- Finding 7's rejected truncation was **bare** — no anchors — and at **1955**,
  205 cm⁻¹ higher. Anchors plus truncation at 1800 is a combination §14 had not
  run, and finding 7 does not rule it out.

Because `create_baseline` receives only `y` (§0), the window *is* the array:
`std_distribution` reclassifies over it and the baseline moves **above** 1800
too. That is the experiment, and it is why this cannot be read off §14.13's
figures.

#### The `int` window is cut in half, so it was re-measured like-for-like

`INT_WINDOW_CM1` is 1838–1750. On this window only 1838–1800 survives — **20
samples against the full-ROI variants' 46**. `int` under the same column name is
therefore a *different statistic*, and the run now prints its sample count and
the per-trace signal range beside it so this cannot be read past.

The comparison below is consequently made on the **same 20 samples for every
variant**, scaled by the **reference** file's range, so the only thing differing
between the rows is the baseline:

| file | regime | `current` | `anchored` | `anchored 1800` |
|---|---|---|---|---|
| `…-007` `.0042` | post | −0.61 | +8.94 | **+8.80** |
| `…-008` `.0042` | post | −2.23 | +4.48 | **+4.39** |
| `…-012` `.0052` | post | +0.16 | +14.88 | **+14.71** |
| `…-027` `.0052` | post | −0.32 | +5.76 | **+5.73** |
| `…-017` `.0022` | **pre** | −7.30 | −9.67 | **−2.27** |
| `…-021` `.0022` | **pre** | −7.80 | −10.31 | **−2.77** |
| `…-022` `.0022` | guard | −0.46 | +29.11 | +29.36 |
| `…-022` `.0042` | guard | +0.26 | +12.26 | +12.61 |

#### Finding 48. The denominator moves only on the two guard files — measured, not assumed

Dropping 1800–1750 removes the 1795/1775 bands from the array, so
`signal_range` — which every percentage in §14 divides by — could shift for a
reason that has nothing to do with the baseline. It does not, on the files that
matter: the range is **identical to five significant figures on all six judged
files** (100.0% of the reference). It moves only on the two `…-022` guard files,
to **88.2%** and **79.8%**, where the removed region carried the extremum that
set the range.

So the judged six are directly comparable and the guard pair's percentages are
inflated by 1/0.88 and 1/0.80 respectively. Their numbers below are read with
that in mind rather than at face value.

#### Finding 49. On the post-crossing regime, truncation is very nearly a no-op

The property §14.7 exists for is untouched. Band heights, as a ratio to
`current`:

| file | `anchored` 2040 / 1980 | `anchored 1800` 2040 / 1980 |
|---|---|---|
| `…-007` | 1.428 / 1.706 | **1.428 / 1.706** |
| `…-008` | 1.234 / 1.213 | 1.233 / 1.213 |
| `…-012` | 2.053 / n/a | **2.053 / n/a** |
| `…-027` | 1.663 / 1.205 | **1.663 / 1.205** |

Bit-identical on three of four and equal to three decimals on the fourth. `mid`
and `und` are likewise identical on `…-007`, `…-012` and `…-027`
(−4.9876 / −0.7831, −12.9747 / −9.4694, −3.0993 / +1.2252 in both rows) and move
in the second decimal on `…-008`. Like-for-like `int` moves by ≤ 0.17.

**Removing the bottom 50 cm⁻¹ does not disturb the region the anchors fixed.**
That is not obvious in advance — the window is the array — and it is the result
that makes the next finding usable rather than a trade.

#### Finding 50. On the pre-crossing `.0022` regime it moves every target the right way — and still finishes behind §14.12 and §14.15 on all three

This is the regime §14.10 through §14.15 kept failing to fix, and the one
§14.10.1 finding 24 withdrew a claimed fix for.

**This finding first claimed the move was the largest in §14. That was written
before it was measured, and it is wrong** — the run behind it contained only
`current`, `anchored` and `anchored 1800`, so the comparison the claim made was
never performed. It has since been run (`plot=False`, numbers only, the two
forms read back out of `__main__`), and both §14.12's `pspline_arpls` and
§14.15's continuation beat this form on **all three targets on both files**:

| `…-017` | target | `current` | `anchored` | `anchored 1800` | `pspline_arpls` §14.12 | continuation §14.15 |
|---|---|---|---|---|---|---|
| `mid` | −4.23 (pre) | +0.35 | +2.48 | −2.55 | −4.41 | **−4.96** |
| `und` | 0 from below | +3.17 | +5.19 | +2.43 | +0.79 | **+0.54** |
| `int_shared` | 0 | −7.30 | −9.67 | −2.27 | **+0.12** | +0.13 |

| `…-021` | target | `current` | `anchored` | `anchored 1800` | `pspline_arpls` §14.12 | continuation §14.15 |
|---|---|---|---|---|---|---|
| `mid` | −4.76 (pre) | +0.97 | +3.17 | −2.02 | **−4.41** | −5.08 |
| `und` | 0 from below | +4.08 | +6.15 | +2.48 | +0.21 | **−0.19** |
| `int_shared` | 0 | −7.80 | −10.31 | −2.77 | **+0.09** | +0.26 |

So the honest reading is a **clear third**. Against `anchored` — the form the
user asked to go back to, and the only baseline this variant actually modifies —
every target improves, and `mid` crosses from the wrong side of zero to the
right one: `und` falls from cutting 5–6% of range into the 1850/1870–1880 bands
to 2.4–2.5%, and `int_shared` improves by 7.4 and 7.5 points. Against the two
forms §14 already has on record, it is not close: the continuation lands `mid`
within 0.3–0.7 of target and `und` at ±0.5, where this sits 1.7–2.7 and 2.4–2.5
away.

What remains true and is the only reason to keep it in view: it gets there
**with no cut** — no seam, no second curve, no second algorithm, no classifier
change. §14.15 buys its result with `num_std: 3.0`, which its own *"what is not
settled"* calls the section's largest risk and a regime coincidence; §14.12's
algorithm is rejected on a third ground. This buys a smaller result with a
window and nothing else. Whether a smaller, structurally simpler move is worth
more than a larger one carrying those risks is a judgement, and it is the
user's, not this document's.

**`probe@1800` is deliberately not in the tables above.** Under this window 1800
is the array edge — the lowest sample is 1801 — so `np.interp(1800, …)` returns
the edge value rather than an interior measurement, and it carries roughly the
same information as `int_shared`'s bottom end. It is reported by the run, and it
is not a fourth independent target. For the record it reads −2.48 (`…-017`) and
−1.99 (`…-021`) against `anchored`'s −10.40 and −10.83.

The figure for `…-021` shows the mechanism plainly: below ~1900 the orange
(`anchored`) curve lifts off the raw trace while the green (`anchored 1800`)
stays on it, and above ~1950 the two are indistinguishable.

#### Finding 51. The cost is the guard files, and it is real

`…-022` is the regression gate — the file whose 1942 band costs it the 1955
anchor. Truncation makes it worse on every column:

| | `anchored` | `anchored 1800` |
|---|---|---|
| `…-022` `.0022` `mid` | −23.11 | −26.19 |
| `…-022` `.0022` `und` | −6.54 | −7.39 |
| `…-022` `.0042` `mid` | −12.11 | −15.65 |
| `…-022` `.0042` `und` | +4.96 | +5.85 |

Part of that is finding 48's denominator — deflate by 0.88 / 0.80 and `mid` on
`.0022` is ≈ −23.1 against −23.1, i.e. roughly flat, while `.0042` is ≈ −12.5
against −12.1, still worse. So the guard files degrade, by less than the raw
numbers say and by more than nothing. The gate itself still fires correctly:
`anchors_gated` is `1955` on both, exactly as in §14.7.

#### What this settles, and what it does not

- **Settled:** anchoring plus a 1800 window is very nearly a no-op on the
  post-crossing regime (finding 49) and moves every pre-crossing target the
  right way against `anchored`, with no seam, no second curve and no classifier
  change — while finishing **behind both §14.12 and §14.15 on all three targets
  on both pre-crossing files** (finding 50). The denominator confound is
  measured and confined to the guard pair (finding 48).
- **Settled — the ranking, this time by measurement.** The first draft of
  finding 50 asserted this was the largest improvement in §14 without having run
  the comparison. It has now been run and the assertion was false. The
  `int_shared` column exists so that this particular mistake cannot be repeated
  silently: plain `int` is not comparable across a window change, which is what
  made the wrong claim look plausible.
- **Not settled — the visual call.** As everywhere in §14, nothing is
  recommended and no default is changed. `DEFAULT_WINDOW`, `config/analysis.yaml`
  and `io.py`'s production ROI are all untouched; this is the experiment's
  `window` knob only. The user's *"I know that will cause reprocessing"*
  authorises the experiment, not a change to the production ROI.
- **Not settled — `int` on the post-crossing files.** It is +4.4 to +14.7 under
  both anchored forms. That is §14.7's pre-existing problem, the one §14.12 built
  `pspline_arpls` for; truncation neither fixes nor worsens it.
- **Not settled — breadth.** This is the judged eight only. Every earlier
  section that mattered was checked against the 60-file sample, and §14.11
  finding 30 is the standing warning that the wider sample can disagree. **That
  check has not been run here.**
- **Not settled — what happens below 1800.** Nothing is computed there, so the
  1795/1775 bands and §4's two dormant peaks have no baseline at all under this
  form. Under §14.13's floor they at least had the full-ROI curve. Whether that
  matters depends on whether those peaks are ever fitted, which §14.12 recorded
  the user as leaving open.

#### Where the figures are

`...\baseline_experiments\anchored_1800` — three traces plus raw, on the judged
eight. The `continuation` and `four_trace` runs are unchanged beside it.

#### Probes

**Nothing here rests on an unpreserved probe.** §14.15 had to rebuild
`mid`/`und`/`int` because §14.12, §14.13 and §14.14 each re-derived them in a
scratchpad that was not kept, and finding 50's load-bearing number would have
been the fourth — so `int_shared` is a **column**, not a probe:
`INT_SHARED_WINDOW_CM1` and `baseline.int_shared`, printed per trace and written
to `baseline_comparison.csv`. Findings 48–51 are all re-derivable from
`uv run python src\utils\ir_fitting\api.py`, which now prints `int`'s sample
count, `int_shared`, and each trace's own signal range.

The one thing that needs a code change to reproduce is finding 50's ranking
columns, because §14.12's and §14.15's forms are commented out of `__main__` at
the user's *"no split"* instruction. Uncomment those two variants and re-run
with `plot=False` to get the two right-hand columns back; the figures are
deliberately left as the three traces plus raw that were asked for.

### 14.17 Edge anchor at 1800 — selected for the truncated experiment

The latest experiment remains the single anchored baseline on
`TRUNCATED_WINDOW_1800 = (2250, 1800)`: no split, no second baseline, and no
production-ROI change. The user selected one additional anchor at the cutoff,
so the truncated variant now uses
`TRUNCATED_ANCHOR_POINTS_1800_CM1 = (2240, 2006, 1955, 1800)`.

This is intentionally **not** a change to `ANCHOR_POINTS_CM1`. The full-ROI
`anchored` variant remains the three-anchor twin required to attribute movement
to truncation, and production defaults remain unchanged. The 1800 point is an
edge anchor: the truncated data array's lowest available sample is just above
1800, so its data estimate is a short one-sided local fit at the cutoff rather
than an interior measurement. The existing prominence guard runs on the
truncated array and the anchor is reported through `anchors_applied` or
`anchors_gated` like the other points.

The figures and comparison table must be re-run before judging the change. In
particular, compare the new truncated form against the unchanged `anchored`
twin, and keep the guard files separate: removing 1800–1750 also removes the
low bands that previously influenced their signal range.

### 14.18 Live trial: edge anchor at 1790

The next trial changes the live experiment from the measured 1800 cutoff to a
1790 cutoff so that an anchor at 1790 is inside the fitted array. The production
ROI and the full-ROI `anchored` twin remain unchanged. The live variant is now
named `anchored 1790`, uses `TRUNCATED_WINDOW_1790 = (2250, 1790)`, and has
anchors `(2240, 2006, 1955, 1790)`.

The live `int_shared` comparison window moves with it to `1838–1790`; the
earlier `1838–1800` values in §14.16 remain historical measurements.

This section records an experiment request, not a result. The plots and the
comparison table must be regenerated before interpreting the effect; the
historical 1800 measurements above remain the reference for comparison.

### 14.19 Five lower anchors under the 1955 cut — measured, not selected

The 1790 truncation trial is superseded for the active experiment. The run is
back on the full `DEFAULT_WINDOW = (2250, 1750)`, with the established three
upper anchors `(2240, 2006, 1955)` and a lower-only cut at `1955`. The lower
experiment adds the separate five-point set `(1955, 1790, 1800, 1810, 1820)`.
The two-endpoint `LOWER_ANCHOR_POINTS_CM1` default remains unchanged; this is
an experiment-only alternative.

The active comparison is `current`, `anchored`, `lower split 1955`, and
`lower split 1955 + five lower anchors`, written to
`C:\Figures\nn1120-4_pd_ceo2_000\baseline_experiments\lower_anchors_1955`.
All eight judged files ran with no degenerate baselines. The lower-only split
left the region at and above the cut identical to `anchored`:
`upper_max_abs_diff = 0.0e+00` on every row. Both `...-022` guard files gated
1955, so the lower-anchor variant fell back to `anchored` there and applied no
lower anchors.

On the six ungated files, the five-point lower correction changed the seam from
the unanchored lower split's `(-2.870, -1.775, -5.639, +2.018, +0.846,
-0.530)` to `(-1.899, -0.818, -2.945, +1.789, +1.430, -0.723)` % of signal
range, in judged-file order `...-007`, `...-008`, `...-012`, `...-017`,
`...-021`, `...-027`. Its absolute seam is smaller on the first four and larger
on `...-021` and `...-027`. This is a measurement, not a quality score.

With five lower anchors the correction is least-squares, so the two-anchor
identity that predicts the seam from the upper residual at 1955 no longer
applies. The run prints that quantity only as a reference. Visual judgement
and, if this form remains of interest, a breadth check are still open; no
production ROI, configuration default, or recommendation changed.

### 14.20 Seven anchors on the full ROI — measured

The lower-split comparison in §14.19 was superseded for the next experiment.
The active run returned to the **uncut** `DEFAULT_WINDOW = (2250, 1750)` and
compared the current baseline, the established three-anchor full-ROI curve
`(2240, 2006, 1955)`, and one full-ROI curve with four additional lower anchors:
`(2240, 2006, 1955, 1790, 1800, 1810, 1820)`. The new set is exposed as
`FULL_ROI_ANCHOR_POINTS_SEVEN_CM1`; neither `ANCHOR_POINTS_CM1` nor any
production default changed.

The run used eight judged files, produced eight figures, and had no degenerate
baselines. The established three-anchor trace remains the orange trace and the
seven-anchor trace is green. There is no cut, second baseline, seam, or
`lower_anchors` operation in this comparison.

The prominence guard still gated `1955` on both `...-022` files. The additional
lower points were applied there, so those traces used
`(2240, 2006, 1790, 1800, 1810, 1820)` rather than silently treating the guard
as a guard for the whole seven-point set. On the six ungated files, the maximum
green-versus-orange displacement was 5.8--15.5% of signal range; its signed
mean displacement varied by regime, so this is a movement measurement, not a
quality score.

The figures show the intended trade: the added lower points pull the lower
extrapolation substantially toward the 1790--1820 data while also reweighting
the single affine correction across the upper region. The lower-region probe at
1800 moved from the orange trace's +6.5 to +15.2% / −10.4 to −10.8% range to
approximately +1.0 to +1.7% / −1.1 to −1.2% on the six ungated files. The
upper band heights therefore must still be judged alongside the lower-region
figures; no automatic baseline-quality score exists.

### 14.21 Current locked experiment — dense upper anchors with the lower split

**Superseded as a comparison by §14.22, which runs variant 4 below on its own.
The recipe is unchanged; only the other three traces are gone.**

The active `api.py` comparison is now the lower-split experiment selected after
the §14.20 full-ROI run. It uses the full `DEFAULT_WINDOW = (2250, 1750)` and
these four variants, in order:

1. `current`
2. `anchored`, with `ANCHOR_POINTS_CM1 = (2240, 2006, 1955)`
3. `lower split 1955`, with the same three full-ROI anchors and
   `lower_split_cm1 = 1955`
4. `lower split 1955 + five lower anchors`, with
   `lower_split_cm1 = 1955`, `lower_anchors = (1955, 1790, 1800, 1810, 1820)`,
   and the full-ROI anchors written in `api.py` as:

   ```python
   (*ANCHOR_POINTS_CM1, 2011, 2010, 2009, 2008, 2007, 2006, 2005,
    2004, 2003, 2002, 2001, 2000)
   ```

The added upper anchors are experiment-only and affect the full-ROI correction
used by the selected lower-split trace. The expression intentionally preserves
the current code exactly; because `ANCHOR_POINTS_CM1` already contains `2006`,
the dense set contains `2006` twice and therefore gives that wavenumber double
weight in the least-squares affine correction. Do not deduplicate it without a
new comparison run.

The lower segment remains **1955–1750 cm⁻¹**. The run name is
`lower_anchors_1955`; figures and `baseline_comparison.csv` are written under
the dataset's `baseline_experiments` directory. This is the locked offline
experiment, not a change to live or production baseline defaults.

### 14.22 The final candidate, shown alone

The user selected variant 4 of §14.21 — the lower-only split at 1955 with
**anchors on both segments** — and asked to see only it. `api.py`'s `variants`
list is now that one entry; `current`, `anchored` and the unanchored
`lower split 1955` are commented out directly beneath it, in the order that
restores their established colours.

The recipe is byte-identical to §14.21's variant 4, including the duplicated
`2006` in the dense upper set. Nothing about the baseline changed. What changed
is the figure: raw subIFG in black against one trace, with both anchor sets
drawn — black circles for the full-ROI anchors (the 2000–2011 cluster renders as
one blob at ROI scale), green squares for the lower anchors, and the purple
dash-dot cut at 1955. The `anchored` twin's orange trace is gone, so the
candidate takes `tab10[0]` and is blue.

Two consequences of running one variant, both reported by the run rather than
left to be inferred:

- **Every reference-relative column is self-referential.** The single variant
  *is* the reference, so `moved_pct_of_range` is 0 and each `_x_ref` ratio is
  1.0000 by construction — not a measurement, and specifically not the "near 2
  means the band stopped being halved" reading those columns otherwise carry.
  The block prints this warning whenever `len(variants) == 1`. The raw
  `height_*` columns and the lower-region targets remain real.
- **`upper_max_abs_diff` is not checked.** It needs an unsplit twin with the
  *same* settings, window and anchors, and the dense upper set has none here.
  This was already true in §14.21 — variant 4's anchors differ from
  `anchored`'s, so its `upper_max_abs_diff` was `nan` there too, and the
  printed PASS came from the other split variant. With that variant gone the
  summary would have called `nan` a FAIL; it now prints **NOT CHECKED** and
  names what to add. A nan in that column has always meant an unperformed
  check, never a failed one.

Measured on the eight judged files: 8 figures, no degenerate baselines.

**Two of those eight figures do not show the candidate.** On both `...-022`
guard files the prominence guard fired twice — the guard runs on the 1955
*anchor* and on the 1955 *cut* independently, and 1955 failed both. The CSV
records `anchors_gated = 1955` and `split_gated = 1955` with `split` empty.
With no cut there is no lower segment, so the five lower anchors were neither
applied nor gated: `lower_anchors` and `lower_anchors_gated` are both blank.
What those two traces actually are is the dense upper set *minus* 1955 on an
uncut full ROI — the §14.19 fallback, not the candidate. `seam_pct_of_range` is
`nan` there because there is no seam, and their `mid` ≈ −24 / `int` ≈ +31 % of
range belong to that fallback curve, not to the form under judgement. The six
ungated files are the candidate; read those.

This is the guard doing its stated job — `...-022`'s raw subIFG minimum sits at
1942 cm⁻¹, which is what makes those files guard cases rather than baselines
certified correct (§14.2) — and it is unchanged from §14.21. It is only more
visible now: with the comparison traces gone, nothing else in the figure shows
what the candidate would have done.

Restoring the comparison is uncommenting three lines.

---

## 15. Cleanup to the selected form — what the code now contains

**§0–§14 above are the historical record of what was tried and are left
unedited.** This section is the one place that says which of it is still in the
code. Where a subsection above says a form is "built", "available as a knob" or
"kept", check the table below before believing it — several of those knobs are
gone.

The user selected §14.22's form and asked for the other constructions to be
removed. No baseline behaviour changed: this is a deletion, not a new
iteration.

### 15.1 What the code is now

The knobs on `BaselineVariant`, and the values the selected form uses:

| Knob | Selected form | Why that value |
|---|---|---|
| `settings` | `{}` — unchanged `voigt_fit.baseline` | Swept twice, nothing recommended (§14.3 finding 1, §14.11) |
| `window` | `DEFAULT_WINDOW` = `(2250, 1750)` | Every truncation was rejected (§14.6 finding 7, §14.16–§14.18) |
| `anchors` | `DENSE_UPPER_ANCHOR_POINTS_CM1` | §14.7's three calibrated points plus the 2011–2000 cluster (§14.21) |
| `lower_split_cm1` / `lower_anchors` | `1955` / `(1955, 1790, 1800, 1810, 1820)` | The lower-only cut of §14.9 with the five-point set of §14.19 |
| `anchor_guard_cm1` / `anchor_prominence_frac` | `25.0` / `0.5` | §14.7 finding 8 calibrated the pair once; **never swept**. Added as fields in §16 — the values are unchanged, so every measurement above still stands |

The last row was function defaults inside `gating_extremum` until §16 and is the
one part of the construction §14 introduced without ever varying. Making it
settable changed no default and no measurement; it made the untested thing
testable.

The inline `(*ANCHOR_POINTS_CM1, 2011, 2010, …, 2000)` expression of §14.21 and
§14.22 is now the named constant `DENSE_UPPER_ANCHOR_POINTS_CM1`.
**Value-identical, including the duplicated `2006`** and the double weight it
carries in the least-squares correction. §14.21's instruction not to
deduplicate it without a new comparison run stands.

Two properties remain load-bearing, and both are still checked rather than
argued:

- At and above the cut the result is bit-for-bit the unsplit anchored baseline.
  `upper_max_abs_diff` must be exactly `0.0`, needs an unsplit twin with the
  same anchors in the same run, and reports `nan` — an **unperformed** check,
  never a passed one — when there is none. Running the selected form alone is
  that case, and `__main__` prints **NOT CHECKED** (§14.22).
- The anchor at 1955 and the cut at 1955 are gated **independently** by one
  test. On both `...-022` files each fires, so those two traces are the uncut
  fallback rather than the selected form. Read the six ungated files.

### 15.2 What was removed

Every entry is still described in its section above. Removing it from the code
does not withdraw the measurement; re-adding any of it means re-reading that
section first.

| Removed | Was | Recorded in |
|---|---|---|
| `split_cm1`, `split_form` | The truncating split — cut the array and recomputed **both** sides on truncated arrays | §14.8 |
| `lower_method`, `lower_method_kwargs`, `_segment_pybaselines` | A different **algorithm** below the cut, any `pybaselines.Baseline` method | §14.12, rejected §14.14 decision 1 |
| `lower_floor_cm1`, `floor_edges`, `floor_seam_jump` | The lower segment tied off at 1800 | §14.13, removed by the user §14.13.1 |
| `lower_continuation_lam`, `_segment_continuation`, `lower_continuation_points` | The C¹ continuation below the cut | §14.14, §14.15 |
| `lower_settings`, `LOWER_CONTINUATION_SETTINGS` | `std_distribution` overrides for the lower segment; under a continuation, the classifier lever (`num_std` 3.0) | §14.10.1, §14.11, §14.15 |
| `TRUNCATED_WINDOW_1790`, `TRUNCATED_ANCHOR_POINTS_1790_CM1` | The truncated-array experiments and their edge anchors | §14.16–§14.18 |
| `FULL_ROI_ANCHOR_POINTS_SEVEN_CM1` | Seven anchors on an uncut full ROI | §14.20 |
| Two-endpoint `LOWER_ANCHOR_POINTS_CM1` = `(1955, 1750)` | Exactly two anchors, hit exactly, which made the seam predictable from the upper residual alone | §14.10, §14.10.1 |
| `int_shared`, `INT_SHARED_WINDOW_CM1` | `int` restricted to the samples a truncated variant also covered | §14.16 |
| `seam_excess_jump` | The seam with the grid step removed, so a continuous continuation could be compared against a spliced form | §14.14, §14.15 |
| `LOWER_MID_PROBE_CM1` | The 1800 drift probe — 1800 is now an anchor | §14.10.1 |
| `LOWER_METHOD_CANDIDATE`, `LOWER_FLOOR_POINT_CM1`, `LOWER_CONTINUATION_LAM` | The named defaults for the above | §14.12–§14.15 |
| `BaselineVariant.is_default_window`, `BaselineOutcome.anchor_note` | Helpers with no callers | — |

Consequences worth knowing:

- **The seam is no longer predictable before the run.** With exactly two lower
  anchors it was minus the anchored baseline's residual at the cut (§14.10.1
  finding 21). The selected form has five, so the lower correction is a
  least-squares pull and that identity does not hold (§14.19). The
  predicted-vs-actual probe `__main__` used to print is gone with it.
- **`seam_pct_of_range` is the seam column again.** `seam_excess` existed only
  to compare a continuous form against a spliced one; for two independent
  segments the two were within rounding of each other anyway.
- **The positional tuple is now at most 6 slots**,
  `(label, settings[, window[, anchors[, lower_split_cm1[, lower_anchors]]]])`.
  §10's eight-slot signature is historical.
- **The CSV lost 8 columns**: `split_form`, `lower_method`, `lower_cont_lam`,
  `lower_cont_pts`, `lower_floor`, `floor_seam_pct_of_range`,
  `seam_excess_pct_of_range`, `int_shared`. Nothing downstream reads this file,
  so it is not the output contract `CLAUDE.md` protects — that one is the
  `*_Carbonyl*` files, which this package never writes.
- **The figure legend drops the cut-form tag**: `split 1955 lower_only (seam …)`
  became `split 1955 (seam …)`, there being one cut form. §14.22's three
  commented-out comparison variants are unchanged, so restoring the comparison
  is still uncommenting three lines.

### 15.3 Verification of the cleanup

There is no test suite, so this followed `CLAUDE.md`'s convention: run against
real data and diff the output. The selected form ran on the eight judged files
before and after.

| Check | Result |
|---|---|
| Baseline curves, all 8 judged files | **bit-identical** — per-file `sum` / `min` / `max` to 12 significant digits |
| Every surviving CSV column | identical; only the 8 columns of §15.2 dropped, none added |
| `upper_max_abs_diff` with an unsplit twin present | **0.0e+00** on all 8 files — re-checked by adding `anchored` plus both cut variants, since the selected form alone reports `nan` |
| Guard on `...-022`, both files | still fires **twice** — `anchors_gated = 1955` *and* `split_gated = 1955`, `split` blank, `lower_anchors` blank, `seam_pct_of_range` `nan`, result identical to `anchored` |
| Degenerate flag | forced with `num_std: 0.8` on `...-008_delta10.0042`, the reproducer named in `DEGENERATE_WARNING`: `degenerate` `True`, `degenerate_segments == ("full",)`, CSV column `True`, counted in `summary()`. The flag survives the restructured in-place path; it fired in no other run |
| `ruff check src/` | no new findings; **zero `F821`**, and no unused imports in `ir_fitting` |
| `src/visualizations` imports | `plot_baseline`, `plot_individual_fit`, `_axes` all import clean |

`src/analysis`, `src/instrument`, `runner.py`, `writer.py`, the fit path
(`fit_file` / `fit_folder` / `load_measurement`) and §4's dormant extra-peaks
workstream were not touched. No `config/analysis.yaml` default, production ROI
or live baseline changed — as at every point in §14.

---

## 16. The CLI — what is exposed, and what is not

`scripts\run_baseline_experiment.py` → `src/utils/ir_fitting/baseline_cli.py`,
wrapping `api.compare_baselines`. Built when the next workstream (curve fitting
on top of this package) made the baseline recipe something to sweep rather than
something to settle, which is the condition §12 named.

**With no arguments it is §14.22**: the selected form alone, on the eight judged
files, under `run_name = lower_anchors_1955`. That was the acceptance gate —
see §16.3.

### 16.1 The inventory — everything that feeds the selected baseline

| # | Input | Selected value | Was a knob? | Changed in §14? | Exposed? |
|---|---|---|---|---|---|
| 1 | `settings` (`std_distribution` params) | `voigt_fit.baseline`, unmodified | yes | swept twice, **nothing changed** | **no** |
| 2 | `window` | `(2250, 1750)` | yes | truncations tried, all rejected | **yes** |
| 3 | `anchors` | `DENSE_UPPER_ANCHOR_POINTS_CM1` | yes | **yes** | **yes** |
| 4 | `lower_split_cm1` | `1955` | yes | **yes** | **yes** |
| 5 | `lower_anchors` | `(1955, 1790, 1800, 1810, 1820)` | yes | **yes** | **yes** |
| 6 | `ANCHOR_GUARD_CM1` | `25.0` cm⁻¹ | **no** — function default | introduced, never swept | **yes** |
| 7 | `ANCHOR_PROMINENCE_FRAC` | `0.5` of ROI range | **no** — function default | introduced, calibrated once | **yes** |
| 8 | `anchor_data_value(half_width)` | `10.0` cm⁻¹ | **no** | never touched | no |
| 9 | reporting windows (`MID_*`, `UND_*`, `INT_*`, `REPORTED_BANDS_CM1`) | — | no | — | no |

Rows 6 and 7 are the answer to *"is there anything else we exposed"* — and
strictly they were never exposed at all. `gating_extremum`'s two thresholds were
used by every caller and overridden by none, so exposing them meant new
`BaselineVariant` fields threaded through `apply_anchors` and the cut's own
gate, not a flag.

**Why 1 is not a flag.** It was swept twice and nothing was recommended (§14.3
finding 1, §14.11), so a flag would invite re-running a settled question. It
remains reachable as `BaselineVariant(settings=...)`. It would also be a trap:
`settings` reaches the **upper** curve only — `_compute_lower_split` hands the
lower segment the unmodified `voigt_fit.baseline` on purpose, and
`lower_settings` was removed in §15.2. The `--help` epilog says so.

**Why 8 and 9 are not flags.** 8 decides *where* an anchor lands, not *whether*
it survives, and §14 never touched it. 9 is measurement rather than
construction: changing one changes what a number means, not what the baseline
is — and §14.16 finding 48 is the worked case of a window change making a metric
incomparable under an unchanged name.

### 16.2 Things the flags have to preserve

- **`--anchors` keeps order and duplicates.** The default set contains `2006`
  twice on purpose, for double weight in the least-squares correction (§14.21,
  §15.1). The parser builds an ordered list and never deduplicates, sorts or
  rejects a repeat. Checked directly.
- **The guard values are part of `_recipe_key`.** Two variants with identical
  `anchors` but different thresholds can gate *different* anchors, so they are
  not each other's unsplit twin. Keying without the guards would measure
  `upper_max_abs_diff` against the wrong curve and print PASS — the one failure
  that check exists to catch.
- **One guard, three gate sites.** `--anchor-guard-cm1` / `--anchor-prominence-frac`
  configure each full-ROI anchor, each lower anchor **and** the cut together.
  The anchor guard and the cut guard are two verdicts from one test (§14.22); a
  variant that set them apart would not be the form §14 measured.
- **`--with-twin` is the flag that pays for the CLI.** §14.22 records
  `upper_max_abs_diff` as **NOT CHECKED**, because the check needs an unsplit
  twin with the *same* anchors and `anchored` carries the three-point set.
  `--with-twin` synthesizes an uncut variant from this run's own window, anchors
  and guards, placed immediately before the candidate — so the twin table sees
  it, and `current` stays the reference under `--compare` where §14.21's colours
  depend on the order. Measured: **0.0e+00 on all eight files, PASS**, the first
  time the selected form has been checked rather than asserted.
- Two new CSV columns, `anchor_guard_cm1` and `anchor_prominence_frac`. Without
  them an empty `anchors_gated` cannot be told from a threshold raised until
  nothing gates. Nothing downstream reads this file (§15.2).
- **`--with-twin` shifts every trace's colour by one.** `plot_baseline.py`
  assigns `tab10[index % 10]` by position in the variant list, so inserting the
  twin ahead of the candidate gives the *twin* `tab10[0]` and the candidate
  `tab10[1]`. §14.22's "the candidate takes `tab10[0]` and is blue" therefore
  describes the no-argument run only; under `--with-twin` the blue trace is the
  uncut twin and the candidate is orange. Nothing about the baselines changes —
  this is a reading note for the figure, and the legend names both traces.
  `--compare` is unaffected: `current` is still first and still blue.

### 16.3 Verification

Repo convention — run against real data and diff (`CLAUDE.md`). The pre-CLI
`__main__` was run on the eight judged files first and kept.

| Check | Result |
|---|---|
| No-argument CLI vs. the pre-CLI `__main__` | 8 rows; **every pre-existing column identical value-for-value**; exactly the 2 guard columns added, none dropped |
| The three-target report block | **character-identical** |
| `NOT CHECKED` still printed with one variant | yes |
| Guard on `...-022`, both files | still fires **twice** — `anchors_gated` and `split_gated` both 1955, `split` blank, `lower_anchors` blank, `seam` `nan` |
| Degenerate baselines | 0, as before |
| `--with-twin` | `upper_max_abs_diff` **0.0e+00** on all 8 files → **PASS** instead of NOT CHECKED. Read it as 6 + 2: on the six ungated files this is the real check that the splice left the region above the cut untouched; on the two `...-022` files the cut is gated, so there is no second segment and 0.0 is trivially true rather than a measurement (§14.22's "read the six ungated files") |
| `--compare` | reproduces §14.21's four traces in order, `lower split 1955` PASSes against `anchored` |
| `--anchor-prominence-frac 0.9` | `...-022` **stops** being gated (it scores 0.75–0.82) and gains a cut + lower segment |
| `--anchor-prominence-frac 0.2` | `...-021` **becomes** gated (it scores ≤ 0.24) and falls back to the uncut form |
| `--anchor-guard-cm1 5` | `...-022` stops being gated — its band at 1942 is 13 cm⁻¹ from the anchor, outside ±5 |
| Both gates move together in every sweep | `anchors_gated` and `split_gated` never disagree |
| `--anchors` duplicate `2006` | survives parsing, twice; order preserved, not sorted |
| Bad `--window`, out-of-window anchor, `--lower-anchors` above the cut, negative guard, zero prominence, out-of-range cut | each rejected at variant construction with the existing message |
| `ruff check src/utils/ir_fitting/` | zero `F401`; the 3 remaining `BLE001` are the pre-existing deliberate catches |

No `config/analysis.yaml` default, production ROI, live baseline or output
schema changed. `src/analysis`, `src/instrument`, `runner.py`, `writer.py`, the
fit path and §4's dormant extra-peaks workstream were not touched.

### 16.4 Printed output trimmed

A no-argument run printed 121 lines. About 60 were fixed prose explaining each
column, the table had ~25 columns and wrapped, and three follow-up blocks
repeated numbers already in it (`mid`/`und`/`int`, the seam and `lower_moved`
each printed twice; the missing-twin warning printed once **per file**). All of
it was already in `baseline_comparison.csv` or in this spec. The user asked for
it cut and for the prose deleted outright rather than hidden behind a flag.

What `print_summary` prints now, after the unchanged pre-run block
(`Files ->`, `Variants ->`, `Writing to ->`):

1. One table, one row per file × variant: `file, variant, gated, seam, mid,
   pre, und, int, n, h2040, h1980`. `gated` merges `anchors_gated` and
   `split_gated`. `n` is kept beside `int` (§14.16 finding 48); `rng` was
   dropped. `h2040_x_ref`, `h1980_x_ref` and `moved` are added only with two
   or more variants. With one variant they are 1 / 1 / 0 by construction, and
   leaving them out replaces the old ONE VARIANT warning.
2. `upper check: PASS / FAIL (worst …e…) / NOT CHECKED -- add --with-twin`.
   This is still an exact-zero test printed in `.3e`.
3. `gated: <files>`, printed only when something was gated.
4. `CSV -> <path>`, or `not saved`. The duplicate `Output ->` line is gone.

`compare_baselines` now logs the missing-twin warning once per variant label
per run, with the text unchanged.

§16.3's "three-target report block character-identical" check no longer
applies, because that block is gone. Across runs, compare the CSV instead.
Verified: with `--no-plot`, the no-argument, `--with-twin` and `--compare`
runs each produce a `baseline_comparison.csv` byte-identical to the pre-trim
run. Printed length went 121 → 25, 126 → 37 and 202 → 65 lines. The verdicts
are unchanged: NOT CHECKED with no arguments, PASS with `--with-twin` and
`--compare`. Both `...-022` files are listed as gated.
