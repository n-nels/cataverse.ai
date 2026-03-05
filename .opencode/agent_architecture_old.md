#CataVerse Agentic Architecture Blueprint

This document defines the specialized markdown framework for the **CataVerse** project. It serves as a map for OpenCode to understand how to interpret, validate, and document the codebase within a high-autonomy "vibe coding" workflow.

## 1. Global Orchestration (Root Level `/`)
The files at the root level define the global engineering culture and safety boundaries for the entire project.

| File Name | Role Type | Focus |
| :--- | :--- | :--- |
| `.agent.md` | **Project Lead** | Defines the primary tech stack (Python 3.11), general persona, and high-level architectural goals. |
| `security_auditor.md` | **Guardian** | Focuses on network security (`network_messaging.py`), sanitizing inputs, and secure serial communication. |
| `.safety.md` | **Guardian** | Defines physical safety gates. Prevents commands that could damage actuators or the NI DAQ hardware. |
| `code_reviewer.md` | **Validator** | Enforces best practices: hardware context managers, thread safety, and standardized error handling. |
| `hardware_manifest.md` | **Truth** | The "Digital Twin." Maps physical hardware (IPs, COM ports, NI DAQ pinouts) to the code. |
| `.memory.md` | **Chronicler** | A persistent log of architectural decisions, bug-fix post-mortems, and lessons learned. |

---

## 2. Directory-Specific Implementation
Markdown files located in subdirectories provide **Local Overrides** and specific context for those modules.

### 📂 `instrument_control/` (The Core)
* **`.context.md`**: Maps the dependency flow between `core/config.py`, `devices/`, and `operations/`.
* **`.instructions.md`**: Global rules for instrument handling (e.g., "Always verify connection before sending a payload").

### 📂 `instrument_control/devices/` (Hardware Layer)
* **`.spec.md`**: Technical specifications for the NI USB-6009, serial protocols, and Kasa SmartPlugs.
* **`.instructions.md`**: Low-level drivers rules (timeouts, retry logic, baud rate consistency).

### 📂 `instrument_control/experiments/` (Science Layer)
* **`.spec.md`**: Defines the "Scientific Validation" logic—what constitutes a valid experiment run.
* **`documentation_writer.md`**: Specialized role to translate experimental code changes into the `docs/` folder.

### 📂 `legacy/` (The Archive)
* **`.agent.md`**: Sets a "Read-Only/Historian" persona. Forbids refactoring unless explicitly requested.
* **`.context.md`**: Explains the data structure of legacy `.csv` and `.parquet` files for the agent's reference.

---

## 3. The "Vibe Coding" Workflow Protocol
For OpenCode to work autonomously, it must follow this **Execution Cycle** using the files above:

1.  **Discovery**: Before writing code, the agent must check the local `.agent.md` and the root `.safety.md`.
2.  **Simulation**: For hardware changes, the agent must cross-reference `hardware_manifest.md`.
3.  **Self-Review**: Upon completion, the agent must run its output against the `code_reviewer.md` logic.
4.  **Logging**: Every significant change or bug fix must be summarized in `.memory.md`.

---

## 4. Content Structure Standards
Every `.md` file in this architecture should follow this formatting for machine-readability:

* **`<role>`**: Define the active persona.
* **`<thinking_process>`**: Mandatory step-by-step logic the agent must follow.
* **`<validation_gate>`**: A checklist that must return `PASS` before the task is marked complete.
* **`<style_guide>`**: Specific formatting or library preferences.