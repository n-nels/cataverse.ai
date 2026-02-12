# IR Spectroscopy Node - Directory Restructuring Plan

**Date**: 2026-01-22
**Status**: In Progress (Phase 7)
**Priority**: Safe migration with minimal disruption to running OPUS server

---

## Executive Summary

This plan outlines a safe, phased approach to professionalize the directory structure of the IR spectroscopy codebase. The primary challenge is that `opusWrapper.py` runs continuously as a ZMQ server and cannot be disrupted during experiments. This refactoring effort aims to introduce a standard Python package structure, centralize configuration, and remove hardcoded paths to improve maintainability and robustness.

---

## Status & Completed Milestones

- **Phases 0–4**: ✓ COMPLETED (baseline, scaffolding, config consolidation, implementation, validation).
- **Phase 5**: ✓ COMPLETED (all modules refactored and modularized; Phase 5.3.A implementation complete)

## Phase 5: Module Refactoring

- **Status**: ✓ COMPLETED
- **Summary**: Refactoring and modularization of analysis + instrument code complete, including peak fitting, pipeline orchestration, and OPUS server decomposition. All modules refactored, outputs preserved, and parity checks completed.

---

## Phase 6: Migration to Production

### 6.1 OPUS Server Testing (Brief Disruption)
- **Status**: ✓ Completed
- **Task**: Briefly stop the production server in a scheduled maintenance window. Run the new `scripts/run_server.py` to verify that it starts, binds to the ZMQ socket, and responds to basic commands.

### 6.2 Swap Procedure
- **Status**: ✓ Completed
- **Task**: Once all validation passes, the `ir-spectro-node-refactor/` directory will be promoted to `ir-spectro-node/` after backing up the original. The new server will be started from `scripts/run_server.py`.

### 6.3 Rollback Procedure
- **Status**: ✓ Completed (not executed; deemed unnecessary after stable swap)
- **Task**: A detailed rollback plan is in place. If the new server fails, the backup can be restored in under 3 minutes to minimize downtime.

---

## Phase 7: Post-Migration Tasks

### 7.1 Cleanup & Documentation
- **Status**: ✓ Completed
- **Task**: Update the `README.md` and other documentation to reflect the new structure, configuration, and operating procedures. Archive or delete legacy backups and artifacts.

### 7.2 Git Workflow Establishment
- **Status**: Pending
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
- **Phase 6**: [x] Production swap successful, OPUS server running
- **Phase 7**: [ ] Documentation updated, backup cleaned up (7.1 complete; 7.2 pending)

### Final State Indicators

- [x] Code organized into `src/`, `scripts/`, `tests/`, `config/`
- [ ] Zero hardcoded paths in active code
- [x] Configuration loaded from YAML
- [x] Proper Python package structure
- [x] Entry points via scripts directory
- [x] OPUS server running from new location
- [ ] All workflows functional
- [ ] Git workflow established for future work

---
**End of Refactoring Plan**
