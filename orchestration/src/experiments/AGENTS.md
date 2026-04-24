# experiments/ — Experiment Protocol Layer

See root `AGENTS.md` for global safety constraints. See `docs/clean_up_plan.md` for the active work plan.

---

## Purpose

Defines experiment protocols and session metadata management. Orchestrates calls across the control, datalog, and hardware layers to run adsorption and related experiments end-to-end.

Responsibilities:
- Experiment/session metadata (README generation, experiment-ID naming, share-drive copies)
- Protocol orchestration (valve sequences, temperature ramps, gas delivery, spectrum acquisition)
- Threaded acquisition coordination (OPUS, pressure logger, temperature logger, mass-spec logger)

Current structure:
- `session.py` — `ExperimentSession`: metadata, naming, README, end-of-experiment finalization
- `adsorption.py` — `AdsorptionExperiment`: active adsorption protocol

**Deprecated (excluded from Phase 8 work):**
- `isotopic_exchange.py` — `IsotopicExchangeCalibration`: scheduled for revisit in a future phase. Do not modify as part of the current cleanup plan.

## Dependencies

**Depends on:** `control`, `datalog`, `hardware`, `core`

**Depended on by:** `main.py`

## Module-Specific Notes

- Protocol methods in `adsorption.py` are behavior-sensitive. Changes are permitted but gated by the `[FROZEN]` marker in the cleanup plan — see root `AGENTS.md` for the gate procedure.
- `ExperimentSession` owns path construction and README field writes. Plumbing methods that construct and start threaded loggers live here (not on the experiment class).
- `AdsorptionExperiment.finalize(success: bool)` is the end-of-experiment cleanup entry point. It must run on both happy path and abort. `main.py` wraps each experiment run in `try/finally` to guarantee this.
- Threaded loggers (`PressureLogger`, `TemperatureLogger`, `MassSpecLogger`) hold their CSV files open for the duration of the logger. Call `logger.stop()` before any `shutil.copy2` of those files, or the copy will fail on Windows.