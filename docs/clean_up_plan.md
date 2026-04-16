# Cleanup Plan — Post-Refactor Polish

This plan addresses small issues found during post-refactor review. The layered architecture (`config_loader` → `hardware` → `control` / `datalog` → `experiments` → `main`) is correct and hardware-validated. These tasks are polish: stale language, dead code, small bugs, a layering tightening, and one targeted dependency narrowing.

**Scope:** structural, documentation, and a focused layering fix. No changes to valve sequencing, gas delivery pressure/dither logic, pressure checks, or timing in `control/gas_delivery.py`, `control/valves.py`, or the experiment protocol methods.

**Approach:** one task per commit. Human reviews `git diff` before each commit. Tests pass after each phase.

---

## Phase 1 — Remove "v2" and "will port" language

The refactor is complete. Remove transitional vocabulary that implies work-in-progress.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 1.1 | Rewrite `AdsorptionExperiment` class docstring. Replace "V2 adsorption experiment orchestrator. This class will port legacy adsorption protocol methods to the new architecture..." with a description of what the class *is*, not what it *will become*. | `src/experiments/adsorption.py` | [x] |
| 1.2 | Rewrite `IsotopicExchangeCalibration` class docstring. Same fix as 1.1. | `src/experiments/isotopic_exchange.py` | [x] |
| 1.3 | Update `main.py` module docstring: remove "v2 architecture" language. The file is the entry point, full stop. Keep the mock/real hardware explanation. | `main.py` | [x] |
| 1.4 | Update `argparse` description in `main.py` from `"CataVerse v2 Architecture"` to `"CataVerse instrument control"`. | `main.py` | [x] |
| 1.5 | Grep the repo for remaining occurrences of "v2", "V2", "will port", "legacy" (outside of `.opencode/memory.md` and `docs/refactor_plan*.md`, which are historical). Report findings before editing so the human can decide per-occurrence. | all `src/`, all `docs/`, all `tests/` | [x] |

**Validation:** `pytest` still passes. No functional changes.

---

## Phase 2 — Small code cleanups

Targeted fixes for dead code, late imports, and a misplaced helper.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 2.1 | Remove `_path` staticmethod from `AdsorptionExperiment`. It wraps `pathlib.Path` which is already imported at the top of the file. Replace each `self._path(x)` call with `Path(x)`. | `src/experiments/adsorption.py` | [x] |
| 2.2 | Check `IsotopicExchangeCalibration` for an equivalent `_path` helper. If present, apply the same fix. | `src/experiments/isotopic_exchange.py` | [x] |
| 2.3 | Move all local/deferred imports to module top. Specifically: the `from src.datalog.temperature_logger import TemperatureLogger` inside `AdsorptionExperiment.start_temperature_log`. Grep both experiment modules for other `from ... import ...` statements inside function bodies and hoist them. | `src/experiments/adsorption.py`, `src/experiments/isotopic_exchange.py` | [x] |
| 2.4 | Move imports in `src/datalog/__init__.py` to the top of the file, above function definitions. Verify no circular import is introduced — if one exists, document it as the reason for the current ordering and leave it alone. | `src/datalog/__init__.py` | [x] |
| 2.5 | Delete `src/experiments/automation/`. The `__init__.py` advertises `ActiveLearningEngine`, `DataProcessor`, `run` in `__all__` but none of these exist anywhere in the package. | `src/experiments/automation/` | [x] |

**Validation:** `pytest tests/ -v` passes. No new warnings. Smoke-import `src.experiments.adsorption` and `src.experiments.isotopic_exchange`.

---

## Phase 3 — Make the control-layer boundary consistent

**Problem.** Experiments currently reach past the control layer to read sensors, and they do it inconsistently:

- `adsorption.py` reads pressure and temperature via `self.devices.pressure.read()` / `self.devices.temperature.read_temperature()`.
- `isotopic_exchange.py` reads the same values via `self.gas_controller.pressure.read()` / `self.gas_controller.temperature.read_temperature()`.

On top of that, `GasDelivery.__init__` injects `temperature: WatlowTemperature` that `GasDelivery` itself never uses — it exists only so `isotopic_exchange.py` can reach through it. That is dead weight in the signature and the root cause of the inconsistency.

**Goal.** Every experiment sensor read goes through a controller method. The `WatlowTemperature` adapter lives on `TemperatureController`, not on `GasDelivery`. `GasDelivery` keeps its existing pressure adapter because it legitimately uses pressure for its own feedback loops.

