# Session Memory

---

## User Outstanding Items

- Revisit `fsd_peak_indices` handling in `src/analysis/main.py` and ensure alignment with wavenumber expectations.
- Persisted-CSV parity fix: evaluate a long-term replacement that avoids loading from disk (in-memory history object or cached DataFrame approach).
- Align 'peak_base_list' in config with name in analysis.
- Revisit `shape_mismatches.log` handling from `plot_spectrum_fit`.
- Set kinetic fitting parameter by 3 points

## Current Session

- [decided] The latest IR baseline experiment remains the single anchored baseline
  on the truncated `(2250, 1800)` window; no split, second baseline, or production
  ROI change was introduced.
- [decided] The truncated experiment now adds an edge anchor at 1800 through
  `TRUNCATED_ANCHOR_POINTS_1800_CM1`; the full-ROI `ANCHOR_POINTS_CM1` remains
  `(2240, 2006, 1955)`.
- [measured] A no-write comparison on all 8 judged files applied the 1800 anchor
  on every truncated trace; the existing 1955 guard still gated the two `...-022`
  files. Compilation and a synthetic edge-anchor check passed.
- [assumed] The new edge anchor should be judged visually and against the saved
  comparison output before being treated as a preferred scientific baseline.
- [decided] For the next trial, move the live cutoff and edge anchor together to
  1790; use the renamed `anchored_1790` output so it cannot be confused with the
  historical 1800 experiment.

## Violations

- Rule: Ruff's `BLE001` forbids broad `except Exception` handlers.
  Context: The lint run reported three pre-existing handlers in `api.py`; this
  session did not alter their behavior because they are outside the anchor change.
  Suggested remediation: replace them with specific exceptions or add a narrowly
  justified project-level exception policy in a separate cleanup phase.

---
