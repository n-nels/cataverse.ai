    # Cleanup Plan — Phase 8: Module-by-Module Review

> **Entry point for Claude Code.** On invocation: (1) read this document end-to-end; (2) find the first task whose Status is `[ ]`; (3) verify any predicate tasks listed in its description are marked `[x]`; (4) report the task number, description, and any blockers to the human; (5) STOP and wait for explicit go-ahead before making changes. Do not proceed on the assumption that "the next task" is implicitly authorized. After completing a task and commit, return and update the Status column from `[ ]` to `[x]` for that task, then stop and wait for the next invocation.

---

Phases 1–7 of the earlier cleanup plan are complete. This document tracks the remaining work from a fine-tooth-comb review pass, walking the codebase bottom-up through the dependency stack.

**Review order (bottom-up):**

1. `src/` package root — **config + physics** (this phase)
2. `src/hardware/`
3. `src/control/`
4. `src/datalog/`
5. `src/experiments/`
6. `main.py`

Each package review produces a findings list. Items that warrant action land in this document as a numbered phase. Items that are cosmetic or not worth the churn are noted in the per-package review and left alone.

**Approach:** one task per commit. Human reviews `git diff` before each commit. Tests pass after each phase.

**Scope policy — frozen behavior.** This pass permits changes to behavior-frozen code (valve sequencing, gas delivery, pressure checks, timing-sensitive protocol methods) where the review finds a genuine improvement. However: any task that changes code inside a behavior-frozen region requires an explicit human flag and go-ahead before the change is committed. The task description must call out the behavior-frozen touch and include a validation plan (existing tests + real-hardware revalidation if warranted). If Claude Code encounters a behavior-frozen change while executing a task, STOP and ask before proceeding.

---

## Phase 8.1 — Create `src/core/` package

The two foundation modules (`config_loader.py`, `physics.py`) currently float at `src/` level with no grouping. This is the base of the dependency stack — everything else depends on them — and they should be grouped accordingly.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.1.1 | Create `src/core/` directory with `__init__.py`. | `src/core/__init__.py` | [x] |
| 8.1.2 | Move `src/config_loader.py` → `src/core/config_loader.py`. | — | [x] |
| 8.1.3 | Move `src/physics.py` → `src/core/physics.py`. | — | [x] |
| 8.1.4 | Update all imports across the codebase: `from src.config_loader` → `from src.core.config_loader`, `from src.physics` → `from src.core.physics`. Grep exhaustively under `src/`, `tests/`, and `main.py`. | all | [x] |
| 8.1.5 | Write `src/core/AGENTS.md` describing the package's purpose and scope-creep guard: "This package contains typed configuration loading and pure physics calculations. It depends on nothing internal. New modules belong in `hardware/`, `control/`, `datalog/`, or `experiments/` unless they are genuinely foundational and have no dependencies on any other internal package." | `src/core/AGENTS.md` | [x] |
| 8.1.6 | Update `docs/directory_structure.md` to reflect the new location. | `docs/directory_structure.md` | [x] |
| 8.1.7 | Optionally update `src/core/__init__.py` to re-export the most-used names (`AppConfig`, `load_config`, `SystemVolumes`, `moles_from_pressure`, etc.) so callers can write `from src.core import AppConfig`. Or leave `__init__.py` empty and require explicit submodule imports. Human to decide before 8.1.4. **Decision: explicit submodule imports; `__init__.py` stays empty.** | `src/core/__init__.py` | [x] |

**Validation:** `pytest tests/ -v` passes. `python main.py --mock --adsorption` runs clean. Grep confirms no remaining `from src.config_loader` or `from src.physics` anywhere except inside `src/core/` itself.

---

## Phase 8.2 — `core/config_loader.py` improvements

Findings from the package review. Ordered by priority.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.2.1 | **[C7]** Move `load_dotenv()` from module top-level (import-time side effect) to inside `load_config()`, or into `main()`. Import-time side effects make the loader hard to test with alternate `.env` files and can mask errors. Pick one location and document it. | `src/core/config_loader.py`, possibly `main.py` | [x] |
| 8.2.2 | **[C9]** Verify the `ActuatorConfig` field name vs. `tests/test_config_loader.py` assertion. The dataclass declares `actuator_map: dict[str, tuple[str, str]]` but the test reads `cfg.hardware.actuator.device_map["H2"]`. Determine which is current and fix the mismatch. This is a 5-minute check that could reveal a real bug. | `src/core/config_loader.py`, `tests/test_config_loader.py`, `config/devices.yaml` | [x] |
| 8.2.3 | **[C3]** Make "optional with default" consistent across all config dataclasses. Currently `SampleConfig.metal_molar_mass_g_mol` uses a dataclass-level default, while `ExtrelRegisterConfig` fields are required in the dataclass but filled via `.get(..., default)` in the loader. Pick one pattern — **dataclass-level defaults are preferred** because they document the contract in the type system. Audit every `.get(key, default)` call in `load_config` and either (a) move the default to the dataclass, or (b) make the field truly required and drop the default. | `src/core/config_loader.py` | [x] |
| 8.2.4 | **[C6]** `_resolve_config_dir` uses `Path(__file__).resolve().parents[1]` to find the repo root. After the `src/core/` move (Phase 8.1), this needs to become `parents[2]`. More robustly, remove the fallback entirely and require either an explicit `config_dir` argument or the `CATAVERSE_CONFIG_DIR` env var. Decide with the human which. **Decision: removed `parents[]` fallback; require explicit `config_dir` or `CATAVERSE_CONFIG_DIR` env var.** | `src/core/config_loader.py` | [x] |
| 8.2.5 | **[C5]** Break up `load_config`. It is currently ~100 lines of nested YAML lookups and dataclass construction. Extract per-config-group helpers: `_build_system_constants(data)`, `_build_hardware_config(data)`, `_build_sample_config(data)`, `_build_paths_config(data)`. Each helper takes a dict and returns one dataclass. Easier to debug when a specific YAML section is malformed. No behavior change. | `src/core/config_loader.py` | [x] |

**Validation after each task:** `pytest tests/test_config_loader.py -v` passes. Full suite green after 8.2.5.

---

## Phase 8.3 — `core/physics.py` improvements

Findings from the package review. All minor — this module is the cleanest in the codebase.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.3.1 | **[P3]** Promote `manifold_m1m2 + tube_50ml` and `manifold_m1m2m3 + tube_50ml` to `SystemVolumes` properties. These combinations are computed inline in multiple experiment call sites as "source volume for gas delivery." Naming to be decided with the human — these are domain concepts (likely `source_m1m2_tube`, `source_m1m2m3_tube` or similar). Once properties exist, update all inline computations in `experiments/` and `datalog/` to use them. | `src/core/physics.py`, experiment and logger call sites | [ ] |
| 8.3.2 | **[P4]** Introduce `DEFAULT_TEMPERATURE_K = 298.0` as a module-level constant in `physics.py` and import it in `datalog/pressure_logger.py` (and anywhere else the default is hard-coded). Same treatment as the existing `DEFAULT_GAS_CONSTANT_L_TORR_PER_K_MOL`. A deeper question — whether these defaults should exist at all in `PressureLogger.__init__` when real callers always pass config values — is flagged for the datalog review. | `src/core/physics.py`, `src/datalog/pressure_logger.py` | [ ] |
| 8.3.3 | **[P7]** Reconsider the `amount_adsorbed` signature. The function asks the caller to precompute `n_initial_mol`, but the caller almost always does so via `moles_from_pressure` with a *different* volume than the `total_volume_l` it then passes. This pushes ideal-gas arithmetic back onto the caller, defeating the point of centralizing it. Two options: (a) add a convenience wrapper `amount_adsorbed_from_pressures(p_initial_torr, source_volume_l, p_equilibrium_torr, total_volume_l, ...)` that does both moles calculations internally; or (b) leave `amount_adsorbed` alone and accept that experimental protocols will always need some manual wiring. Human decides after reviewing the call sites in `pressure_logger.py` and `experiments/adsorption.py`. | `src/core/physics.py`, call sites | [ ] |

