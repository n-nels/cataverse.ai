# AGENTS.md

## Project Overview

This is **cataverse.ai** — a Python system that controls laboratory instruments for catalysis experiments. It manages gas flow, pressure, temperature, and spectral acquisition for adsorption and isotopic exchange studies on supported metal catalysts.

The system controls real physical hardware. Changes to this code can open valves, pressurize vessels, and heat samples. **Read safety constraints before modifying any device or operations code.**

## On Start

Before writing any code, read the following in order:

1. `.opencode/memory.md` — Recent session context and outstanding items.
2. The `AGENTS.md` in whatever module directory you will be working in.

## On Close

Before ending a session, update the following as needed:

1. `.opencode/memory.md` — Log what was done, decisions made, and anything unfinished.
2. Any `AGENTS.md` files in modules that were modified — keep them accurate.

## Package Structure

See `docs/directory_structure.md` for the full file listing if needed.

The active dependency flow is: **experiments -> control + datalog -> hardware -> config/physics**. Package-level `AGENTS.md` files document module-specific constraints where present.

## Behavior-Sensitive Code

The control and experiment layers contain sequences of valve operations, pressure checks, timing delays, and temperature ramps that were validated against real hardware. These values are not arbitrary.

Any change to behavior-sensitive code (valve sequencing, gas delivery, pressure checks, timing-sensitive protocol methods) requires explicit human go-ahead before committing. If you encounter an unintended behavior change — different timing, different valve order, different pressure threshold — STOP and report. Do not "fix" it silently.

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
