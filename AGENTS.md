# Agent Guidelines for IR Spectroscopy Node

This file is the primary manifest for AI agents. It provides the high-level operational protocol and directs agents to the appropriate OpenCode native agents.

---

## Agent System Overview

This project uses OpenCode's native agent system. Agents are defined in `opencode.json` and their detailed instructions live in `.opencode/agent/*.md`.

### Primary Agents (Tab to switch)
| Agent | Purpose | Can Edit Files? |
|-------|---------|-----------------|
| `coder` | Safely refactors legacy code following `REFACTORING_PLAN.md` | ✅ Yes |
| `architect` | Designs systems and plans major features | ❌ No (read-only) |

### Subagents (Invoke with @mention)
| Agent | Purpose | Can Edit Files? |
|-------|---------|-----------------|
| `@reviewer` | Reviews code for quality and conventions | ❌ No |
| `@debugger` | Investigates errors and identifies root causes | ❌ No (bash only) |
| `@validator` | Validates scientific/numerical code changes | ❌ No (bash only) |
| `@historian` | Summarizes learnings and updates memory | ✅ Yes (memory files only) |

---

## Agent Operational Protocol

### On Session Start
1. Read `REFACTORING_PLAN.md` to understand the current phase and its limitations.
2. Read `.opencode/memory.md` to load short-term memory from the previous session.
3. Identify which **primary agent** is appropriate for the current task.

### Before Any Action
- Adhere to the rules in `.opencode/instructions.md`.
- Follow the conventions in `.opencode/conventions.md`.
- Respect the `tools` restrictions defined in `opencode.json` for your current agent.

### For Specific Information
- **Coding style, naming, formatting**: `.opencode/conventions.md`
- **Build commands, environment, data paths**: `.opencode/environment.md`

---

## Trigger-Based Agent Selection

| Situation | Action |
|-----------|--------|
| **Planning/Designing** | Switch to `architect` agent (Tab) |
| **Writing/Refactoring Code** | Switch to `coder` agent (Tab) |
| **After Code Changes** | Invoke `@reviewer` for review |
| **Encountering Errors** | Invoke `@debugger` for root cause analysis |
| **Modifying Scientific Code** | Invoke `@validator` before and after changes |
| **End of Phase** | Invoke `@historian` to update `.opencode/memory.md` |

---

## Workflow Guidelines

1. **Modify existing code**: Follow best practices and conventions.
2. **Add new features**: Create new files with descriptive names.
3. **Refactor**: Maintain backward compatibility where possible.
4. **Test changes**: Run the relevant script with sample data.
5. **Document**: Add comments only for non-obvious logic.
6. **Archive**: Move old versions to `arxiv/` before major changes.

---

## Session Closing Checklist

Before ending a work session, ensure the following documentation is updated:

1. **Required updates**
   - `REFACTORING_PLAN.md`
   - `.opencode/memory.md`
2. **If impacted by the session**
   - `DIRECTORY_STRUCTURE.md`
   - `.opencode/foundations.md`
   - The `.spec.md` and `.agent.md` files in the subdirectory that was the focus of the session
   - Other relevant `.opencode/*.md` files
3. **Context Management**
   - Prune the *.md files if there is extraneous information about Phases that have been completed

---

## Agent Capabilities Reference

Detailed persona instructions for each agent are located in:
- `.opencode/agent/coder.md`
- `.opencode/agent/architect.md`
- `.opencode/agent/reviewer.md`
- `.opencode/agent/debugger.md`
- `.opencode/agent/validator.md`
- `.opencode/agent/historian.md`

These files define the **behavioral traits** and **negative constraints** for each agent. The `opencode.json` file **enforces** the tool restrictions.
