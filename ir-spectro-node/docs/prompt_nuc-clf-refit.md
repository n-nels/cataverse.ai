You are solving this problem directly, not building a framework for solving it.
No runner scripts, no config systems.

Work in iterations. At the end of each one, append to JOURNAL_nuc-clf-refit.md:
what you tried, what actually happened, what you're trying next and why. Append
only — never revise earlier entries, including wrong ones.

Write the journal for someone with no memory of this session, because that's what
will read it. Enough detail that they could pick up where you left off.
Keep each entry to roughly 500 characters. That's a hard budget, not a suggestion
to pad toward — say the decision and the one fact that explains it, not a
transcript.

---

## X — what to do

Develop a new nucleation classifier for the **refit** peak areas. The
`monomer_sum` / `cluster_sum` definitions changed with the 24-peak refit
(`src/utils/kinetics/spec-working.md`: `cluster_sum` = the 15 cluster peaks of
`ir_fitting.fit`, `monomer_sum` = Peak_2113/2103/2093), and the old rules
(`classify_trajectory_combined`, `docs/spec_nuc-clf.md`) drop from 285/288 on
live areas to 257/288 on the refit areas — worst in `nn1120-4_pd_ceo2_000`
(16/33), where the 6 new low-band cluster peaks fill in the drawdown the old
rule keyed on.

User's starting hypothesis: **Peak_1988 (13CO) moves off its floating baseline
at about the same time (on the scale of the observation period) as
`monomer_sum` reaches its maximum.** A detector that decides when Peak_1988 is
"off baseline" could classify nucleation. "Off baseline" should be a threshold
scaled to the variance of the data while it sits on the baseline, not a fixed
absolute delta (the old `rise_delta = 0.11 au`).

Background worth reading first: `docs/spec_nuc-clf.md` (ground truth, the latch,
why the old detectors fail), `docs/JOURNAL_nuc-clf.md`, and
`docs/JOURNAL_monomer-kinetics.md` (rounds 4–7: `Delta_Group` levels are
offset ~0.30 au from each other vs ~0.03 au scatter within a group — a
variance estimate that pools groups will be dominated by that offset; the
monomer max lands near the cluster curve's steepest growth).

Constraints (carried over from the nuc-clf loop, still binding):
- **Data-only.** No sample/folder/material identity as input. If/then branches
  are fine if chosen from the trajectory itself.
- **Causal.** At each prefix the detector sees only rows with time ≤ that
  prefix's time. A baseline estimated from the whole run is not allowed.
- **Monotonic once triggered** via `classification.latch_sweep` (currently 3
  consecutive fires). Changing the required count is allowed only with a
  journaled reason measured on the data.
- Any `Peak_Name` row in the area CSV may be used (Peak_1988 is the starting
  point; `monomer_sum`, other peaks, and sums are allowed if a round shows they
  help).
- Develop offline in `src/utils/kinetics/` (a new detector module or a new
  sibling in `classification.py`). Do not touch `src/analysis/` (live), and do
  not change the fit CLI's default classifier without the user.
- Do not edit `ground_truth.json` without the user. Label questions go to the
  user, as in nuc-clf round 6.
- Any written output goes to a `_test` subfolder; never overwrite `_reprocess\`
  area CSVs.
- This is the lab machine (OPUS / `run_server.py` / `run_norhoff.py` run here):
  keep compute light, no parallel sweeps without asking.

## Y — success criterion, and how to check it

**Revised 2026-09-30 (user):** the original 288/288 target is dropped. The
refit changed the data, and the algorithm-derived `continuous` labels in 003/004
are suspect (e.g. `003-113` should match `003-110`). `ground_truth.json` is kept
unedited as a reference; only the parts the user vouches for are scored hard.

Correctness uses the causal prefix-sweep definition: a file is `discontinuous`
iff the latch engages at some prefix. **Label only** — latch time is not scored.
Report it beside the `monomer_sum` maximum time as a diagnostic.

**Y is met when all four hold:**
1. **nn1120-4_pd_ceo2_000: 33/33** against `ground_truth.json`. The user
   re-reviewed this folder on 2026-09-30, so these labels are authoritative.
2. **Pre-20250722 folders: 104/104 quiet.** That covers nn1120-2_pd_ceo2_000,
   nn1120-3_pd_ceo2_000/_001/_002, all basis `user_confirmed_matches_algorithm`.
   The user expects these "mostly continuous". Any file that fires goes to the
   user with its plot; it does not count as a pass until the user relabels it.
3. **nn1120-3_pd_ceo2_003: 117/117**, with one tolerance: **at most 2 files in
   `003-080`…`003-089` may fire** (basis `user_declared_2026-09-30_ambiguous`;
   the user calls that signal ambiguous). The user relabeled this folder on
   2026-09-30:
   - `000`–`089` are `continuous`;
   - `090`–`120` are `discontinuous`, except `107`, `108` and `117`;
   - that gives 26 discontinuous / 91 continuous.
   This supersedes `spec_nuc-clf.md` §4's "003-109 is continuous" decision.
4. **nn1120-3_pd_ceo2_004: 34/34.** The user relabeled this folder on
   2026-09-30:
   - discontinuous: `008 014 016 018 020 021 022 024 026 028 029 030 031 032
     033 034`;
   - everything else is continuous;
   - that gives 16 discontinuous / 18 continuous.
   The user called `008` (low S/N), `014`, `016`, `021` and `031` borderline
   (basis `user_declared_2026-09-30_borderline`). They are still scored as
   `discontinuous`. Any tolerance for missing them is the user's call.

**How to check it:** `src/utils/kinetics/validation.py::run_validation(...,
input_subfolder="_reprocess")` against `src/utils/kinetics/ground_truth.json`
(288 files; 65 discontinuous / 223 continuous as of the 2026-09-30 relabels;
nn1120-4 is 23 discontinuous / 10 continuous, with `000-011` now `continuous`), or its CLI
`python scripts\run_kinetics_classification.py --validate --input-subfolder
_reprocess --classifier <name>`. If the new detector needs rows other than
`cluster_sum`, extend the harness so it hands the detector the right
trajectory (or the prefix of the whole area frame); do not write a second,
parallel scoring loop. The harness must recompute from `Time (s)` /
`Cumulative_Peak_Area` and never read the `classification` column in any CSV.

**Calibration first:** before trusting a new detector's score, rerun the
harness with the existing `combined` detector on `_reprocess` and confirm it
still gives 257/288 (21 hit, 27 missed, 4 FP). If it doesn't, the harness is
wrong and nothing built on it is trustworthy yet.

Report per round:
- the four parts of Y separately:
  - nn1120-4 x/33;
  - pre-20250722 quiet x/104;
  - 003 x/117, plus fires in 080–089;
  - 004 x/34, with borderline misses called out;
- the full 288 harness line, for reference only, not as the target;
- the mismatch list. A result that only holds at the full trajectory length (batch)
is not a pass.
