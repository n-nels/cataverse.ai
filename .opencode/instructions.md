# Agent Instructions for IR-Spectro-Node Project

version: 1.2
last_updated: 2025-01-16
changelog:
  - 1.2: Migrated from persona system to OpenCode native agents. Updated Rule Priority and Activation Protocol.
  - 1.1: Formalized Rule Priority, Overrides, Persona Activation, and Compliance Auditing.
  - 1.0: Initial creation of core rules.

---

These are the non-negotiable, global rules for working on this project. They must be followed at all times, by all agents.

## 1. Core Mandate: Safety and Phased Refactoring

Your primary objective is to assist in the phased refactoring of the `ir-spectro-node` codebase.

- **Production is Sacred:** The `C:\Users\labuser\CataVerse\ir-spectro-node` directory is the live, production environment. **You must NEVER modify, read from, or interact with it.**
- **Work exclusively** in the refactor workspace: `C:\Users\labuser\CataVerse\ir-spectro-node-refactor`.

## 2. Rule Priority & Overrides

### Rule Priority (Highest to Lowest)

1. Safety rules in this file (`instructions.md`).
2. Current phase constraints in `REFACTORING_PLAN.md`.
3. Active agent instructions (`.opencode/agent/*.md`).
4. Agent tool restrictions enforced by `opencode.json`.
5. Local `.agent.md` rules in working directories.
6. Code conventions in `.opencode/conventions.md`.

### Emergency Override

If the user explicitly states `[OVERRIDE: <rule>]`, you may proceed but MUST log the override in `.opencode/memory.md` with a justification.

## 3. The Refactoring Plan is Law

All work must align with `REFACTORING_PLAN.md`.

- **Check Your Phase:** Before taking any action, read `REFACTORING_PLAN.md` to confirm the current active phase.
- **Do Not Jump Ahead:** You are strictly forbidden from starting work on a new phase without explicit user permission. If a request seems to cross a phase boundary, you must ask for confirmation.

## 4. Agent Activation Protocol

This project uses OpenCode's native agent system defined in `opencode.json`.

### Primary Agents (Switch with Tab)

| Agent | Purpose |
|-------|---------|
| `coder` | Refactors code following the plan |
| `architect` | Plans and designs systems (read-only) |

### Subagents (Invoke with @mention)

| Agent | Purpose |
|-------|---------|
| `@reviewer` | Reviews code quality and correctness |
| `@debugger` | Investigates errors and root causes |
| `@validator` | Validates scientific/numerical changes |
| `@historian` | Updates memory and foundations |

### Switching Rules

- **To switch primary agents:** Use Tab key or `/agent <name>`
- **To invoke subagents:** Use `@agent_name` in your message
- **Tool restrictions are enforced:** Each agent's `tools` block in `opencode.json` determines what actions are permitted. Do not attempt to circumvent these restrictions.

## 5. The "Think-First" Protocol

Before proposing any code modification, you MUST use a thinking block to verify your logic.

- **Internal Monologue:** In this block, reason through your proposed action.
- **Verification Checklist:** Your monologue MUST check your plan against the rule priority list.

## 6. The "Read-First" Protocol

- **Read Before Writing:** Always use the read tool on a file before using write or edit.
- **Understand the Locals:** When modifying code, read sibling files or related modules to understand local conventions and architecture.

## 7. Critical Code Safety & Definition of Done

- **Instrument Code (`src/instrument/`):** Your work is not done until you provide a mock-test plan for any modification.
- **Analysis Code (`src/analysis/`):** Your work is not done until you have explicitly confirmed that NumPy array shapes are handled correctly and have manually traced the mathematical operations for a sample input in your thinking block.

## 8. Context & Memory Management

- **Context Sweep:** When you start a new task, check the current directory and all parent directories for `.agent.md` or `.spec.md` files.
- **Session Handoff:** Before ending a multi-turn task, write a brief summary to `.opencode/memory.md`.
- **Memory Distillation:** When `.opencode/memory.md` grows too large (more than approximately 5000 tokens), propose a "Distillation Task" to summarize its key findings into `foundations.md` and then clear `memory.md`.

## 9. Formatting and Communication Standards

- **Use LaTeX** for complex mathematical formulas.
- **Use Markdown tables** when comparing old vs. new logic.

## 10. Compliance & Auditing

### Compliance Checkpoint

At the end of any code-modifying action, you must output:
- [ ] Phase verified: [Phase X]
- [ ] Persona active: [Name]
- [ ] Think-First block used: Yes/No
- [ ] Local .agent.md checked: [paths]

### Violation Reporting

If you detect a rule violation (by yourself or in existing code), log it in `.opencode/memory.md` under a `## Violations` section with:
- Rule violated
- Context
- Suggested remediation
