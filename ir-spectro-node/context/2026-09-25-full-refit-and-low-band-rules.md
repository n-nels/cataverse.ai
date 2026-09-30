---
date: 2026-09-25
title: Self-contained full refit on the anchored baseline, plus low-band rules
subtitle: src/utils/ir_fitting/runner.py
files:
  - src/utils/ir_fitting/voigt.py
  - src/utils/ir_fitting/runner.py
  - src/utils/ir_fitting/api.py
  - src/utils/ir_fitting/writer.py
  - src/utils/ir_fitting/config.py
  - src/utils/ir_fitting/baseline.py
  - src/utils/ir_fitting/baseline_cli.py
  - src/utils/ir_fitting/refit_cli.py
  - src/utils/ir_fitting/result_types.py
  - src/visualizations/plot_individual_fit.py
  - scripts/run_refit.py
  - config/analysis.yaml
source: backfill from src/utils/ir_fitting/spec-working.md (2026-09-23→09-25) + git log to ab4ca27
captured: 2026-09-28
related:
  - 2026-09-16-ir-fitting-package-and-extra-peaks.md
  - 2026-09-20-baseline-cleanup-and-cli.md
  - 2026-09-17-baseline-investigation.md
tags: [refit, voigt, param-rules, low-band, seeding, optimizer]
---

## What this was about
Refit all 24 peaks (18 existing + six new 13CO cluster peaks 1938/1928/1913/1877/1849/1838) jointly on the anchored two-segment baseline, entirely inside `src/utils/ir_fitting/`, writing live-schema CSVs to `_test`. Then tune the low-band rules. Full design lives in `spec-working.md`.

## Decisions
- [decided] Full refit is the only mode; append-only, `on_existing`, `merge_params` removed. Output CSV holds only this run's rows.
- [decided] Vendor the fit into `voigt.py` and own rules in `ir_fitting.fit` — **reverses** the 09-16 "wrap, don't re-implement" / "no local rules" decisions, because rule edits for this work would otherwise leak into the live server. Guarded by the parity gate.
- [decided] Seeding from `*_CarbonylPeakFitParams.csv` always on; bounds always from the rule around nominal (else centers walk across refits); out-of-bound seeds clipped and counted; fixed params (`y0`) never seeded.
- [decided] Seeds within 1% of a bound are nudged inside (`SEED_NUDGE_FRAC`) — without it lmfit's bound transform has zero derivative and the fit never moves.
- [decided] `least_squares` replaces `leastsq`; `method="leastsq"` kept for parity.
- [decided] `BaselineVariant()` defaults *are* the recipe, so CLI and fitter can't drift. `baseline="recompute"` is the default.
- [decided] 2175 (12CO) regrouped monomer → unknown in `ir_fitting.fit` only; moving it in `voigt_fit` would change live `monomer_sum`.
- [decided] Low-band rules (09-25): free amplitude sign (1838 later back to `min: 0`), 1928/1913 widened, 1877/1849/1838 kept narrow, 1913 center offset −3/+1 instead of renaming. Staged 1790/1770 rules dropped from `ir_fitting.fit` only.
- [decided] Large batches run on another machine; this one hosts OPUS/server/LN2 loop.

## Rejected
- Original parity gate (seeded refit vs saved CSV): matched to 5e-13 only because the fit never moved. Replaced by live `peak_fit` vs copy from the same start.
- Adding Peak_1856; merging close pairs (1938/1928, 1849/1838).
- Letting 1877/1849/1838 go wide — they become plateaus trading area with the 1913 tail.
- `amplitude.min: 0` on all six — cannot fit the ~1852 dip.

## Measurements
- [measured] Parity: live vs copy identical (Δmodel 0.0, Δparams 0.0, 60,339 nfev each).
- [measured] `least_squares` vs `leastsq`, 24 pk seeded `-021 delta10.0022`: 10 s converged vs 248 s; `-017`: 4 s vs 194k-cap non-convergence. Rule-start 18 pk is 0.1% worse RSS.
- [measured] New low-band rules on `-000` 0042–0072: RSS 1955–1800 drops 1.4–5×, 0042 now converges; on 8 default files all converge in 3–7 s.
- [measured] -022 delta10.0022/0042: low band fits negative (−0.069, −0.034) — attributed to the lower baseline segment, not the rules.

## Open
- [assumed] Hand edits after step 8 (1877 −3/+2, 1849 & 1838 −2/+6 centers, 1838 `min: 0`) are **unvalidated**; step 7–8 numbers describe the earlier rules.
- -022 lower baseline anchors (1955/1820/1800) don't follow the data.
- 1913 gamma cap 3.0 → ~4?; 1849 sign flips; 1877/1849/1838 centers pin on bounds.
- Existing-peak width cap (6.37/2.8) pins on 1975/2000/2015/2156 — out of scope.
- Spec says fits are serial, but ab4ca27 (09-26) added parallel workers to `api.py`/`refit_cli.py`; not covered by the spec or this note.
- Offline kinetics still reads `voigt_fit.*_peaks_base`, not the new groups.

## Provenance
Condensed from `spec-working.md` as of 09-25; [decided] tags follow the spec's decisions log. Measurements are the spec's own reported numbers, not re-run here.
