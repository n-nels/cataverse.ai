# AGENTS.md — `src/core/`

## Purpose

This package contains typed configuration loading and pure physics calculations. It is the base of the dependency stack — everything else depends on it.

## Scope-creep guard

`core/` depends on nothing internal. New modules belong in `hardware/`, `control/`, `datalog/`, or `experiments/` unless they are genuinely foundational and have no dependencies on any other internal package.

## Contents

- **`config_loader.py`** — Loads YAML configuration files and environment variables into typed dataclasses (`AppConfig`, `HardwareConfig`, `SampleConfig`, `PathsConfig`, etc.).
- **`physics.py`** — Pure functions for ideal-gas calculations, volume definitions (`SystemVolumes`), and adsorption metrics. No side effects, no I/O.
