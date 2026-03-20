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

## Chunk 1 — Foundation: Config, Physics, and Test Infrastructure

**Goal:** Stand up the typed config loader, centralize gas law calculations, and create the test scaffolding that all later chunks depend on.

**Why first:** Everything downstream imports config and uses physics calculations. Getting these right and tested unlocks all other chunks.

**Estimated scope:** 5–7 files, ~400 lines of new code + tests.

### Tasks

| # | Task | File(s) | Notes |
|---|------|---------|-------|
| ✅ 1.1 | Create `src/config_loader.py`. Define frozen dataclasses for each config group: `SystemConstants`, `HardwareConfig` (with nested `SerialDeviceConfig`, `ActuatorConfig`, `NetworkConfig`, `KasaConfig`), `SampleConfig`, `PathsConfig`, `AppConfig` (top-level container). Write `load_config() -> AppConfig` that reads from YAML. | `src/config_loader.py` | Does NOT replace `core/config.py` — both exist in parallel. New code imports from `config_loader`, old code still uses `core.config`. |
| ✅ 1.2 | Add `metal_molar_mass` field to `config/sample.yaml` (default `106.42` for Pd). Use it in `SampleConfig`. | `config/sample.yaml` | Backward-compatible: existing `core/config.py` ignores the new field. |
| ✅ 1.3 | Create `src/physics.py`. Extract and centralize: `SystemVolumes` dataclass (with `m3` and `total` as computed properties), `moles_from_pressure(p, v, t)`, `cell_pressure_from_manifold(p_mfld, v_source, v_total)`, `amount_adsorbed(n_initial, p_eq, v_total, temp_k, mass_g)`, `metal_surface_density(metal_load, molar_mass, support_sa)`. All pure functions, no hardware or I/O dependencies. | `src/physics.py` | These calculations currently live inline in `instrument_operations.pressure_log`, `deliver_gas_to_mfld`, `adsorption.py`, and `config.py`. The new module replaces the inline math. |
| ✅ 1.4 | Create `tests/conftest.py` with shared fixtures: `mock_serial_conn` (pyserial mock), `mock_modbus_client`, `mock_nidaqmx_task`, `mock_zmq_socket`, `sample_config`, `hardware_config`, `system_volumes`. Also add `pytest` and `pytest-cov` to `pyproject.toml` dev dependencies. | `tests/conftest.py`, `pyproject.toml` | These fixtures are used by all later chunks. |
| ✅ 1.5 | Create `tests/test_physics.py`. Test every function in `physics.py` with known inputs and hand-calculated expected outputs. Test edge cases: zero pressure, zero mass, division behavior. | `tests/test_physics.py` | Pure unit tests. No mocking needed. |
| ✅ 1.6 | Create `tests/test_config_loader.py`. Test that `load_config()` returns correct types and values from the actual YAML files. Test that `metal_molar_mass` defaults correctly. Test that derived values in `SystemVolumes` match `core.config` equivalents. | `tests/test_config_loader.py` | |

### Validation
```bash
pytest tests/test_physics.py tests/test_config_loader.py -v
```
All tests must pass. `physics.py` values must match the inline calculations currently in the codebase (cross-reference with `core/config.py` derived values for `v_m3`, `v_tot`, `metal_density`).

Chunk 1 validation run completed successfully in this environment with:
`PYTHONPATH=. pytest tests/test_physics.py tests/test_config_loader.py -v` (14 passed).

### Definition of done
- `load_config()` returns a fully typed `AppConfig` from YAML
- `physics.py` functions reproduce the same numerical results as the current inline calculations
- All tests pass
- No existing code modified (except `sample.yaml` gaining one new field, `pyproject.toml` gaining test deps)

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
