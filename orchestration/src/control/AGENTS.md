# control/ — Instrument Operations and Actuator Sequencing

See root `AGENTS.md` for global safety constraints. See `docs/clean_up_plan.md` for the active work plan.

---

## Purpose

Coordinates hardware-layer calls into operational sequences. Controllers own timing, ordering, and safety checks; adapters own protocol details.

Responsibilities:
- Valve and actuator open/close/write sequencing (`valves.py`)
- Gas delivery to manifold and cell with pressure-based feedback (`gas_delivery.py`)
- Temperature ramp, hold, and cooling sequences (`temperature_control.py`)
- Spectrometer request/retry and acquisition coordination (`spectrometer_control.py`)
- Mass-spec register sequence start/stop (`mass_spec_control.py`)

This is the highest-risk layer in the codebase. Sequencing errors here can open valves against closed pumps, overpressure the manifold, or expose the turbo to atmosphere.

## Dependencies

**Depends on:** `hardware`, `core`, Python `logging`

**Depended on by:** `experiments`, `main.py`

## Module-Specific Notes

- Valve defaults: closed = `1.0 V`, open = `5.0 V`. If unsure, close.
- Pressure and safety limits live in `core.config`. Controllers read them; they do not define their own.
- Unrecoverable failures (connection loss, safety-limit exceeded, thermocouple fault) raise distinctive exceptions from the hardware/control error hierarchy. Controllers do not call `sys.exit` and do not swallow errors into sentinel returns.
- Controllers expose `read_pressure()` and `read_temperature()` pass-through methods so experiments never reach through the controller to the adapter. The adapter itself is not a public attribute.
- Behavior-sensitive sequences (gas delivery timing, ramp/cool/hold branching in `watlow()`, valve ordering in `deliver_gas_to_manifold`) are gated by the `[FROZEN]` marker in the cleanup plan. Changes require explicit go-ahead per the root `AGENTS.md` gate procedure.
- `GasDelivery.deliver_gas_to_manifold` currently contains a 400+ line behavior-frozen port. Do not refactor it without an explicit plan task and hardware revalidation.