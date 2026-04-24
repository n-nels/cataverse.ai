# AGENTS.md

## Project Overview

This is **cataverse.ai** — a Python system that controls laboratory instruments for catalysis experiments. It manages gas flow, pressure, temperature, and spectral acquisition for adsorption and isotopic exchange studies on supported metal catalysts.

The system controls real physical hardware. Changes to this code can open valves, pressurize vessels, and heat samples. **Read safety constraints before modifying any device or operations code.**

## On Start

Before writing any code, read the following in order:

1. `.opencode/memory.md` — Recent session context and outstanding items.
2. `docs/clean_up_plan.md` — The active work plan. Identify which phase and task you are on.
3. The `AGENTS.md` in whatever module directory you will be working in.

## On Close

Before ending a session, update the following as needed:

1. `.opencode/memory.md` — Log what was done, decisions made, and anything unfinished.
2. `docs/clean_up_plan.md` — Mark completed tasks, note the current phase.
3. Any `AGENTS.md` files in modules that were modified — keep them accurate.

## Package Structure

See `docs/directory_structure.md` for the full file listing.

The active dependency flow is: **experiments -> control + datalog -> hardware -> config/physics**. Package-level `AGENTS.md` files document module-specific constraints where present.

## Behavior-Sensitive Code

The control and experiment layers contain sequences of valve operations, pressure checks, timing delays, and temperature ramps that were validated against real hardware. These values are not arbitrary.

Changes to these sequences are permitted in this cleanup pass, but are gated. Tasks in `docs/clean_up_plan.md` that touch behavior-sensitive code are marked `[FROZEN]`. When executing a `[FROZEN]` task:

1. Stop before making changes, summarize what will change and why, and wait for explicit human go-ahead.
2. Validate the change against existing tests and, where the task requires it, plan a real-hardware revalidation.
3. If you encounter an unintended behavior change in a task *not* marked `[FROZEN]` — different timing, different valve order, different pressure threshold — STOP and report. Do not "fix" it silently.

Hardware Safety Rules (below) are never changed regardless of phase.

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