**Validation:** `pytest tests/test_physics.py -v` passes. Any changes to call sites outside `core/` revalidated via their own test suites.

---

## Phase 8.4 — `hardware/` package improvements

Findings from the hardware package review. Ordered by priority: latent bugs first, then error-handling policy, then casts, then smaller items.

### Latent bugs

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.4.1 | **[H12]** Fix `NI_USB6009.read_analog_input` voltage range. Current code declares `min_val=10.0, max_val=10.0` — a zero-width range, nonsensical. Change to `min_val=0.0, max_val=5.0` to match the actuator write range and typical signal levels. Verify with the human that these are the correct bounds for your signals before committing. | `src/hardware/analog_io.py` | [ ] |
| 8.4.2 | **[H8]** Resolve `KasaConfig` field mismatch. `KasaPower.__init__` reads `credentials.username` and `credentials.password`, but the `KasaConfig` dataclass in `config_loader.py` does not declare those fields. Test fixtures construct `KasaConfig(..., username="user", password="pass")`. Grep the real `config_loader.py` for the current truth; if `username`/`password` are missing, add them (with `None` defaults, since creds come from env vars). Run on real hardware after the fix — this is a latent `AttributeError` that only fires when live credentials are used. | `src/core/config_loader.py`, `src/hardware/power.py`, `tests/test_hardware/test_connections.py` | [ ] |

### Error-handling policy

Hardware adapters currently use three different failure conventions (raise, return `None`/`{}`, return a tuple with `None` inside). Downstream code has to guess which applies per adapter, which is error-prone and unsafe for a lab instrument.

**Policy:** unrecoverable hardware failures (missing connection, missing actuator mapping, Modbus read error, thermocouple fault) raise a distinctive exception. The hardware layer never calls `sys.exit`. The control or experiment layer catches these exceptions and triggers a safe-shutdown sequence (close gas valves, stop heating, turn on chiller, close log files) before exit.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.4.3 | Define a small exception hierarchy in `src/hardware/__init__.py` (or `src/hardware/errors.py`): `HardwareError` (base), `HardwareConnectionError`, `HardwareReadError`, `HardwareMappingError`, `ThermocoupleFault`. Document each in the hardware `AGENTS.md`. | `src/hardware/__init__.py` or `src/hardware/errors.py`, `src/hardware/AGENTS.md` | [ ] |
| 8.4.4 | **[H2, H4, H5]** Replace `sys.exit` in `WatlowTemperature.tc_malfunc` with `raise ThermocoupleFault(...)`. Keep the recovery behavior (reading setpoint, logging) but leave the abort decision to the caller. Remove the `NoReturn` annotation since the method now raises instead of exiting. | `src/hardware/temperature.py` | [ ] |
| 8.4.5 | **[H2]** Standardize "no mapping" and "no connection" behavior across adapters. Currently `AnalogIO.write` returns `False` on missing mapping, `WatlowTemperature` raises, `ExtrelMassSpec` returns `None`, `MKSPressure` logs and returns a tuple-with-`None`s, `OpusSpectrometer` returns `{}`. Per the policy above: `AnalogIO.write` should raise `HardwareMappingError` when the actuator ID is unknown. All adapters should raise `HardwareConnectionError` when the injected client is `None`. Update tests. | `src/hardware/analog_io.py`, `src/hardware/mass_spec.py`, `src/hardware/power.py`, `src/hardware/pressure.py`, `src/hardware/spectrometer.py`, `tests/test_hardware/` | [ ] |
| 8.4.6 | **[H13]** Fix silent degraded-connection mode in `DeviceManager.connect`. Currently when `self._watlow_client.connect()` or the Extrel equivalent returns `False`, the manager logs an error and sets the client to `None`, then happily constructs an adapter around it. A partially-connected system is dangerous. Choose one: (a) raise `HardwareConnectionError` from `connect()` when any required device fails; or (b) add an explicit `allow_partial: bool = False` flag that callers must opt into. Default must be fail-loud. | `src/hardware/connections.py`, `main.py`, `tests/test_hardware/test_connections.py` | [ ] |

### Cast removal

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.4.7 | **[H1]** Resolve the `cast(str, ...)` / `cast(int, ...)` calls in `connections.py` for Watlow and Extrel Modbus construction. These exist because `SerialDeviceConfig.parity`/`stopbits`/`bytesize` are typed `str \| None` / `int \| None` but are required in practice for Modbus devices. Tied to Phase 8.2.3 (C3). Either (a) split into `SerialDeviceConfig` (MKS-style, truly optional fields) and `ModbusSerialDeviceConfig` (Modbus-style, required fields), or (b) keep the single dataclass and validate-then-cast at construction time. | `src/core/config_loader.py`, `src/hardware/connections.py` | [ ] |
| 8.4.8 | **[H1]** Remove `cast(zmq.Socket, self._zmq_socket)` in `DeviceManager.connect`. Replace with an `if self._zmq_socket is None: raise HardwareConnectionError(...)` guard before the line that uses it. Same pattern for any similar "I know it's not None by now" casts elsewhere in `connections.py`. | `src/hardware/connections.py` | [ ] |
| 8.4.9 | **[H1]** Replace `cast(float, analog_value)` in `NI_USB6009.read_analog_input` with `float(analog_value)` (a real coercion). The zero-width range bug (8.4.1) probably means this read path has never been used, but the cast is still wrong. | `src/hardware/analog_io.py` | [ ] |
| 8.4.10 | **[H1]** Document the remaining cast: `cast(int, socket.getsockopt(zmq.RCVTIMEO))` in `spectrometer.py`. The `pyzmq` API returns `int | bytes` and this is a genuine polymorphic API, not a type system workaround. Add a short inline comment explaining why the cast is necessary so future readers don't try to "fix" it. Remove the unused `Any` import in the same pass ([H11]). | `src/hardware/spectrometer.py` | [ ] |

### H3 — Pressure gauge over-range behavior

**Context (from the human):** The `PressureReading` named tuple allows `str` values in `manifold` and `cell` fields on purpose. When the MKS gauge over-pressures it can't return a numeric reading, so the adapter captures the raw string. The *intent* was for downstream code to detect the string and trigger a pump-down to get back into gauge range. In practice gas delivery has been tuned finely enough that this rarely fires, and the human is not sure the recovery path was ever wired correctly.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.4.11 | **[H3, investigation only]** Grep the full codebase for consumers of `PressureReading` and document how each one handles the `manifold: float \| str \| None` / `cell: float \| str \| None` fields. Specifically look for (a) unconditional arithmetic (`p_mfld > threshold`) that would raise `TypeError` on a string, (b) explicit `isinstance(x, str)` or `type` checks, (c) callers that convert or ignore non-float values. Report to the human. Do not change code in this task. | all | [ ] |
| 8.4.12 | **[H3, decision required]** Based on 8.4.11, the human decides: (a) remove the string-in-tuple path entirely and treat an over-range read as a `HardwareReadError` that a controller catches and responds to with a pump-down; (b) keep the current data shape but fix the recovery wiring so the pump-down actually runs; (c) document the current behavior as known-broken and move on. Do not pick unilaterally. | `src/hardware/pressure.py`, `src/core/physics.py` (if the tuple changes shape) | [ ] |

