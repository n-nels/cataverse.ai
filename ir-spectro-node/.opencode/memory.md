# Session Memory

---

## User Outstanding Items

- Revisit `fsd_peak_indices` handling in `src/analysis/main.py` and ensure alignment with wavenumber expectations.
- Persisted-CSV parity fix: evaluate a long-term replacement that avoids loading from disk (in-memory history object or cached DataFrame approach).
- Align 'peak_base_list' in config with name in analysis.
- Revisit `shape_mismatches.log` handling from `plot_spectrum_fit`.
- Set kinetic fitting parameter by 3 points

## Current Session

- [decided] Supersede the 1790 truncation trial for the active baseline run.
  Restore the full `(2250, 1750)` window, the three upper anchors
  `(2240, 2006, 1955)`, and a lower-only cut at `1955`.
- [decided] Add an experiment-only lower anchor set at
  `(1955, 1790, 1800, 1810, 1820)`. Preserve the established two-endpoint
  `LOWER_ANCHOR_POINTS_CM1` constant as the default.
- [measured] The judged run produced 4 variants × 8 files with no degenerate
  baselines. `upper_max_abs_diff` was exactly zero throughout; both `...-022`
  guard files gated at 1955 and applied no lower anchors.
- [measured] On the six ungated files, five lower anchors reduced absolute seam
  on the first four and increased it on `...-021` and `...-027`, relative to the
  unanchored lower split. The five-point seam is not governed by the old
  two-anchor prediction identity.
- [open] Figures and a breadth check still need visual/scientific judgement;
  no production ROI or configuration default changed.

- [superseded] The lower-split five-anchor run above was replaced for the next
  comparison by an uncut full `(2250, 1750)` run.
- [decided] Keep the established `(2240, 2006, 1955)` anchor trace second in
  the active variant list (orange); compare it against a single full-ROI
  least-squares correction with four added points `(1790, 1800, 1810, 1820)`.
- [measured] The new run produced 8 figures from 8 files with 0 degenerate
  baselines. Both `...-022` guard files gated only `1955`; the four additional
  lower anchors still applied. On six ungated files, the green-vs-orange
  maximum displacement was 5.8--15.5% of signal range.
- [measured] The 1800 lower-region probe moved from the orange trace's large
  ±6.5--15.2% / −10.4--10.8% offsets to about +1.0--1.7% on post-crossing and
  −1.1--1.2% on pre-crossing files. This is a visual/scientific trade, not an
  automatic quality score; no production default changed.
- [open] Decide from the generated figures and a breadth check whether the
  seven-anchor full-ROI curve should remain an experiment-only form.

## Violations

- Rule: Ruff's `BLE001` forbids broad `except Exception` handlers.
  Context: The lint run reported three pre-existing handlers in `api.py`; this
  session did not alter their behavior because they are outside the anchor change.
  Suggested remediation: replace them with specific exceptions or add a narrowly
  justified project-level exception policy in a separate cleanup phase.

---
