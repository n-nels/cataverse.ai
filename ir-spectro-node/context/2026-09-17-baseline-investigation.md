---
date: 2026-09-17
title: Baseline investigation — anchors, cut at 1955, lower segment
subtitle: src/utils/ir_fitting/baseline.py
files:
  - src/utils/ir_fitting/baseline.py
  - src/utils/ir_fitting/api.py
  - src/visualizations/plot_baseline.py
source: backfill from src/utils/ir_fitting/spec.md §14 + git log (7d678c1..48b3254, 09-17→09-19)
captured: 2026-09-23
related:
  - 2026-09-16-ir-fitting-package-and-extra-peaks.md
  - 2026-09-20-baseline-cleanup-and-cli.md
tags: [baseline, anchors, isosbestic, nn1120-4]
---

## What this was about

`std_distribution` baseline (tuned for no-nucleation "Regime 1") halves the 2040/1980
bands on post-crossing `.0042/.0052` files of `nn1120-4_pd_ceo2_000`, and is wrong
in the opposite sign on pre-crossing `.0022` files. [measured] It is one progression
through the run, not two bugs.

## Decisions

- [decided] Judgement is visual. [measured] Envelope scores rank the one good file
  worst, because the low bands are negative-going and the baseline is a centre-line.
- [measured] There is an isosbestic point at ~1957 in 27/35 lgRefl files. [decided] Use an
  affine anchor correction through (2240, 2006, 1955). The 2240 pin is needed to keep the high end flat.
- [decided] Prominence guard: drop an anchor or cut if an extremum ≥ 0.5 of the *whole-ROI*
  range lies within ±25 cm⁻¹. Local-scale prominence gated every file.
- [decided] Lower-only cut at 1955: the anchored curve is untouched above it, and a second
  `create_baseline` runs below. [measured] max|diff| above the cut is exactly 0.0.
- [decided] Final pick (§14.22): anchors on both segments. This was later superseded by the CLI
  defaults (see related cleanup note).
- [decided] Duplicate anchors are deliberate weights. Never deduplicate them.

## Rejected (on stated grounds)

- Tuning `std_distribution` settings: swept twice, and on bad files the settings have nothing to grip.
- Any array truncation (top edge, at 1955, 2250–1800/1790): it moves good files more than bad ones.
- Split recomputing *both* sides on truncated arrays (§14.8): measured worse.
- `pspline_arpls` below the cut: it met all 3 targets but "caused major problems elsewhere".
- Lower segment floored at 1800 (§14.13): the jump moved to 1800, 6.5–16.6% of range.
- Interior anchors at 1854 (upper) and 1800 (as a 3rd lower point): removed on the figures.
- Full-ROI algorithm swap: out of scope, because historical datasets would need refitting.

## Removed at selection, NOT rejected on merit

- C¹ continuation below the cut + `num_std: 3.0` (§14.15). [measured] Best-measured form:
  seam_excess 0.36 vs 5.58, 51/53 breadth. Risk: it works via a regime coincidence.
- Seven anchors on an uncut full ROI (§14.20). Truncation to 1800 with an edge anchor (§14.16–18).

## Open

- [assumed] "Doesn't break good files" rests on n=1. `...-022` is a guard file, not certified good.
- [assumed] The guard can't protect anchors below ~1900 (the bands there are 2–9% of ROI range).
- `int` on the pre-crossing files was never fixed by an accepted form.

## Provenance

Backfilled from spec §14 (~2,900 lines, revised in place; finding 50's first draft
was wrong). [measured] figures are the spec's, on the 8 judged files unless noted.