This is a small, well-bounded change but it is the single biggest layering-quality improvement in this plan. Do it before Phase 7 (the `DeviceManager` narrowing) — the result of Phase 3 is that experiments no longer need `devices.pressure` or `devices.temperature` at all, which simplifies Phase 7 dramatically.

### Phase 3a — Verify the assumption

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 3a.1 | Grep `src/control/gas_delivery.py` for every use of `self.temperature`. Confirm there are zero call sites. If any are found, STOP and report — the rest of this phase depends on this being true. | `src/control/gas_delivery.py` | [ ] |
| 3a.2 | Grep both experiment files for all sensor-read call sites: `self.devices.pressure.*`, `self.devices.temperature.*`, `self.gas_controller.pressure.*`, `self.gas_controller.temperature.*`. Record the exhaustive list. | `src/experiments/adsorption.py`, `src/experiments/isotopic_exchange.py` | [ ] |

### Phase 3b — Add controller read methods

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 3b.1 | Add `GasDelivery.read_pressure(self) -> tuple` method that returns `self.pressure.read()`. Thin pass-through. Docstring explains it exists so callers don't reach through the controller. | `src/control/gas_delivery.py` | [x] |
| 3b.2 | Add `TemperatureController.read_temperature(self) -> float` method that returns `self.temperature.read_temperature()`. Thin pass-through. Same docstring pattern. | `src/control/temperature_control.py` | [x] |

### Phase 3c — Route experiments through the new methods

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 3c.1 | In `adsorption.py`, replace every `cast(Any, self.devices.pressure).read()` with `self.gas_controller.read_pressure()`. Remove `cast` and `Any` imports if no longer needed. | `src/experiments/adsorption.py` | [x] |
| 3c.2 | In `adsorption.py`, replace every `cast(Any, self.devices.temperature).read_temperature()` with `self.temp.read_temperature()`. | `src/experiments/adsorption.py` | [x] |
| 3c.3 | In `isotopic_exchange.py`, replace every `self.gas_controller.pressure.read()` with `self.gas_controller.read_pressure()`. | `src/experiments/isotopic_exchange.py` | [x] |
| 3c.4 | In `isotopic_exchange.py`, replace every `self.gas_controller.temperature.read_temperature()` with `self.temp.read_temperature()`. | `src/experiments/isotopic_exchange.py` | [x] |
| 3c.5 | Confirm both experiment files no longer reference `self.devices.pressure`, `self.devices.temperature`, `self.gas_controller.pressure`, or `self.gas_controller.temperature` anywhere. Grep to verify. | `src/experiments/adsorption.py`, `src/experiments/isotopic_exchange.py` | [x] |

### Phase 3d — Drop the unused injection

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 3d.1 | Remove `temperature: WatlowTemperature` from `GasDelivery.__init__`. Remove `self.temperature = temperature`. Remove the `WatlowTemperature` import if no longer used in the file. | `src/control/gas_delivery.py` | [x] |
| 3d.2 | Update `main.py`: drop `temperature=devices.temperature` from the `GasDelivery(...)` constructor call. | `main.py` | [x] |
| 3d.3 | Update `tests/test_control/test_gas_delivery.py`: remove `temperature=MagicMock()` from `GasDelivery(...)` construction. | `tests/test_control/test_gas_delivery.py` | [x] |
| 3d.4 | Grep tests broadly for any other `GasDelivery(` construction sites that need updating. | `tests/` | [x] |

**Validation:**
- `pytest tests/ -v` passes.
- `python main.py --mock --adsorption` and `python main.py --mock --isotopic` run clean.
- Grep confirms: (a) `GasDelivery` has no `temperature` attribute, (b) no experiment file references `self.devices.pressure`, `self.devices.temperature`, `gas_controller.pressure`, or `gas_controller.temperature`.

**Rollback plan:** self-contained. If anything breaks, revert 3b–3d and reconsider.

---

## Phase 4 — `main.py` logging hygiene

`main.py` currently uses `print()` and never calls `configure_logging()`. Every `logger.info(...)` call elsewhere in the codebase goes to the default root logger handler, which may or may not produce visible output depending on how Python is invoked.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 4.1 | Add `from src.datalog import configure_logging, get_logger` and `logger = get_logger(__name__)` at the top of `main.py`. Call `configure_logging()` as the first line of `main()`. | `main.py` | [x] |
| 4.2 | Replace the three `print(...)` calls in `main()` and inside `run_adsorption_experiment()` with `logger.info(...)`. | `main.py` | [x] |
| 4.3 | Grep `main.py` for any remaining `print(` calls and convert them to `logger.info`. Leave `argparse` help output (handled by argparse itself) untouched. | `main.py` | [x] |

