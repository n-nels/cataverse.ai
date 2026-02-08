# Project Foundations & Core Rules

This document contains foundational principles and permanent rules that must be followed throughout the project's lifecycle. These rules override any general instructions.

## 1. Preservation of `peak_fitting.py`

- **Rule:** Do not remove, delete, or alter the contents of `src/analysis/peak_fitting.py` unless explicitly instructed to do so in a specific task.
- **Reason:** This module is being kept for legacy purposes and will be handled separately by the user. Functions may be extracted from it, but the original file must remain intact.

## 2. Refactor Artifacts

- Refactor artifacts such as verification copies and hygiene passes (e.g., `voight_fit_new.py`, `voight_fit_v3.py`) are permitted in the refactor workspace so long as they do not replace or delete legacy files until parity is confirmed and the user approves promotion.
