## Round 1 — 2026-09-11

**Setup.** This is the first round; `docs/prompt.md` was scaffolded this round
from `docs/spec.md` (spec was already fully written and decided through §4;
§6.2/§7 were the open work). Loop folder lives in `docs/` alongside the spec.

**What I did:**

1. Fixed the debug-filter bug spec.md §4 already claimed was "Removed" but
   wasn't: `process_carbonyl_peak_area_files` in `src/utils/kinetic_fit_writer.py`
   (around line 1690) still had `if "20260404_182647_pd_ceo2_004-012" not in
   str(csv_file): continue`, silently skipping every file except one. Deleted
   the guard. This only affects the folder-reprocessing entry point
   (`WRITER.process_carbonyl_peak_area_folder` / the module's `__main__`
   block) — it does not affect `src/utils/kinetics/api.py`'s `fit_file`/
   `fit_folder`, which call `write_model_fit_params`/`write_pfo_classification`
   directly and never went through this filter. So it wasn't actually
   blocking the harness (below), but it was a live landmine for anyone using
   the folder-reprocessing path, and the spec is now honest.

2. Built `src/utils/kinetics/validation.py`: `run_validation()` reads
   `ground_truth.json` (288 entries already present, built in an earlier
   session before this loop existed), and for each file recomputes
   classification *from scratch* from `Time (s)` / `Cumulative_Peak_Area`
   for `Peak_Name == "cluster_sum"` rows — it never reads the `classification`
   column that's already baked into the raw CSVs under `X:\peakFit\` from a
   prior real-time run (confirmed via `advisor()` before writing anything:
   reading that column would make the harness report a meaningless 288/288).
   Design choices, both deliberately matching what the existing pipeline
   already does so the harness measures the detector, not itself:
   - No dedup across `Delta_Group`. A `cluster_sum` trajectory is the
     concatenation of all delta-subtraction groups (delta5..delta10 in the
     one file I inspected), sorted by `Time (s)` only — nearby-but-not-
     identical values from different delta windows at close/equal times, not
     literal duplicates. This is exactly what
     `KineticWriter._classification_payload` already feeds
     `classify_trajectory` (groups by `Peak_Name` alone, sorts by time,
     no dedup), confirmed by reading that code before assuming.
   - `ever_fires()` implements "prefix sweep": calls
     `classify_trajectory(time_s[:k], intensity[:k])` for every
     `k` from `MIN_POINTS=4` to `len(trajectory)`, and reports True if
     `"discontinuous"` appears at *any* k. Per `docs/prompt.md`'s Y, this
     *is* the correctness definition under monotonic-once-triggered
     aggregation, not a secondary check.

3. Ran the harness with the **unmodified** `KineticClassification`
   (`kinetic_fit_writer.CLASSIFIER`) as a calibration step before trusting
   the harness at all:

   ```
   Overall: 264/288 correct
   Discontinuous: 25 correctly fired, 22 missed | Continuous: 239 correctly quiet, 2 false positives
     nn1120-2_pd_ceo2_000: 33/33
     nn1120-3_pd_ceo2_000: 10/10
     nn1120-3_pd_ceo2_001: 57/57
     nn1120-3_pd_ceo2_002: 4/4
     nn1120-3_pd_ceo2_003: 115/117  <-- mismatches here
     nn1120-3_pd_ceo2_004: 34/34
     nn1120-4_pd_ceo2_000: 11/33  <-- mismatches here
   ```

**What actually happened, and what it means:**

The `nn1120-4_pd_ceo2_000` numbers match spec §5 exactly: of 24
discontinuous-labeled files, 2 ever fire and 22 never do (0/9 false positives
among the continuous-labeled files there) — this is the detection-logic gap
spec §6.2 describes, reproduced independently by this harness.

The four "clean" folders (`nn1120-2_pd_ceo2_000`, `nn1120-3_pd_ceo2_000/001/002`,
144 files) are 100% correct, also as spec §3 claims.

