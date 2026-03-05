# Agent Instructions for IR-Spectro-Node Project

---

## 1. Rule Priority & Overrides

### Rule Priority (Highest to Lowest)

1. Safety rules in this file (`instructions.md`).
2. Active agent instructions (`.opencode/agent/*.md`).
3. Agent tool restrictions enforced by `opencode.json`.
4. Local `.agent.md` rules in working directories.
5. Code conventions in `.opencode/conventions.md`.

## 2. Agent Activation Protocol

This project uses OpenCode's native agent system defined in `opencode.json`.

### Primary Agents

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

## 3. The "Think-First" Protocol

Before proposing any code modification, you MUST use a thinking block to verify your logic.

- **Internal Monologue:** In this block, reason through your proposed action.
- **Verification Checklist:** Your monologue MUST check your plan against the rule priority list.

## 4. The "Read-First" Protocol

- **Read Before Writing:** Always use the read tool on a file before using write or edit.
- **Understand the Locals:** When modifying code, read sibling files or related modules to understand local conventions and architecture.

## 5. Context & Memory Management

- **Context Sweep:** When you start a new task, check the current directory and all parent directories for `.agent.md` or `.spec.md` files.
- **Session Handoff:** Before ending a multi-turn task, write a brief summary to `.opencode/memory.md`.
- **Memory Distillation:** When `.opencode/memory.md` grows too large (more than approximately 1000 tokens), propose a "Distillation Task" to summarize its key findings into `foundations.md` and then clear `memory.md`.

## 6. Formatting and Communication Standards

- **Use LaTeX** for complex mathematical formulas.
- **Use Markdown tables** when comparing old vs. new logic.

## 7. Compliance & Auditing

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
