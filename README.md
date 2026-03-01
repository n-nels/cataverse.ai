# IR Spectroscopy Node

Production-ready Python package for the OPUS ZMQ server and analysis workflows.
This repository hosts the live instrument control and analysis tooling.

## Quick Start (Production)

From the repository root:

```bash
# OPUS instrument control server (ZMQ)
python scripts\run_server.py

# Norhof LN2 pump control loop
python scripts\run_norhoff.py
```

## Project Layout

```
src/        # Application code (analysis, instrument, utilities, visualizations)
scripts/    # Entry points for server and utilities
config/     # YAML configuration
```

## Configuration

- YAML configuration lives in `config/`.
- Analysis settings are loaded via `src.core.config` and referenced by key
  (for example, `analysis.voigt_fit`).

## Operations Notes

- The OPUS server communicates over the named pipe `\\.\pipe\OPUS`.
- Data paths are configured via YAML
- The system preserves legacy output filenames and schemas.
