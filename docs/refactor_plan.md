# Refactor Plan

This document tracks the refactoring of the `src/` package. The refactor is **structural only** — it improves readability, organization, and maintainability without changing what the code does.

**Environment:** All refactoring is done in a Docker container with no access to physical hardware.

**Approach:** One file at a time. After each file, verify that the public interface (function signatures, return values, side effects) is unchanged.

---

## Current Phase: Phase 2

---

## Phase 0 — Project Setup and Documentation

Rename the package directory and update all references. Establish the documentation framework.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 0.1 | Rename `instrument_control/` to `src/` | directory, `pyproject.toml` | [x] |
| 0.2 | Update all internal import paths to reflect new package name | all `__init__.py`, all `from ...` imports | [x] |
| 0.3 | Update `main.py` imports to explicit, see 0.7 | `main.py` | [x] |
| 0.4 | Write root `AGENTS.md` | `AGENTS.md` | [x] |
| 0.5 | Write module-level `AGENTS.md` for each directory | `src/core/`, `src/devices/`, `src/operations/`, `src/experiments/`, `src/utils/` | [x] |
| 0.6 | Clean up `.opencode/` files to reflect this project (not ir-spectro-node) | `.opencode/instructions.md`, `.opencode/conventions.md` | [x] |
| 0.7 | Remove flat re-exports from `src/__init__.py`. All imports should be explicit from submodules (e.g. `from src.devices import SerialDevices`, not `from src import *`). | `src/__init__.py` | [x] |

---

## Phase 1 — Configuration and Core

Extract hardcoded values into YAML config files. Make `core/` a loader rather than a bag of global variables.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 1.1 | Create `config/system.yaml` for physical constants (R, volumes, temperatures) | `config/system.yaml` | [x] |
| 1.2 | Create `config/devices.yaml` for device settings (COM ports, baud rates, IPs, device map, Kasa IDs) | `config/devices.yaml` | [x] |
| 1.3 | Create `config/sample.yaml` for sample information (notebook, metal, support, mass, metal_load, support_sa). These are values passed to the `experiment_parameters` constructor. Runtime parameters like pretreatment gas, pressure, and temperature stay as method arguments in code. Keep `metal_density` as a derived value in `core/config.py`. | `config/sample.yaml` | [x] |
| 1.4 | Create `config/paths.yaml` for all file paths (data directory, share drive, etc.) | `config/paths.yaml` | [x] |
| 1.5 | Rewrite `core/config.py` to load from YAML files and expose the same values | `src/core/config.py` | [x] |
| 1.6 | In `core/config.py`, clearly separate raw values (loaded from YAML) from derived values (computed from raw). Document each derived value with its formula and units. | `src/core/config.py` | [x] |
| 1.7 | No-op for current codebase: there is no network password in `config.py`; all required network/device configuration is stored in `config/devices.yaml`. | `src/core/config.py`, `config/devices.yaml` | [x] |
| 1.8 | No-op for current `core/config.py`: no `print()` calls present to replace. Added module logger for future config-load diagnostics. | `src/core/config.py` | [x] |
| 1.9 | Update `core/__init__.py` exports | `src/core/__init__.py` | [x] |

**Validation:** Every value currently importable from `core.config` must still be importable with the same name and same value after this phase.

---

## Phase 2 — Devices

Flatten the device sub-packages into single modules. Clean up each device file. Do not change any device communication logic.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 2.1 | Flatten `devices/serial/serial_devices.py` → `devices/serial_devices.py` | move file, update imports | [x] |
| 2.2 | Flatten `devices/ni_daq/ni_usb6009_devices.py` → `devices/ni_usb6009.py` | move file, update imports | [x] |
| 2.3 | Flatten `devices/network/network_messaging.py` → `devices/network_messaging.py` | move file, update imports | [x] |
| 2.4 | Remove empty sub-package directories and their `__init__.py` files | `devices/serial/`, `devices/ni_daq/`, `devices/network/` | [x] |
| 2.5 | Update `devices/__init__.py` exports | `src/devices/__init__.py` | [x] |
| 2.6 | Clean up `serial_devices.py` — load COM ports and baud rates from `config/devices.yaml` instead of hardcoding | `src/devices/serial_devices.py` | [x] |
| 2.7 | Clean up `serial_devices.py` — replace `print()` with `logging` | `src/devices/serial_devices.py` | [x] |
| 2.8 | Clean up `ni_usb6009.py` — load `device_map` from `config/devices.yaml`, remove empty-string keys | `src/devices/ni_usb6009.py` | [x] |
| 2.9 | Clean up `ni_usb6009.py` — replace `print()` with `logging` | `src/devices/ni_usb6009.py` | [x] |
| 2.10 | Clean up `network_messaging.py` — load default IP/port from `config/devices.yaml` | `src/devices/network_messaging.py` | [x] |
| 2.11 | Clean up `network_messaging.py` — replace `print()` with `logging` | `src/devices/network_messaging.py` | [x] |
| 2.12 | Add type hints to all device files where missing | all `src/devices/*.py` | [x] |
| 2.13 | Split `SerialDevices` into per-instrument classes: `MKSPressureGauge`, `WatlowController`, `ExtrelMassSpec`. Keep `SerialDevices` as a thin container holding instances of each so the upstream interface doesn't change. | `src/devices/serial_devices.py` → `src/devices/mks_pressure.py`, `src/devices/watlow_controller.py`, `src/devices/extrel_mass_spec.py` | [x] |
| 2.14 | Extract Kasa smart plug control into `devices/kasa_plugs.py` — move chiller/variac plug logic out of operations/experiments into a proper device module | `src/devices/kasa_plugs.py` | [x] |
| 2.15 | Move `device_map` definition out of `ni_usb6009.py` — it is configuration, not device logic. After Phase 1 it lives in `config/devices.yaml`; remove the in-code definition. | `src/devices/ni_usb6009.py` | [x] |

