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

## Violations

- Rule: Ruff's `BLE001` forbids broad `except Exception` handlers.
  Context: The lint run reported three pre-existing handlers in `api.py`; this
  session did not alter their behavior because they are outside the anchor change.
  Suggested remediation: replace them with specific exceptions or add a narrowly
  justified project-level exception policy in a separate cleanup phase.

---
