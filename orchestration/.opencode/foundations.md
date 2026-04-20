# Project Foundations & Core Rules

This document contains foundational principles and permanent rules that must be followed throughout the project's lifecycle.

## 1. Parity-Safe Control Flow

- **Rule:** Do not introduce new early-return branches that alter legacy control flow without explicit parity confirmation.
- **Reason:** New exit points (for example, returning when a data check fails but legacy would continue) can silently skip output generation (e.g., missing `*_Carbonyl` files). Any added return paths must be explicitly reviewed for parity.

## 2. Script Execution Context

- Modules are typically executed directly from VSCode (interactive runs) instead of CLI.

## 3. Import context

- Do not do local imports. Import at the top.

