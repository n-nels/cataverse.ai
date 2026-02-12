# IR Spectroscopy Node

Refactored Python package for the OPUS ZMQ server and analysis workflows.
The production server now runs from this repository using the scripts in
`scripts/`.

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
src/        # Application code (analysis, instrument, utilities)
scripts/    # Entry points for server and utilities
config/     # YAML configuration
tests/      # Smoke tests
arxiv/      # Archived legacy scripts (read-only)
```

## Configuration

- YAML configuration lives in `config/`.
- Analysis settings are loaded via `src.core.config` and referenced by key
  (for example, `analysis.voigt_fit`).

## Operations Notes

- The OPUS server communicates over the named pipe `\\.\pipe\OPUS`.
- Data paths are configured via YAML and documented in
  `.opencode/environment.md`.
- The refactor preserves legacy output filenames and schemas.
