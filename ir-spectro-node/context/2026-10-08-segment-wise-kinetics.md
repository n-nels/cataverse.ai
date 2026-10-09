---
date: 2026-10-08
title: Segment-wise kinetics for the new classifier
subtitle: src/utils/kinetics/segments.py
files:
  - src/utils/kinetics/segments.py
  - src/utils/kinetics/models.py
  - src/utils/kinetics/api.py
  - src/utils/kinetics/fit_cli.py
  - src/utils/kinetics/validation.py
  - src/utils/kinetics/classify_cli.py
  - src/visualizations/plot_kinetics_fit.py
  - scripts/run_kinetics_fit.py
source: backfill from src/utils/kinetics/spec-working.md (D1–D27, sessions 2026-10-03 → 10-08; commits 9ce4dfb, 46152d2, bb8a6b7)
captured: 2026-10-09
related:
  - 2026-09-29-kinetics-reprocessing-on-refit.md
tags: [kinetics, segments, nucleation, pfo, offline-reprocess]
---

## What this was about

Offline kinetics (`--mode segments`, now the default) fits each (peak, segment) once over the whole trajectory, with segments chosen by the final nucleation label, instead of refitting after every row. Live `kinetics_fitting.py` untouched.

## Decisions

- [decided] D1/D2: one fit per segment is the default; `--mode rolling` stays, unchanged, for live parity.
- [decided] D3: boundaries from a pooled, 5-point centered median of the sum trajectory. Per-group smoothing runs maxima ~7 h early (17 pts/group ⇒ 15 h window).
- [decided] D17/D20: discontinuous monomer = `supersaturation` (secondary_pfo) → `depletion` (new exp_decay) at `t_b = max(monomer max, growth onset)`, contiguous; written as `depletion_start_s`.
- [decided] D21: no-spike discontinuous cluster = `pre_nucleation` pfo → `ripening` pfo, split at growth onset. Spike files: `burst_nucleation`/`diffusion_growth` written blank (`model = none`, D6) while models are explored.
- [decided] D18/D23: spike = prominence ≥ 5 and rise ≥ 5 (MAD noise), base = growth onset. User-labelled `spike` in `ground_truth.json`; true spikes are 000-000/026/029/032/034/041 only.
- [decided] D24: every segment's clock starts at its first row (~420 s), `q0` fixed there. Reason (user): the target is the **slow** kinetics; the 0–420 s admission phase is out of scope. Segments mode only — rolling/live keep absolute-time pfo.
- [decided] D26: monomer secondary_pfo keeps `q0` = first row.
- [decided] D25/D7: two outputs only, `*_CarbonylKineticParams.csv` + `*_CarbonylKineticFeatures.csv`.
- [decided] D10/D11/D19: short supersaturation segments, poor constituent pfo fits (`q_e ≥ 0` vs falling signal), and peak-then-decay continuous monomer are all left as is.

## Rejected

- Walk-left / windowed-minimum spike base: 6.6 h on 000-026 where the rise visibly starts ~11.5 h. Growth onset matched all six.
- Free `q0` (Q12 option B): on monomer it lifts the curve 0.03–0.20 au above early data (gain in R² is fake); on cluster it acts as a free offset on 000-026/004-008.
- Fitting from (0,0) with seed rows (option D): fails everywhere, k pinned at 0.01 — one pfo can't do admission + slow rise.
- Biexponential fast+slow: only ~3 points in the fast part; not built.
- Leaving a gap / blank segment between monomer max and onset (Q11 b/c).
- A `--plot` flag (D15): plotting lives in `plot_kinetics_fit.py`.

## Measured

- [measured] Spike score separates with a gap: detected 5.3–25.7, next 4.9 (001-034), 3.9 (003-097), rest < 2. `--validate-spikes` 66/66.
- [measured] Nucleation `--validate --input-subfolder _reprocess` = 287/289 (journal's 286/288 + 000-041). Plain `--validate` scores live areas, not refit — don't misread as drift.
- [measured] D24 changed only trajectory-start pfo, e.g. 000-000 cluster R² 0.808 → 0.937.
- [measured] Segments run 5–90 s/file vs up to ~5 h rolling.

## Open

- [proposed] Redo all kinetics folder-by-folder (user starts runs, D16); only the 8 test files have post-D24 fits.
- Deferred (D27): 003-097 sub-threshold post-onset hump (monotone pfo can't fall; ripening R² 0.33); short early `pre_nucleation` (000-002, 8 rows) whose k is admission tail, not slow kinetics.

## Provenance

Backfilled from spec-working.md, itself written across the sessions with decisions dated in its §1. Numbers are from runs recorded there, not re-run for this note.