### Smaller items

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.4.13 | **[H6, flag only]** Confirm that `opus_vertex80` lives in `src/control/spectrometer_control.py`, not `src/hardware/spectrometer.py`. Rename is deferred to Phase 8.5 (control review). Do not rename in this phase. | — | [ ] |
| 8.4.14 | **[H7]** Remove `OpusSpectrometer.send_message`. First grep all callers (`send_message` as a method, not as a string) and update each one to call `send` directly. Most will be in `SpectrometerController.opus_vertex80`. Then delete the compatibility method. Update any tests. | `src/hardware/spectrometer.py`, `src/control/spectrometer_control.py`, `tests/test_hardware/test_spectrometer.py` | [ ] |
| 8.4.15 | **[H9]** Cache the Kasa cloud auth token in `KasaPower`. Currently every `set_state` call calls `self.login()` first, re-authenticating on every relay change. Change to: on first `set_state`, log in and cache the token. On subsequent calls, try the cached token. If the Kasa API response indicates auth failure (typically `error_code != 0` with an "unauthorized" or "token expired" message), re-login once and retry. Log the cache-miss case. **Note:** this is a behavior change — verify with the human that the original per-call login was not load-bearing for a specific reason (e.g., very short token TTLs) before committing. | `src/hardware/power.py`, `tests/test_hardware/test_power.py` | [ ] |
| 8.4.16 | **[H10]** Add a docstring comment to `OpusSpectrometer.reconnect` explaining that the method replaces `self.socket` with a new socket. Outside references to the old socket object become stale after `reconnect()` is called. No code change — comment only. | `src/hardware/spectrometer.py` | [ ] |
| 8.4.17 | **[H11]** Remove unused `Any` import from `src/hardware/spectrometer.py`. Can be swept with 8.4.10. | `src/hardware/spectrometer.py` | [ ] |

**Validation:**
- `pytest tests/test_hardware/ -v` passes after each task.
- Full suite green at the end of the phase.
- Behavior checks to verify manually on real hardware: (a) Watlow thermocouple fault now raises `ThermocoupleFault` and `main` handles it with a safe shutdown; (b) Kasa plug control works with the cached token and recovers from token expiry; (c) DeviceManager fails loudly on any device that cannot connect; (d) NI analog input reads sensible voltages with the corrected range.

---

## Phase 8.5 — `control/` package improvements

Findings from the control package review. This is the highest-risk layer in the codebase — several items touch behavior-frozen code and are flagged for careful handling.

Tasks are grouped: error-handling policy, renames, structural extractions (the `watlow()` split and related datalog move), and small cleanups.

### Error-handling policy

The `control/` layer inherits the mixed error conventions of `hardware/`. Fixing here depends on the hardware exception hierarchy from 8.4.3.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.5.1 | **[CT1]** Replace `sys.exit` calls in `valves.py` with proper exceptions. Two call sites: `write()` when `voltage > voltage_max_write` (gas bulb empty), and `safe_mass_spec_open()` when `p_cell > mass_spec_open_max_cell_torr`. Introduce a `SafetyLimitExceeded` exception (in `src/hardware/errors.py` alongside the hardware hierarchy from 8.4.3, or a new `src/control/errors.py` — human decides placement). The exception should carry enough context (actuator_id, voltage or pressure, limit) for the experiment layer to log and trigger safe shutdown. Update the two tests in `test_valves.py` that currently assert `pytest.raises(SystemExit, match=...)` to match the new exception. | `src/control/valves.py`, `src/hardware/errors.py` or `src/control/errors.py`, `tests/test_control/test_valves.py` | [ ] |
| 8.5.2 | **[CT2]** Standardize error handling across all four control modules to use the hardware exception hierarchy (from 8.4.3). Audit each module and ensure: connection failures raise `HardwareConnectionError`; safety limits raise `SafetyLimitExceeded` (from 8.5.1); recoverable transient read errors may return sentinels only when the calling loop is explicitly polling. Document the per-method contract in docstrings. | `src/control/valves.py`, `src/control/gas_delivery.py`, `src/control/temperature_control.py`, `src/control/spectrometer_control.py` | [ ] |
| 8.5.3 | **[CT3]** Fix log levels in `spectrometer_control.py`. Three `logger.info(...)` calls in `opus_vertex80` (soon to be `send_opus_request`, see 8.5.4) log error conditions: "Error: Failed to send message to OPUS", "Reconnection or retry failed: %s", "Error: No response from OPUS after timeout and retry". Change to `logger.error` or `logger.warning` as appropriate. | `src/control/spectrometer_control.py` | [ ] |

### Renames and API shape

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.5.4 | **[CT5]** Rename `SpectrometerController.opus_vertex80` → `send_opus_request`. The current name refers to a specific Bruker instrument model; the function describes a request/reply pattern that would work with any OPUS-compatible spectrometer. Update the two internal callers in `opus_acquire`, the four caller sites in `experiments/adsorption.py` and `experiments/isotopic_exchange.py` (one is tagged `[fix] could use a better name`), and all tests in `tests/test_control/test_spectrometer.py`. | `src/control/spectrometer_control.py`, `src/experiments/adsorption.py`, `src/experiments/isotopic_exchange.py`, `tests/test_control/test_spectrometer.py` | [ ] |
| 8.5.5 | **[CT12]** Type `GasDelivery.read_pressure()` and `MKSPressure.read()` returns as `PressureReading` (the `NamedTuple` already defined in `src/hardware/pressure.py`). Currently annotated `tuple[Any, Any, Any]` which defeats type-checking. Remove `from typing import Any` from `gas_delivery.py` if no longer needed. Downstream callers that unpack the tuple (`dt, p_mfld, p_cell = ...`) continue to work unchanged since `PressureReading` is a NamedTuple. | `src/control/gas_delivery.py`, `src/hardware/pressure.py`, possibly caller signatures that explicitly annotate the tuple | [ ] |
| 8.5.6 | **[CT9]** Remove `GasDelivery.pressure_adapter()` and `TemperatureController.temperature_adapter()`. Their only caller is `PressureLogger` / `TemperatureLogger` construction in `experiments/isotopic_exchange.py` and `experiments/adsorption.py`. Replace with direct adapter injection from `main.py` — pass the `MKSPressure` and `WatlowTemperature` instances (already available as `devices.pressure` / `devices.temperature`) straight into the experiment constructors, then into the loggers. Keep `read_pressure()` and `read_temperature()` — those are legitimate pass-throughs used by experiment control flow. | `src/control/gas_delivery.py`, `src/control/temperature_control.py`, `src/experiments/adsorption.py`, `src/experiments/isotopic_exchange.py`, `main.py` | [ ] |
| 8.5.7 | **[CT14]** Consolidate `TemperatureController` plug methods. Remove `chiller_state(cmd)` and `variac_state(cmd)` convenience wrappers — they hardcode specific plug IDs and duplicate `kasa_plug_state`. Rename `kasa_plug_state` → `set_plug_state` (symmetric with `set_temperature`, drops the implementation-detail "kasa" prefix). Update callers — `experiments/` uses `chiller_state` and `variac_state` in `chiller_variac_state(...)`; those become `set_plug_state(self.kasa.chiller_id, cmd)` etc. | `src/control/temperature_control.py`, `src/experiments/adsorption.py`, `src/experiments/isotopic_exchange.py`, tests | [ ] |

### Structural extractions — `watlow()` split and the datalog move

These three tasks are coupled. **CT6** (remove module-level globals) and **CT7** (split `watlow()` into three methods) are the same cleanup seen from two angles: the globals exist because the CSV-writing logic lives in `control/` instead of `datalog/` where it belongs. Moving the CSV writes to `datalog/` makes the globals evaporate and makes the `watlow()` split cleaner.

