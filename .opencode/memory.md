# Session Memory

## 2026-03-19

- Began and completed Chunk 1 (tasks 1.1–1.6) from `docs/refactor_plan-1.md`.

- Implemented new typed config loader:
  - Added `src/config_loader.py` with frozen dataclasses:
    - `SystemConstants`, `SerialDeviceConfig`, `ActuatorConfig`, `NetworkConfig`, `KasaConfig`, `HardwareConfig`, `SampleConfig`, `PathsConfig`, `AppConfig`
  - Added `load_config(config_dir: Path | None = None) -> AppConfig`
  - Included validation helpers for required keys and actuator channel tuple shape/types.

- Added sample molar mass field:
  - Updated `config/sample.yaml` with `sample.metal_molar_mass: 106.42`.

- Implemented centralized physics module:
  - Added `src/physics.py` with:
    - `SystemVolumes` (`m3`, `total` properties)
    - `moles_from_pressure`, `cell_pressure_from_manifold`, `amount_adsorbed`, `metal_surface_density`

- Added test scaffolding and tests:
  - Added `tests/conftest.py` shared fixtures:
    - `mock_serial_conn`, `mock_modbus_client`, `mock_nidaqmx_task`, `mock_zmq_socket`, `sample_config`, `hardware_config`, `system_volumes`
  - Added `tests/test_physics.py` covering all physics functions and edge cases.
  - Added `tests/test_config_loader.py` covering typed load, values from YAML, default molar mass fallback, and derived volume parity with `src.core.config`.
  - Updated `pyproject.toml` with `[dependency-groups].dev = ["pytest", "pytest-cov"]`.

- Validation:
  - Initial run exposed one YAML escaping issue in `tests/test_config_loader.py` (Windows paths in double-quoted YAML strings in temp file fixture).
  - Fixed by using single-quoted YAML path strings in the fixture.
  - Final validation passed:
    - `PYTHONPATH=. pytest tests/test_physics.py tests/test_config_loader.py -v`
    - Result: 14 passed.

- Process notes:
  - Reviewer agent was invoked after each substantial edit task and follow-up fixes.
  - No commits made.
