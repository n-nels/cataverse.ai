---
name: alignment
description: Periodically re-check experiment instructions and scope during long-running autonomous model experimentation.
---

# Autoresearch Alignment Check

Use this skill during autonomous experimentation.

## Trigger This Check

Perform an alignment check:

- Every 30 minutes of active experimentation.
- Every 5 completed trials.
- Before editing a file outside the current experiment manifest or model-specific configuration.
- Before changing model implementation code.
- When considering a new experiment direction or scope expansion.
- Before finalizing the campaign report.

## Required Review

Re-read:

1. The repository root `AGENTS.md`.
2. The package AGENTS.md' if it exists.
3. The package spec.md` if it exists.
4. The active experiment manifest.

## Alignment Record

After completing the check, append an entry to the active run log:

```text
[alignment-check] <timestamp> | trial=<trial_number> | status=aligned | next_action=<brief description>