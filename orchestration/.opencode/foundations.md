# Project Foundations & Core Rules

This document contains foundational principles and permanent rules that must be followed throughout the project's lifecycle.

## 1. Frozen-Behavior Gate

Tasks in `docs/clean_up_plan.md` that modify behavior-sensitive code (valve sequencing, gas delivery, pressure checks, timing-sensitive protocol methods) are marked `[FROZEN]`. When executing a `[FROZEN]` task:

1. Stop before making changes. Summarize what will change and why. Wait for explicit human go-ahead.
2. Validate against existing tests. If the task requires it, plan real-hardware revalidation.
3. If you encounter an unintended behavior change in a task *not* marked `[FROZEN]` — different timing, different valve order, different pressure threshold — STOP and report. Do not "fix" it silently.

Hardware Safety Rules (in root `AGENTS.md`) are never modified regardless of phase.

## 2. Exception Hierarchies Over Sentinels

Unrecoverable hardware and safety failures raise distinctive exceptions (`HardwareConnectionError`, `HardwareMappingError`, `ThermocoupleFault`, `SafetyLimitExceeded`, etc.). Adapters and controllers do not call `sys.exit`, do not swallow errors into `None`/`{}`/`False` return values, and do not silently degrade. The experiment or `main.py` layer catches the exception and decides what to do — including safe shutdown where applicable.

## 3. Script Execution Context

Modules are typically executed directly from VSCode (interactive runs) instead of CLI.
