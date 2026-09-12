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
