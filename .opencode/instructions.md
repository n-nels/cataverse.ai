# Agent Instructions

For project context, safety rules, and the boot/shutdown sequence, see `AGENTS.md` at the project root.

---

## Golden Rule

**Preserve function.** The valve sequences, gas delivery logic, pressure checks, and timing were validated against real hardware by the experimentalist. When porting code from legacy packages to new packages, copy control flow verbatim. You may change dependency wiring, replace `print()` with `logger.info()`, and add types — but the sequence of calls, values, sleeps, and branching must remain identical.

---

## Rule Hierarchy

When instructions conflict, follow the nearest file to the root. `AGENTS.md` overrides this file. This file overrides agent role definitions in `.opencode/agent/`. Agent role definitions override module-level `AGENTS.md` files in subdirectories.

---

## Work Protocol

The active plan lives in `docs/clean_up_plan.md`.

**Before:** Read the phase instructions, the target module's `AGENTS.md`, and any legacy file you are porting from.

**During:** One task per commit. If you're unsure whether a change alters behavior, don't make it and ask the user.

**After:** Verify imports resolve, tests pass. Mark the task complete in the execution plan.

---

## Memory Management

**`.opencode/memory.md`** — Short-lived session context. At session end, log: what was done, what's next, any open questions. Keep it under ~50 lines; distill into foundations when it grows.

**`.opencode/foundations.md`** — Permanent record of recurring issues and user-identified corrections. Only add entries when the user flags a problem that should not happen again.