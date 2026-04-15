# experiments/ — Experiment Protocol Layer

See root `AGENTS.md` for global safety constraints and behavior-preservation rules.

---

## Purpose

This module defines experiment protocols and automation workflows (e.g., adsorption and isotopic exchange), including:

- Experiment/session parameter handling
- Protocol orchestration across control/hardware
- Data/log file setup and experiment metadata writing via datalog/session
- Threaded acquisition/monitoring coordination

Current structure:
- `session.py` — `ExperimentSession`
- `adsorption.py` — `AdsorptionExperiment`
- `isotopic_exchange.py` — `IsotopicExchangeCalibration`
- `automation/` — automation package scaffold

## Dependencies

**Depends on:** `control`, `datalog`, `hardware`, `config_loader`, `physics`

**Depended on by:** top-level scripts (e.g., `main.py`)

## Critical Constraints

- Protocol behavior is frozen: preserve sequence/order of operation calls.
- Preserve pressure/temperature checks, delay values, and hold times exactly.
- Preserve thread lifecycle behavior and synchronization semantics.
- Preserve public class/function interfaces used by existing scripts.

## Refactor Scope

Allowed: structural cleanup, module split/extraction, docstrings, type hints, path/config centralization (per plan), and logging improvements.

Not allowed: changing experiment control flow, timing, or device command ordering.
