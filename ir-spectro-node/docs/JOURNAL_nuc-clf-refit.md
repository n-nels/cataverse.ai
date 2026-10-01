## Round 1 — 2026-09-30

Calibration OK: `combined` on `_reprocess` = 257/288. Tried a one-sided CUSUM on
per-group Peak_1988 increments (σ from the first `n_base` increments;
`src/utils/kinetics/baseline_departure.py`; harness got `trajectory_fn`), tuned on
human-labeled files only. Best: n_base 6, k 0.5, h 160 → **256/288**
(30 hit / 18 miss / 14 FP). Failure: in nn1120-4, 10 of 24 positives peak in
monomer before 2.5 h, so the rise sits inside the baseline window.
Label question: 9 algorithm-labeled `continuous` files in 003/004 match
positives (`003_reprocess\_test\nuc-clf-refit_r1_label_pairs.png`).
Next: take σ from high-frequency roughness, not an early window.

## User commentary after round 1 — 2026-09-30 (steering for round 2+)

- Agrees `003-110` and `003-113` should share a label. The algorithm-basis
  `continuous` labels in 003/004 are suspect. The new detector should keep most
  prior discontinuous hits and is expected to find more.
- No steady Peak_1988 baseline means nucleation has already started. So an
  event can be a threshold above a 0 baseline, since Peak_1988 usually starts at
  or below 0.
