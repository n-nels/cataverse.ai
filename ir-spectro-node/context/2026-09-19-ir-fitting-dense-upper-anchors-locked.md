---
date: 2026-09-19
title: IR fitting dense upper-anchor experiment locked
subtitle: src/utils/ir_fitting/api.py
files:
  - src/utils/ir_fitting/api.py
  - src/utils/ir_fitting/spec.md
source: opencode session
captured: 2026-09-19
related:
  - 2026-09-19-ir-fitting-lower-five-anchors-restored.md
tags: [ir-fitting, baseline, anchor, experiment]
---

## What this was about

The current API iteration was selected as the baseline experiment to preserve
in the specification.

## Decisions

- [decided] Keep the full `(2250, 1750)` ROI and lower-only cut at `1955`.
- [decided] Keep the selected variant's upper anchors as
  `(*ANCHOR_POINTS_CM1, 2011, 2010, ..., 2000)` and its lower anchors as
  `(1955, 1790, 1800, 1810, 1820)`.
- [decided] Preserve the duplicate `2006` in that expression; it gives that
  point double weight in the least-squares correction.
- [decided] Treat this as an offline experiment only; production defaults remain
  unchanged.

## Provenance

The active configuration was read directly from `api.py` and documented in
`spec.md` §14.21 without changing the implementation.