**`[FROZEN]` tasks.** These touch behavior-frozen code. Per the top-level scope policy, each requires explicit human go-ahead before execution. Validation must produce identical Modbus writes, identical `time.sleep` durations, identical variac on/off ordering, identical CSV rows written at identical times.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.5.8 | **[CT6 preparation]** Before any code change, grep `watlow()` and document every write to `dir_tempLog` and `path_tempLog`, every read, every `log_temperature(...)` call, every `create_directory(...)` call, and every `open(path_tempLog, "a", ...)` inside `hold_temp`. Produce a list of "log entries written per `watlow()` invocation" for each of the three branches (ramp, cooling, else). This is the behavioral contract the refactor must preserve. Report to the human before proceeding. | `src/control/temperature_control.py` | [ ] |
| 8.5.9 | **[CT6, CT7]** Create a `TemperatureLogWriter` class in `src/datalog/` (likely a new `temperature_log_writer.py` — distinct from the threaded `TemperatureLogger` which polls the thermocouple). `TemperatureLogWriter` owns the CSV path construction, directory creation, and row-appending logic currently implemented via the `dir_tempLog` / `path_tempLog` module globals. Its interface takes a `paths: PathsConfig`, `filename`, `foldername` at construction, and exposes `write_ramp_rows(write_temps, read_temps, timestamps)` and `append_hold_row(write_temp, read_temp, timestamp)`. No behavior change — the methods produce the same CSV output as the current `log_temperature` call and the inline `csv_file.write(...)` call in `hold_temp`. | `src/datalog/temperature_log_writer.py`, `src/datalog/__init__.py` | [ ] |
| 8.5.10 | **[FROZEN] [CT7]** Split `TemperatureController.watlow()` into three methods: `ramp_to_target(...)` (the `rate != 0` branch), `cool_to_target(...)` (the `rate == 0 and current_temp > target+5` branch), and `hold_at_target(...)` (the else branch, plus the final `hold_temp` call shared by all branches). The public `watlow(...)` method becomes a thin dispatcher: construct the `TemperatureLogWriter` from 8.5.9, select the branch based on `rate` and `current_temp` vs `target`, and delegate. Remove the nested `generate_temp_list` and `hold_temp` functions — promote them to private methods (`_generate_setpoint_list`, `_hold_at_setpoint`) that receive the log writer explicitly. | `src/control/temperature_control.py` | [ ] |
| 8.5.11 | **[CT6]** Remove module-level `dir_tempLog` and `path_tempLog` declarations from `temperature_control.py`. Remove `global dir_tempLog, path_tempLog` from all methods. Remove the test fixture line `temperature_control_module.path_tempLog = "unused.csv"` that works around the global state. | `src/control/temperature_control.py`, `tests/test_control/test_temperature.py` | [ ] |
| 8.5.12 | **[FROZEN]** Hardware revalidation after 8.5.8 – 8.5.11. Run a ramp, a cooling cycle, and a set-and-hold on real hardware. Byte-diff the generated `_tempLog.csv` files against a reference file captured before the refactor. Any difference — timestamps, setpoints, read values, row count — means a behavior change slipped through. | real hardware | [ ] |

### Investigation — overpressure recovery path

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.5.13 | **[FROZEN] [CT8]** Investigate and remove the broken overpressure-recovery path in `deliver_gas_to_manifold`. The nested `pressure_difference()` function uses `global p_mfld_f` with a `try/except TypeError` to catch the string-from-gauge case (the H3 pattern from hardware review). The human has confirmed this path was intended to trigger a pump-down on overpressure but does not actually work as intended. Steps: (a) grep `gas_delivery.py` for every use of `p_mfld_f` and document the control flow; (b) confirm with the human that the path should be removed entirely rather than fixed; (c) remove the `global p_mfld_f` declaration, the `try/except TypeError` handler, and any code paths downstream of them that depend on the string-value signal; (d) verify tests still pass and that the remaining happy-path behavior is unchanged. This is coupled to hardware task 8.4.12 — the decision on pressure-gauge overrange handling must be consistent between the two layers. | `src/control/gas_delivery.py`, possibly `src/hardware/pressure.py` | [ ] |

### Smaller items

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.5.14 | **[CT4, flag only]** Document thread-safety expectations of control-layer methods. Currently `experiments/adsorption.py` launches threads targeting `self.ftir.opus_acquire` and `self.gas_controller.cell_open_admit`; both methods call hardware adapters that share serial/Modbus connections with the main thread. No control-layer class declares which methods are safe to call concurrently. Add a "Concurrency" section to each control module's class docstring stating: (a) which methods are safe to call from a background thread; (b) which shared hardware adapters are re-entered and how contention is avoided (if at all). No code change — documentation only. Full fix deferred to Phase 8.7 (experiments review). | `src/control/gas_delivery.py`, `src/control/spectrometer_control.py`, `src/control/temperature_control.py`, `src/control/valves.py` | [ ] |
| 8.5.15 | **[CT10]** Standardize on `pathlib.Path` throughout `control/`. Replace `os.path.join(...)` in `temperature_control.py` and `gas_delivery.py` with `Path(...) / ...`. Update imports accordingly. Verify downstream callers (`create_directory`, `log_actuator_state`, `log_temperature` in `datalog/file_io.py`) accept `Path` or `str` — they should already, but confirm. | `src/control/temperature_control.py`, `src/control/gas_delivery.py` | [ ] |
| 8.5.16 | **[CT11]** Remove `paths: PathsConfig` from `GasDelivery.__init__`. Its only use is constructing `path_actLog` inside `deliver_gas_to_manifold`. Move path construction to the caller (experiment or session layer) and pass the resolved path into `deliver_gas_to_manifold` as an argument. This makes `GasDelivery` a pure control class with no I/O-location concerns — matches the same goal as 8.5.9 for `TemperatureController`. Update `main.py`, experiment call sites, and tests. | `src/control/gas_delivery.py`, `main.py`, `src/experiments/adsorption.py`, `src/experiments/isotopic_exchange.py`, tests | [ ] |
| 8.5.17 | **[CT13]** Remove unused imports from `gas_delivery.py`. `datetime` and `timedelta` are imported but not used in the file. | `src/control/gas_delivery.py` | [ ] |

**Validation:**
- `pytest tests/test_control/ -v` passes after each task.
- Full suite green at the end of the phase.
- Hardware revalidation after 8.5.12 — byte-diff `_tempLog.csv` against a pre-refactor reference.
- Manual smoke test on real hardware: one adsorption run, one isotopic exchange run. Confirm: (a) no `SystemExit` from safety paths — exceptions bubble up and `main.py` handles cleanly; (b) OPUS request/retry behavior unchanged after the rename; (c) no regression in gas delivery timing or pressure dithering.

---

## Phase 8.6 — `datalog/` package improvements

Findings from the datalog package review. This is where most of the codebase's threading lives, so several tasks address the "threading events inconsistent" concern directly.

Tasks are grouped: threading consistency, constructor and config cleanup, structural questions requiring human input, small cleanups.

### Threading consistency

The three threaded loggers (`PressureLogger`, `TemperatureLogger`, `MassSpecLogger`) have the same structure but diverge in per-read error handling, `KeyboardInterrupt` handling, log-level usage, parameter names, and interval types.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.6.1 | **[DL2, DL13]** Make `MassSpecLogger` consistent with the other two loggers. Add `try/except KeyboardInterrupt` around the `while not self._stop.is_set()` loop, mirroring the pattern in `PressureLogger._run` and `TemperatureLogger._run`. Add `try/except Exception` around the `self.mass_spec.read_registers(...)` call so a single bad read does not kill the worker thread; on exception, log via `logger.error` and continue the loop (write a `None` row or skip, matching what the other loggers do on read failure). Change the existing "read error" message from `logger.info` to `logger.error`. | `src/datalog/mass_spec_logger.py` | [ ] |
| 8.6.2 | **[DL14]** Change `TemperatureLogger.read_interval_s` from `int = 5` to `float = 5.0`. Allows sub-second polling and matches the type used by `PressureLogger`. Audit callers — if any pass `int` positional arguments, they continue to work via implicit conversion. | `src/datalog/temperature_logger.py`, possibly caller sites | [ ] |
| 8.6.3 | Standardize the interval parameter name across all three loggers. `MassSpecLogger` uses `poll_interval_s`; the other two use `read_interval_s`. Pick one — `read_interval_s` is more consistent with the polling-based pattern and matches the majority. Rename `MassSpecLogger.poll_interval_s` → `read_interval_s`. Update `tests/test_datalog/test_mass_spec_logger.py` and any construction sites. | `src/datalog/mass_spec_logger.py`, tests | [ ] |
| 8.6.4 | **[DL12]** Extract the "create CSV with headers if missing, else append" logic that is duplicated in all three loggers' `_run` methods. Add a helper `_open_csv_with_header(path: Path, header: list[str]) -> tuple[TextIO, csv.writer]` (or similar) either in `datalog/_csv_helpers.py` or as a private function in each logger's module. Thin, not worth a base class. Apply to all three loggers. | `src/datalog/pressure_logger.py`, `src/datalog/temperature_logger.py`, `src/datalog/mass_spec_logger.py`, possibly `src/datalog/_csv_helpers.py` | [ ] |

