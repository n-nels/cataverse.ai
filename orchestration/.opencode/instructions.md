# Agent Instructions

For project context, safety rules, and the boot/shutdown sequence, see `AGENTS.md` at the project root.

---


---

## Memory Management

**`.opencode/memory.md`** — Short-lived session context. At session end, log: what was done, what's next, any open questions. Keep it under ~50 lines; distill into foundations when it grows.

**`.opencode/foundations.md`** — Permanent record of recurring issues and user-identified corrections. Only add entries when the user flags a problem that should not happen again.
