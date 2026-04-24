# Agent Instructions

For project context, safety rules, and the boot/shutdown sequence, see `AGENTS.md` at the project root.

---

## Active Plan

The active work plan is `docs/clean_up_plan.md`. On invocation, read the plan end-to-end, find the first task with Status `[ ]`, verify its predicates are `[x]`, and report the task to the user before making changes. Do not proceed without explicit go-ahead.

The earlier `docs/refactor_plan*.md` files are historical reference only. Do not edit them.

---

## Rule Hierarchy

When instructions conflict, follow the nearest file to the root. `AGENTS.md` overrides this file. This file overrides agent role definitions in `.opencode/agent/`. Agent role definitions override module-level `AGENTS.md` files in subdirectories.

---

## Working Protocol

**Before starting a task:**
- Read the target file, its siblings in the same package, and the package's `AGENTS.md`.
- Confirm the task's predicates are satisfied (other task numbers marked `[x]` in the plan).
- If the task is marked `[FROZEN]` or contains a decision point ("human decides," "human picks," "human flag," "human confirms"), stop and wait for explicit go-ahead before changing code.

**During:**
- One task per commit. No squashing.
- Keep changes small and reviewable.
- If a change you were not expecting to make appears necessary, stop and report before making it.

**After:**
- Verify imports resolve. Run `pytest tests/ -v` for phase-boundary validation.
- Update the task's Status column from `[ ]` to `[x]` in `docs/clean_up_plan.md`. Include this edit in the same commit as the work.
- Stop and wait for the next invocation.

---

## Memory Management

**`.opencode/memory.md`** — Short-lived session context. At session end, log: what was done, what's next, any open questions. Keep it under ~50 lines; distill into foundations when it grows.

**`.opencode/foundations.md`** — Permanent record of recurring issues and user-identified corrections. Only add entries when the user flags a problem that should not happen again.
