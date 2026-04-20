# IR Spectroscopy Node

Instrument node for controlling a Bruker FTIR spectrometer and performing real-time spectral analysis. This repository is one node in the cataverse.ai project.

The node handles the full lifecycle of an IR spectroscopy experiment: instrument control via the OPUS named pipe, interferogram acquisition, subtracted-interferogram processing, Voigt-profile spectral fitting, kinetics fitting (PFO and coupled-ODE secondary PFO models), and trajectory classification.

## Requirements

- Python >= 3.12
- Windows (required for OPUS named pipe integration)
- [uv](https://docs.astral.sh/uv/) package manager
- Bruker OPUS software running with pipe interface enabled (`\\.\pipe\OPUS`)

## Quick Start

```bash
# Install dependencies
uv sync

# Start the OPUS instrument control server (ZMQ)
python scripts\run_server.py

# Start the Norhof LN2 pump control loop
python scripts\run_norhoff.py
```

## Architecture

The node exposes a ZMQ server that accepts commands from the cataverse.ai orchestrator. Incoming messages trigger instrument operations (background/sample measurements) and queue analysis work that runs asynchronously on single-threaded dispatch queues.

```
Orchestrator (ZMQ)
    |
    v
server.py          -- message routing and polling loop
    |
    +-- acquisition.py   -- measurement workflow (acquire, subtract IFGs)
    |       |
    |       +-- client.py        -- low-level OPUS pipe commands
    |       +-- dispatch.py      -- analysis queue management
    |
    +-- analysis pipeline (triggered per subtracted-IFG file)
            |
            +-- spectral_fitting.py  -- Voigt profile fitting
            +-- kinetics_fitting.py  -- PFO / secondary PFO models
            +-- output.py            -- CSV output generation
```

### Data Flow

1. **Acquire**: OPUS collects interferograms; the server subtracts sequential IFG pairs at multiple delta steps.
2. **Fit**: Each subtracted-IFG file is fitted with a multi-peak Voigt profile. Peak parameters are saved to `*_CarbonylPeakFitParams.csv`.
3. **Kinetics**: Cumulative peak areas are computed from the fit history, then kinetics models are fitted. Results are saved to `*_CarbonylPeakArea.csv`.
4. **Classify**: Cluster-sum trajectories are classified as continuous or discontinuous (growth onset detection).

## Project Layout

```
scripts/                    Entry points
  run_server.py               OPUS ZMQ server
  run_norhoff.py               Norhof LN2 pump control
  run_analysis.py              Batch analysis CLI

src/
  core/
    config.py                  YAML configuration loader
  instrument/
    main.py                    Server bootstrap
    server.py                  ZMQ message handling and loop
    acquisition.py             Measurement workflow
    client.py                  OPUS named pipe commands
    dispatch.py                Analysis queue management
    state.py                   Runtime state (paths, queues, counters)
    paths.py                   Path/config assembly
  analysis/
    main.py                    Analysis pipeline orchestration
    spectral_fitting.py        Voigt profile fitting
    kinetics_fitting.py        PFO and secondary PFO models
    output.py                  DataFrame computation and CSV I/O
    io.py                      Data loading and validation
    peak_heights.py            Peak height extraction
    monomer_max.py             Monomer max computation
    integrate_ir_iso_xchg.py   Isotopic exchange utilities
  utils/
    kinetic_fit_writer.py      Standalone kinetics batch processor
    subtract_ifg.py            IFG subtraction utilities
    norhof.py                  LN2 pump serial control
    readme.py                  README-to-CSV converter
    monomer_max_writer.py      Monomer max batch writer
    delete_files.py            File cleanup utilities
    rename_files.py            File renaming utilities
  visualizations/
    plot_spectrum_fit.py       Spectrum fit plots
    plot_monomer_cluster_fit.py  Kinetics fit plots
    plot_area_vs_time.py       Peak area vs time plots
    plot_params.py             Parameter trend plots
    plot_monomer_max.py        Monomer max plots

config/
  analysis.yaml                Voigt fit, peak lists, isotope settings
  paths.yaml                   Data directory paths

sandbox/                     Experimental scripts and notebooks
docs/                        Internal documentation
```

## Configuration

Configuration is YAML-based, loaded through `src.core.config`:

- **`config/paths.yaml`** -- data directories, output paths, OPUS file locations.
- **`config/analysis.yaml`** -- Voigt fit settings, peak lists, baseline parameters, isotope shifts, kinetics model defaults.

Settings are accessed by dotted key (e.g., `config.get_analysis_setting("analysis.voigt_fit")`).

## Key Concepts

### Kinetics Models

Two kinetics models are fitted to cumulative peak area vs. time:

- **PFO** (pseudo-first-order): `q(t) = q_0 + q_e * (1 - exp(-k * t))`. Used for cluster peaks.
- **Secondary PFO** (coupled ODE): Models adsorption with a secondary surface process via `solve_ivp`. Used for monomer peaks. Parameters: `k_a`, `q_e`, `k_s`, `k_p`, `q_inf`, `q_0`.

### Real-Time vs. Batch Mode

- **Real-time** (`run_spectral_fit` with `run_kinetics=True`): Only fits the latest time point, carrying forward prior kinetics results from the saved CSV. O(1) per new data point.
- **Batch** (`run_kinetics_fit` or `kinetic_fit_writer.py`): Fits all time points from scratch. Used for reprocessing existing data.

### Trajectory Classification

Cluster-sum trajectories are classified as `continuous` or `discontinuous` based on flat-region detection and growth onset analysis. Discontinuous trajectories include pre/post breakpoint PFO fits.

## Operations Notes

- The OPUS server communicates over the Windows named pipe `\\.\pipe\OPUS`.
- Data paths are configured via YAML; all output preserves legacy filenames and schemas.
- The ZMQ server runs a single polling loop; analysis is dispatched to per-type queues.
- The Norhof LN2 pump controller runs as a separate process.

## Development

```bash
# Lint
ruff check .

# Format
ruff format .
```

Scripts in `sandbox/` are run directly from VSCode with editable constants at the top of each file.
