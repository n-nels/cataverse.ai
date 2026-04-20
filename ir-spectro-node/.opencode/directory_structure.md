# IR Spectroscopy Node - Directory Structure

This document outlines the current directory structure of the project.

Last updated: 2026-03-01 (repository documentation refresh)

## Current Structure

Note: This listing omits build artifacts (e.g., `__pycache__/`, `.venv/`,
`.pytest_cache/`) and other generated files.

```
ir-spectro-node/
│
├── .env.local
├── .gitconfig
├── .gitignore
├── .opencode/
│   ├── agent/
│   │   ├── architect.md
│   │   ├── coder.md
│   │   ├── debugger.md
│   │   ├── historian.md
│   │   ├── lint.md
│   │   ├── reviewer.md
│   │   ├── strategy.md
│   │   └── validator.md
│   ├── bun.lock
│   ├── conventions.md
│   ├── directory_structure.md
│   ├── environment.md
│   ├── foundations.md
│   ├── instructions.md
│   ├── memory.md
│   └── package.json
│
├── .python-version
├── .vscode/
│   ├── launch.json
│   └── settings.json
├── AGENTS.md
├── README.md
├── config/
│   ├── analysis.yaml
│   └── paths.yaml
├── docs/
│   └── migration_notes.md
├── nul
├── null
├── opencode.json
├── pyproject.toml
├── sandbox/
│   ├── notebooks/
│   │   └── phase1_starter.ipynb
│   ├── signal_processing/
│   │   ├── __pycache__/
│   │   ├── plot_monomer_max_ridgeline.py
│   │   └── scratch_pad.py
│   └── ml_experiments/
├── scripts/
│   ├── __init__.py
│   ├── run_analysis.py
│   ├── run_norhoff.py
│   └── run_server.py
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
│   │   ├── monomer_max.py
│   │   ├── output.py
│   │   ├── peak_heights.py
│   │   └── spectral_fitting.py
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py
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
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── delete_files.py
│   │   ├── kinetic_fit_writer.py
│   │   ├── monomer_max_writer.py
│   │   ├── norhof.py
│   │   ├── readme.py
│   │   ├── rename_files.py
│   │   ├── subtract_ifg.py
│   │   └── subtract_ifg_manual.py
│   └── visualizations/
│       ├── plot_area_vs_time.py
│       ├── plot_monomer_cluster_fit.py
│       ├── plot_monomer_max.py
│       ├── plot_params.py
│       └── plot_spectrum_fit.py
└── uv.lock
```
