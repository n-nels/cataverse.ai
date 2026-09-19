---
date: 2026-09-19
title: IR fitting lower five-anchor comparison restored
subtitle: src/utils/ir_fitting/api.py
files:
  - src/utils/ir_fitting/api.py
  - src/utils/ir_fitting/spec.md
source: opencode session
captured: 2026-09-19
related:
  - 2026-09-19-ir-fitting-lower-five-anchors.md
  - 2026-09-19-ir-fitting-full-seven-anchors.md
tags: [ir-fitting, baseline, lower-anchor, experiment]
---

## What this was about

The active baseline experiment was returned from the uncut seven-anchor
comparison to the previously measured lower-split five-anchor form.

## Decisions

- [decided] Keep the full `(2250, 1750)` window and upper anchors
  `(2240, 2006, 1955)`.
- [decided] Compare a lower-only cut at `1955` against the same cut with lower
  anchors `(1955, 1790, 1800, 1810, 1820)`.
- [decided] Leave the five-anchor set experiment-only; production defaults are
  unchanged.

## How to vary it

Change `lower_split_cm1` and `lower_anchors` in the active `BaselineVariant` in
`api.py`. The lower segment runs from the cut down to the ROI floor `1750`; all
lower anchors must be within that segment.

## Provenance

The restored constants and variants constructed successfully, and `api.py`
compiled. Ruff and pytest were unavailable in the environment.
