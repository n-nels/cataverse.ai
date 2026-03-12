# utils/ — Data Logging and Helper Utilities

For project-wide context and safety constraints, refer to root `AGENTS.md`.

---

## Purpose

This module contains utility functions for experiment data I/O and support tasks, including:

- Directory creation and file path helpers
- CSV/README logging helpers
- Share-drive copy helpers and related experiment file management

Utilities should remain reusable and avoid embedding experiment sequencing logic.

## Dependencies

**Depends on:** `core` (for shared config values where currently used), Python stdlib

**Depended on by:** `operations`, `experiments`

## Constraints

- Preserve output formats (CSV columns/order, markdown content layout) unless explicitly planned.
- Preserve function signatures and side effects used by upstream modules.
- Keep behavioral changes out of this layer during structural refactor.
