# devices/ — Hardware Communication Layer

For project-wide safety and behavioral constraints, read the root `AGENTS.md` first.

---

## Purpose

This module contains low-level device drivers and communication adapters for the lab hardware:

- Serial instruments (MKS pressure gauge, Watlow temperature controller, Extrel mass spectrometer)
- NI USB-6009 analog output devices used for actuator/valve control
- Network messaging (ZMQ/OPUS communication)

Current structure is flattened at `src/devices/` (`serial_devices.py`, `ni_usb6009.py`, `network_messaging.py`) with per-instrument serial helpers (`mks_pressure.py`, `watlow_controller.py`, `extrel_mass_spec.py`) and Kasa plug control (`kasa_plugs.py`).

`devices/` provides hardware primitives to the `operations/` layer. It should not contain experiment sequencing logic.

## Dependencies

**Depends on:** `core` (configuration/constants), third-party device libraries (`pyserial`, `pymodbus`, `nidaqmx`, `pyzmq`)

**Depended on by:** `operations` (primary), top-level scripts (e.g., `main.py`)

## Constraints

- Preserve existing public interfaces and method names during refactor.
- Do not change device command formats, register addresses, baud/port behavior, or voltage write ranges unless explicitly planned.
- Keep hardware side effects identical: same calls, order, and arguments.
- Refactors here are structural only (organization, typing, logging, docs).