- `ground_truth.json` no longer strictly applies because the data changed, but
  keep it as a ballpark reference (user: "it should be ballpark >300 with
  improved detector sensitivity").
- Expected: data before 20250722 mostly `continuous`; nn1120-4_pd_ceo2 mostly
  `discontinuous`. **nn1120-4_pd_ceo2_000 labels are accurate** (user just
  reviewed them). 003/004 are mixed; the user will settle them from plots later
  (fine-tuning).
- Implication for Y: 288/288 against the current 003/004 labels is not the
  target as stated. Revisit Y with the user before scoring against it again.

## Y revised — 2026-09-30 (user)

288/288 dropped. The new three-part Y is in `prompt_nuc-clf-refit.md`: nn1120-4
33/33; 104/104 pre-20250722 files quiet; 003/004 keep all 24 current positives,
and the user signs off on per-file plots. Scored against the new Y, round 1 was
nn1120-4 26/33, pre-20250722 102/104 (`2_000-008` and `3_001-007` fire), and
003/004 floor 13/24.

## Labels updated — 2026-09-30 (user)

User relabeled nn1120-3_pd_ceo2_003 in `ground_truth.json`:
- `000`–`089` continuous, with `080`–`089` ambiguous (≤2 may fire);
- `090`–`120` discontinuous, except `107`/`108`/`117`;
- 12 files flipped to discontinuous: 093/095/097/101–105/109/113/115/120;
- 003 is now 26 discontinuous / 91 continuous;
- `003-109` reverses the old spec §4 decision.

nn1120-4 `000-011` is now continuous (the user's review), so round 1's nn1120-4
score is 27/33, not 26. 004 is next. Y is now four parts; see the prompt.

## Labels updated — 2026-09-30 (user), 004

User relabeled nn1120-3_pd_ceo2_004 in `ground_truth.json`:
- discontinuous: 008/014/016/018/020/021/022/024/026/028–034;
- 6 files flipped to discontinuous (016/018/024/031/033/034); none flipped the
  other way;
- borderline, still scored discontinuous: 008 (low S/N), 014, 016, 021, 031.

Totals: 004 is 16/18, all files 65/223. Every folder's labels are now
user-declared or user-confirmed, so Y is fully scorable by the harness.

## Round 2 — 2026-09-30

Calibration: `combined` = 240/288 on the new labels. New detector in
`baseline_departure.py`: `run_validation(input_subfolder="_reprocess",
classify_fn=classify_window_rise, trajectory_fn=peak_monomer_trajectory)`.
- Rise, per group: smoothed Peak_1988 − max(0, 8 h min). Fire when the group
  median exceeds 0.00275 au (fixed, not σ-scaled; z added nothing) and
  monomer_sum > 0.
- Both parameters were tuned on the scored labels.

Score 283/288:
- 4: 33/33.
- pre: 102/104 (FP 3_001-000/034).
- 003: 115/117 (FP 077, miss 102).
- 004: 33/34 (miss 018, where monomer < 0 blocks it).

Latch−monomer max = 7 h median. Plots: `003_reprocess\_test\nuc-clf-refit_r2_mismatches.png`.
Next: see whether 004-018 (a d label) vs 004-025 (a c label) is a label question.

## User commentary after round 2 — 2026-09-30 (steering for round 3+)

- Fixed-au threshold accepted. Add an absolute-amplitude gate (~0.01 au
  peak-to-trough): 3_001-000 has the right shape but spans only ~0.008.
- Negative monomer_sum at the latch must dismiss the classification (round 2's
  gate already does this). **004-018 → continuous** (like 004-025).
- **3_001-034 → discontinuous.**
- 003-102 miss is fine ("the rules are the rules"); 003-077 is borderline (low
  S/N), either label OK.
- `ground_truth.json` edited (user-approved): 004-018 → continuous; 3_001-034 →
  discontinuous, basis `user_declared_2026-09-30`. Totals unchanged: 65/223.

## Round 3 — 2026-09-30

Added the amplitude gate: `classify_window_rise_gated` in `baseline_departure.py`
(round 2 AND median-over-groups smoothed Peak_1988 max−min over the prefix ≥ 0.006).
The gate must hold on the 3 rise-fire prefixes. At 0.007, 003-091/098 were lost
(best span 0.0069); 001-000 is 0.0055.
Score 286/288: nn1120-4 33/33; pre 104/104; 004 34/34; 003 115/117. The 2 misses
are 077 FP and 102 miss, both user-excused; no 080–089 fires. The margin is thin
and tuned on labels. Latch time not re-measured.
Next: the user formalizes the 077/102 waiver and signs off on plots.

## User commentary after round 3 — 2026-09-30 (steering for round 4+)

- Round 3's `prefix_amplitude` has no zero floor and no 8 h window, unlike the
  round-2 rise. A climb from −0.01 to +0.005 scores 0.015 on the gate but 0.005
  on the rise. Next round: floor the gate the same way (span = max −
  max(0, trough)). Then recheck whether a gate still separates 001-000 (0.0055)
  from 003-091/098 (0.0069); both numbers were measured without the floor.
- Correction to round 3: latch time was measured after the entry. Latch −
  monomer_sum max = 7.5 h median (IQR 5–12), n = 64, with the max taken per time
  as the median over groups. That method may differ from round 2's 7 h figure.

## Round 4 — 2026-09-30

Floored the gate per user: `prefix_amplitude(zero_floor=True)` (span = max −
max(0, min)); used via `classify_window_rise_gated(zero_floor=True)`, still 0.006.
Critical span (gate at first prefix of a 3-fire rise run, best over the run) is
now 0.0050 for 3_001-000, 0.0069 for 003-091/098: gap widened, 0.006 still splits.
Score 286/288, same as round 3: nn1120-4 33/33; pre 104/104; 004 34/34; 003
115/117 (077 FP, 102 miss, both user-excused; no 080–089 fires). Next: user
signs off on plots and makes zero_floor the default.

## Correction to round 4 — 2026-09-30

Round 4's "user signs off on plots" was wrong. It came from the superseded
three-part Y. The current four-part Y in the prompt has no plot sign-off. Plots
go to the user only if a pre-20250722 file fires, and none did. Against Y as
written, the only gap is part 3: 003 is 115/117 (077 FP, 102 miss). Both are
excused only in the user's round-2 commentary, not in the prompt or
`ground_truth.json`. The user decides whether to amend the prompt or relabel.

## Promoted — 2026-10-01

The detector is now `classification.classify_nucleation` (+ `nucleation_trajectory`).
Its parameters live in yaml `kinetics_reprocess_classification`, with `zero_floor:
false` (the round-3 gate, user's choice). The writer, the harness and both CLIs use
it. The legacy cluster_sum detectors and `baseline_departure.py` were removed.
`--validate --input-subfolder _reprocess` = 286/288 (003-077 FP, 003-102 miss).
`run_kinetics_classification.py --folder <ds>` writes `classification` +
`growth_onset_s` (latch time) to `_reprocess\_test_classification\`.

## Round 5 — 2026-10-01

User asked: flatten Delta_Group (mean per time) to fix latch timing. Added
`classification.flat_trajectory` (one group, so `classify_nucleation` runs as-is).
Flat at yaml defaults = 274/288 (14 FPs, 0 misses). Best grid = rise 0.0045, amp
0.010 → **283/288**: 4 33→31 (FP 013/030), pre 104, 003 116 (077), 004 32 (FP
010/013). Latch−monomer max is 5.0 h median (IQR 1.3–10.5), vs 7.5 h per-group.
A per-time median scored the same, and smooth_n 2/5 did no better.
Next: root-cause nn1120-4 013/030.

## Round 6 — 2026-10-01

Why round 5 FPs: groups come in rotation, usually 1 per time, so a per-time mean
jumps between group offsets. Fix: `flat_trajectory` now carries each group
forward and averages. Yaml defaults 281/288; best rise 0.0035, amp 0.006 →
**283**: 004-010/013 fixed, but new FPs 003-079 and 004-023.
- 4-030: all 6 groups rise 0.013→0.044 after monomer max (~7 h). Per-group needs 3
  points per group, so it lags. Label question for the user.
- 4-013: monomer is just > 0 (0.004).
Latch−mmax = 4.5 h median.

## Round 7 — 2026-10-01

User asked to drop the flatten (rounds 5–6) and go back to per-group medians.
Restored `classification.py` from main HEAD (`git checkout`); the only diff was
the uncalled `flat_trajectory`, now gone. Yaml was untouched. Check:
`run_kinetics_classification.py --validate --input-subfolder _reprocess` =
**286/288** (003-077 FP, 003-102 miss), matching Promoted. Flatten's lead was
latch timing (4.5 h vs 7.5 h latch−mmax), not score. Next: improve latch timing
inside the per-group detector, or the user's call.
