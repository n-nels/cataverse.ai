# Nucleation Classifier

Status: **in design.** Ground truth, aggregation policy, and architecture
constraints are settled (§4). The detection-logic redesign itself has not
started (§6) — that is the remaining work.

## 1. Purpose

`classify_trajectory()` in `src/analysis/kinetics_fitting.py` (lines 306-334)
classifies a `cluster_sum` peak-area trajectory as `continuous` or
`discontinuous` by looking for a flat window followed by a sustained rise.
It does a good job on the data it was tuned on (`nn1120-3_pd_ceo2_003/004`),
but is not robust on newer data (`nn1120-4_pd_ceo2_000`), where it currently
detects nothing. This document specifies a replacement/extension, developed
and validated offline in `src/utils/` before any change reaches the live
real-time path.

## 2. Data model

- `X:\peakFit\` holds 288 `*_CarbonylPeakArea.csv` files across 7 sample
  folders (an 8th, `_test`, holds reprocessing output and is excluded).
- Each CSV is long-format: one row per `(Peak_Name, Time (s))` [duplicated
  across `Delta_Group`], with `Cumulative_Peak_Area` as the intensity
  metric. `Peak_Name` includes individual peaks (named by shifted
  wavenumber, e.g. `Peak_1975`) plus two synthetic rows: `cluster_sum` and
  `monomer_sum`.
- `classify_trajectory()` runs **only** on `cluster_sum` — never
  `monomer_sum`, never individual peaks (`_prepare_pfo_fit_rows`,
  kinetics_fitting.py:522-606, gated by `sum_names = ["cluster_sum"]`).
- Cluster peaks (`config/analysis.yaml`, `cluster_peaks_base`, 12CO base,
  shifted -50 cm-1 for 13CO): base `[2123,2112,2100,2090,2080,2065,2050,
  2038,2025]` maps to shifted `[2073,2062,2050,2040,2030,2015,2000,1988,
  1975]`. `Peak_2000`/`Peak_1988`/`Peak_1975` (the fallback signal
  candidates) are the three lowest-wavenumber members of this list,
  already summed into `cluster_sum`; they are not a separate measurement.

## 3. Ground truth

All 288 files are labeled. **48 discontinuous, 240 continuous** (was 47/241 —
see the 2026-09-11 correction in §4).

| Folder | Files | Discontinuous | Basis |
|---|---|---|---|
| `nn1120-3_pd_ceo2_003` | 117 | 14 | Matches existing algorithm, batch mode |
| `nn1120-3_pd_ceo2_004` | 34 | 10 | Matches existing algorithm, batch mode, except one user correction (§4) |
| `nn1120-4_pd_ceo2_000` | 33 | 24 | User-declared (existing algorithm says 0) |
| `nn1120-2_pd_ceo2_000` | 33 | 0 | User-confirmed, matches existing algorithm |
| `nn1120-3_pd_ceo2_000` | 10 | 0 | User-confirmed, matches existing algorithm |
| `nn1120-3_pd_ceo2_001` | 57 | 0 | User-confirmed, matches existing algorithm |
| `nn1120-3_pd_ceo2_002` | 4 | 0 | User-confirmed, matches existing algorithm |

The 23-file reference set (`nn1120-3_pd_ceo2_003/004`) reproduces exactly
what `classify_trajectory()` already gets right when run once on each
file's complete trajectory (batch mode) - see §5. Within
`nn1120-4_pd_ceo2_000`, 9 of 33 files are short (11-17 hr vs. the typical
52+ hr) with near-zero or negative signal throughout and are labeled
continuous; the remaining 24 are labeled discontinuous by domain judgment,
not algorithmic agreement.

The exact per-file list is not restated here - it is a volatile inventory
that will drift as this dataset expands, and belongs in the ground-truth
data file produced in §7 step 2, not in prose that will go stale.

## 4. Decisions made

For a decision that touches the detection/classification mechanism itself (not
a scope, process, or architecture-boundary choice), state the mathematical or
logical mechanism explicitly - the equation, threshold rule, or condition, and
why it produces the observed effect - not just the decision and its measured
outcome. Scope/process decisions (what's in/out, where code lives, naming) don't
need one.

- **2026-09-11 - Ground truth is user-declared for `nn1120-4_pd_ceo2_000`,
  not derived.** The existing algorithm gives zero algorithmic labels
  there; the 24/9 split (§3) is a domain judgment.
- **2026-09-11 - Classification label names may change.** "continuous" /
  "discontinuous" may be renamed to better reflect the physical process
  once the mechanism is better understood. Not blocking.
- **2026-09-11 - Aggregation policy: monotonic once triggered.** Once a
  trajectory is classified discontinuous, it stays discontinuous for the
  rest of that run, regardless of later data. Rejected alternative:
  unweighted majority-vote-over-history - moot, since it would have
  misclassified 17 of the 23 reference files (induction periods are
  usually longer than the elevated period that follows, so whole-history
  voting favors "continuous" on real positives). Verified safe on the
  reference set in §5.
- **2026-09-11 - Classifier is data-only.** No material/sample identity,
  external metadata, or per-material calibration as inputs. Must
  generalize from the measured trajectory alone.
- **2026-09-11 - Architecture may use if/then branches, but only on data.**
  A single unified metric is preferred but not required. Multi-rule
  (if/then) detection is acceptable, including as a way to handle
  genuinely different physical regimes - provided branch selection is
  computed from the trajectory itself (shape, peak-emergence pattern),
  never from an externally supplied material/sample label. If branches
  happen to align post hoc with which physical sample produced the data,
  that is evidence the branches are physically meaningful, not license to
  key off sample identity directly.
- **2026-09-11 - Deliverable: this spec plus a working prototype**, not
  spec-only. The prototype modifies `src/utils/kinetic_fit_writer.py` (and
  or `src/utils/kinetics/`) in place - the offline/reprocessing context -
  not `src/analysis/kinetics_fitting.py` (the live real-time path).
  Iterate against real recorded CSVs first; port a proven approach into
  the live workflow later, as separate future work (§7).
- **2026-09-11 - Output convention: per-folder `_test`, matching existing
  code.** `kinetic_fit_writer.py` already writes to
  `X:\peakFit\<folder>\_test\<file>.csv`
  (`legacy_path.parent / output_folder_name`); no change needed.
- **2026-09-11 - Aggregation policy amended: require 3 consecutive fires
  before latching, not 1.** Resolves §6.0. The two known transient false
  positives in `nn1120-3_pd_ceo2_003` (`...-097`, `...-115`) fire in isolated
  runs of at most 2 consecutive prefixes before reverting; requiring 3
  consecutive `discontinuous` classifications before the monotonic latch
  engages sits just above that measured noise ceiling and eliminates both.
  Implemented as `REQUIRED_CONSECUTIVE_FIRES = 3` /
  `ever_fires(..., required_consecutive=3)` in
  `src/utils/kinetics/validation.py`. Net effect on the 288-file harness:
  264/288 -> 265/288 overall, false positives 2 -> 0. Cost: one previously-
  correct file, `nn1120-3_pd_ceo2_004-014`, stopped latching - its fires are
  intermittent (isolated single hits at prefixes 82/85/88/90, then only a
  run of 2 at 92-93 before the trajectory ends) rather than a clean sustained
  transition, so it never reaches 3 in a row. This is a real trade, not a
  free fix: the threshold is calibrated to the two known noise cases, not to
  every borderline true positive, and a future round changing the underlying
  detector (§6.2) should re-check this threshold rather than assume it still
  holds.
- **2026-09-11 - Bug fix: remove the single-file debug filter.**
  `process_carbonyl_peak_area_files` (kinetic_fit_writer.py, ~line
  1690-1692) contained a line skipping every file except one specific
  filename, an inverted single-file debug filter left over from
  2026-04-15, misleadingly logged as "Skipping known problematic file."
  This broke the entire "reprocess a folder" workflow the prototype
  depends on. Removed. **Correction (2026-09-11, iterate round 1):** this
  had not actually been removed yet as of the start of that round - the
  line was still live. It is now. It never affected
  `src/utils/kinetics/api.py` (which calls `write_model_fit_params`/
  `write_pfo_classification` directly), only the
  `process_carbonyl_peak_area_folder` entry point.
- **2026-09-11 - Ground truth correction: `nn1120-3_pd_ceo2_004-032` is
  `discontinuous`, not `continuous`.** User correction, direct instruction
  ("004-032 should be discontinuous"), overriding the prior
  `algorithm_batch_matches_existing` basis. This file was flagged in round 3
  of `docs/JOURNAL.md` as one of three files where the new
  `detect_discontinuity_drawdown` rule fired against a `continuous` label -
  it turns out the label, not the detector, was wrong here. Updated in
  `src/utils/kinetics/ground_truth.json` (`basis` now
  `user_corrected_2026-09-11`); `nn1120-3_pd_ceo2_004`'s count moves 9->10
  discontinuous, folder total 47->48 overall. Re-running the harness with
  `classify_trajectory_combined` moves the full-harness result
  284/288 -> **285/288** immediately (the false positive on this file is now
  a correctly-fired true positive) - no detector change required. Two
  mismatches remain: `nn1120-3_pd_ceo2_003-109` (still an unresolved false
  positive) and `nn1120-3_pd_ceo2_004-014` (the intermittent-flicker miss
  from round 2/§6.0). `docs/JOURNAL.md` round 5 has the harness output.
- **2026-09-11 - Ground truth confirmed correct for `nn1120-3_pd_ceo2_003-109`:
  `continuous`, label stands.** Unlike `..._004-032` above, this one was
  checked with the user directly rather than assumed. Trajectory: rises
  0.285->1.197 (peak at ~t=58000s, roughly the run's midpoint out of
  113699s total), then eases to 0.958 by the end - a ~20% pullback from
  peak, but ending >3x above its starting value, not back near baseline
  like the genuine `nn1120-4_pd_ceo2_000` rise-then-decay positives. User
  confirmed this is `continuous`: a mild late pullback after sustained
  elevated growth, not a reversal event. This makes the drawdown rule's
  fire here a genuine detector-precision gap (the rule's `drawdown_delta`
  threshold is too sensitive to a partial pullback), not a ground-truth
  problem - do not revisit this label again without new evidence.

## 5. Verification to date

**Monotonic-once-triggered preserves the 23-file reference set.** Confirmed
by running `classify_trajectory()` over every growing prefix (not just the
real-time pipeline's actual sampling checkpoints) of each of the 23
reference trajectories and checking whether "discontinuous" appears at any
prefix length. Since the full-length prefix is exactly the already-verified
batch call (23/23 correct), and monotonic-once-triggered only needs the
flag to appear once, ever, this holds by construction - and is strictly
safer than reading the on-disk CSV's literal final row, since a few
reference files transiently revert mid-run before re-triggering.

**Monotonic-once-triggered does not close the `nn1120-4_pd_ceo2_000` gap.**
The same full-prefix-sweep simulation against all 33 files in that folder
(would the existing detection logic have fired at any prefix length, under
monotonic-latch aggregation?) shows:

- Of the 24 files labeled discontinuous, only 2 ever trigger the existing
  logic, at any prefix length. The other 22 never fire, at any amount of
  data - a detection-logic gap, not an aggregation/timing problem.
- Of the 9 files labeled continuous, all 9 correctly never trigger (no
  false positives from the current logic).

**Mechanism.** `detect_discontinuity()` (kinetics_fitting.py:211-243)
requires the trajectory's final ~5% to remain elevated relative to the
detected flat-window baseline (`tail_mean < baseline + rise_delta` implies
rejected). Coarse time-binned sampling of `nn1120-4_pd_ceo2_000` shows
`cluster_sum` characteristically rising sharply mid-run and then declining
back toward zero (or below) by the end - the opposite shape from the
reference files, where it rises and stays elevated. A rise-then-decay
shape fails the tail-elevation check regardless of how large the mid-run
rise was. The decline is peak-selective, not uniform: the three
lowest-wavenumber cluster peaks (`Peak_2000/1988/1975`) decline the most,
the other six cluster peaks less, and non-cluster peaks least - suggestive
of a real chemistry process rather than generic drift, but not proven (see
§6.1).

**Refined mechanism (2026-09-11, iterate round 3).** The rise-then-decay
`nn1120-4_pd_ceo2_000` trajectories have **no flat lead-in at all** - they
rise from the first recorded point (t~420s), peak in the first ~10-20% of
the run, then decay almost monotonically for the remaining tens of thousands
of seconds. This is a single rise-then-decay hump, not a level shift, and
`find_flat_transition()` locking onto a late, spurious flat window (the
round-2 finding) is a *symptom* of scanning for a flat window that was never
going to exist near the true event - not a search-order bug to patch. See
`docs/JOURNAL.md` round 3 for the diagnostic detail and the new
`detect_discontinuity_drawdown()` detector this motivated.

## 6. Open questions

### 6.0 Resolved - see §4 ("Aggregation policy amended: require 3 consecutive
fires before latching, not 1.")

Was: does monotonic-once-triggered latch onto transient false positives? Yes -
2 of 117 files in `nn1120-3_pd_ceo2_003` fired `discontinuous` at an
intermediate prefix, invisible to the batch-mode evaluation §5 used to
"verify" the aggregation policy. Fixed by requiring 3 consecutive fires
before latching, calibrated to the measured noise ceiling (max consecutive
run = 2) of those two files. Cost one previously-correct file
(`nn1120-3_pd_ceo2_004-014`, an intermittent/flickering true positive) - see
§4 for the full trade-off. Any future change to the detector itself (§6.2)
should re-run the harness and re-check whether 3 is still the right
threshold, since it was calibrated against the old detector's noise
characteristics, not a property of the data independent of the detector.

### 6.1 Is the late-run decline chemistry or instrument drift?

- **Missing:** A true zero-signal control peak to rule out generic
  baseline drift. `Peak_1775`/`Peak_1795` were tried as controls but are
  absent from the sampled files.
- **What it takes:** Re-run the peak-selective decline check (§5) across
  all 24 positive files in `nn1120-4_pd_ceo2_000` (only 3 were sampled so
  far) with a peak that reliably has data in this folder, or ask the user
  directly whether a known physical process (sintering, ripening,
  restructuring) explains it.
- **When it stops being deferrable:** Before the detection logic leans on
  the decline shape itself as a positive signal (rather than merely
  tolerating it) - if it's drift, building a detector around it will not
  generalize to other datasets.

### 6.2 Detection-logic redesign

- **Missing:** An actual replacement/extension for `detect_discontinuity()`
  that fires on the 23 currently-undetected `nn1120-4_pd_ceo2_000` files
  (22 originally, +1 after the §4/§6.0 aggregation change) without producing
  false positives on the 241 labeled continuous.
- **Tried and failed (2026-09-11, iterate round 2):** relaxing the tail-
  elevation check alone (`detect_discontinuity_sustained_rise` /
  `classify_trajectory_sustained_rise` in `kinetic_fit_writer.py`, tolerating
  a later decay instead of requiring the trajectory to still be elevated at
  its very end) barely moved the needle (264/288, net *worse* than the
  265/288 baseline - 1 new true positive, but 1 new false positive and 1 new
  miss). Root cause: `find_flat_transition()` itself locks onto the wrong
  "baseline" window on rise-then-decay trajectories - it returns the first
  flat-then-nonflat pair scanning forward from `MIN_FLAT_START_S`, which for
  these files is often a coincidentally-flat stretch found *after* the real
  rise-and-decay has already happened, not the true early induction period.
  E.g. `..._000-002`: chosen baseline window at t=124498-144297s (baseline
  0.385) vs. the trajectory's actual range of 0.205-1.376 across
  t=420-187498s - the entire >1.0-unit rise (9x `rise_delta`) happens before
  the window the algorithm picked as "flat." Both of round 2's proposed
  fixes assumed a real early flat baseline exists to anchor to or search
  for - **round 3 found that it doesn't** (see next entry); neither should
  be pursued as originally framed.
- **Largely solved (2026-09-11, iterate round 3) - different mathematical
  approach, per direct user instruction not to stay confined to a windowed
  search.** Diagnosis: the `nn1120-4_pd_ceo2_000` trajectories have no flat
  lead-in anywhere - they rise from the first recorded point, peak early,
  then decay almost monotonically to the end. A single rise-then-decay
  **hump**, not a level shift. New detector,
  `detect_discontinuity_drawdown()` in `kinetic_fit_writer.py`: no forward
  window search - two purely causal running quantities on the smoothed
  trajectory-so-far, `rise_magnitude` (running max minus the minimum at or
  before it) and `drawdown` (running max minus the current value), both
  must exceed a threshold. Alone, this rule gets **all 33 files in
  `nn1120-4_pd_ceo2_000` correct**. Combined with the original
  `detect_discontinuity` via OR (`classify_trajectory_combined` -
  spec §4's if/then-branches-on-data-shape is exactly this), full-harness
  result: **284/288** (up from 265/288). Remaining gap: 1 known intermittent
  miss (§4/§6.0's `..._004-014`) plus 3 new false positives from the
  drawdown rule - large, sustained real humps in `continuous`-labeled files,
  not noise (checked: they fire on 9/15/86 consecutive prefixes, so not an
  aggregation-threshold problem). A `drawdown/rise` ratio separates 2 of the
  3 from the true-positive distribution but not the third
  (`..._004-031`, ratio 1.8, inside the true-positive range of 0.74-5.0) -
  not committed to code, since it would be a knife-edge partial fix. See
  `docs/JOURNAL.md` round 3 for full detail.
- **Tried and mostly failed (2026-09-11, iterate round 4).** The
  `drawdown/rise` ratio above was computed non-causally, at full trajectory
  length - re-derived causally (ratio at the actual prefix where the
  drawdown rule first fires, as the real-time pipeline would see it), the
  separation vanishes entirely: true-positive range 0.068-0.648 vs. false
  positives at 0.141 and 0.761, both inside/above that range. Not a real
  discriminator; dead end. Per-peak decline
  (`Peak_2000`/`Peak_1988`/`Peak_1975` vs. the other six cluster peaks,
  relative drawdown) fares partway better - separates `..._003-109` and
  `..._004-031` from all 24 true positives, but not `..._004-032` (0.709,
  inside the true-positive range) - and was also computed non-causally, so
  unverified for real-time use even where it does separate. See
  `docs/JOURNAL.md` round 4.
- **Ground truth correction (2026-09-11), see §4.** `..._004-032` is
  actually `discontinuous` - the drawdown rule firing on it was correct, the
  label was wrong. Harness result **284/288 -> 285/288** with no detector
  change. Two mismatches remain: `..._003-109` (false positive, still
  unresolved) and `..._004-014` (the intermittent-flicker miss, §4/§6.0).
- **What it takes:** `..._003-109`'s label is now confirmed correct (see
  above) - this is a real detector-precision gap, not a label issue. The
  drawdown rule needs to distinguish "mild pullback after sustained
  elevated growth, ends far above baseline" (`..._003-109`, continuous)
  from "rise then genuine reversal toward original baseline"
  (`nn1120-4_pd_ceo2_000` positives, discontinuous). Two tried features
  don't do this (causal ratio, per-peak decline - round 4). A feature based
  on *how far back toward the starting/pre-rise baseline* the drawdown goes
  (not just its absolute or peak-relative size) is untried and is the
  natural next candidate, given `..._003-109` ends >3x its starting value
  while genuine positives decay back to near-zero/original baseline.
- **When it stops being deferrable:** Very close - 285/288, one confirmed
  detector-precision gap (`..._003-109`) plus one unrelated intermittent
  miss (`..._004-014`), neither a systemic failure.

## 7. Approach

1. Fix the filter bug in `kinetic_fit_writer.py` (§4 - done).
2. Persist the ground-truth labels (§3) as a plain data file, not prose
   here - a two-column (`file`, `label`) CSV or JSON covering all 288
   files, likely under `src/utils/kinetics/` alongside the code that
   consumes it.
3. **Done (2026-09-11, iterate round 1).** Validation harness:
   `src/utils/kinetics/validation.py::run_validation()`. Recomputes
   classification from raw `Time (s)`/`Cumulative_Peak_Area` rows (never
   reads the `classification` column already present in the source CSVs),
   sweeps every growing prefix per file (`ever_fires()`), and reports
   matches against `ground_truth.json` under the monotonic-once-triggered
   correctness definition (§6.0). Baseline (unmodified `KineticClassification`):
   **264/288** - reproduces §3/§5's 2/24-ever-fire result in
   `nn1120-4_pd_ceo2_000` exactly, but also surfaces the 2-file leak in §6.0
   that batch-only ground truth had missed.
4. Iterate on `KineticClassification` (or a new sibling in the same
   module) using this harness. Starting material: the confirmed tail-
   elevation mechanism (§5), the peak-selective decline pattern in
   `Peak_2000/1988/1975` (already tracked individually, no new data
   needed), and the monotonic-once-triggered aggregation policy (§4,
   verified safe in §5).
5. Keep this spec updated as iteration proceeds - new decisions appended
   to §4, resolved items removed from §6.
6. Once a detection approach clears the full 288-file check, decide
   (with the user) whether/how to port it into the live path
   (`src/analysis/kinetics_fitting.py`) - out of scope until then.

**Verification:** the validation harness's match/mismatch report against
the 47/241 split (§3) is the acceptance test for any candidate - there is
no separate check beyond this. Before considering a candidate done, re-run
the full-prefix-sweep style check from §5 to confirm it doesn't merely pass
on final-state batch evaluation while still failing to trigger earlier
(relevant given the monotonic-once-triggered policy: what matters is
whether it ever fires, not just its last-row answer).

## 8. Non-goals

- Fixing the `kinetic_fit_writer.py` / `kinetics_fitting.py` duplication
  (already tracked in CLAUDE.md). Relevant because the prototype's home
  sits on the offline side of that exact duplication -
  `src/utils/kinetics/api.py::classify_file()` already calls into
  `kinetic_fit_writer.KineticClassification`, a separate copy of today's
  algorithm from the one this spec replaces/extends.
- Porting the new logic into `src/analysis/kinetics_fitting.py` (§7 step
  6) - out of scope for this effort.
