# Agent Instructions

For project context, safety rules, and the boot/shutdown sequence, see `AGENTS.md` at the project root.

---

## Golden Rule

**Preserve function.** This refactor changes structure, not behavior. The actuator valve logic, gas delivery sequences, pressure checks, and timing were validated against real hardware. Do not alter what the code does — only how it is organized.

---

## Rule Hierarchy

When instructions conflict, follow the nearest file to the root. `AGENTS.md` overrides this file. This file overrides agent role definitions in `.opencode/agent/`. Agent role definitions override module-level `AGENTS.md` files in subdirectories.

---

## Refactoring Protocol

The refactor plan lives in `docs/refactor_plan.md`.

**Before:** Read the target file, its siblings, and the module's `AGENTS.md`.

**During:** One file at a time. Keep changes small and reviewable. If you're unsure whether a change alters behavior, don't make it.

**After:** Verify imports resolve. Mark the task complete in the plan.

---

## Memory Management

**`.opencode/memory.md`** — Short-lived session context. At session end, log: what was done, what's next, any open questions. Keep it under ~50 lines; distill into foundations when it grows.

**`.opencode/foundations.md`** — Permanent record of recurring issues and user-identified corrections. Only add entries when the user flags a problem that should not happen again.