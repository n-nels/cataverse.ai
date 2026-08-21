# AGENTS.md

## Project Overview

This is **cataverse.ai** — a Python system that controls laboratory instruments for catalysis experiments. It manages gas flow, pressure, temperature, and spectral acquisition for adsorption and isotopic exchange studies on supported metal catalysts.

The system controls real physical hardware. Changes to this code can open valves, pressurize vessels, and heat samples. **Read safety constraints before modifying any device or operations code.**

## Behavior-Sensitive Code

The control and experiment layers contain sequences of valve operations, pressure checks, timing delays, and temperature ramps that were validated against real hardware. These values are not arbitrary.

Any change to behavior-sensitive code (valve sequencing, gas delivery, pressure checks, timing-sensitive protocol methods) requires explicit human go-ahead before committing. If you encounter an unintended behavior change — different timing, different valve order, different pressure threshold — STOP and report. Do not "fix" it silently.

## Package Structure

The active dependency flow is: **experiments -> control + datalog -> hardware -> config/physics**. Package-level `AGENTS.md` files document module-specific constraints where present.

## Hardware Safety Rules

A strict plan in .md format must be referenced prior to any changes in hardware. Hard enforcement.

### Frozen-Behavior Gate

1. Stop before making changes. Summarize what will change and why. Wait for explicit human go-ahead.
2. Validate against existing tests. If the task requires it, plan real-hardware revalidation.

## Code Conventions

Before editing code, read and follow `~/.opencode/conventions.md` when it is available.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
