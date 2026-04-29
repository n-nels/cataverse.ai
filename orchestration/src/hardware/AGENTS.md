# AGENTS.md — `src/hardware/`

## Purpose

Low-level instrument adapters that operate on injected, already-open connections (serial, Modbus, DAQ, ZMQ, HTTP). Exposes device read/write primitives without embedding higher-level experiment sequencing logic.

## Dependencies

**Depends on:** `core` (config dataclasses only)

**Depended on by:** `control`, `datalog`, `experiments` (via adapters injected at construction)

## Error-Handling Policy

Unrecoverable hardware failures raise a distinctive exception from `src/hardware/errors.py`. The hardware layer **never** calls `sys.exit`. The control or experiment layer catches these exceptions and triggers a safe-shutdown sequence.

### Exception Hierarchy

| Exception | When to raise |
|---|---|
| `HardwareError` | Base class — do not raise directly |
| `HardwareConnectionError` | Device not connected, connection lost, or injected client is `None` |
| `HardwareReadError` | Failed to read from a device (Modbus read error, serial timeout, etc.) |
| `HardwareMappingError` | Unknown actuator ID or channel mapping |
| `ThermocoupleFault` | Watlow controller detects thermocouple malfunction |

## Module-Specific Notes

- `analog_io.py` — NI USB-6009 DAQ adapter. Voltage range: 0–5V for both read and write.
- `connections.py` — `DeviceManager` constructs and owns all hardware connections.
- `pressure.py` — MKS pressure gauge. Over-range (non-numeric) readings raise `HardwareReadError`; the control layer catches this and triggers pump-down. `PressureReading` fields are `float | None` (no longer `str`).
- `spectrometer.py` — OPUS ZMQ adapter. The `cast(int, socket.getsockopt(zmq.RCVTIMEO))` is intentional — `pyzmq` returns `int | bytes`.
- `temperature.py` — Watlow Modbus adapter. Thermocouple faults raise `ThermocoupleFault`.
- `power.py` — Kasa cloud smart-plug adapter. Credentials come from `KasaConfig` or env vars.