**Validation:** Run `python main.py --mock --adsorption` and confirm:
- "Running in MOCK mode" appears in stdout with a timestamp and log level prefix.
- Downstream `logger.info` calls from `control/`, `datalog/`, `experiments/` now appear with the same formatting.

Note: `main.py` is a test/demo entry point. The human plans to replace it with a proper experiment-runner later. Keep changes minimal — just get the logging plumbing right.

---

## Phase 5 — Reuse `SystemVolumes.total` in `main.py`

Right now `main.py` recomputes the total volume inline when wiring `GasDelivery`, even though `SystemVolumes.total` is a computed property that does the same thing. Build the `SystemVolumes` first, then pass `volumes.total` to `GasDelivery`.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 5.1 | In `main.py`, construct `SystemVolumes` **before** constructing `GasDelivery`. Pass `volumes.total` as `total_volume_l` to `GasDelivery`. Pass the same `volumes` to `ExperimentSession` (this is already the case — just reorder). | `main.py` | [x] |
| 5.2 | Verify that `SystemVolumes.total` formula matches the inline computation being replaced: `manifold_m1m2m3 + cell + valve + tube_50ml`. If it does not, STOP and ask the human — this would indicate a physics mismatch, not a cleanup. | `src/physics.py`, `main.py` | [x] |

**Validation:** `python main.py --mock --adsorption` runs end-to-end with no changes in behavior. The numeric value of `total_volume_l` passed to `GasDelivery` is identical before and after.

---

## Phase 6 — Investigate `start_temperature_log` return bug

**This is an investigation task, not a blind fix.** The current code looks wrong, but there may be a downstream caller that uses the returned `stop_temp_log` event in a way that compensates.

Current code in `AdsorptionExperiment.start_temperature_log`:

```python
def start_temperature_log(self) -> tuple[threading.Thread, threading.Event]:
    stop_temp_log = threading.Event()
    ...
    temp_logger = TemperatureLogger(temperature=..., path=..., read_interval_s=5)
    # stop_temp_log is never passed to TemperatureLogger
    temp_logger.start()
    return temp_logger._thread, stop_temp_log
```

The concern: `stop_temp_log` is created locally, never wired to the logger, and returned. If a caller does `stop_temp_log.set()`, nothing listens to it. Also, `temp_logger._thread` reaches through the class boundary.

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 6.1 | Grep the full repo (including tests) for callers of `start_temperature_log`. Record each caller's use of the returned `(thread, stop_event)` tuple. Report findings to the human before changing anything. | all | [ ] |
| 6.2 | Inspect `TemperatureLogger`'s own start/stop interface. Confirm whether it has its own internal stop mechanism (analogous to `PressureLogger.stop()`). | `src/datalog/temperature_logger.py` | [ ] |
| 6.3 | Based on 6.1 and 6.2, the human will decide the fix. Likely outcomes: (a) return the `TemperatureLogger` instance and let callers call `.stop()` on it, mirroring the `PressureLogger` pattern; (b) actually wire `stop_temp_log` into `TemperatureLogger`'s constructor and use it; (c) current behavior is somehow fine and only the return type annotation is wrong. DO NOT pick an option unilaterally. | — | [ ] |
| 6.4 | Implement the human's chosen fix. Update all callers found in 6.1. Update the return type annotation to match. | `src/experiments/adsorption.py`, `src/experiments/isotopic_exchange.py` (if applicable), callers | [ ] |

**Validation:** Every caller of `start_temperature_log` can successfully stop the logger and the worker thread exits. Add a test under `tests/test_experiments/` if one does not already exist.

---

## Phase 7 — Narrow `DeviceManager` dependency in experiment classes

After Phase 3 completes, experiments no longer reach into `self.devices.pressure` or `self.devices.temperature`. What remains in `self.devices.*` should be narrow: mass-spec writes and Extrel register config. Phase 7 makes that narrowing explicit in the type system.

### Phase 7a — Verify Phase 3 did what we expect

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 7a.1 | Grep both experiment classes for every remaining `self.devices.*` reference. Expected result after Phase 3: only `self.devices.mass_spec.*` and `self.devices.config.extrel_ms.registers.*`. If anything else appears (`pressure`, `temperature`, `analog_io`, `spectrometer`, `power`), STOP and report — Phase 3 missed a call site and must be revisited before Phase 7 proceeds. | `src/experiments/adsorption.py`, `src/experiments/isotopic_exchange.py` | [ ] |

