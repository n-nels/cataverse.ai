---
date: 2026-09-19
title: IR fitting 1790 cutoff trial
subtitle: src/utils/ir_fitting/api.py
files:
  - src/utils/ir_fitting/api.py
  - src/utils/ir_fitting/baseline.py
  - src/utils/ir_fitting/spec.md
related:
  - 2026-09-19-ir-fitting-anchor-1800.md
source: opencode session
captured: 2026-09-19
tags: [ir-fitting, baseline, anchor, experiment]
---

## What this was about

The user wanted to try an anchor at 1790 cm⁻¹. Because 1790 is below the 1800
cutoff, the live experiment had to move its cutoff to 1790 as well.

## Decisions

- [decided] Rename the live trial to `anchored 1790` and use window `(2250, 1790)`.
- [decided] Use anchors `(2240, 2006, 1955, 1790)` only for this truncated trial;
  production and the full-ROI twin remain unchanged.
- [decided] Move the live shared comparison window to `1838–1790`; preserve the
  `1838–1800` measurements as historical §14.16 results.

## Rejected

- [decided] Do not place an out-of-window 1790 anchor on the `(2250, 1800)` array;
  that would require an extrapolation design rather than the current edge-anchor
  construction.

## Open

- [proposed] Visually judge the generated 1790 plots against the historical 1800
  plots and the unchanged full-ROI `anchored` twin.

## Provenance

The live run generated 8 figures with 3 variants and 0 degenerate baselines at
`C:\Figures\nn1120-4_pd_ceo2_000\baseline_experiments\anchored_1790`.
