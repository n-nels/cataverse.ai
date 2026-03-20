# AGENTS.md

## Project Overview

This is **CataVerse** — a Python system that controls laboratory instruments for catalysis experiments. It manages gas flow, pressure, temperature, and spectral acquisition for adsorption and isotopic exchange studies on supported metal catalysts.

The system controls real physical hardware. Changes to this code can open valves, pressurize vessels, and heat samples. **Read safety constraints before modifying any device or operations code.**

## On Start

Before writing any code, read the following in order:

1. `.opencode/memory.md` — Recent session context and outstanding items.
2. `docs/refactor_plan-X.md` — The active work plan. Identify which chunk and task you are on.
3. The `AGENTS.md` in whatever module directory you will be working in.

## On Close

Before ending a session, update the following as needed:

1. `.opencode/memory.md` — Log what was done, decisions made, and anything unfinished.
2. `docs/refactor_plan-X.md` — Mark completed tasks, note the current chunk.
3. Any `AGENTS.md` files in modules that were modified — keep them accurate.

## Current State

**Phases 0–6 (structural refactor) are complete.** See `docs/refactor_plan.md` for historical reference.

**The active work is an architectural restructure.** New packages (`hardware/`, `control/`, `datalog/`, `config_loader.py`, `physics.py`) are being built alongside the legacy code. The legacy packages (`core/`, `devices/`, `operations/`, `utils/`) are not modified or deleted until the new code is validated on physical hardware.

See `docs/restructure_execution_plan.md` for the chunk-by-chunk plan. See `docs/architecture_rethink.md` for the design rationale.

## Package Structure

See `docs/directory_structure.md` for the full file listing.

The legacy dependency flow is: **experiments → operations → devices → core**, with `utils` used by operations and experiments. The new architecture replaces this with: **experiments → control + datalog → hardware → config/physics**. Each new package has its own `AGENTS.md` with module-specific context.

## Critical: Preserve Behavior

This system was developed by a scientist iterating directly with physical hardware. The specific order of operations, delay values, voltage thresholds, and safety checks exist because they were validated against the real system. They are not arbitrary.

**Valve sequences and gas delivery logic are behavior-frozen.** When porting code from legacy packages to new packages, copy the control flow verbatim. You may change dependency wiring (e.g., `self.serial.read_pressure()` → `self.pressure.read()`), replace `print()` with `logger.info()`, and add type hints — but the sequence of calls, the values passed, the sleep durations, and the branching logic must remain identical.

When working on any control or hardware code, verify:

- The same functions are called in the same order with the same arguments.
- No safety checks, pressure readings, or state verifications are removed or reordered.
- Timing (`time.sleep()` calls, delays, hold times) is preserved exactly.
- Error handling behavior (what happens on failure) does not change.

### Hardware Safety Rules

These override all other instructions:

1. **Never open a gas valve without verifying the downstream path.** Gas must have somewhere to go (cell, pump, or vent). Dead-heading a pressurized line risks equipment damage.
2. **Pressure limits are hard limits.** The manifold and IR cell have maximum operating pressures. Any code that supplies gas must check pressure before and during delivery.
3. **TurboPump requires roughing first.** The turbomolecular pump cannot start or be exposed to atmosphere. Always rough-pump before opening to turbo.
4. **Actuator default state is closed (1.0V).** Open is 5.0V. If unsure, close. A closed valve is safe; an open valve may not be.
5. **Temperature ramp rates matter.** Rapid heating can damage samples, IR windows, or the cell itself. Respect ramp rate parameters.
6. **Never remove or weaken a safety check** without explicit user approval and documentation of why.

## Agent Configuration

This project uses OpenCode. See `.opencode/` for agent roles, workflow protocols, conventions, and session memory. See `pyproject.toml` for dependencies and build configuration.