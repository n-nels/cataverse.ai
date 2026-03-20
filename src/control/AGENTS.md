# control/ — Instrument Operations and Actuator Sequencing (New Architecture)

For project-wide safety rules, behavioral preservation, and hardware constraints, see root `AGENTS.md`.

---

## Purpose

This module implements high-level instrument operations by coordinating hardware-layer calls:

- Valve/actuator open/close/write behavior
- Gas delivery to manifold/cell
- Evacuation and pressure-based control flow
- Spectrometer and acquisition-related operational sequences

This is the highest-risk layer because it directly controls sequencing that affects gas flow, pressure, and pump safety.

## Dependencies

**Depends on:** `hardware`, `core` logging utilities

**Depended on by:** `experiments`, top-level execution scripts

## Critical Constraints

- Treat actuator and valve logic as behavior-frozen.
- Preserve exact call order, pressure checks, branching behavior, and timing (`time.sleep`).
- Preserve valve semantics: default closed = `1.0 V`, open = `5.0 V`.
- Never remove, weaken, or reorder safety checks (turbo/roughing, pressure limits, downstream path assumptions).
- Preserve error-handling behavior: failures must trigger the same control responses as legacy logic.

## Refactor Scope

Allowed: naming cleanup, type hints, docstrings, logging improvements, small extraction/refactors that keep identical behavior.

Not allowed: logic optimizations or sequence changes that alter physical behavior.
