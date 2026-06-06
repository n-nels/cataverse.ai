# Project Foundations & Core Rules

This document contains foundational principles and permanent rules that must be followed throughout the project's lifecycle.

## 1. Frozen-Behavior Gate

1. Stop before making changes. Summarize what will change and why. Wait for explicit human go-ahead.
2. Validate against existing tests. If the task requires it, plan real-hardware revalidation.
3. If you encounter an unintended behavior change in a task *not* marked `[FROZEN]` — different timing, different valve order, different pressure threshold — STOP and report. Do not "fix" it silently.

Hardware Safety Rules (in root `AGENTS.md`) are never modified regardless of phase.


