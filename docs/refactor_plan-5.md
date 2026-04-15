# CataVerse Restructure — Execution Plan (Completed)

This document breaks the architecture rethink into **5 executable chunks**. Each chunk is self-contained: it can be completed, tested, and committed before starting the next. The old code is never deleted — it stays alongside the new code until hardware validation (which is a human-only step outside this plan).

**Global rules for all chunks:**
- Build new modules alongside old ones. Do not modify existing `src/` files except `main.py` at the very end.
- One task per commit. Human reviews `git diff` before commit.
- All new code uses PascalCase classes, `snake_case` functions, type hints, `logger.info()` (no print wrappers).
- Every new module gets a docstring explaining its role and dependencies.
- Tests accompany each module. Use `pytest` + `unittest.mock`. Mock at the hardware boundary.

**Directory convention:** New code goes in `src/` alongside existing subpackages. We use new package names (`hardware/`, `control/`, `logging_/`, `physics.py`, `config_loader.py`) so there are zero conflicts with existing code during the build-out.

> Note: Python's standard library has a `logging` module, so we name our package `logging_/` (trailing underscore) to avoid shadowing. Alternatively, `datalog/` — your call.

---

## Chunk 5 — Experiments, Main, and Cleanup

**Goal:** Rewrite experiment classes using the new layers. Write new `main.py`. Clean up stale files. Prepare for hardware validation.

**Why last:** Depends on everything from Chunks 1–4.

**Estimated scope:** 5–7 files, ~400 lines of new code + integration tests.

### Tasks

| # | Task | File(s) | Notes |
|---|------|---------|-------|
| 5.1 | Create `src/experiments/adsorption.py` (new version, lives alongside old one during transition — use a `v2_` prefix or put in a `v2/` subdirectory temporarily if needed to avoid collision). `AdsorptionExperiment` class. Constructor takes `session: ExperimentSession`, `devices: DeviceManager`, `gas: GasDelivery`, `temp: TemperatureController`, `spec: SpectrometerController`. Rewrite each method to use control and logging layer instead of raw device calls and inline threading. | Completed (`src/experiments/adsorption.py`) | Completed; protocol sequencing preserved. |
| 5.2 | Create new `isotopic_exchange.py` using same approach. `IsotopicExchangeCalibration` class. | Completed (`src/experiments/isotopic_exchange.py`) | Completed; protocol sequencing preserved. |
| 5.3 | Create `main_v2.py` at repo root. Build the full session: `load_config()` → `DeviceManager` → controllers → experiment. Show the equivalent of the current `main.py` workflow using the new architecture. | Completed then promoted to `main.py` | `main_v2.py` removed after successful hardware validation cutover. |
| 5.4 | Create `tests/test_experiments/test_adsorption.py`. Integration-level test: mock all hardware, run a simplified experiment sequence, verify the correct order of control calls and logging start/stops. | `tests/test_experiments/test_adsorption.py` | |
| 5.5 | Create `tests/test_integration.py`. Full-stack test: `load_config()` → `DeviceManager(mock)` → build all controllers → run a minimal experiment. Verify no exceptions and correct call ordering. | `tests/test_integration.py` | |
| 5.6 | Delete stale root files: `kasa_smartPlug.py`, `data_processing.py` (if confirmed stale), `C/` directory (if present). Delete `operations/code_reviewer_old.md`. | Various | |
| 5.7 | Update `docs/directory_structure.md` to reflect the new architecture alongside the old. Mark old packages as `# legacy — pending hardware validation`. | `docs/directory_structure.md` | |
| 5.8 | Write `MIGRATION.md` — a checklist for the hardware validation step. Lists every experiment sequence in `main.py`, what to run, and what to verify (pressure readings, temperature ramps, valve behavior, OPUS communication, data files). | `docs/MIGRATION.md` | This is the bridge to Phase F (human-only hardware validation). |

**Completion note:**
- Chunk 5 tasks were completed.
- Post-chunk hardware validation was completed.
- Final cutover was completed:
  - `main_v2.py` replaced `main.py` and was then removed.
  - `_v2` experiment modules were promoted to canonical names.
  - Legacy packages (`core/`, `devices/`, `operations/`, `utils/`) were removed.

### Validation
```bash
pytest tests/ -v --cov=src --cov-report=term-missing
```

### Definition of done
- New experiment classes produce the same device call sequences as the old ones (verified by mock tests)
- `main.py` is the live entrypoint on the new architecture (same experiment workflows)
- All tests pass across the entire test suite
- Stale files removed
- `MIGRATION.md` written with hardware validation checklist
- Legacy code retirement completed after hardware validation

---

## Post-Chunk: Hardware Validation (Human Only)

This is NOT part of the agent work. After Chunk 5:

1. Switch to the physical workstation with hardware access
2. Replace `main.py` with `main_v2.py`
3. Run through the `MIGRATION.md` checklist
4. Verify pressure readings, temperature control, valve sequences, OPUS communication
5. Run at least one full adsorption experiment end-to-end
6. If everything works: delete old code (`core/`, `devices/`, `operations/`, old experiment files), rename `v2` files to final names
7. If something breaks: `git diff` to find the discrepancy, fix in the new code, re-validate

---

## Chunk dependency graph

```
Chunk 1 (config + physics + test infra)
   │
   ├──→ Chunk 2 (hardware layer)
   │       │
   │       ├──→ Chunk 3 (control layer)     ← highest risk, behavior-frozen
   │       │
   │       └──→ Chunk 4 (logging + session)
   │               │
   │               └──→ Chunk 5 (experiments + main + cleanup)
   │                       │
   │                       └──→ Hardware Validation (human)
```

Chunks 3 and 4 can be done in parallel if desired — they don't depend on each other. Both depend on Chunk 2. Chunk 5 depends on both 3 and 4.
