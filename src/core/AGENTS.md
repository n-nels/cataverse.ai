# core/ — Configuration and Constants

For project-level rules, safety constraints, and behavioral preservation, see the root `AGENTS.md`. For refactoring protocol, see `.opencode/instructions.md`.

---

## Purpose

This module loads configuration from YAML files and exposes values used throughout the package. It is the only module that reads config files directly — all other modules import from here.

## Current State

`config.py` now loads raw values from YAML files (`config/system.yaml`, `config/devices.yaml`, `config/sample.yaml`, `config/paths.yaml`) and exposes compatibility aliases with the same public variable names used elsewhere in the codebase. Derived values remain computed in Python.

## Files

- **`config.py`** — Loads YAML config and computes derived values; exports compatibility variable names used across the codebase.
- **`logging.py`** — Central logging setup (`configure_logging`) and logger access (`get_logger`).
- **`__init__.py`** — Re-exports core configuration and logging helpers.

## Config Sources (after Phase 1)

| YAML File | Contents |
|-----------|----------|
| `config/system.yaml` | Physical constants: R, t_mfld, manifold volumes (v_vessel, v_valve, v_cell, v_m1m2, v_m1m2m3, v_50tube, v_flask) |
| `config/devices.yaml` | COM ports, baud rates, OPUS IP/port, device_map (actuator-to-channel mapping), Kasa smart plug IDs |
| `config/sample.yaml` | Sample info: notebook, metal, support, mass, metal_load, support_sa |
| `config/paths.yaml` | Data directory, share drive paths, any other file system locations |

## Derived Values

These are computed in `config.py` from raw YAML values. Document each with its formula.

| Variable | Formula | Units |
|----------|---------|-------|
| `v_m3` | `v_m1m2m3 - v_m1m2 - v_valve` | L |
| `v_tot` | `v_m1m2m3 + v_cell + v_valve + v_50tube` | L |
| `metal_density` | `(metal_load / 100) * (1 / 106.42) * (6.023e23) * (1 / support_sa) * (1e-9**2)` | nm⁻² |

Note: `106.42` is the molar mass of Pd (g/mol). If the metal changes, this value must change. This is a known coupling that should be documented.

## Dependencies

**Depends on:** `config/` YAML files

**Depended on by:** every other module — `devices/`, `operations/`, `experiments/`, `utils/`

## Constraints

- Every value currently importable from `core.config` must remain importable with the same name and same value after refactoring.
- Derived values must produce identical results to the current hardcoded computations.