### Constructor and config cleanup

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.6.5 | **[DL4]** Simplify `PressureLogger.__init__`. Currently takes 11 parameters including three that are duplicated from `SystemConstants` / `SampleConfig` (`metal_molar_mass_g_mol`, `temperature_k`, `gas_constant`) and three that come from `SampleConfig` (`mass_g`, `metal_load_wt_percent`, etc.). Replace with `sample: SampleConfig`, `constants: SystemConstants`, `volumes: SystemVolumes` (renamed from `physics` for clarity), plus the runtime values (`p_mfld_initial`, `p_cell_initial`, `path`, `read_interval_s`). Eliminates the duplicated default values that currently exist only as fallback. Update `main.py` and both experiment files that construct `PressureLogger`. | `src/datalog/pressure_logger.py`, `main.py`, `src/experiments/adsorption.py`, `src/experiments/isotopic_exchange.py`, `tests/test_datalog/test_pressure_logger.py` | [ ] |
| 8.6.6 | **[DL5, P7]** Extract the derived-metrics physics math from `PressureLogger._run` into a pure function in `core/physics.py`. Proposed signature: `compute_pressure_metrics(p_mfld: float, p_cell: float, dt: datetime, t0: datetime, p_mfld_initial: float, p_cell_initial: float, volumes: SystemVolumes, sample: SampleConfig, constants: SystemConstants) -> PressureMetrics` where `PressureMetrics` is a small NamedTuple or dataclass with fields `relative_time_s`, `amount_adsorbed_umol_per_g`, `apparent_conversion`, `apparent_coverage`. `PressureLogger._run` calls this per tick and writes the NamedTuple as a CSV row. Resolves the `amount_adsorbed`-caller-does-manual-arithmetic problem flagged in P7. Unit-testable in isolation without threading. | `src/core/physics.py`, `src/datalog/pressure_logger.py`, `tests/test_physics.py` | [ ] |
| 8.6.7 | **[DL6]** Move `MassSpecLogger` tag names out of the code. Currently `tags = ["V1_I_28", "V1_I_29", "V1_I_44", "V1_I_45"]` is hardcoded in `_run`. Add `stream_tags: list[str]` to `ExtrelRegisterConfig` (or a nearby config dataclass) and populate from `config/devices.yaml` under `extrel_ms.stream_tags`. Pass into `MassSpecLogger.__init__`. Tests update to pass test tags. | `src/core/config_loader.py`, `config/devices.yaml`, `src/datalog/mass_spec_logger.py`, `main.py`, `tests/test_datalog/test_mass_spec_logger.py` | [ ] |
| 8.6.8 | **[DL7]** After 8.6.7, replace the hardcoded 4-pair decode in `MassSpecLogger._run` with an iteration over `len(self.stream_tags)`: `vals = [self.mass_spec.decode_ieee754_cdab(regs[2*i], regs[2*i+1]) for i in range(len(self.stream_tags))]`. Also derive `count` in `read_registers(..., count=2 * len(self.stream_tags))`. Removes the "4" magic number. | `src/datalog/mass_spec_logger.py` | [ ] |

### Structural — human decision required

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.6.9 | **[DL9, human decision]** `file_io.py` currently mixes three responsibilities: (1) CSV/markdown primitives (`create_directory`, `log_to_csv`, `log_experiment_parameters`); (2) domain-specific loggers (`log_actuator_state`, `log_temperature`, `write_material_parameters`); (3) experiment session bookkeeping (`generate_experiment_id`, `_increment`, `material_prefix`, `copy_to_share_drive`). Option A: split into `datalog/csv_io.py`, `datalog/markdown_io.py`, and move session-bookkeeping functions to `experiments/session_naming.py` (or similar). Option B: leave as-is, accept the mixing. Option C: partial split — keep CSV/markdown together in `datalog/` but move session-bookkeeping to `experiments/`. This is a structural split affecting imports across much of the codebase; the human decides based on how often these modules are edited. Report and wait for go-ahead before any file moves. | `src/datalog/file_io.py`, possibly `src/experiments/` | [ ] |
| 8.6.10 | **[DL10]** If 8.5.9 is executed (creating `TemperatureLogWriter` in `datalog/`), rename the two similarly-named classes to avoid future confusion. Current: `TemperatureLogger` (threaded thermocouple poller) and `TemperatureLogWriter` (synchronous ramp CSV writer). Proposed: `ThermocouplePoller` or `TemperatureMonitor` for the threaded one; `RampLogger` or `SetpointLogger` for the synchronous one. Human picks names. If 8.5.9 is *not* executed, this task is dropped. | `src/datalog/temperature_logger.py`, possibly `src/datalog/temperature_log_writer.py`, all callers, tests | [ ] |
| 8.6.11 | **[DL11, human flag]** Document the file-handle lifetime of the threaded loggers. All three hold the CSV file open for the entire experiment duration and flush after every row. This is a deliberate design choice (avoids reopen overhead, preserves data on crash) but it's also why `shutil.copy2(...)` calls on the log files in `adsorption.py` can fail with "file in use" on Windows during an experiment. Add a short note to each logger's class docstring explaining: (a) the file is held open for the duration of the logger; (b) to safely copy the file externally, call `logger.stop()` first. No code change. The human may later decide to restructure copy-to-share-drive to happen after `logger.stop()` as part of the Phase 8.7 end-of-experiment cleanup work ("do post `__init__` to move readme" note). Flag for that phase. | `src/datalog/pressure_logger.py`, `src/datalog/temperature_logger.py`, `src/datalog/mass_spec_logger.py` | [ ] |

### Small cleanups

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.6.12 | **[DL1]** Remove the `cast(float, p_mfld)` in `PressureLogger._run`. Once H3 / 8.4.12 / 8.5.13 resolve how pressure over-range is handled at the hardware and control layers, `PressureReading.manifold` will be a real `float | None` (no string case). At that point the cast is dead code. Schedule this task to run after 8.4.12 and 8.5.13 complete. If those decisions land on "keep the string path," this task is dropped. | `src/datalog/pressure_logger.py` | [ ] |
| 8.6.13 | **[DL3]** Align `PressureLogger._run` with whatever decision is made in 8.4.12 / 8.5.13 about pressure gauge over-range. If the string-value path is removed upstream, the `is not None` branching in `_run` simplifies — just write the row. If the string path stays, add an explicit handler in `_run` so an over-range reading does not silently land in the CSV as a string in a float column. Coupled to 8.6.12. | `src/datalog/pressure_logger.py` | [ ] |
| 8.6.14 | **[DL8]** Convert `file_io.py` to `pathlib.Path` throughout. Replace `os.path.exists`, `os.path.join`, `os.makedirs`, `os.listdir`, `os.path.basename`, `glob.glob` with `Path` equivalents. Higher-churn than the control-layer pathlib task (8.5.15) because `file_io.py` does more filesystem work. Verify downstream callers still work — most accept `str | Path` already. | `src/datalog/file_io.py`, callers | [ ] |
| 8.6.15 | **[DL15]** Review `src/datalog/__init__.py`. Goal: confirm that the imports-at-top cleanup from the earlier Phase 2.4 task was completed, and that re-exports (`configure_logging`, `get_logger`) are the minimal set actually used externally. Document what's exported and why in a module docstring. No functional change expected — this is a verification task. | `src/datalog/__init__.py` | [ ] |

