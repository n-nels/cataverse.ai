# IR Spectroscopy Node - Directory Restructuring Plan

**Date**: 2026-01-22
**Status**: In Progress
**Priority**: Safe migration with minimal disruption to running OPUS server

---

## Executive Summary

This plan outlines a safe, phased approach to professionalize the directory structure of the IR spectroscopy codebase. The primary challenge is that `opusWrapper.py` runs continuously as a ZMQ server and cannot be disrupted during experiments. This refactoring effort aims to introduce a standard Python package structure, centralize configuration, and remove hardcoded paths to improve maintainability and robustness.

---

## Status & Completed Milestones

- **Phases 0–4**: ✓ COMPLETED (baseline, scaffolding, config consolidation, implementation, validation).
- **Phase 5**: ✓ COMPLETED (all modules refactored and modularized; Phase 5.3.A implementation complete)

## Phase 5: Module Refactoring

- **Status**: ✓ COMPLETED (5.1–5.3.A all complete)

### 5.1 Refactor `peak_heights.py`
- **Status**: ✓ COMPLETED

### 5.2 Refactor `voight_fit.py`
- **Task**: Refactor internal logic in `voight_fit.py` (module already extracted) to improve modularity and configuration-driven parameters.
- **Status**: ✓ COMPLETED
- **Summary**: 
  - Phase 5.2.A–5.2.C: Parity validation and lint cleanup complete (user verified).
  - Phase 5.2.D: Decomposition by responsibility complete—split into focused modules (io, baseline, fit, calibration, outputs).
  - Phase 5.2.E: API separation complete—pure computation functions separated from file I/O; `main.py` orchestrator has explicit COMPUTE → I/O phases; all output filenames/schemas preserved.

**Module Organization (5.2.D)**
- `io.py`: Data import/export
- `spectral_fitting.py`: Peak analysis computation
- `kinetics_fitting.py`: Kinetics analysis
- `peak_heights.py`: Peak height extraction
- `output.py`: Compute and save functions
- `main.py`: Analysis orchestration
- `integrate_ir_iso_xchg.py`: Isotope exchange integration

**API Separation (5.2.E)**
- Compute functions return structured results (dicts/DataFrames)
- Save functions handle file I/O only
- Orchestrator manages COMPUTE → I/O ordering
- All output filenames and column labels unchanged (backward compatible)

### 5.3 Refactor `opus_wrapper.py`
- **Task**: Refactor `opus_wrapper.py` to improve clarity, separation of concerns, and use of the refactored analysis modules.
- **Status**: ✓ COMPLETED
- **Summary (completed work)**:
   - Global state consolidated into dataclasses (`OpusState`, `OpusPaths`, analysis queues).
   - Path/config handling centralized; analysis dispatch routed through queue helpers.
   - Acquisition, background handling, and message routing split into focused helpers.
   - ZMQ server loop remains intact; parity review completed.
   - End-of-experiment cleanup: unload last 10 file IDs on experiment end.
   - Removed legacy wrapper functions and `Subtract_ifg()` wrapper (entry point now ZMQ messages only).
   - Message schema validation remains minimal (Option A); future API hardening documented for Phase 7+.

### 5.3.A Module Decomposition
- **Task**: Separate monolithic `opus_wrapper.py` into focused modules with clear responsibilities.
- **Status**: ✓ COMPLETED
- **Completed structure**:
   - `client.py`: OPUS pipe adapter (low-level commands like `pipe_command`, `load_file`, `do_sample_measurement`, `save_as`).
   - `paths.py`: Path and config assembly (`OpusPaths` dataclass, `build_paths()`, `define_paths()`).
   - `state.py`: Runtime state container (`OpusState` dataclass, global STATE/socket management, `get_state()`, `set_state()`, `ensure_paths()`, `ensure_queues()`).
   - `dispatch.py`: Analysis queue management and dispatch (`AnalysisQueue`, `AnalysisQueues`, `build_analysis_queues()`, `dispatch_analysis()`).
   - `acquisition.py`: Measurement workflow (`subtract_ifg_files()`, `opus_acquire()`).
   - `server.py`: ZMQ message handling and server loop (`handle_background()`, `handle_readme()`, `handle_end_experiment()`, `handle_message()`, `run_server()`).
   - `main.py`: Entry point and bootstrap (`main()`, `run_server_main()`).
- **Implementation decisions**:
   - `opus_wrapper.py` removed entirely and replaced by modular structure.
   - `main_tpd` removed (legacy-only, unused).
   - `define_paths` retained within `paths.py` for backward compatibility.
   - Type hints use `TYPE_CHECKING` guard in `state.py` to avoid circular imports at runtime.
   - All OPUS command strings and semantics preserved (backward compatible).
- **Testing & Validation**:
   - All 7 modules created and tested for import.
   - Linting via black and ruff passed.
   - Code review by `@reviewer` passed.
   - `scripts/run_server.py` updated to import from `src.instrument.main`.
   - `src/instrument/__init__.py` exports `main` and `run_server_main`.

---

## Phase 6: Migration to Production

### 6.1 OPUS Server Testing (Brief Disruption)
- **Task**: After receiving explicit user permission, briefly stop the production server in a scheduled maintenance window. Run the new `scripts/run_server.py` to verify that it starts, binds to the ZMQ socket, and responds to basic commands. **This step requires user confirmation before proceeding.**
- **Gate**: User approval is required before any Phase 6 work begins.
- **Note**: Phase 5.3.A code is complete and tested for import. Awaiting user manual verification that refactored behavior is identical to legacy.

### 6.2 Swap Procedure
- **Task**: Once all validation passes, the `ir-spectro-node-refactor/` directory will be promoted to `ir-spectro-node/` after backing up the original. The new server will be started from `scripts/run_server.py`.

### 6.3 Rollback Procedure
- **Task**: A detailed rollback plan is in place. If the new server fails, the backup can be restored in under 3 minutes to minimize downtime.

---

## Phase 7: Post-Migration Tasks

### 7.1 Cleanup & Documentation
- **Task**: Update the `README.md` and other documentation to reflect the new structure, configuration, and operating procedures. Archive or delete legacy backups and artifacts.

### 7.2 Git Workflow Establishment
- **Task**: Create a `develop` branch and establish a feature-branching workflow for all future development.

---

## Success Criteria

### Phase Completion Checklist

- **Phase 0**: [x] Baseline established, refactor copy created
- **Phase 1**: [x] New structure defined, file migration complete
- **Phase 2**: [x] Config system created, hardcoded paths identified
- **Phase 3**: [x] Files moved, imports updated, entry points created
- **Phase 4**: [x] Refactor copy validated (static checks + sample runs)
- **Phase 5**: [x] All modules refactored (5.1-5.2 complete; 5.3 complete; 5.3.A implementation complete)
- **Phase 6**: [ ] Production swap successful, OPUS server running
- **Phase 7**: [ ] Documentation updated, backup cleaned up

### Final State Indicators

- [x] Code organized into `src/`, `scripts/`, `tests/`, `config/`
- [ ] Zero hardcoded paths in active code
- [x] Configuration loaded from YAML
- [x] Proper Python package structure
- [x] Entry points via scripts directory
- [ ] OPUS server running from new location
- [ ] All workflows functional
- [ ] Git workflow established for future work

---
**End of Refactoring Plan**
