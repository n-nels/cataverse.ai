---
date: 2026-09-29
title: Kinetics reprocessing on refit data
subtitle: src/utils/kinetics/writer.py
files:
  - src/utils/kinetics/timeline.py
  - src/utils/kinetics/areas.py
  - src/utils/kinetics/utils.py
  - src/utils/kinetics/classification.py
  - src/utils/kinetics/validation.py
  - src/utils/kinetics/classify_cli.py
  - src/utils/kinetics/writer.py
  - src/utils/kinetics/api.py
  - src/utils/kinetics/fit_cli.py
  - src/utils/kinetics/__init__.py
  - src/analysis/output.py
  - src/utils/ir_fitting/config.py
  - scripts/run_kinetics_fit.py
  - scripts/run_kinetics_classification.py
source: backfill from src/utils/kinetics/spec-working.md (progress log, 2026-09-29)
captured: 2026-09-30
related:
  - 2026-09-25-full-refit-and-low-band-rules.md
tags: [kinetics, classification, refit, timeline, parallel]
---

## What this was about

Rerun offline kinetics on the 24-peak refit output (`_reprocess\`) with redefined sums, and check the `combined` classifier still works. Three blockers: no params→area step, the written label wasn't the causal one being validated, and sum groups came from live `voigt_fit`.

## Decisions

- [decided] `cluster_sum` = the 15 `ir_fitting.fit` cluster peaks; `monomer_sum` = 2113/2103/2093. Groups are baked into the area CSVs (reverses spec.md's "sums are a fitting concern only").
- [decided] Time comes from a per-spectrum timeline (subIFG log + exp params), never from which params rows exist. Missing spectra get a row with correct time and NaN area; no interpolation. Reason: summing `Time_Delta` over params rows silently shifts every later time after a gap (e.g. 14,400 s).
- [decided] `classification` is a causal per-row latch (3 consecutive fires) via one shared `latch_sweep`, so the writer and the harness can't disagree.
- [decided] Classification runs on the 15-peak `cluster_sum`; 257/288 accepted for now. Retuning is later, separate work.
- [decided] Model assignment is a `(group, regime)` table (`REGIME_MODELS`); discontinuous entries are placeholders for the four-equation redesign.
- [decided] Outputs built fresh per measurement into `_reprocess\_test\`; merge-onto-legacy path removed.
- [decided] `--workers N` (one process per measurement, spawn, BLAS=1 thread, below-normal priority) — user asked, after the serial cost measurement.
- [decided] Sort rows with pandas' default (live's) not a stable sort — required for secondary_pfo parity.

## Rejected

- Stable sort in `sorted_trajectory`: matched live on only ~80% of secondary_pfo rows; tie-order changes steered L-BFGS on ill-conditioned rows.
- `classify_trajectory_sustained_rise`: net worse (spec_nuc-clf §6.2); removed.
- `full_series` mode, `write_fit_params_to_legacy`, `fit_file`/`fit_folder`, legacy-column migration: superseded by the per-measurement path; removed.
- Forcing area parity on measurements with gaps: live times there are already wrong, so differences are reported, not matched.

## Measured

- [measured] Timeline gate: 24,199/24,199 spectra match saved live `Time_Delta` (297 measurements); 58 spectra newly timed.
- [measured] Area parity, nn1120-3_004 live params + `voigt_fit` groups: 34/34 identical (max 6e-11 s).
- [measured] Classifier, 288 files: source 9-peak 285, refit 9-peak 275, refit 15-peak 257. Refit-15 losses concentrated in nn1120-4_000 (16/33): low-band growth fills the drawdown hump.
- [measured] `004-019` vs live `append_fit_results(latest_only=False)`: 20 kinetic columns bit-identical over 453 rows.
- [measured] Serial rolling secondary_pfo on `004-008` `monomer_sum`: 4,808 s, 165 ODE timeouts. Est. ~5 h/long file, weeks for all 296.
- [measured] Parallel `--workers 2` on `-035` equals serial output exactly.

## Open

- secondary_pfo returns all-NaN when `monomer_sum` ≤ 0 (inverted `q_e` bound); 14/296 refit files. Same in live. Belongs to model redesign.
- ODE timeouts are wall-clock (0.1 s), so results under load depend on machine load; parity held only at 0 timeouts.
- Four-equation discontinuous models, label rename, and porting the classifier to live — out of scope.
- [assumed] nn1120-4 `-041` was still acquiring during the refit (11 spectra not refit).

## Provenance

Backfilled next day from the spec-working progress log, which was written during the session. Numbers are as logged there, not rerun. Nothing committed by me; the user commits.
