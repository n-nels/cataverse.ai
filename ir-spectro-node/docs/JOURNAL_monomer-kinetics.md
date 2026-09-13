## Round 1 — 2026-09-12

**Setup, no feature work attempted yet — user explicitly asked this round be
alignment/clarifying-questions only.** `docs/prompt_monomer-kinetics.md`
scaffolded this round. Read both `X:\` chat exports (LaMer theory; the
`dM/dt = k_a(q_eq-q) - k_s*p`, `dp/dt = k_p(q_eq-q_inf-p)` derivation matching
this repo's `pfo-sec_*` columns) and inspected `monomer_sum` in one file under
`C:\Data\peakFit\nn1120-4_pd_ceo2_000\`: classic LaMer hump, rises ~0.44→1.74
by t≈6900s, decays to ~0.15-0.3 by t≈274000s. Also reviewed the mature
nuc-clf loop (`docs/JOURNAL_nuc-clf.md`, 8 rounds, 285/288 on `cluster_sum`
only) and `src/utils/kinetics/spec.md` (the fit/classify CLI split — fit CLI
already produces the `pfo-sec_*` columns via `--peak-names monomer_sum
--model secondary_pfo`, classify CLI only ever touches `cluster_sum`).

**Alignment reached via several rounds of clarifying questions, decisions:**
1. Y is human-judged/exploratory — no ground-truth onset labels exist for
   `monomer_sum`. No loop-wide numeric target.
2. Features may draw on both the raw/smoothed curve and the already-fit
   `pfo-sec_*` parameters.
3. Deliverable is a feature catalog only — no detector/classifier this loop
   (deferred to a future separate loop).
4. Scope: `monomer_sum` only, `nn1120-4_pd_ceo2_000`'s 34 files only. Other
   6 reference folders and `cluster_sum`'s detector code untouched.
5. Develop in a new standalone module `src/utils/kinetics/monomer_features.py`
   — plain functions + editable-constants `__main__`, no CLI yet (matches how
   `classification.py` started before it got one).
6. Saved output goes to `_test/`, technique-dependent shape: scalar-per-file
   results → one shared catalog CSV (one row per file); curve-shaped results →
   extra columns on a per-file `_test/` copy, mirroring `fit_cli`/`classify_cli`.
7. Every round must produce a PNG per file with `monomer_sum` AND `cluster_sum`
   overlaid (twin y-axis likely) plus that round's extracted feature(s)
   marked — this is the actual check, not numbers alone.
8. Dropped an earlier "one distinct mathematical technique per round"
   framing (my own initial read of the user's original wording) — the user
   found it unclear and reframed the actual goal as: can mapping our existing
   ODE model onto LaMer's stages tell us where nucleation/growth begin and
   end, and what else might it reveal? A round can combine approaches freely.

**What's next:** round 2 is the first real attempt — start from the most
direct mapping available: the p/dp-dt model's own parameters already suggest
candidate onset markers (e.g. `k_p`'s timescale as when the secondary/growth
sink "turns on"; the fitted curve's inflection point) worth comparing visually
against `cluster_sum`'s independently-known `growth_onset_s`/`classification`
(from the nuc-clf detector) on the same file, where available, as a first
physical sanity check — not as a formal validation set, since Y here is
human-judged, but because it's the one piece of independently-derived timing
information already sitting in these same CSVs.

## Round 2 — 2026-09-12

**Built `src/utils/kinetics/monomer_features.py`** (plain functions, no CLI,
reuses nothing exotic — just `pandas`/`matplotlib` plus `WRITER`/`CLASSIFIER`
from `writer.py` for a read-only reference call). Two candidate features
computed for every file in `nn1120-4_pd_ceo2_000` (34 files, all processed, 0
failures): (1) `monomer_sum` peak time/amplitude (3-point smoothed pick,
raw-value report); (2) `q_inf_onset_time_s` — first sustained time the
*rolling* secondary-PFO fit's `q_inf` crosses 10% of its own eventual max in
that file, on the reasoning that a fresh expanding-window fit only "needs"
`q_inf > 0` once the data has actually started declining, so its jump is a
model-internal analog of the nucleation-burst-ending/growth-starting
transition. Also called `CLASSIFIER.classify_trajectory_combined` on the full
`cluster_sum` trajectory (batch, not the nuc-clf harness's prefix-sweep — a
single read-only reference point, not a claim about that loop's own metric)
to get an independent `growth_onset_s` per file for comparison. `cluster_sum`
was read time-sorted-only (no dedup across `Delta_Group`), matching
`validation.py`'s own convention, specifically so this reference call
reproduces what the real classifier harness would see — `monomer_sum` itself
is instead averaged across `Delta_Group` at equal `Time (s)` for one clean
curve, since peak-picking needs one value per time, not the classifier's
tolerance for near-duplicate points.

**Headline finding:** of the 24/34 files where the cluster classifier fired
`discontinuous` (matches nuc-clf's known 24/9 split for this folder — a good
sign the batch reference call is behaving), the `monomer_sum` peak occurs
*before* `cluster_sum`'s detected `growth_onset_s` in **23 of 24** files —
median lead time ≈21000s (~5.8h), mean ≈24150s, one exception
(`...-011`: peak *after* onset by +16200s). This is a direct, physically
sensible LaMer reading: monomer accumulation ends (nucleation burst
consuming it faster than it's supplied) well before particle growth has
accumulated *enough* `cluster_sum` signal to cross the existing detector's
own rise/drawdown threshold — so the monomer peak is a substantially earlier
leading indicator of the nucleation→growth transition than the current
cluster-side detector, not a redundant restatement of it.

**Weaker/negative result, reported honestly:** `q_inf_onset_time_s` only
resolved (crossed threshold) in 20/34 files, and against `peak_time_s` the gap
ranges -64800s to +54000s (median ≈1800s, std ≈26500s) — no clean
relationship. Root cause not yet confirmed, but the raw `pfo-sec_q_inf_au`
series is visibly non-monotonic across time in the one file inspected in
round 1 (jumps up then down), consistent with rolling-fit instability rather
than a real signal. Also: for the 9 `continuous`-labeled files (no real
LaMer burst), the peak-picker still returns a "peak" — a near-zero or
slightly negative value right at the first few points — which is noise, not
a feature; peak-time/amplitude should probably be gated on
`cluster_classification` or on amplitude magnitude before being trusted as
meaningful, not reported unconditionally.

**Saved output:** `_test/monomer_features_lamer_mapping.csv` (34 rows: file,
peak time/amplitude, `q_inf_onset_time_s`, final `pfo-sec_*` values,
`cluster_classification`, `cluster_growth_onset_s`, and their difference) +
one PNG per file, `_test/<stem>_monomer_lamer.png` (monomer_sum + cluster_sum
twin-axis overlay, peak/onset markers), all under
`C:\Data\peakFit\nn1120-4_pd_ceo2_000\_test\`.

**What's next, and why:** (1) `q_inf_onset` needs a better-behaved input than
a raw rolling-fit threshold crossing — try the fitted secondary-PFO *curve's*
own inflection point (second-derivative sign change) instead of the raw
`q_inf` parameter series, since that's continuous by construction even where
the fit parameters wobble. (2) Look closely at `...-011` (the one reversed
case) and `...-024` (largest gap, ~57600s) individually — worth knowing
whether either is a detector artifact before trusting the 23/24 pattern as
general. (3) The monomer-peak-precedes-cluster-onset finding is strong enough
on its own to be a headline candidate feature for the eventual catalog —
worth telling the human this explicitly next round rather than only
continuing to search for more features.

## Round 3 — 2026-09-12

**User correction, applied this round:** `cluster_growth_onset_s` (from
`classify_trajectory_combined`, round 2's comparison reference) was flagged
as errant — do not use it. `cluster_sum`'s own raw data series stays in
scope, but the onset marker on it must be this loop's own metric, not the
nuc-clf detector's opinion, and the loop should not reach for further
external metrics beyond `monomer_sum`/`cluster_sum`/`pfo-sec_*`.

**Change made:** in `monomer_features.py`, replaced `cluster_reference_onset`
(which called `CLASSIFIER.classify_trajectory_combined`) with
`cluster_rise_onset_feature` — first *sustained* (2 consecutive rows) time
`cluster_sum`'s raw point-to-point rate (`diff(value)/diff(time)`, 3-point
smoothed) exceeds 10% of its own max, deliberately mirroring
`q_inf_onset_feature`'s own-threshold-crossing shape rather than inventing a
new style. `CLASSIFIER`/`WRITER` imports dropped (both now unused). Catalog
column renamed `cluster_growth_onset_s`→`cluster_rise_onset_s`,
`monomer_peak_minus_cluster_onset_s`→`_cluster_rise_onset_s`; plot title no
longer shows `cluster_classification` (that also came from the same call).
Re-ran on all 34 files, 0 failures.

**Result — reported honestly, this is a weaker/noisier result than round 2's
classifier-based comparison, not a confirmation of it:** monomer peak now
leads the new `cluster_rise_onset_s` in only 19/34 files (vs 23/24 against
the old classifier reference); median diff -3540s, mean -15879s, std 45289s
— no clean sign pattern. Visual check on `...-000`: `cluster_sum` there is
*net declining* across the run, and the new metric's onset (t≈59700s) is
just a late noise bump crossing the rate threshold, not real growth — the
same false-positive mode round 2 flagged for `continuous`/noisy files, now
hitting this onset metric directly rather than being screened out by a
classifier label. `...-011` (round 2's one reversed case) is confirmed
visually noisy/flat overall, not a real LaMer trajectory either.

**What's next, and why:** the naive point-to-point rate is too noisy on
`cluster_sum` to threshold directly (unlike `pfo-sec_q_inf_au`, which is a
fitted parameter, not a raw diff). Try either (a) a wider smoothing window
before differencing, or (b) gating this metric on the series' net trend
(rise vs. decline over the whole trajectory) before reporting an onset at
all, so a noise bump in an overall-declining curve can't masquerade as one.
Saved output unchanged in location:
`C:\Data\peakFit\nn1120-4_pd_ceo2_000\_test\monomer_features_lamer_mapping.csv`
+ 34 `*_monomer_lamer.png`.

## Round 4 — 2026-09-12

**Bridge = the two maxima.** Root cause of round 3's failure found:
`cluster_sum`'s "noise" is a `Delta_Group` artifact — within-group scatter
~0.03 au vs ~0.30 au between group means, so pooling six offset levels into
one time-sorted series made the sawtooth that round 3's rate threshold
tripped on. Dropped `cluster_rise_onset_feature`; added `peak_by_delta_group`
(pick the peak inside each group, median across groups, group spread carried
as free uncertainty). Monomer anchor (`monomer_peak_feature`) deliberately
untouched; running the same picker on `monomer_sum` agrees with it (median
|diff| 3300s, 31/34 within 10000s) — method validated before trusting it on
`cluster_sum`, where signal and artifact are the same size.

**Result:** cluster max follows monomer max in **31/34** files, and **24/26**
once both peaks are required interior to the window (`*_peak_index_frac` in
[0.05, 0.95], a threshold-free gate); median lag **23700s**, and the lag
exceeds its own group spread in 17/24. So round 2's monomer-leads ordering
survives on one comparable, series-derived basis — resolving the round-2 vs
round-3 denominator mismatch (23/24 was classifier-gated, 19/34 ungated).
Both gated reversals explained: `-011` flat/noisy, `-013` a null run
(negative `monomer_sum` throughout, group spread 122278s — the spread flags
it automatically). Catalog column `cluster_minus_monomer_peak_lag_s`, same
`_test/` paths as before; plots now draw one thin line per `Delta_Group`,
which is what makes the artifact visible.

**Next:** the lag is a net-growth-phase duration — compare it against
`pfo-sec_k_a`/`k_p` timescales, which is the model-side half of the bridge.

## Round 5 — 2026-09-12

**Collapsed `Delta_Group` by mean** as instructed; every number now comes off
the two collapsed curves (round 4's per-group picking retired, group scatter
kept only as `*_group_std_mean_au`). Inflection is defined as **argmax of the
smoothed d/dt, bounded at the cluster max** — a second-derivative zero
crossing is not stable on 75–107 points, and leaving the search unbounded
reproduces round 3's noise-bump failure one derivative up.

**Hypothesis largely holds.** Casting the monomer max onto the cluster curve:
median |Δ| = **5699s at w5 = 3.2 sampling intervals = 3.0% of span** (gated
n=25, boundary gate from round 4). It lands on the **exact same sample in
5/25** files and within one sampling interval in 8/25. The inflection is
unchanged between smoothing windows w3 and w5 in 15/26 files, so it is not a
smoothing artifact. Direction: the monomer max sits slightly *after* the
inflection (20/25 at w5, median +4800s), not before.

**The "clearer on later-dated samples" claim is NOT supported — it runs the
other way.** |Δ| *grows* with sample date (Spearman rho +0.45, p=0.025 at w3;
early-half median 4500s vs late-half 9599s; weaker and non-significant at w5,
rho +0.30, p=0.14). The cleanest exact hit, `-003`, is early-dated
(2026-07-07). Inspecting `-035` (latest) shows why: its cluster curve rises
early then plateaus noisily, so the bounded argmax lands on a plateau bump
rather than a growth ramp. A sharpness metric meant to test the other reading
of "noticeable" divided by a near-zero rise and returned ~1e15 — discarded as
broken rather than reported.

**Next:** a rise-quality gate (require a real monotone ramp before the max)
would let the date claim be retested on curves where an inflection is
actually defined.

## Round 6 — 2026-09-12

**Inflection removed as instructed.** For the record, how it *was* defined
(round 5): argmax of `np.gradient` over a centered rolling mean (w3/w5),
bounded at the cluster max — smoothing yes, **no threshold**; the 10%-of-max
threshold was round 3's deleted `cluster_rise_onset_feature`. Replaced with
four threshold-free coordinates: each species' max, and the vertical cast of
that max's time onto the other curve. No normalised curve-crossing computed —
the twin y-axis makes a literal crossing an axis artifact.

**Slices:** t0→monomer max = LaMer I, →cluster max = II, →end = III. Gated on
both maxima interior (frac 0.05–0.95) and ordered; 24/34 pass, all 34 casts
in-grid (no `np.interp` clamping). Median durations 10680 / 19200 / 148498s =
5.7% / 10.3% / 79.0% of the run — burst-plus-growth is a tenth of the run,
ripening dominates, which is the LaMer shape. 10 gate failures: 9 have their
max at sample 0 (monotone-declining null runs), plus `-011` where cluster max
precedes monomer max by 1800s — round 4's known flat/noisy file.

**Output:** `_test/monomer_features_lamer_slices.csv` (new name, new schema)
+ 34 `*_monomer_lamer.png` with I/II/III `axvspan` shading and all four
coordinates in the legend. Next: use the slices — per-region LaMer sign test
(monomer slope + in I, − in II; cluster slope II > I).

## Round 7 — 2026-09-12

**Used round 6's slices for a threshold-free LaMer sign test** (least-squares
slope per region, not endpoint differences): monomer rises in I **24/24**,
monomer falls in II **23/24** (1 NaN: `-009` has <3 points in II). But cluster
slope II > slope I holds in only **5/24** — the expected sign fails in 19.

**This is a real result, not noise, and it revises the LaMer reading.** The
cluster curve is already accumulating at its steepest during region I and is
decelerating toward its own max through II (visible on `-024`: cluster ramps
hard before the monomer max, then plateaus). So growth is *not* switched on by
the monomer max — it is already near maximal rate there. That is consistent
with round 5's finding that the monomer max lands on the cluster's
steepest-growth point. Nucleation and growth overlap heavily here; the classic
LaMer separation of a discrete burst *preceding* growth does not hold. The
monomer max marks the end of net monomer supply excess, coinciding with peak
growth rate, and region II is growth deceleration, not growth onset.

**Model-side half:** region II = **7.3×** the ODE's own uptake timescale
1/k_a (median; IQR 4.1–9.7; 1/k_a median 3952s vs region II 19200s), and the
two are uncorrelated (Spearman rho 0.24, p=0.26, n=24) — k_a does not set the
burst-to-cluster-max duration.

**Output:** same `_test/monomer_features_lamer_slices.csv` (now with
`*_slope_*`, three `lamer_*` booleans, `region_II_over_k_a_timescale`) + 34
PNGs, stage labels staggered and the sign-test result in each title. Next: the
failing test says region II is mis-named — consider slicing at the cluster
curve's *rise start* instead of the run start, so region I isn't already
containing the growth ramp.
