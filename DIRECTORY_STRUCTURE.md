# IR Spectroscopy Node - Directory Structure

This document outlines the current directory structure of the project.

Last updated: 2026-02-11 (Phase 7.1 documentation refresh)

## Current Structure

```
ir-spectro-node/
│
├── .opencode/
│   ├── agent/
│   │   ├── architect.md
│   │   ├── coder.md
│   │   ├── debugger.md
│   │   ├── historian.md
│   │   ├── reviewer.md
│   │   └── validator.md
│   ├── .gitignore
│   ├── conventions.md
│   ├── environment.md
│   ├── foundations.md
│   ├── instructions.md
│   └── memory.md
│
├── AGENTS.md
├── DIRECTORY_STRUCTURE.md
├── README.md
├── REFACTORING_PLAN.md
├── opencode.json
├── pyproject.toml
├── uv.lock
│
├── arxiv/
│   ├── (Archived Python scripts...)
│   ├── peak_heights.py
│   └── persona.md.bak
│
├── config/
│   ├── analysis.yaml
│   └── paths.yaml
│
├── docs/
│   └── migration_notes.md
│
├── scripts/
│   ├── __init__.py
│   ├── run_norhoff.py
│   ├── run_peak_fit.py
│   └── run_server.py
│
├── src/
│   ├── __init__.py
│   ├── analysis/
│   │   ├── .agent.md
│   │   ├── .spec.md
│   │   ├── __init__.py
│   │   ├── integrate_ir_iso_xchg.py
│   │   ├── io.py
│   │   ├── kinetics_fitting.py
│   │   ├── main.py
│   │   ├── output.py
│   │   ├── peak_heights.py
│   │   ├── spectral_fitting.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py
│   │
│   ├── instrument/
│   │   ├── .agent.md
│   │   ├── .spec.md
│   │   ├── __init__.py
│   │   ├── client.py            (OPUS pipe adapter: low-level commands)
│   │   ├── paths.py             (Path and config assembly)
│   │   ├── state.py             (Runtime state container: OpusState, OpusPaths, queues)
│   │   ├── dispatch.py          (Analysis queue management and dispatch)
│   │   ├── acquisition.py       (Measurement workflow: acquire, subtract_ifg, background)
│   │   ├── server.py            (ZMQ message handling and polling loop)
│   │   └── main.py              (Entry point and bootstrap)
│   │
│   └── utils/
│       ├── __init__.py
│       ├── delete_files.py
│       ├── norhof.py
│       ├── rename_files.py
│       └── subtract_ifg.py
│
└── tests/
    ├── __init__.py
    └── test_instrument/
        ├── __init__.py
        └── test_server_import.py
```
