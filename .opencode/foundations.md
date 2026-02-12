# Project Foundations & Core Rules

This document contains foundational principles and permanent rules that must be followed throughout the project's lifecycle. These rules override any general instructions.

## 1. Refactor Artifacts

- Refactor artifacts such as verification copies and hygiene passes (e.g., `voigt_fit_new.py`, `voigt_fit_v3.py`) are permitted in the refactor workspace so long as they do not replace or delete legacy files until parity is confirmed and the user approves promotion.

## 2. Parity-Safe Control Flow

- **Rule:** Do not introduce new early-return branches that alter legacy control flow without explicit parity confirmation.
- **Reason:** New exit points (for example, returning when a data check fails but legacy would continue) can silently skip output generation (e.g., missing `*_Carbonyl` files). Any added return paths must be explicitly reviewed for parity.