**Validation:**
- `pytest tests/test_datalog/ -v` passes after each task.
- Full suite green at the end of the phase.
- Smoke-run both experiments in mock mode; confirm logger outputs (CSV row count, header format, column contents) unchanged except where explicitly changed by 8.6.6 (the `compute_pressure_metrics` extraction must produce identical numeric values).
- For 8.6.1, simulate a read-side exception from `MassSpecLogger`'s mock and confirm the worker thread survives and continues writing rows.

---

## Phase 8.7 — `experiments/` package improvements

**Deprecation note.** `src/experiments/isotopic_exchange.py` is deprecated and will be revisited separately. It is **excluded** from every task in this phase, even tasks whose pattern would otherwise apply to it. When the module is revisited in a future phase, these same findings will be re-evaluated against whatever shape the new isotopic-exchange code takes. Do not apply Phase 8.7 edits to `isotopic_exchange.py`.

### Cleanup and refactor tasks

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.7.1 | **End-of-experiment cleanup extraction.** The tail of `AdsorptionExperiment.acquire_spectra` currently does four things after the OPUS acquisition completes: (a) `self.session.mark_success(success=True)`; (b) `self.session.is_new_sample_experiment()`; (c) copies README and pressureLog to the share drive; (d) sends `{"readme": True}` to OPUS. When an experiment is aborted mid-run, none of this executes and the human has to perform the steps manually. Extract into a method `finalize(success: bool)` on `AdsorptionExperiment` that runs steps (a), (b), (c), (d). The happy path in `acquire_spectra` calls `self.finalize(success=True)` at the end. The abort path is wired up in Phase 8.8 (main.py review) — the human will decide there whether to use a context manager, `try/finally`, or another shape. `finalize()` must be idempotent (safe to call twice) in case both the happy path and the abort handler invoke it. | `src/experiments/adsorption.py` | [ ] |
| 8.7.2 | **Clarify `__post_init__`.** The `@dataclass` decorator generates `__init__` from the five injected dependency fields. `__post_init__` is Python's dataclass hook that runs at the end of that generated `__init__`. The current use initializes six instance attributes that aren't dataclass fields (`gas`, `gas_2`, `p_mfld`, `p_cell_calc`, `dt`, `chiller_state`) to `None` so later protocol methods can mutate them without `AttributeError`. This works but hides the object's state from its class signature. Option A: add a docstring to `__post_init__` explaining it initializes runtime-state attributes, list the attributes. Option B: promote the six attributes to full dataclass fields with `None` defaults using `dataclasses.field(default=None)`, putting all state in the class signature; `__post_init__` can then be deleted. Option B is preferred because it makes the state visible at a glance. Human confirms option before proceeding. | `src/experiments/adsorption.py` | [ ] |
| 8.7.3 | **[EX3]** Clean up `ExperimentSession.is_new_sample_experiment` without removing it. Keep the method as a safety-net check for when the user forgets to pass `new_sample=True` to `new_experiment`. Three fixes: (a) replace the regex-match-on-markdown-content for success check with a proper read of the `exp_success` value — since `mark_success` writes this field in a structured way, reading it should not require a regex with `DOTALL | IGNORECASE`; reuse whatever helper `_check_line_exists` uses, or add a `_read_field_value(name: str) -> str | None` helper; (b) thread `new_sample: bool` from `new_experiment()` into README metadata at experiment start (a new `log_experiment_parameters` call that writes the authoritative value); (c) on `is_new_sample_experiment()` call, compute the share-drive-derived value as today but log a warning if it disagrees with the authoritative value written at start. The method keeps its side effect (appending `is_new_sample` to the README) for backward compatibility with downstream consumers. Add a docstring explaining the safety-net role. | `src/experiments/session.py` | [ ] |
| 8.7.4 | **[EX4]** Fix the bug in `AdsorptionExperiment.chiller_variac_state`. Current code passes the literal string `"variac_id_vsl"` to `self.temp.kasa_plug_state(...)` instead of the actual plug ID `self.temp.kasa.variac_id_vsl`. The test also encodes the bug (`assert_called_once_with("variac_id_vsl", False)`). Fix both the production code and the test assertion. Also remove the `None` guards — grep `main.py` confirms no caller passes `None` for any of the three arguments, so the guards are dead code. If a future caller legitimately wants "leave this one alone," they can omit the argument via a default of `None` with an explicit skip, but since no caller does that today, drop the guards. | `src/experiments/adsorption.py`, `tests/test_experiments/test_adsorption.py` | [ ] |
| 8.7.5 | **[EX5]** Move `chiller_variac_state` from the experiment class to `TemperatureController`. The method body is pure delegation to three plug-state calls — the chiller, the manifold-heating variac (`variac_id`), and the vessel-heating variac (`variac_id_vsl`). Propose new method: `TemperatureController.set_heating_elements(chiller: bool, manifold_variac: bool, vessel_variac: bool)` — the parameter names describe what the plugs control rather than the implementation detail of "variac." Delete the experiment-class method. Update `main.py` calls from `ads_exp.chiller_variac_state(...)` to `temp_ctrl.set_heating_elements(...)` — this means `main.py` needs access to the `TemperatureController` directly, which is fine since it's already constructed there. Depends on 8.5.7 (the `kasa_plug_state` consolidation) having landed; if 8.5.7 used a different name, match it. | `src/control/temperature_control.py`, `src/experiments/adsorption.py`, `main.py`, `tests/test_control/test_temperature.py`, `tests/test_experiments/test_adsorption.py` | [ ] |
| 8.7.6 | **[EX6]** Move experiment-class plumbing methods to their proper homes. Candidates for relocation: (a) `start_pressure_log(p_mfld_initial, p_cell_initial)` — constructs and starts a `PressureLogger`; move to `ExperimentSession.start_pressure_log(...)` since `session` already owns `path_pressure_log`, `sample`, and `volumes`; (b) `start_temperature_log()` — same pattern, move to `ExperimentSession.start_temperature_log()`; (c) consider whether `acquire_ms_spectra()` also belongs on session or stays on the experiment class — it mixes valve sequencing (experiment-protocol) with logger start (plumbing); leave it on the experiment class but split the plumbing parts into a `session.start_mass_spec_log(...)` that the experiment method calls. After this task: the experiment class contains protocol methods (`heat_under_evacuation`, `cool_cell`, `supply_gas_to_mfld`, `supply_another_gas_to_mfld`, `introduce_pretreatment_gas_to_cell`, `acquire_spectra`, `acquire_ms_spectra`, `finalize`). Plumbing lives on `ExperimentSession`. Update `acquire_spectra` and other callers to invoke the new `session.*` methods. Depends on 8.5.6 (adapter-method removal) and 8.6.5 (simplified `PressureLogger.__init__`) having landed, so the new session methods take the narrow parameters. | `src/experiments/session.py`, `src/experiments/adsorption.py`, tests | [ ] |
| 8.7.7 | **[EX10]** Verify `ExperimentSession.counter` is actually used. Grep the repo for reads of `self.counter` (not just writes). If no reads exist outside of the two `self.counter = 0` assignments, the field is dead — remove it. If reads exist, document what the counter tracks and leave it alone. | `src/experiments/session.py`, possibly callers | [ ] |
| 8.7.8 | **[EX11]** Review the body of `ExperimentSession._check_line_exists`. It is called by `mark_success` and `log_experimental_parameters` to check whether a section header is already present in the README. Examine the implementation — if it is a simple `"## name" in content` check, that's fine and can be extended (per 8.7.3) to also read values. If it is a fragile regex pattern, fix it. Also produce a parallel `_read_field_value(name: str) -> str | None` helper that returns the value for a given section header, which 8.7.3 uses for the proper `exp_success` read. | `src/experiments/session.py` | [ ] |
| 8.7.9 | **[EX12, EX13]** Deduplicate experiment-ID generation between `ExperimentSession.new_experiment` and `datalog/file_io.generate_experiment_id` / `file_io._increment`. These look to be substantially the same logic. Steps: (a) diff the two implementations side-by-side and confirm the duplication; if they have diverged in subtle ways, document the differences before proceeding; (b) decide the right home for the logic — per 8.6.9, the strong candidate is `src/experiments/session_naming.py` (or equivalent) under `experiments/`, since experiment-ID generation is experiment-session concern, not data-logging concern; (c) move the single canonical implementation to that location; (d) have `ExperimentSession.new_experiment` call it. Depends on 8.6.9 (human decision on `file_io.py` split); do not start until 8.6.9 lands. | `src/experiments/session.py`, `src/datalog/file_io.py`, possibly new `src/experiments/session_naming.py`, tests | [ ] |

