---
date: 2026-09-20
title: Baseline cleanup, CLI, and cut to execution-only
subtitle: src/utils/ir_fitting/baseline_cli.py
files:
  - src/utils/ir_fitting/baseline.py
  - src/utils/ir_fitting/baseline_cli.py
  - src/utils/ir_fitting/api.py
  - src/utils/ir_fitting/result_types.py
  - scripts/run_baseline_experiment.py
  - src/visualizations/plot_baseline.py
source: backfill from src/utils/ir_fitting/spec.md §15–§17 + git log (68764c8..c114eab, 09-20→09-23)
captured: 2026-09-23
related:
  - 2026-09-17-baseline-investigation.md
  - 2026-09-16-ir-fitting-package-and-extra-peaks.md
tags: [baseline, cli, cleanup]
---

## What this was about

The user selected the §14.22 baseline form, then had every other construction deleted.
An argparse CLI was added, the defaults were changed to a new recipe, and then all comparison and metric
code was removed. §14–§16 of the spec now describe code that no longer exists.

## Decisions

- [decided] CLI for baseline runs only; batch fitting stays edit-constants. The recipe is
  what gets swept, and re-typing variant lists is how sweeps go wrong.
- [decided] Current defaults (§16.5, the user's "v3"): upper anchors `2240 2006 1955 1955 1955`
  (1955 triple-weighted), lower `1955 1800 1820`, cut 1955, window (2250, 1750).
  These now live in `baseline.py` as `ANCHOR_POINTS_CM1` / `LOWER_ANCHOR_POINTS_CM1`.
- [decided] Flags: `--window --anchors --lower-split --lower-anchors` + the two guard
  thresholds. `settings` is not a flag: it was swept twice with nothing found, and it only reaches the upper curve.
- [decided] `--anchors` keeps order and duplicates. The duplicates are integer weights.
- [decided] One guard test gates each anchor *and* the cut together; they must not be split.
- [decided] §17: `api.run_baseline` runs one recipe and writes one figure per file; nothing else.
  Removed: `compare_baselines`, all metrics (mid/und/int, seam, band heights,
  `upper_max_abs_diff`), `baseline_comparison.csv`, `--compare`, `--with-twin`,
  gated-anchor reporting, and the tuple form of variants.
- [measured] §17 cleanup: 80/80 baseline arrays `np.array_equal` to pre-cleanup
  across 5 recipes × 8 files. §15 cleanup: curves bit-identical.

## Rejected

- Hiding the verbose summary behind a flag: the user wanted the prose deleted outright.
- Deduplicating anchor lists: it changes the least-squares weights.

## Open

- [assumed] The v3 default has **never been measured** against §14.22 (spec says so).
- [assumed] Guard thresholds (25 cm⁻¹, 0.5) were calibrated once and never swept. The guard also can't
  protect anchors below ~1900, and 1800/1820 are now default lower anchors.
- With the twin check deleted, "the region above the cut is untouched" is no longer checked in code.
  It is only by construction. [measured] It was 0.0 via `--with-twin` before removal.
- To reproduce §14.22, use the explicit flags in spec §16.5. §0's run block still
  lists the removed `--compare`/`--with-twin` flags, so it is stale.

## Provenance

Backfilled from spec §15–§17. §17 is the source of truth for what exists; constants
were checked against `baseline.py` on 2026-09-23.
