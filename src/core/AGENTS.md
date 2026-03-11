# core/ — Configuration and Constants

For project-level rules, safety constraints, and behavioral preservation, see the root `AGENTS.md`. For refactoring protocol, see `.opencode/instructions.md`.

---

## Purpose

This module loads configuration from YAML files and exposes values used throughout the package. It is the only module that reads config files directly — all other modules import from here.

## Current State

`config.py` currently defines everything as module-level variables: physical constants, manifold volumes, sample parameters, device IDs, and a network password. The refactor (Phase 1 in `docs/refactor_plan.md`) replaces this with YAML-backed loading.

## Files

- **`config.py`** — Loads YAML config and computes derived values. After refactoring, this is the bridge between YAML files and the rest of the package.
- **`__init__.py`** — Exports from `config.py`.

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

**Depends on:** `config/` YAML files, `.env` (for network password after 1.7)

**Depended on by:** every other module — `devices/`, `operations/`, `experiments/`, `utils/`

## Constraints

- Every value currently importable from `core.config` must remain importable with the same name and same value after refactoring.
- Derived values must produce identical results to the current hardcoded computations.
- The network password must not appear in any tracked file after Phase 1.