# AGENTS.md

## Project Overview

This is **CataVerse** — a Python system that controls laboratory instruments for catalysis experiments. It manages gas flow, pressure, temperature, and spectral acquisition for adsorption and isotopic exchange studies on supported metal catalysts.

The system controls real physical hardware. Changes to this code can open valves, pressurize vessels, and heat samples. **Read safety constraints before modifying any device or operations code.**

## On Start

Before writing any code, read the following in order:

1. `.opencode/memory.md` — Recent session context and outstanding items.
2. `docs/refactor_plan.md` — Current refactor phase and task list.
3. The `AGENTS.md` in whatever module directory you will be working in.

## On Close

Before ending a session, update the following as needed:

1. `.opencode/memory.md` — Log what was done, decisions made, and anything unfinished.
2. `docs/refactor_plan.md` — Mark completed tasks, update the current phase if applicable.
3. Any `AGENTS.md` files in modules that were modified — keep them accurate.

## Package Structure

The source lives in `src/` with four layers. See `docs/directory_structure.md` for the full file listing.

The dependency flow is strictly downward: **experiments → operations → devices → core**. No layer should import from the layer above it.

- **`core/`** — Configuration, physical constants, experiment parameters.
- **`devices/`** — Hardware communication drivers (serial, NI DAQ, ZMQ network).
- **`operations/`** — High-level instrument sequences (valve control, gas delivery, spectral acquisition).
- **`experiments/`** — Experiment protocols and automation (adsorption, isotopic exchange).
- **`utils/`** — Data logging, file management.

## Current State

This codebase is under active refactoring. See `docs/refactor_plan.md` for the current phase and task list.

## Module Context

Each module directory contains an `AGENTS.md` file with just-in-time context for that area: what the module does, what hardware or protocols are involved, dependencies in and out, and any invariants or constraints specific to that module.

Always read the local `AGENTS.md` before modifying code in a directory.

## Critical: Preserve Behavior

This refactor improves structure, readability, and maintainability. **It does not change what the code does.**

Much of this code — especially valve sequencing, timing, pressure checks, and gas delivery logic — was developed by a human iterating directly with physical hardware. The specific order of operations, delay values, voltage thresholds, and safety checks exist because they were validated against the real system. They are not arbitrary and must not be "optimized," reordered, or simplified.

**Actuator and valve logic is the highest-risk area.** Treat all code in `operations/actuator_control.py`, `operations/instrument_operations.py`, and `experiments/protocols/` as behavior-frozen. You may rename variables, extract methods, improve structure, and add type hints — but the sequence of calls, the values passed, and the control flow must remain identical.

When refactoring any module, verify:

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