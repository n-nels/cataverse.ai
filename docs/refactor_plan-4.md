# CataVerse Restructure — Execution Plan

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

## Chunk 4 — Data Logging Layer and Experiment Session

**Goal:** Create reusable threaded loggers with start/stop interface, modernize experiment metadata management, and centralize file I/O.

**Why fourth:** Experiments (Chunk 5) need both the control layer (Chunk 3) and the logging layer (this chunk). This chunk has low risk — it's I/O and threading, not safety-critical logic.

**Estimated scope:** 7–9 files, ~500 lines of new code + tests.

### Tasks

| # | Task | File(s) | Notes |
|---|------|---------|-------|
| 4.1 | Create `src/datalog/__init__.py` (using `datalog` to avoid `logging` name collision). Export `PressureLogger`, `TemperatureLogger`, `MassSpecLogger`, `configure_logging`, `get_logger`. | `src/datalog/__init__.py` | |
| 4.2 | Move Python logging configuration (`configure_logging`, `get_logger`) from `core/logging.py` into `src/datalog/__init__.py`. Keep `core/logging.py` as-is for old code. | `src/datalog/__init__.py` | |
| 4.3 | Create `src/datalog/pressure_logger.py` — `PressureLogger` class. Constructor takes `pressure: MKSPressure`, `physics: SystemVolumes`, `path: Path`, and initial conditions. Methods: `start()`, `stop()`. Internally creates a daemon thread. Port the CSV writing and calculation logic from `instrument_operations.pressure_log`. Use `physics.py` for amount_adsorbed calculation instead of inline math. Fix the `while stop_event is None` bug (should be `while not self._stop.is_set()`). | `src/datalog/pressure_logger.py` | |
| 4.4 | Create `src/datalog/temperature_logger.py` — `TemperatureLogger`. Same start/stop pattern. Port from `instrument_operations.temperature_log`. | `src/datalog/temperature_logger.py` | |
| 4.5 | Create `src/datalog/mass_spec_logger.py` — `MassSpecLogger`. Port from `instrument_operations.mass_spec_log`. | `src/datalog/mass_spec_logger.py` | |
| 4.6 | Create `src/datalog/file_io.py` — consolidate from `utils/data_logging.py`. Rename functions: `expID` → `generate_experiment_id`, `materParams` → `write_material_parameters`, keep `create_directory`, `copy_to_share_drive`, `log_to_csv`, `log_actuator_state`, `log_temperature`, `log_experiment_parameters`. | `src/datalog/file_io.py` | Professional function names. |
| 4.7 | Create `src/experiments/session.py` — `ExperimentSession` class. Replaces `experiment_parameters`. Constructor takes `SampleConfig` and `SystemVolumes`. Methods: `new_experiment(name, new_sample)` (generates ID, creates dirs, initializes README), `log_pretreatment(...)`, `log_experimental_parameters(...)`, `mark_success()`. Uses `datalog/file_io.py` internally. | `src/experiments/session.py` | PascalCase. Clean typed interface. |
| 4.8 | Create `tests/test_datalog/test_pressure_logger.py`. Mock `MKSPressure.read()` to return a sequence of readings. Verify CSV output using `tmp_path`. Verify thread starts and stops cleanly. | `tests/test_datalog/test_pressure_logger.py` | |
| 4.9 | Create `tests/test_datalog/test_file_io.py`. Test directory creation, CSV writing, README generation using `tmp_path`. | `tests/test_datalog/test_file_io.py` | |
| 4.10 | Create `tests/test_experiments/test_session.py`. Test experiment ID generation, directory structure, parameter logging. | `tests/test_experiments/test_session.py` | |

### Validation
```bash
pytest tests/test_datalog/ tests/test_experiments/test_session.py -v
```

### Definition of done
- All three loggers follow the same `start()`/`stop()` pattern
- `ExperimentSession` produces the same directory structure and README content as the current `experiment_parameters`
- CSV column order and content match the current output
- The `stop_event` bug is fixed
- All tests pass
- No existing code modified

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