### Casts cleanup — resolved by upstream tasks

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.7.10 | **[EX1]** Remove the three `cast(float, ...)` calls (`p_mfld_value`, `p_cell_value`, `t_cell_value`) in `AdsorptionExperiment`. These exist because `self.p_mfld` is typed `float | str | None`. After 8.7.2 option B (runtime state promoted to fields) and 8.4.12/8.5.13 (pressure over-range handling resolved), the `| str` and `| None` go away and the casts become dead. Schedule after those tasks complete. Also remove `cast(str, self.session.path_ms_log)` in `acquire_ms_spectra` — once `ExperimentSession.path_ms_log` is known to be set after `new_experiment()` returns, either replace with an `assert self.session.path_ms_log is not None` guard or make the field non-optional after session init. Remove `from typing import cast` if no other uses remain. | `src/experiments/adsorption.py` | [ ] |

### Known items — deferred to separate design discussion

Not yet filed as concrete tasks. These are architectural questions the human has flagged for later:

- Is `AdsorptionExperiment` correctly a dataclass, or should it be a regular class? (Loosely coupled to 8.7.2 — if option B is chosen, the dataclass stays with richer state. If option A, revisit whether dataclass is pulling its weight.)
- Function naming review beyond `opus_vertex80` (already handled in 8.5.4). Look for other instrument-model-named functions or legacy-style names.
- Threading event consistency — the `start_temperature_log` investigation from earlier Phase 6 lives here if not yet resolved. Also investigate: are threading lifecycles consistent across `opus_thread`, `gas_thread`, `PressureLogger`, `TemperatureLogger`, `MassSpecLogger`? Per the standing checklist, threading primitives must be consistent across sibling modules.
- Further separation-of-concerns work beyond 8.7.5/8.7.6. Current experiments are long procedural methods that mix control-layer calls, pressure/temperature reads, logging setup, and file I/O. 8.7.5 and 8.7.6 move the plumbing out; the question of whether protocol methods themselves should decompose into smaller atomic operations remains open.
- Loggers placement: the original note asked "move loggers to the control layer?" — Phase 8.5 answered part of this the other direction (moving CSV-writing from `control/` to `datalog/`). Revisit whether any threaded loggers (`PressureLogger`, `TemperatureLogger`, `MassSpecLogger`) belong in `control/` instead of `datalog/`, and what the distinction should be. My current read: `datalog/` owns "write data to disk," `control/` owns "make hardware do a thing." Loggers that poll hardware in a thread and write to disk straddle both; `datalog/` is the right home because the purpose is recording, not controlling. Document the decision in `datalog/AGENTS.md` and/or `control/AGENTS.md`.
- Coordinate with 8.6.11 (file-handle lifetime docstrings on loggers): once `finalize()` exists from 8.7.1, revisit the order of operations — `logger.stop()` must run before the share-drive `shutil.copy2` to avoid the Windows "file in use" failure mode.
- `isotopic_exchange.py` is deprecated. When it is revisited, re-evaluate all Phase 8.7 findings against the new shape: parameter naming consistency (camelCase bugs in current code), `copy_readme` vs `finalize` unification, `spec` vs `ftir` field-name consistency with `adsorption.py`, inline CSV-writing in `massSpec_calibration` that should use `log_to_csv`, the `mass_spec_open_calibration` method on `GasDelivery`, and the large undecomposed methods (`isoX_calib_main`, `massSpec_calibration`).

**Validation:**
- `pytest tests/test_experiments/ -v` passes after each task.
- Full suite green at the end of the phase.
- Smoke-run `main.py --mock --adsorption` end-to-end. Confirm: (a) the experiment completes the happy path; (b) `finalize` runs and copies the README / pressureLog / sends the OPUS readme command; (c) the `is_new_sample` field is written both at experiment start (authoritative) and at end (sanity-check), and a warning logs if they disagree; (d) `chiller_variac_state` → `set_heating_elements` change leaves all three plug states correctly set; (e) `start_pressure_log` and `start_temperature_log` called via the session produce CSVs identical to before.

---

## Phase 8.8 — `main.py` improvements

`main.py` is the entry point — argparse, mode selection, object-graph wiring, and dispatching to one of two experiment protocols. The human has noted this file is intended to be replaced with a proper configured experiment-runner in a future work item. Phase 8.8 does not attempt that replacement. It fixes real problems (abort handling, resource cleanup, misplaced test scaffolding) and leaves the larger rewrite for later.

### Abort handling and resource cleanup

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.8.1 | **[MN1]** Wire abort handling via `try/finally`. Depends on 8.7.1 (`finalize(success: bool)` method on `AdsorptionExperiment`) having landed. Pattern: each experiment's run function wraps its body in `try: ... success=True; finally: ads_exp.finalize(success=success)`. The `success` flag starts `False` and flips to `True` only after the last protocol step completes. On exception or `KeyboardInterrupt`, the `finally` runs with `success=False`, which triggers the authoritative `mark_success(False)` + share-drive copy + OPUS readme command even on abort. Example: <br><br> ```python<br>def run_adsorption_experiment(ads_exp):<br>    logger.info("Starting adsorption experiment...")<br>    session.new_experiment()<br>    success = False<br>    try:<br>        ads_exp.chiller_variac_state(...)<br>        ads_exp.heat_under_evacuation(...)<br>        # ... remaining protocol steps ...<br>        ads_exp.acquire_spectra(...)<br>        success = True<br>        logger.info("Adsorption experiment completed!")<br>    finally:<br>        ads_exp.finalize(success=success)<br>``` <br><br> Apply the same pattern to `run_isotopic_exchange_calibration` when the deprecated module is revisited. For now, only wire adsorption. | `main.py` | [ ] |
| 8.8.2 | **[MN10]** Add `devices.disconnect()` to an outer `try/finally` in `main()`. This ensures serial ports and ZMQ sockets are released when the program exits, whether cleanly or via abort. Guard with `if not args.mock` since mock disconnect is a no-op. Pattern: <br><br> ```python<br>try:<br>    if args.adsorption:<br>        ads_exp = AdsorptionExperiment(...)<br>        run_adsorption_experiment(ads_exp)<br>    elif args.isotopic:<br>        iso_exp = IsotopicExchangeCalibration(...)<br>        run_isotopic_exchange_calibration(iso_exp)<br>finally:<br>    if not args.mock:<br>        devices.disconnect()<br>``` <br><br> The nested `try/finally` from 8.8.1 runs inside the run function; this outer one runs at `main()` level and handles the case where an error occurs before the experiment even starts (e.g., during wiring). | `main.py` | [ ] |

