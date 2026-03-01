# Agent Guidelines for IR Spectroscopy Node

This file is the primary manifest for AI agents. It provides the high-level operational protocol and directs agents to the appropriate OpenCode native agents.

---

## Agent System Overview

This project uses OpenCode's native agent system. Agents are defined in `opencode.json` and their detailed instructions live in `.opencode/agent/*.md`.

### Primary Agents (Tab to switch)
| Agent | Purpose | Can Edit Files? |
|-------|---------|-----------------|
| `coder` | Refactors and introduces new functionality | ✅ Yes |
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
1. Read `*.md` file in root (if any) to understand the current project and its limitations.
2. Read `.opencode/memory.md` to load short-term memory from the previous session.

### Before Any Action
- Adhere to the rules in `.opencode/instructions.md`.
- Follow the coding style, naming, fand formatting conventions in `.opencode/conventions.md`.
- Respect the `tools` restrictions defined in `opencode.json` for your current agent.

### For Specific Information
- **Build commands, environment, data paths**: `.opencode/environment.md`

---

## Trigger-Based Agent Selection

| Situation | Action |
|-----------|--------|
| **After Code Changes** | Invoke `@reviewer` for review |
| **Encountering Errors** | Invoke `@debugger` for root cause analysis |
| **Modifying Scientific Code** | Invoke `@validator` before and after changes |

---

## Workflow Guidelines

1. **Modify existing code**: Follow best practices and conventions.
2. **Add new features**: Create new files with descriptive names that integrate with existing code.
3. **Refactor**: Maintain backward compatibility where possible.
4. **Document**: Add comments only for non-obvious logic.

---

## Session Closing Checklist

Before ending a work session, ensure the following documentation is updated:

1. **Required updates**
   - `*.md` in root. Ignore AGENTS.md manifest file
   - `.opencode/memory.md`
2. **If impacted by the session**
   - `directory_structure.md`
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