`nn1120-3_pd_ceo2_003` is **115/117, not 117/117** — 2 continuous-labeled files
fire under the prefix sweep even though the existing algorithm has always been
believed to get this reference folder exactly right. I checked both files
individually (`20260115_215548_pd_ceo2_003-097` and
`20260212_225142_pd_ceo2_003-115`): batch (full-trajectory) classification
returns `"continuous"` for both, matching ground truth — but each fires
`"discontinuous"` at an earlier prefix (k=59/70 and k=47/71 points
respectively) before settling back to a flat/low tail by the end. This is
**not a harness bug**: spec §3's basis for this folder is explicitly
"Matches existing algorithm, batch mode" — i.e. ground truth here was
established by running the classifier once on the complete trajectory, which
never exercises the prefix sweep. Spec §5 already documents that "a few
reference files transiently revert mid-run before re-triggering" for
*positives*; this shows the same kind of transient also happens on some
*negatives*, and under monotonic-once-triggered latching, a transient false
trigger anywhere in the run is permanent. So the reference set spec calls
"already-verified" is only verified under batch evaluation, not under the
aggregation policy the spec actually adopted (§4) and that `docs/prompt.md`'s
Y is stated in terms of. This is exactly the asymmetry `docs/prompt.md`
was written to flag before any detector work started, and it surfaced
immediately on the very first calibration run — I did not expect it to show
up already on the *unmodified* baseline detector, only on a new one.

**Baseline correct-by-Y's-definition: 264/288.** This is the number future
rounds should beat, not the ~266/288 (117+34+104+11) implied by reading §3's
table as if it were a batch-only expectation.

**Calibration double-check (done after `advisor()` flagged two gaps in the
first pass):** the harness's `except` branch scores any read failure on a
continuous-labeled file as "correct" (`fired=False` == `label != "discontinuous"`),
and a trajectory with fewer than `MIN_POINTS=4` cluster_sum points never enters
the sweep loop and is also silently scored "correct" via the same path. Since
spec §3 mentions 9 short files in `nn1120-4_pd_ceo2_000`, this needed
checking, not assuming. Verified directly: (1) `ground_truth.json`'s
per-folder label counts match spec §3's table exactly - 14/103 in `_003`,
9/25 in `_004`, 24/9 in `_000`, and 0 discontinuous across the four clean
folders (33+10+57+4 continuous) - so the "reproduces spec" claim rests on a
measured match, not an inferred one; (2) zero files failed to load or had
fewer than 4 cluster_sum points, so no file's "correct" score this round came
from a silent skip. 264/288 stands as reported.

**What's next, and why:**