**Validation:** `SerialDevices`, `NI_USB6009`, `ActuatorManager`, `device_map`, `NetworkMessaging`, and the new per-instrument classes must all be importable from `devices` with the same interfaces. `SerialDevices` must still expose `connect_mks()`, `connect_watlow_ir()`, `connect_extrel()`, `read_pressure()`, `readTemp_ir()`, `setTemp_ir()`, and `disconnect()` with identical behavior. Kasa plug control must produce the same on/off behavior for chiller and variac IDs.

---

## Phase 3 — Operations

Clean up the operations layer. This is the highest-risk area — actuator sequencing and valve logic must not change.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 3.1 | Clean up `actuator_control.py` — replace `print()` with `logging` | `src/operations/actuator_control.py` | [x] |
| 3.2 | Clean up `actuator_control.py` — add type hints where missing | `src/operations/actuator_control.py` | [x] |
| 3.3 | Clean up `actuator_control.py` — load any hardcoded values from config | `src/operations/actuator_control.py` | [x] |
| 3.4 | Review `actuator_control.py` — document every function's behavior in its docstring without changing logic | `src/operations/actuator_control.py` | [x] |
| 3.5 | Clean up `instrument_operations.py` — replace `print()` with `logging` | `src/operations/instrument_operations.py` | [x] |
| 3.6 | Clean up `instrument_operations.py` — replace hardcoded paths with config lookups | `src/operations/instrument_operations.py` | [x] |
| 3.7 | Clean up `instrument_operations.py` — add type hints where missing | `src/operations/instrument_operations.py` | [x] |
| 3.8 | Review `instrument_operations.py` — document every function's behavior in its docstring without changing logic | `src/operations/instrument_operations.py` | [x] |
| 3.9 | Update `operations/__init__.py` exports | `src/operations/__init__.py` | [x] |

**Validation:** Every method on `ActuatorControl` and `InstrumentOperations` must produce the same sequence of device calls in the same order with the same values. Pay special attention to `time.sleep()` durations, voltage values (1.0 for close, 5.0 for open), and pressure check thresholds.

---

## Phase 4 — Experiments

Clean up experiment protocols. This file is large and mixes several concerns — parameter management, gas delivery sequences, data logging, and threading. Refactor for clarity but preserve all behavior.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 4.1 | Clean up `experiment_protocols.py` — replace hardcoded paths (`C://Data//...`) with config lookups | `src/experiments/protocols/experiment_protocols.py` | [x] |
| 4.2 | Clean up `experiment_protocols.py` — replace `print()` with `logging` | `src/experiments/protocols/experiment_protocols.py` | [x] |
| 4.3 | Clean up `experiment_protocols.py` — add type hints where missing | `src/experiments/protocols/experiment_protocols.py` | [x] |
| 4.4 | Flatten `experiments/protocols/` — move `experiment_protocols.py` up to `experiments/experiment_protocols.py`, remove `protocols/` sub-directory | directory cleanup, update imports | [x] |
| 4.5 | Split `experiment_parameters` into its own module | `src/experiments/parameters.py` | [x] |
| 4.6 | Split `adsorption_experiment` into its own module | `src/experiments/adsorption.py` | [x] |
| 4.7 | Split `isotopic_exchange_calibration` into its own module | `src/experiments/isotopic_exchange.py` | [x] |
| 4.8 | Remove the original `experiment_protocols.py` once all classes are extracted | `src/experiments/experiment_protocols.py` | [x] |
| 4.9 | Update `experiments/__init__.py` exports | `src/experiments/__init__.py` | [x] |

**Validation:** `experiment_parameters`, `adsorption_experiment`, and `isotopic_exchange_calibration` must be importable with the same interfaces. The threading behavior (opus_thread, gas_thread, pressure_thread) and the order of operations in experiment sequences must be identical.

---

## Phase 5 — Utils

Clean up utility functions and data logging.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 5.1 | Clean up `data_logging.py` — replace hardcoded paths with config lookups | `src/utils/data_logging.py` | [ ] |
| 5.2 | Clean up `data_logging.py` — replace `print()` with `logging` | `src/utils/data_logging.py` | [ ] |
| 5.3 | Clean up `data_logging.py` — add type hints where missing | `src/utils/data_logging.py` | [ ] |
| 5.4 | Separate concerns in `data_logging.py` — CSV writing, README generation, and directory management are experiment data I/O. Keep these in `data_logging.py`. | `src/utils/data_logging.py` | [ ] |
| 5.5 | Create `core/logging.py` for Python `logging` module configuration (format, handlers, log levels). All other modules import their logger from here. | `src/core/logging.py` | [ ] |
| 5.6 | Review `data_processing.py` if it exists — same cleanup | `src/utils/data_processing.py` | [ ] |
| 5.7 | Update `utils/__init__.py` exports | `src/utils/__init__.py` | [ ] |

---

## Phase 6 — Package-Level Cleanup

Final pass on the top-level package.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 6.1 | Update `src/__init__.py` to reflect all changes from prior phases | `src/__init__.py` | [ ] |
| 6.2 | Update `main.py` if any interfaces changed | `main.py` | [ ] |
| 6.3 | Update `docs/directory_structure.md` to reflect final structure | `docs/directory_structure.md` | [ ] |
| 6.4 | Final review of all module-level `AGENTS.md` files for accuracy | all `AGENTS.md` files | [ ] |
