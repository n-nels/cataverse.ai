---
date: 2026-09-19
title: IR fitting truncated baseline anchor
subtitle: src/utils/ir_fitting/api.py
files:
  - src/utils/ir_fitting/api.py
  - src/utils/ir_fitting/baseline.py
  - src/utils/ir_fitting/spec.md
source: opencode session
captured: 2026-09-19
related: []
tags: [ir-fitting, baseline, anchor]
---

## What this was about

The latest IR baseline experiment is the single anchored baseline on the
2250–1800 window. The user asked to add an anchor at the cutoff.

## Decisions

- [decided] Keep the established full-ROI anchor set `(2240, 2006, 1955)` and
  production defaults unchanged.
- [decided] Use `(2240, 2006, 1955, 1800)` only for the truncated experiment,
  represented by `TRUNCATED_ANCHOR_POINTS_1800_CM1`.

## Rejected

- [decided] Do not add 1800 to `ANCHOR_POINTS_CM1`; that would alter the full-ROI
  comparison twin and obscure whether movement came from truncation.

## Open

- [proposed] Re-run and visually judge the figures and comparison table before
  treating the edge-anchored form as the preferred scientific baseline.

## Provenance

The design follows `spec.md` §14.16 and the user's follow-up decision. The
eight-file no-write comparison measured 1800 applied on all truncated traces;
the existing 1955 guard remained active on the two `...-022` files.