1. Two things are now tangled and need to be pulled apart before any detector
   redesign: (a) the 22-file miss in `nn1120-4_pd_ceo2_000` (the actual
   §6.2 gap — a real detection-logic problem, tail-elevation check rejecting
   rise-then-decay shapes per spec §5's mechanism), and (b) the 2-file leak in
   `nn1120-3_pd_ceo2_003` (a latent false-positive-under-latching problem that
   predates this loop and was simply never checked before). A fix for (a)
   that, e.g., loosens the tail-elevation requirement to tolerate decay is
   likely to make (b) *worse*, not better, since loosening the condition that
   currently protects continuous files raises exactly the kind of transient
   it would need to ignore. Any detector change has to be checked against
   both counts, not just the 22.
2. Worth flagging to the user before deep detector work: is "fires at any
   single prefix, ever" really the intended aggregation semantics, or should
   monotonic-once-triggered require some sustained/consecutive confirmation
   window before latching? Spec §4 decided monotonic-once-triggered was safe
   based on the reference set being clean under it — that assumption is now
   known to be false for 2/117 files in the reference set itself. This isn't
   blocking (the harness and Y definition are correct as specified), but the
   user may want to revisit the aggregation policy decision in light of this,
   rather than have every future round route around it silently.
3. Next round's actual detector attempt should start from spec §5's own
   lead: the peak-selective decline in `Peak_2000`/`Peak_1988`/`Peak_1975`
   (the three lowest-wavenumber cluster members) versus the other six cluster
   peaks, as a way to distinguish "real rise-then-decay chemistry" (should
   still count as discontinuous) from "noise-level late blip" (should not) —
   this needs per-peak trajectories, not just `cluster_sum`, which
   `validation.py` doesn't currently load. That's the natural next extension
   of the harness, not a rewrite of it.
4. Nothing was changed in `KineticClassification` itself this round beyond
   the harness and the unrelated bug fix — the detector redesign (spec §6.2)
   has not been attempted yet. Recorded as not-yet-done rather than stretched
   into a partial attempt, per the loop's own instructions not to blur "built
   the harness" with "fixed the detector."

## Round 2 — 2026-09-11

**Unlogged interim work since round 1 (done directly with the user, not via
another `/iterate` invocation, but never written up here — recording now so
the journal doesn't have a gap):** round 1 flagged §6.0 as an open question
(does monotonic-once-triggered latch onto transient false positives?). The
user's answer was to require sustained/consecutive confirmation before
latching, calibrated "just above the noise" of the two known transient
false-positive files. I measured their consecutive-fire run lengths directly
(`...003-097`: runs of 1 and 2; `...003-115`: runs of 1 and 1 — max run
across both is 2) and set `REQUIRED_CONSECUTIVE_FIRES = 3` in
`src/utils/kinetics/validation.py`, changing `ever_fires()` from "fires at
any single prefix" to "fires on 3 consecutive prefixes in a row." Result:
**264/288 → 265/288** overall, false positives **2 → 0**. Cost: one
previously-correct file, `nn1120-3_pd_ceo2_004-014`, stopped latching — its
fires are intermittent (isolated single hits, then only a run of 2 right at
the end of its recorded data) rather than a clean sustained transition, so it
never reaches 3 in a row. Logged as a decision in `docs/spec.md` §4 and
resolved §6.0 there (with the trade-off spelled out) at the same time.

**This round's actual goal: attempt the detector redesign itself (spec
§6.2)** — the 22 (now 23, after the round-1.5 aggregation change above)
`nn1120-4_pd_ceo2_000` files that never fire under the existing detector.

**What I tried:** spec §5's diagnosed mechanism is that `detect_discontinuity()`
rejects any trajectory whose final ~5% isn't still elevated above baseline,
and `nn1120-4_pd_ceo2_000` positives characteristically rise sharply mid-run
then decay back down by the end — so the tail-elevation check rejects them
regardless of how large the rise was. I added
`detect_discontinuity_sustained_rise()` / `classify_trajectory_sustained_rise()`
to `KineticClassification` in `kinetic_fit_writer.py`: same flat-window
detection (`find_flat_transition`, unchanged), but instead of requiring the
literal tail of the trajectory to stay elevated, it checks whether a
*smoothed* (4-point running-mean, reusing the existing `SMOOTHING_WINDOW`)
maximum anywhere *after* the detected transition ever exceeded
`baseline + rise_delta` — tolerating a later decay, as long as a sustained
(not single-point-noise) elevation happened at some point.

To test a second detector without duplicating the sweep/aggregation harness,
I generalized `ever_fires()`/`run_validation()` in `validation.py` to accept
any `classify_fn` callable (default `CLASSIFIER.classify_trajectory`) instead
of hardcoding the method name — this is a durable harness improvement
independent of whether this particular candidate works.

**What actually happened:** ran the full 288-file harness with
`CLASSIFIER.classify_trajectory_sustained_rise` as `classify_fn`:

```
Overall: 264/288 correct   (baseline was 265/288)
Discontinuous: 25 correctly fired, 22 missed | Continuous: 239 correctly quiet, 2 false positives
  nn1120-3_pd_ceo2_003: 115/117  <-- new false positive: ...003-097 came back
  nn1120-3_pd_ceo2_004: 33/34    <-- new false positive: ...004-009 (not previously wrong)
  nn1120-4_pd_ceo2_000: 12/33    <-- only 1 more true positive than baseline (was 11/33)
```

**Net regression, not an improvement** — it recovered only 1 of the 22
target files, broke the `...003-097` fix from earlier this round (the
sustained-rise variant has no `REQUIRED_CONSECUTIVE_FIRES` guard applied to
its own transient behavior — I ran it through the same `ever_fires()`, so
this means the relaxed detector reintroduces a transient fire pattern that
the confirmation-count guard doesn't fully suppress for this specific
trajectory shape), and introduced one brand-new false positive
(`nn1120-3_pd_ceo2_004-009`) that neither previous detector produced.

**Root cause, found by digging into why relaxing the tail check barely
moved the needle:** I checked `find_flat_transition()`'s actual output on
three of the still-missed files (`..._000-002/003/004`). It does find *a*
flat window and transition on all three — but for these rise-then-decay
trajectories, the flat window it locks onto is often not the true early
induction period, it's a quasi-flat stretch found much later in the run.
Concretely, for `..._000-002` (105 points spanning t=420s to t=187498s):
`find_flat_transition` returns a flat window at t=124498–144297s (deep into
the second half of the run) with `transition_end=149697s`, giving
`baseline=0.385`. But the trajectory's actual overall range is
`0.205` to `1.376` — a rise of over 1.0 units, more than 9x `rise_delta`
(0.11) — and that entire rise happened *before* t=124498s, i.e. before the
window `find_flat_transition` decided was "the" flat baseline. Everything
after its chosen transition (`post`, only 18 points, t=149697–187498s) is
already past the peak, in the decay tail, maxing out at 0.390 — barely above
its own late-window baseline, nowhere near the true peak. So my
sustained-rise check was comparing the wrong two things: a late,
already-decayed "baseline" against an even-later, still-decaying "post"
region. The actual rise is invisible to it because `find_flat_transition`
never identifies the *true* early induction period as "the" flat window in
the first place — it stops at the first flat-then-nonflat pair it finds
scanning forward from `MIN_FLAT_START_S`, and for these trajectories that
first pair isn't the induction-to-growth transition, it's some later
coincidentally-flat stretch. Same shape confirmed on `..._000-003` (baseline
0.328 from a window at 111898–131697s vs. overall max 1.038) and
`..._000-004` (baseline 0.888 from 23699–41699s vs. overall max 0.948 — here
the "post" segment actually does cover more of the trajectory, which is
presumably why this file came closer to firing than the other two, though it
still didn't).

**What's next, and why:** relaxing the tail-elevation *check* was necessary
but nowhere near sufficient — the real problem is upstream, in how the
"baseline"/induction-period window itself gets chosen. `find_flat_transition`
was designed for trajectories with one clean flat→rise transition; it has no
way to prefer an *early* flat window over a *later coincidental* one, and
rise-then-decay trajectories apparently have enough locally-flat stretches
after the real event that it locks onto the wrong one. Two candidate
directions for next round, not yet tried:
1. Anchor "baseline" to the trajectory's earliest available data (e.g. mean
   of the first `SMOOTHING_WINDOW` or first `MIN_FLAT_START_S` seconds of
   points) instead of searching forward for the first flat/non-flat pair at
   all — closer to how `q_0` is already fixed to the first observed point
   elsewhere in this codebase's secondary-PFO model (CLAUDE.md). Then check
   whether the trajectory *ever* (smoothed) rises `rise_delta` above that
   early baseline, regardless of where or whether a "flat window" is found
   later.
2. Keep `find_flat_transition` but bias it to prefer the *earliest* flat
   window that satisfies a minimum duration, rather than the first one
   encountered — needs care since "earliest" and "first encountered" should
   usually coincide; the actual failure mode above needs one more debugging
   step (why does the scan not stop at the true early induction period on
   these files?) before assuming which fix is right.
Either direction should be checked against all three known failure modes at
once now, not just the 22-miss count: the `nn1120-4` misses (§6.2), the two
original transient false positives in `nn1120-3_pd_ceo2_003` (§6.0), and
whatever `REQUIRED_CONSECUTIVE_FIRES=3` was calibrated against — changing the
baseline-selection logic changes the noise characteristics the "3" was tuned
to, per the caveat already written into spec.md §4/§6.0.

The new `detect_discontinuity_sustained_rise` / `classify_trajectory_sustained_rise`
methods and the `classify_fn`-parameterized harness are left in place
(harmless, not called by default) since the next attempt can reuse or
replace them without re-deriving the harness generalization.

## Round 3 — 2026-09-11

**Steering note for this round:** the user explicitly said not to stay
confined to a windowed-search approach and to consider different math. Before
writing any code, I called `advisor()`, which flagged that round 2's own
evidence already undercut its "anchor baseline to early points" idea: for
`..._000-004`, baseline 0.888 and overall max 0.948 — barely any headroom, no
obvious quiet start. It told me to print the first ~10 `(time, intensity)`
points of several missed files before designing anything, since if there's no
quiet early stretch either, "anchor to early points" fails the same way
`find_flat_transition` did, for a different reason.

**Diagnostic finding that reframed the whole round:** I printed the first 12
points, then a full coarse resample, of three still-missed
`nn1120-4_pd_ceo2_000` files. Result: **these trajectories have no flat
lead-in anywhere.** They rise steadily from the very first recorded point
(t≈420s), peak somewhere in the first ~10-20% of the run, then **decay
almost monotonically for the rest of the recorded time** (tens of thousands
of seconds), ending near zero. E.g. `..._000-002` (105 points, t=420 to
187498s): rises 0.845→1.373 by t≈14700s, then declines steadily all the way
to 0.312 by the end. This is not "flat, then rise" — it's a single rise-then-
decay **hump**. Round 2's diagnosis (wrong flat-window chosen) was correct as
far as it went, but its proposed fixes (anchor baseline to early points;
bias the flat-window search toward the earliest window) both assumed a real
early flat baseline exists to anchor to or search for. **It doesn't, for
these files.** Neither round-2 candidate direction should be pursued as
originally framed — recording this correction here per the loop's rule
against rewriting round 2's entry.

I also went back and looked at `20260115_215548_pd_ceo2_003-097` — the
"noisy blip" false positive from rounds 1-2 that's labeled `continuous`. Its
full trajectory (not just the tail I'd checked before) is a continuous,
noisy, **monotonically increasing** climb from 0.099 to 0.55 with no decay
at all, right to the last recorded point. That's consistent with a domain
reading of "continuous" I hadn't stated explicitly before: it means ongoing
single-phase growth, however large, as long as it never reverses — not
"small rise." That reading is exactly what a drawdown-based test would also
need to respect: magnitude of rise alone must not be sufficient; reversal
from a peak is the actual signal.

**New detector, genuinely different math from `find_flat_transition`:**
added `detect_discontinuity_drawdown()` to `KineticClassification` in
`kinetic_fit_writer.py`. No forward window search at all. It smooths the
trajectory (existing `SMOOTHING_WINDOW` running mean), then computes two
purely causal running quantities from the smoothed prefix:
- `rise_magnitude` = (running max so far) − (minimum value at or before that
  running max) — did it genuinely rise before peaking?
- `drawdown` = (running max so far) − (current/last value) — has it fallen
  back substantially from its own peak?

Fires `discontinuous` iff both exceed a threshold (`rise_delta` and
`drawdown_delta`, both defaulted to the existing `RISE_DELTA_DEFAULT=0.11`).
Both quantities use only `time_s[:k]`/`intensity[:k]` for whatever prefix `k`
is passed — confirmed causal so it's valid to run inside `ever_fires()`'s
growing-prefix sweep exactly like the original detector (`advisor()`'s
second point: a "global max vs. baseline" statistic evaluated only at full
length would pass the harness while being unimplementable in the live
pipeline; this isn't that).

Tested `classify_trajectory_drawdown` (this rule alone, no flat-window branch
at all) against the full 288-file harness:

```
Overall: 264/288 correct
Discontinuous: 26 correctly fired, 21 missed | Continuous: 238 correctly quiet, 3 false positives
  nn1120-4_pd_ceo2_000: 33/33   <-- every file in the target folder, correct
```

It gets **all 33 files in `nn1120-4_pd_ceo2_000` right**, alone — the exact
folder every previous detector failed on. It misses most of the
`nn1120-3_pd_ceo2_003/004` reference-set positives, as expected: those rise
and *stay* elevated (per spec §5), they don't decay, so a drawdown-only rule
has nothing to catch there.

**Combined detector** (`classify_trajectory_combined`): fires if EITHER the
original `detect_discontinuity` (flat-then-rise) OR the new
`detect_discontinuity_drawdown` (rise-then-decay) fires — an if/then branch
computed purely from the trajectory's own shape, which spec.md §4 explicitly
permits ("Architecture may use if/then branches, but only on data... to
handle genuinely different physical regimes"). Full harness, default
`REQUIRED_CONSECUTIVE_FIRES=3` inherited unchanged from round 2:

```
Overall: 284/288 correct        (was 265/288 going into this round)
Discontinuous: 46 correctly fired, 1 missed | Continuous: 238 correctly quiet, 3 false positives
  nn1120-4_pd_ceo2_000: 33/33
  nn1120-3_pd_ceo2_003: 116/117  <-- 1 new false positive
  nn1120-3_pd_ceo2_004: 31/34    <-- 2 new false positives, 1 pre-existing miss (...004-014, from round 2)
```

**284/288 — the best result so far, but Y (288/288) is not met.** Four
mismatches remain:
1. `..._004-014` — the intermittent-flicker miss already diagnosed in round
   2 (isolated single fires under the flat-then-rise rule, never 3
   consecutive). Unrelated to this round's work, unchanged.
2. Three new false positives from the drawdown rule:
   `nn1120-3_pd_ceo2_003/..._003-109`, `nn1120-3_pd_ceo2_004/..._004-031`,
   `.../..._004-032`. I checked whether these are noise-level blips fixable
   by raising `REQUIRED_CONSECUTIVE_FIRES`: no — they fire on 9, 15, and 86
   *consecutive* prefixes respectively, i.e. large, sustained, real humps in
   files ground truth calls `continuous`, not transients. This is a genuine
   detector-precision gap, not an aggregation-noise problem, so retuning the
   consecutive-fires threshold (which per round 2's own caveat was
   calibrated against the *old* detector and never re-checked for this one)
   would not fix it.

**Explored, not committed:** tried a `drawdown / rise` ratio as a possible
extra discriminator, computed non-causally (full trajectory) purely as a
diagnostic, not wired into the detector. Across all 24 `nn1120-4` true
positives the ratio ranges 0.74-5.00 (min 0.742). Two of the three false
positives fall clearly below that (`..._003-109`: 0.251; `..._004-032`:
0.607) — a ratio threshold around 0.7 would exclude them without excluding
any true positive. But the third, `..._004-031`, has ratio 1.800 — squarely
inside the true-positive range. A ratio cutoff cannot separate all three
false positives from all 24 true positives with only these two features
(rise, drawdown); it would fix at most 2 of 3 while risking new edge cases
near the 0.74 boundary. Didn't commit this to code — a knife-edge partial
fix that trades one known problem for a thinner, less-tested one isn't
progress, per the loop's own "don't fabricate a pass" rule.

**What's next, and why:** `..._004-031` needs a feature the trajectory's
overall shape alone doesn't provide. Spec §5's own lead — the peak-selective
decline in `Peak_2000`/`Peak_1988`/`Peak_1975` (the three lowest-wavenumber
cluster peaks decline more than the other six cluster peaks in genuine
`nn1120-4`-style events) — is exactly this kind of extra signal, and was
already flagged as the natural next step back in round 1 but still hasn't
been tried; it needs per-peak trajectories, which `validation.py` currently
doesn't load (only `cluster_sum`). That's the concrete next round: extend
the harness to pull individual peak trajectories per file, and check whether
`..._004-031`'s per-peak decline pattern looks different from the 24 true
positives' pattern — if it does, that's the discriminator; if it doesn't,
the "continuous" label on `..._004-031` itself may be worth a second look
with the user, the same way `nn1120-4_pd_ceo2_000`'s labels were originally
user-declared rather than algorithmic (spec §3/§4).

All new methods (`detect_discontinuity_drawdown`, `classify_trajectory_drawdown`,
`classify_trajectory_combined`) are additive in `kinetic_fit_writer.py` —
`classify_trajectory` (the original, still used by the live path per spec
§4's non-goals) is untouched.

## Round 4 — 2026-09-11

Per advisor: 2 negative results before per-peak work. (1) Threaded
`required_consecutive` into `run_validation` (was hardcoded); combined detector
at rc=1/2/3 stays 283-284/288 (rc=2 trades the `004-014` miss for `003-097` as
a new FP) — no free gain, rc=3 stands. (2) Round 3's drawdown/rise ratio was
computed non-causally at full trajectory length; recomputed at each fire's
actual prefix, separation vanishes (TP range 0.068-0.648 vs FP `003-109`=0.141,
`004-031`=0.761 — both inside/above the TP range) — dead end, not a real
discriminator. (3) Per-peak decline (low 3 vs other 6 cluster peaks, relative
drawdown) separates `003-109`/`004-031` from all 24 TPs but not `004-032`
(0.709, inside TP range); also non-causal, unverified for real-time use. No
detector change landed; 284/288 stands. Next: ask the user whether the 3
remaining FPs (all `basis=algorithm_batch_matches_existing`, same weak status
as round 1's `003-097`/`003-115`) are batch-only mislabels, or keep hunting a
real 4th feature.

## Round 5 — 2026-09-11

User, directly: "`004-032` should be discontinuous" - answering round 4's
open question for one of the three files. Corrected
`src/utils/kinetics/ground_truth.json` (`nn1120-3_pd_ceo2_004-032`:
`continuous`->`discontinuous`, `basis`->`user_corrected_2026-09-11`) and
`docs/spec.md` §3/§4 (folder count 9->10 discontinuous, 47/241->48/240
overall). Re-ran the harness (`classify_trajectory_combined`,
`required_consecutive=3`, no code change): **284/288 -> 285/288** - the
drawdown rule's fire on this file was correct all along, the label was wrong.
Two mismatches remain: `..._003-109` (false positive - round 4's causal-ratio
and per-peak-decline checks don't separate it either) and `..._004-014`
(intermittent-flicker miss, §4/§6.0, unrelated). `..._003-109` carries the
same `algorithm_batch_matches_existing` basis `..._004-032` had before this
correction - worth asking the user about that one too before more detector
work, per spec §6.2.

## Round 6 — 2026-09-11

Asked the user about `..._003-109` (shape: rises 0.285->1.197 by midpoint,
eases to 0.958 by end - a ~20% pullback but ending >3x above start, not
back near baseline). User confirmed: **`continuous`, label stands** -
unlike `..._004-032`, this is not a mislabel. Recorded in `docs/spec.md`
§4/§6.2. This reframes the remaining gap: `..._003-109` is now a confirmed
detector-precision problem, not a ground-truth question - the drawdown
rule needs to tell "mild pullback, stays elevated" apart from "genuine
reversal toward original baseline," which neither of round 4's tried
features (causal ratio, per-peak decline) does. Untried candidate for next
round: a feature measuring how far the drawdown closes back toward the
*pre-rise* baseline (not just its absolute/peak-relative size) - true
positives return near their starting value, `..._003-109` does not. No
code or harness change this round; 285/288 stands, with `..._003-109`
(false positive) and `..._004-014` (unrelated intermittent miss) as the
two remaining, both now well-understood rather than open questions.

## Round 7 — 2026-09-11

User asked how to use `src/utils/kinetics/` to actually reprocess (write
output CSVs), not just validate. Found the gap: `classify_file`/
`write_pfo_classification` hardcoded `classifier.classify_trajectory` (the
original detector) via `_classification_payload` - there was no way to
write output with `classify_trajectory_combined`. Added an optional
`classify_fn` parameter threaded through `_classification_payload` ->
`prepare_pfo_classification_rows` -> `write_pfo_classification` ->
`classify_file` (all default `None`, falling back to
`classifier.classify_trajectory` - no behavior change for existing
callers). Also added `classify_folder` to `src/utils/kinetics/api.py`
(mirrors `fit_folder`'s file-discovery loop; `classify_folder` didn't
exist before - only `classify_file` did), exported from `__init__.py`.
Smoke-tested: `classify_file(path, classify_fn=CLASSIFIER.classify_trajectory_combined)`
on `nn1120-4_pd_ceo2_000-000` (a file the old detector always missed) wrote
`_test/..._000-000_CarbonylPeakArea.csv` with `classification=discontinuous`,
`growth_onset_s=14701.4` - confirms the wiring reaches real output, not
just the in-memory validation harness. `fit_file`/`prepare_model_fit_rows`'s
own `_classification_payload` call (used for PFO pre_/post_ fit segments)
was left on its default (still `classify_trajectory`) - out of scope for
this ask, unchanged behavior there.

## Round 8 — 2026-09-11

Before running, queried the existing `graphify-out/graph.json` per user
instruction (`classify_file`/`classify_folder`, Community 9 in
`kinetics/api.py`, has no edge to `classify_trajectory()` in
`kinetics_fitting.py`, Community 1) - confirms the offline reprocess path
is structurally isolated from the live real-time detector, consistent with
CLAUDE.md's two-implementations warning. No surprises, proceeded.

Ran `classify_folder(folder, classify_fn=CLASSIFIER.classify_trajectory_combined)`
over all 7 sample folders, writing to each folder's `_test/`. All 289
on-disk files processed, 0 failures (33+10+57+4+117+34+34 - note 34 not 33
in `nn1120-4_pd_ceo2_000`, see below).

**Found: an unlabeled 289th file.** `nn1120-4_pd_ceo2_000` has
`20260910_181627_pd_ceo2_000-035_CarbonylPeakArea.csv` on disk (dated
2026-09-10) that isn't in `ground_truth.json` (still 288 entries, 33 for
this folder) and was never part of the 285/288 harness result.
`classify_folder` discovers files from disk, not from ground truth, so it
got reprocessed anyway - classified `continuous`. Needs a label (algorithm
or user) and a `ground_truth.json` entry before it counts toward Y; flagging
rather than guessing one.