### Phase 7b — Replace `DeviceManager` with narrow fields

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 7b.1 | Change `AdsorptionExperiment` dataclass fields: replace `devices: DeviceManager` with `mass_spec: ExtrelMassSpec` and `extrel_registers: ExtrelRegisterConfig`. Import types from `src.hardware.mass_spec` and `src.config_loader`. Update `self.devices.mass_spec.foo(...)` → `self.mass_spec.foo(...)` and `self.devices.config.extrel_ms.registers.X` → `self.extrel_registers.X` throughout. | `src/experiments/adsorption.py` | [ ] |
| 7b.2 | Apply the same change to `IsotopicExchangeCalibration`. | `src/experiments/isotopic_exchange.py` | [ ] |
| 7b.3 | Update `main.py` to pass `mass_spec=devices.mass_spec` and `extrel_registers=config.hardware.extrel_ms.registers` to both experiment constructors. Remove `devices=devices` from those calls. | `main.py` | [ ] |
| 7b.4 | Update `tests/test_experiments/test_adsorption.py`. The `mock_devices` fixture currently sets `devices.config.extrel_ms.registers.sequence_start_address = 1` etc. — replace with separate `mock_mass_spec` and `mock_extrel_registers` fixtures. Update the `adsorption_experiment` fixture to use them. | `tests/test_experiments/test_adsorption.py` | [ ] |
| 7b.5 | Update `tests/test_experiments/test_session.py` if it touches the experiment constructor signature. | `tests/test_experiments/test_session.py` | [ ] |
| 7b.6 | Update `tests/test_integration.py`. Its `TestMainIntegration` only tests that `main.py` imports, so may not need changes, but verify. Other integration tests that construct experiments must be updated. | `tests/test_integration.py` | [ ] |
| 7b.7 | Run full test suite: `pytest tests/ -v`. All pre-existing passing tests must still pass. | — | [ ] |

**Validation:** Full test suite green. Smoke-run `python main.py --mock --adsorption` and `python main.py --mock --isotopic` — both must complete without exceptions.

**Rollback plan:** this phase is self-contained. If anything breaks, revert the phase's commits and the rest of the cleanup remains intact.

---

## Phase 8 — Reserved for future module-by-module improvements

The human plans a separate pass to walk each module and apply targeted improvements (the `[fix]` comments sprinkled in code, misc. refinements). That is a different kind of work than this structural cleanup and belongs in its own plan document.

Potential Phase 8 follow-up: move logger construction/start-stop orchestration behind control-layer APIs so experiment modules do not pass hardware adapters (`pressure`, `temperature`) directly to logger classes.

Do not start Phase 8 work as part of this plan.

---

## Out of scope

The following were considered and explicitly rejected for this cleanup:

- **Rewriting `GasDelivery.deliver_gas_to_manifold`.** It's a 400+ line behavior-frozen port. Hardware-validated. Do not touch.
- **Changing `GasDelivery`'s constructor to take `SystemVolumes` + `SystemConstants` instead of individual floats.** Worth considering eventually, but would cascade into tests and was deferred.
- **Pulling `paths` and file I/O concerns out of `GasDelivery` and `TemperatureController`.** Real layering concern, but untangling it risks behavior changes in timing-sensitive code. Deferred to Phase 8 (module pass) if the human wants it addressed at all.
- **Removing module-level globals `dir_tempLog` / `path_tempLog` in `TemperatureController`.** Known-bad, preserved in original refactor to avoid behavior drift. Deferred to Phase 8.
- **Cleaning up stale `docs/refactor_plan*.md` files and `.opencode/agent/*.md` plan references.** The human is doing this separately in an `AGENTS.md` / agent-support-file refresh.

---

## Execution notes for Claude Code

- One task per commit. No squashing.
- After each phase, run `pytest tests/ -v` and report pass/fail.
- For Phase 3a, Phase 6, and Phase 7a, do not proceed past the investigation/grep step without the human's explicit go-ahead.
- If any task reveals a behavior change — timing shift, valve-order change, different pressure threshold — STOP immediately and report to the human. Do not "fix" it silently.
- `docs/refactor_plan*.md` files in `docs/` are **historical reference only**. Do not edit them. All active work is tracked in this file.
