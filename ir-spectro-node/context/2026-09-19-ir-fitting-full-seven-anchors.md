---
date: 2026-09-19
title: IR fitting full-ROI seven-anchor comparison
subtitle: src/utils/ir_fitting/api.py
files:
  - src/utils/ir_fitting/api.py
  - src/utils/ir_fitting/baseline.py
  - src/utils/ir_fitting/spec.md
related:
  - 2026-09-19-ir-fitting-lower-five-anchors.md
  - 2026-09-19-ir-fitting-anchor-1790.md
source: opencode session
captured: 2026-09-19
tags: [ir-fitting, baseline, full-roi-anchor, experiment]
---

## What this was about

The lower-split five-anchor trial was superseded. The user asked to compare the
full 2250--1750 orange three-anchor curve against the same full-ROI correction
with the additional lower points, without a cut.

## Decisions

- [decided] Keep `(2240, 2006, 1955)` as the second active variant so it stays
  orange, and add `(1790, 1800, 1810, 1820)` to a separate full-ROI variant.
- [decided] Keep the seven-anchor set experiment-only; production defaults and
  `ANCHOR_POINTS_CM1` remain unchanged.

## Measured

- [measured] Eight files ran with three variants, eight figures, and zero
  degenerate baselines.
- [measured] Both `...-022` guard files gated 1955 only; the four added lower
  anchors applied. On six ungated files the maximum green-versus-orange shift
  was 5.8--15.5% of signal range.
- [measured] The 1800 probe moved close to zero on both post- and pre-crossing
  regimes, while the upper-band changes remain a trade to judge visually.

## Open

- [proposed] Review the figures and run a breadth check before deciding whether
  the seven-anchor full-ROI form should remain experiment-only.

## Provenance

The run used `uv run python src\\utils\\ir_fitting\\api.py` and wrote figures plus
`baseline_comparison.csv` under
`C:\\Figures\\nn1120-4_pd_ceo2_000\\baseline_experiments\\full_roi_anchors_2250_1750`.
