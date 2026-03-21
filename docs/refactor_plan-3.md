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

## Chunk 3 — Control Layer: Valve, Gas Delivery, Temperature, and Spectrometer Control

**Goal:** Create `control/` package that coordinates hardware calls into physical operations. This is the highest-risk chunk because it ports the valve and gas delivery logic.

**Why third:** Depends on hardware layer types from Chunk 2. Everything in Chunks 4 and 5 depends on control layer interfaces.

**Estimated scope:** 5–7 files, ~800 lines of ported code + tests.

**CRITICAL: The valve sequences and gas delivery logic in this chunk are behavior-frozen. Copy them verbatim from `operations/actuator_control.py` and `operations/instrument_operations.py`. Do not refactor, optimize, or change any:**
- Voltage values (1.0 close, 5.0 open)
- Step sizes (0.04, 0.1, etc.)
- Sleep durations
- Pressure thresholds and tolerance multipliers
- Dither increment/decrement logic
- Loop structure and branching
- Safety check sequences (turbo, mass spec)

**The ONLY changes allowed** are: replacing `self.actuators.set_value()` → `self.analog_io.write()`, replacing `self.serial.read_pressure()` → `self.pressure.read()`, and replacing `print()` → `logger.info()`. The control flow, math, and timing must be identical.

### Tasks

| # | Task | File(s) | Notes |
|---|------|---------|-------|
| ✅ 3.1 | Create `src/control/__init__.py`. | `src/control/__init__.py` | |
| ✅ 3.2 | Create `src/control/valves.py` — `ValveController` class. Constructor takes `analog_io: AnalogIO` and `pressure: MKSPressure`. Port ALL methods from `actuator_control.py`: `write(id, voltage)`, `open(id)`, `close(id)`, `close_all(device_map)`, `safe_turbo_open()`, `safe_mass_spec_open()`. **Verbatim logic.** Replace `self.print()` with `logger.info()`. Flag `sys.exit()` calls with `# TODO: consider custom exception` comment but do NOT change them yet. | `src/control/valves.py` | **Behavior-frozen.** |
| ✅ 3.3 | Create `src/control/gas_delivery.py` — `GasDelivery` class. Constructor takes `valves: ValveController` and `pressure: MKSPressure`. Port: `deliver_gas_to_manifold()` (from `deliver_gas_to_mfld`), `evacuate_cell()`, `cell_open_admit()`, `mass_spec_open_calibration()` (from `MassSpec_open_calibration`), `calc_pressure()`. **Verbatim logic** for all valve sequences and dithering. Replace `print()` → `logger.info()`. Use `physics.py` for any gas law calculations that are currently inline. | `src/control/gas_delivery.py` | **Behavior-frozen** for valve sequences. OK to call `physics.py` functions for the math parts (moles, pressure equilibrium). |
| ✅ 3.4 | Create `src/control/temperature_control.py` — `TemperatureController` class. Constructor takes `temperature: WatlowTemperature` and `power: KasaPower`. Port the `Watlow()` method from `instrument_operations.py` (ramp/hold logic), and variac/chiller state management. | `src/control/temperature_control.py` | |
| ✅ 3.5 | Create `src/control/spectrometer_control.py` — `SpectrometerController` class. Constructor takes `spectrometer: OpusSpectrometer`. Port `opusAcquire()` and `OpusVertex80()` from `instrument_operations.py`. | `src/control/spectrometer_control.py` | |
| ✅ 3.6 | Create `tests/test_control/test_valves.py`. **Critical tests:** verify that `open("H2")` calls `analog_io.write("H2", 5.0)` then sleeps. Verify `safe_turbo_open` opens RoughPump when pressure is high, polls until low, then closes. Verify `safe_mass_spec_open` exits when cell pressure exceeds limit. Verify `write()` with over-max voltage calls close then `sys.exit`. | `tests/test_control/test_valves.py` | These tests are the safety net for the most critical code in the system. |
| ✅ 3.7 | Create `tests/test_control/test_gas_delivery.py`. Test `deliver_gas_to_manifold` with a mock that returns decreasing-then-target pressure values. Verify the correct sequence of actuator writes. Test `evacuate_cell` similarly. | `tests/test_control/test_gas_delivery.py` | Since valve sequences are frozen, the test can verify the exact call sequence. |
| ✅ 3.8 | Create `tests/test_control/test_temperature.py` and `tests/test_control/test_spectrometer.py`. | `tests/test_control/` | |

### Validation
```bash
pytest tests/test_control/ -v
```

Chunk 3 validation run completed successfully in this environment with:
`PYTHONPATH=. pytest tests/test_control/ -v` (12 passed).

### Definition of done
- `ValveController` methods produce the exact same sequence of `analog_io.write()` calls as the current `ActuatorControl` methods produce `actuators.set_value()` calls
- `GasDelivery` methods produce the same device call sequences as the current `InstrumentOperations` methods
- All safety checks present and tested
- All `print()` replaced with `logger.info()`
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