### Structural — test scaffolding and CLI hygiene

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.8.3 | **[MN2]** Move `create_mock_devices` out of `main.py`. Interim home: `src/hardware/mocks.py`. Reason for the interim placement: during the Docker-based refactor verification, `main.py --mock` is used as a smoke-test of the full object graph without real hardware, which is a dev-time use case, not a pytest use case. Keeping the mock in `src/hardware/` rather than `tests/` lets `main.py` import it cleanly while that verification is ongoing. Update the import in `main.py` to `from src.hardware.mocks import create_mock_devices`. Audit existing tests for any hand-rolled `MagicMock(spec=DeviceManager)` fixtures that duplicate this code and replace with imports from the new location. | `main.py`, `src/hardware/mocks.py`, existing test files | [ ] |
| 8.8.3b | **[MN2 follow-up, human flag]** Once the human has completed Docker-based refactor verification and is back to daily work on real hardware, revisit whether `src/hardware/mocks.py` should move to `tests/fixtures/mock_devices.py`. The decision hinges on whether `main.py --mock` is still serving a dev-time role. If the human still uses `--mock` for smoke-testing after hardware changes, the file stays in `src/hardware/`. If `--mock` has become purely a test utility, move it to `tests/` and update the `main.py` import to be a late import inside the `if args.mock:` branch (so tests never pull in production code they don't need, and real-hardware runs never touch the `tests/` directory). Human confirms which direction before moving. | `src/hardware/mocks.py`, possibly `tests/fixtures/mock_devices.py`, `main.py` | [ ] |
| 8.8.4 | **[MN3]** Add explicit CLI error when no experiment flag is set. Currently `python main.py --mock` with no `--adsorption` or `--isotopic` sets up the full mock device graph and exits silently. Add an `else` branch after the experiment dispatch that calls `parser.error("Must specify --adsorption or --isotopic")`. Consider also making `--adsorption` and `--isotopic` mutually exclusive via `add_mutually_exclusive_group` and making the group required, which produces a clearer argparse error automatically. Human picks the approach. | `main.py` | [ ] |

### Design questions requiring human input

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.8.5 | **[MN4, human decision]** Decide: should `main.py` construct experiment objects lazily (one per run, inside the dispatch branch) or eagerly (both up front, as today)? Arguments for lazy: (a) a broken import or constructor in the deprecated `IsotopicExchangeCalibration` cannot break adsorption runs; (b) resource acquisition in `__enter__` (if a future context-manager version is adopted) does not fire for the unused experiment; (c) cleaner pairing with 8.8.1 / 8.8.2. Arguments for eager: (a) current shape; (b) catches constructor errors at program start rather than at dispatch; (c) minor — matches how the deprecated experiment is wired alongside adsorption during the transition period. Recommendation: lazy, given (a)(b)(c) above and the deprecation status of `IsotopicExchangeCalibration`. Human decides before implementation. If lazy, the wiring in 8.8.2 is already written that way; this task becomes essentially a confirmation. If eager, 8.8.2 needs a small edit to preserve today's shape. | `main.py` | [ ] |
| 8.8.6 | **[MN6, human flag]** The two experiment object constructions take identical keyword arguments. Today this is fine — five keyword lines each, no duplication cost beyond readability. If the `main.py` rewrite adds more dependencies (e.g., a `runner` or `parameters` object), the duplication grows. Options today: (a) leave as-is; (b) factor into a local `deps = dict(session=..., gas_controller=..., ...)` and use `**deps` at both call sites; (c) introduce an `ExperimentDependencies` dataclass. Recommendation: (a) — given the upcoming `main.py` rewrite, minor cleanup here is probably wasted work. Human flags for confirmation; the default is to skip. | `main.py` | [ ] |

### Downstream consequences of Phase 8.7

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.8.7 | **[MN7]** Update `main.py` after 8.7.5 lands. Replace the four `ads_exp.chiller_variac_state(chiller_cmd=..., variac_cmd=..., variac_vsl_cmd=...)` calls with `temp_controller.set_heating_elements(chiller=..., manifold_variac=..., vessel_variac=...)`. This is a pure mechanical substitution — 8.7.5 moves the method from the experiment class to the temperature controller, and `main.py` needs to call the new location. Depends on 8.7.5 having landed. If 8.7.5 used a different method name, match it. | `main.py` | [ ] |

### Small cleanups

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.8.8 | **[MN8]** Audit imports in `main.py` for unused names after Phase 8.8 completes. Run `ruff check --select F401 main.py` or equivalent. Remove any unused imports. Pay particular attention to `IsotopicExchangeCalibration` — if 8.8.5 lands on "lazy construction," the import can move inside the `if args.isotopic:` branch. | `main.py` | [ ] |
| 8.8.9 | **[MN9]** Rename two fields on `AdsorptionExperiment` to use the short-form convention that matches `temp` and `ftir`: (a) `mass_spec` → `ms`; (b) `gas_controller` → `gas`. Short form is preferred because these are instance variables, not public API. Apply the renames to the dataclass field declarations, all internal `self.*` references, test fixtures (`mock_gas_controller` → `mock_gas`, `mock_mass_spec` → `mock_ms`), and `main.py` construction calls. Check `isotopic_exchange.py` for the same pattern but **do not apply** the rename there — per the Phase 8.7 deprecation banner, `isotopic_exchange.py` is excluded from this phase. | `src/experiments/adsorption.py`, `tests/test_experiments/test_adsorption.py`, `main.py` | [ ] |

### Future-work flag

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 8.8.10 | **[MN5, flag only — not a task for this phase]** `main.py`'s experiment-run functions contain hardcoded toy protocol parameters (`target_temp=25`, `repeat=[0]`, `delay=[0]`, etc.). These are placeholders because `main.py` is a test/demo entry point; real experimental parameters come from somewhere else (YAML, CSV, CLI arguments). The next major work item after Phase 8 completes is to replace `main.py` with a proper configured experiment runner that reads protocol parameters from an external source. This task does not belong in the cleanup plan — it is a new development effort. Noted here so the placeholder values in `run_adsorption_experiment` are not "cleaned up" in a way that would waste effort. Leave them untouched. | — | N/A |

**Validation:**
- `pytest tests/ -v` passes after each task.
- `python main.py --mock --adsorption` runs clean: (a) happy path completes; (b) `finalize(success=True)` runs and logs the share-drive copies; (c) `devices.disconnect()` fires once at exit.
- Abort test: `python main.py --mock --adsorption`, send `Ctrl+C` partway through, confirm `finalize(success=False)` runs and the README ends with `exp_success: False`.
- CLI test: `python main.py --mock` (no experiment flag) produces an argparse error, not a silent exit.
- Import test: if 8.8.5 lands on "lazy construction," break `src/experiments/isotopic_exchange.py` with a syntax error and confirm `main.py --mock --adsorption` still runs. Revert the intentional break.

---

## Standing checklist for every package review

Each review pass should explicitly check against:

- Zero uses of `cast()`; if present, flag and replace with proper typing.
- Failures raise runtime errors and exit gracefully. No silent swallowing, no sentinel returns.
- Function names describe behavior, not implementation (e.g., `opus_vertex80` → `acquire_ir_spectrum` or similar).
- Threading primitives (`threading.Event`, thread lifecycle) are consistent across sibling modules.
- Module-level globals are justified or removed.
- No `sys.path` manipulation.
- No `print()` calls — use the logger.

---

## Execution notes for Claude Code

- **One task per commit. No squashing.** After committing, update the task's Status column from `[ ]` to `[x]` in this document and include that edit in the same commit.
- **Before starting any task, verify its predicates.** Tasks often reference other tasks as dependencies ("Depends on 8.5.7 having landed" or "Schedule this task to run after 8.4.12 and 8.5.13 complete"). Grep the referenced task numbers, confirm their Status is `[x]`. If any predicate is still `[ ]`, STOP and report to the human — do not execute out of order.
- After each phase (not each task), run `pytest tests/ -v` and report pass/fail.
- Phase 8.1 is a mechanical move-and-reimport; it must be complete and green before any other Phase 8 work starts.
- For any task tagged with a decision point (marked with "human decides," "human picks," "human flag," or "human confirms"), do not pick a direction unilaterally — report findings and wait for the human.
- **Frozen-behavior gate.** Tasks that modify behavior-frozen code (valve sequencing, gas delivery, pressure checks, timing-sensitive protocol methods) are marked with `[FROZEN]` in their task description. When executing a `[FROZEN]` task: stop before making changes, summarize what will change and why, and wait for explicit human go-ahead. Do not proceed on the assumption that the task author (the human, earlier) already meant to authorize it — they did not. Each `[FROZEN]` execution is its own gate.
- If any task reveals an unintended behavior change — timing shift, valve-order change, different pressure threshold, different physics result in a task that was *not* marked `[FROZEN]` — STOP immediately and report. Do not "fix" it silently.
