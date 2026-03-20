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

## Chunk 2 — Hardware Layer: Device Drivers with Injected Connections

**Goal:** Create the new `hardware/` package where each device class receives an already-open connection. Build `DeviceManager` to own connection lifecycle.

**Why second:** The control layer (Chunk 3) depends on hardware classes as its input types. We need these interfaces defined and tested before building control logic.

**Estimated scope:** 8–10 files, ~500 lines of new code + tests.

### Tasks

| # | Task | File(s) | Notes |
|---|------|---------|-------|
| 2.1 | Create `src/hardware/__init__.py` with package docstring. | `src/hardware/__init__.py` | |
| 2.2 | Create `src/hardware/pressure.py` — `MKSPressure` class. Constructor takes `serial.Serial`. Methods: `read() -> PressureReading` (a `NamedTuple` with `timestamp`, `manifold`, `cell`), `disconnect()`. Port protocol logic from `devices/mks_pressure.py`. Include the reconnection-on-failure logic from the existing `read_pressure()` — keep it in this class per our decision. | `src/hardware/pressure.py` | `PressureReading` replaces the raw `(datetime, float, float)` tuple. |
| 2.3 | Create `src/hardware/temperature.py` — `WatlowTemperature` class. Constructor takes `ModbusClient`. Methods: `read_temperature() -> float` (Celsius), `set_temperature(setpoint: float)`, `f2c()`, `c2f()`. Port from `devices/watlow_controller.py`. | `src/hardware/temperature.py` | Rename `readTemp_ir` → `read_temperature`, `setTemp_ir` → `set_temperature`. |
| 2.4 | Create `src/hardware/mass_spec.py` — `ExtrelMassSpec` class. Constructor takes `ModbusClient`. Methods: `read_registers(address, count, unit) -> list`, `write_register(address, value) -> bool`, `decode_ieee754_cdab(r0, r1) -> float`. Port from `devices/extrel_mass_spec.py`. | `src/hardware/mass_spec.py` | |
| 2.5 | Create `src/hardware/analog_io.py` — `AnalogIO` class. Constructor takes `device_map: dict[str, tuple[str, str]]`. Methods: `write(actuator_id: str, voltage: float) -> bool`, `read(device_name: str, channel: str) -> float`. Internally caches `NI_USB6009` instances by device name (don't reconstruct per call). | `src/hardware/analog_io.py` | Replaces `NI_USB6009` + `ActuatorManager` as separate concepts. |
| 2.6 | Create `src/hardware/spectrometer.py` — `OpusSpectrometer` class. Constructor takes `zmq.Socket`. Methods: `send(message: dict) -> dict`, `reconnect()`. Port from `devices/network_messaging.py`. | `src/hardware/spectrometer.py` | |
| 2.7 | Create `src/hardware/power.py` — `KasaPower` class. Constructor takes `credentials: KasaConfig`. Methods: `set_state(device_id: str, on: bool)`, `login()`. Load credentials from `.env` if not provided. Port from `devices/kasa_plugs.py`. | `src/hardware/power.py` | |
| 2.8 | Create `src/hardware/connections.py` — `DeviceManager` class. Constructor takes `HardwareConfig`. Methods: `connect()`, `disconnect()`. Creates all hardware instances with proper connections. Exposes `pressure`, `temperature`, `mass_spec`, `analog_io`, `spectrometer`, `power` as typed attributes. | `src/hardware/connections.py` | |
| 2.9 | Create `tests/test_hardware/` directory with one test file per hardware module. Each test mocks the underlying library (pyserial, pymodbus, nidaqmx, pyzmq, requests) and verifies the protocol class behaves correctly. | `tests/test_hardware/test_pressure.py`, `test_temperature.py`, `test_mass_spec.py`, `test_analog_io.py`, `test_spectrometer.py`, `test_power.py` | |
| 2.10 | Create `tests/test_hardware/test_connections.py`. Test that `DeviceManager.connect()` creates all instances and `disconnect()` cleans up. Mock all underlying libraries. | `tests/test_hardware/test_connections.py` | |

### Validation
```bash
pytest tests/test_hardware/ -v
```

### Definition of done
- Each hardware class is instantiable with a mock connection and all methods callable
- `DeviceManager.connect()` produces a fully wired set of hardware instances
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
