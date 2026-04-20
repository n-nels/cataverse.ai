# CataVerse

CataVerse is a Python-based laboratory automation platform for catalysis experiments.
It coordinates gas delivery, pressure monitoring, temperature control, and spectral acquisition for adsorption and isotopic exchange workflows.

## Overview

The project is designed for instrument-driven experimental protocols where sequencing and safety checks are as important as data capture.

Core capabilities include:

- experiment orchestration for adsorption and isotopic exchange runs
- hardware adapters for pressure gauges, temperature controllers, mass spectrometer, analog I/O, power control, and OPUS communication
- control-layer logic for evacuation, gas admission, valve sequencing, and ramp/hold temperature routines
- structured logging for pressure, temperature, mass-spec streams, and experiment metadata

## Architecture

Current dependency flow:

`experiments -> control + datalog -> hardware -> config/physics`

Main entrypoint:

- `main.py`

Primary packages:

- `src/experiments/`
- `src/control/`
- `src/datalog/`
- `src/hardware/`
- `src/config_loader.py`
- `src/physics.py`

## Quick Start

### 1) Prerequisites

- Python 3.12+
- Access to required device interfaces for hardware runs (serial, NI USB-6009, networked OPUS, smart-plug control)

### 2) Configure the system

Update configuration files to match your local setup:

- `config/devices.yaml`
- `config/system.yaml`
- `config/sample.yaml`
- `config/paths.yaml`

### 3) Run in mock mode (no hardware required)

```bash
python main.py --mock
python main.py --mock --adsorption
python main.py --mock --isotopic
```

### 4) Run with hardware

```bash
python main.py
python main.py --adsorption
python main.py --isotopic
```

## Testing

```bash
python -m pytest -q
```

## Safety Notice

This software can control real laboratory hardware. Incorrect configuration or sequencing can create unsafe conditions.

- Verify instrument connectivity and safe valve states before hardware runs.
- Review pressure and pump safety constraints before changing control logic.
- Use mock mode for development and protocol rehearsal whenever possible.

## Project Structure

- `config/` - YAML configuration for devices, paths, system constants, and sample metadata
- `src/` - application source code
- `tests/` - automated tests
- `docs/` - migration notes, architecture history, and project documentation

## Status

The refactor and architecture cutover are complete, and `main.py` is the active runtime entrypoint.
