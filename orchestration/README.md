# cataverse.ai Orchestration

`orchestration/` is the Python orchestration layer for the cataverse.ai platform.
It coordinates experiment protocols, control logic, device adapters, and data logging
for experimental workflows.

## What This Package Does

- Runs experiment protocols (`adsorption`, `isotopic_exchange`)
- Coordinates control logic for valves, gas delivery, temperature, and acquisition
- Interfaces with instrument adapters (pressure, temperature, mass spec, OPUS, analog I/O, power)
- Writes structured logs and experiment metadata

Dependency flow:

`experiments -> control + datalog -> hardware -> config_loader/physics`

## Safety-Critical Software

This code can control real hardware (valves, pumps, heaters, gas lines).
Incorrect sequencing or configuration can create unsafe conditions.

- Validate configuration before running with hardware
- Confirm safe valve states and pressure limits
- Use mock mode when developing or rehearsing workflows

For engineering constraints and behavior-preservation rules, see `AGENTS.md`.

## Repository Layout

- `main.py` - runtime entrypoint and wiring
- `config/` - YAML configuration (`devices.yaml`, `system.yaml`, `sample.yaml`, `paths.yaml`)
- `src/config_loader.py` - typed config loading
- `src/physics.py` - system volume and physics utilities
- `src/hardware/` - device adapters
- `src/control/` - actuator and operations controllers
- `src/datalog/` - logging and file I/O utilities
- `src/experiments/` - experiment/session orchestration
- `tests/` - unit and integration tests

## Prerequisites

- Python `>=3.12`
- Device access for hardware mode (serial devices, NI DAQ, OPUS endpoint, networked power devices)

## Setup

### 1) Install dependencies

Using `uv` (recommended in this repo):

```bash
uv sync
```

Or with `pip`:

```bash
pip install -e .
```

### 2) Configure local environment

Review and update:

- `config/devices.yaml`
- `config/system.yaml`
- `config/sample.yaml`
- `config/paths.yaml`

If needed, set `cataverse.ai_CONFIG_DIR` to use an alternate config directory.

## Running

From `orchestration/`:

Mock mode (no hardware):

```bash
python main.py --mock
python main.py --mock --adsorption
python main.py --mock --isotopic
```

Hardware mode:

```bash
python main.py
python main.py --adsorption
python main.py --isotopic
```

## Testing

```bash
pytest tests/ -v
```

## Notes After Unification

- This folder now represents the orchestration runtime within the unified codebase.
- Use this README for orchestration-specific setup and execution.
- The repository-level README describes the broader project context.
