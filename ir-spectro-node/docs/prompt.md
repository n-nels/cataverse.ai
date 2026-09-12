You are solving this problem directly, not building a framework for solving it.
No runner scripts, no config systems.

Work in iterations. At the end of each one, append to JOURNAL.md: what you tried,
what actually happened, what you're trying next and why. Append only — never
revise earlier entries, including wrong ones.

Write the journal for someone with no memory of this session, because that's what
will read it. Enough detail that they could pick up where you left off.

---

## X — what to do

Carry out the remaining work described in `docs/spec.md` (read it in full first —
it is the actual spec; this file only points at it and adds loop-specific
framing). In short: `classify_trajectory()` in
`src/analysis/kinetics_fitting.py` (mirrored offline by `KineticClassification`
in `src/utils/kinetic_fit_writer.py`) detects a flat-then-rise discontinuity in
a `cluster_sum` peak-area trajectory. It works on the data it was tuned on but
detects nothing on 22 of 24 hand-labeled positives in `nn1120-4_pd_ceo2_000`
(spec §5). All prototyping happens offline, in
`src/utils/kinetic_fit_writer.py` and/or `src/utils/kinetics/`, against real
recorded CSVs under `X:\peakFit\` — never in the live real-time path
(`src/analysis/kinetics_fitting.py`), per spec §4.

Concretely, per spec §7:
1. The debug-filter bug spec §4 claims was already "removed"
   (`kinetic_fit_writer.py`, `process_carbonyl_peak_area_files`, ~line 1690)
   was still live as of this loop's first round — check it's actually gone.
2. Ground truth already exists: `src/utils/kinetics/ground_truth.json`, 288
   files, 47 discontinuous / 241 continuous (spec §3).
3. Build/extend a validation harness (plain function(s) under
   `src/utils/kinetics/`, no CLI/argparse — follow the `if __name__ ==
   "__main__":` + editable-constants convention already used in this repo) that
   runs classification across all 288 files and reports matches against
   ground truth.
4. Iterate on the detection logic (`KineticClassification` in
   `kinetic_fit_writer.py`, or a new sibling) so it correctly classifies all
   288, under the constraints in spec §4: data-only (no material/sample
   identity as input), branches (if any) computed from the trajectory itself,
   monotonic-once-triggered aggregation (once "discontinuous" fires it stays
   fired for the rest of that run).

Read spec.md §5's stated mechanism (tail-elevation check fails on
rise-then-decay shapes) and §6 open questions before designing a fix — they are
the load-bearing clues, not just background.

## Y — success criterion, and how to check it

**Definition of correct, under monotonic-once-triggered aggregation:** a file
labeled `discontinuous` is classified correctly iff the detector fires
`discontinuous` at *some* prefix of its trajectory (not necessarily the last);
a file labeled `continuous` is classified correctly iff the detector *never*
fires `discontinuous` at any prefix. This is not a secondary check on top of a
batch/final-row comparison — under the monotonic latch, the prefix-sweep
result *is* the definition of correctness. (Spec §5 verified the existing
algorithm holds up here; a modified detector has to be re-verified, since it
no longer gets to lean on "final-length prefix already known correct".)

**Y is met when:** the validation harness reports all 288/288 files correct by
that prefix-sweep definition, matched against
`src/utils/kinetics/ground_truth.json`.

**How to check it:** run the harness. It must recompute classification from
`Time (s)` / `Cumulative_Peak_Area` (`Peak_Name == "cluster_sum"` rows) itself
— the raw CSVs under `X:\peakFit\` already carry a `classification` column
written by a previous real-time run; the harness must never read that column,
or it will report a meaningless 288/288.

**Calibration step, do this before trusting any new-detector result:** run the
harness against the *unmodified* existing algorithm first and confirm it
reproduces the numbers spec §3/§5 already claims (14 discontinuous in
`nn1120-3_pd_ceo2_003`, 9 in `_004`, 0 in the four clean folders, and — under
the prefix sweep — exactly 2/24 ever-firing with 0/9 false positives in
`nn1120-4_pd_ceo2_000`). If the harness doesn't reproduce that baseline, the
harness itself is wrong and no result built on it is trustworthy yet.

Note the asymmetry: a new detector faces 241 continuous files × every prefix
of each as a chance to false-positive, not just one batch comparison per file
— don't call Y met on a batch-only pass.
