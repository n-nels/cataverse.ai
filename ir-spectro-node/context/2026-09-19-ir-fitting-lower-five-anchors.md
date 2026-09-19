---
date: 2026-09-19
title: IR fitting lower five-anchor trial
subtitle: src/utils/ir_fitting/api.py
files:
  - src/utils/ir_fitting/api.py
  - src/utils/ir_fitting/baseline.py
  - src/utils/ir_fitting/spec.md
related:
  - 2026-09-19-ir-fitting-anchor-1790.md
  - 2026-09-19-ir-fitting-anchor-1800.md
source: opencode session
captured: 2026-09-19
tags: [ir-fitting, baseline, lower-anchor, experiment]
---

## What this was about

The 1790 truncated-window trial was superseded. The user asked to return to the
three established upper anchors, cut the lower segment at 1955, and add lower
anchors at 1955, 1790, 1800, 1810, and 1820.

## Decisions

- [decided] Keep the full `(2250, 1750)` window and upper anchors
  `(2240, 2006, 1955)`; do not alter production defaults.
- [decided] Add `(1955, 1790, 1800, 1810, 1820)` as a separate experiment-only
  lower-anchor constant, preserving the two-endpoint default.
- [decided] Compare the five-anchor lower split against an unanchored 1955
  lower-split twin, with the full-ROI anchored variant retained as the upper twin.

## Measured

- [measured] Eight judged files, four variants, no degenerate baselines;
  `upper_max_abs_diff` was exactly zero.
- [measured] Both `...-022` guard files gated 1955 and applied no lower anchors.
- [measured] Five lower anchors reduced absolute seam on four of six ungated
  files and increased it on `...-021` and `...-027`.

## Open

- [proposed] Judge the figures and run a breadth check before selecting this
  form. The two-anchor seam prediction does not apply to five anchors.

## Provenance

The run used `uv run python src/utils/ir_fitting/api.py` and wrote figures plus
`baseline_comparison.csv` under `C:\Figures\...\lower_anchors_1955`.
