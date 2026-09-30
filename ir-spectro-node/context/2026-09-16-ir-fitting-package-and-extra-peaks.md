---
date: 2026-09-16
title: ir_fitting package — wrap spectral_fitting, append extra peaks
subtitle: src/utils/ir_fitting/runner.py
files:
  - src/utils/ir_fitting/api.py
  - src/utils/ir_fitting/runner.py
  - src/utils/ir_fitting/writer.py
  - src/utils/ir_fitting/config.py
  - src/utils/ir_fitting/result_types.py
  - src/analysis/spectral_fitting.py
  - src/visualizations/plot_individual_fit.py
source: backfill from src/utils/ir_fitting/spec.md §1–§13 + git log (19d1caf..7d678c1)
captured: 2026-09-23
related:
  - 2026-09-17-baseline-investigation.md
  - 2026-09-20-baseline-cleanup-and-cli.md
tags: [ir-fitting, extra-peaks, architecture]
---

## What this was about

Offline package to fit two historic low-wavenumber bands (12CO 1845/1825, i.e. 13CO
`Peak_1795`/`Peak_1775`) onto existing fits without touching live output. It also
serves as the host for baseline EDA. The extra-peaks workstream is now dormant:
`extra_peaks_base: []`.

## Decisions

- [decided] Wrap `src/analysis/spectral_fitting.py`, do not re-implement it. The reason is that
  `src/utils/kinetics` duplicates the live path and the two silently diverge.
- [decided] `append_only=True` default: the bands sit ~180 cm⁻¹ below `Peak_1975`,
  so there is no Voigt overlap with the saved 18. Backfilling in-cluster peaks
  (2093/2176/2196) is `append_only=False` (a full refit), never append.
- [decided] `on_existing` = skip (default) / overwrite / error, because
  `nn1120-2` already has these rows and duplicates would double-count fit history.
- [decided] `PdCO_mol` left NaN on appended rows. The calibration was derived in the
  carbonyl region, so it is not justified at 1775–1795.
- [decided] `Peak_Value` = nominal shifted value. Live FSD snapping is a no-op bug
  (indices compared to wavenumbers), so matching it reproduces live output.
- [decided] Baseline default `"saved"`. [measured] recompute vs saved agree to 1e-16
  over 72 files, and the baseline never sees the peak list.
- [decided] Unknown baseline-settings keys raise: `create_baseline` uses `.get`,
  so a typo would silently run the defaults.

## Rejected

- `ir_fitting`-local param rules. Bounds are hand-edited in `voigt_fit.param_rules`.
- Fixing the live FSD snapping bug. It would change `Peak_Value` in live output,
  which is a schema contract.

## Open

- [measured] When 1845/1825 were seeded, the centers pinned at their bounds in ~70% of 72
  files, pushing toward each other. The two bands likely describe one feature, and
  their areas are provisional until `param_rules` change.
- The catch-all `default: true` param rule silently gives narrow bounds (warn only).
- `window` is not threaded into the fit path, because it would put `Peak_2196` ~4 cm⁻¹
  from the edge.

## Provenance

Backfilled from an agent-written spec that was revised in place. "[decided]" means
the spec attributes the call to the user; this note did not witness the sessions.
The measurements are from spec §13's verification log.
