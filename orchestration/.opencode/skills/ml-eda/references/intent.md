# EDA Skill — Intent

## Purpose

This skill exists to provide a repeatable, structured methodology for developing new analysis capabilities in the cataverse.ai IR spectroscopy node. It captures meta-learnings from past feature development into a general workflow that any agent can follow.

## What This Skill Is

A framework for moving from "we need this analysis" to "this analysis is implemented, tested, and documented." It prescribes:

1. How to isolate work (git worktrees)
2. How to scope a feature (inputs/outputs)
3. How to plan implementation (phased, verifiable)
4. How to validate results (functional, performance, visual)
5. How to respect project constraints (behavior-sensitive code, simplicity)

## What This Skill Is Not

- Not specific to any single analysis type (2D correlation, PCA, etc.)
- Not a substitute for domain knowledge
- Not a testing framework — it prescribes what to test, not how

## How It Evolves

This skill should be refined after each project that uses it. When a pattern works well, capture it. When a step is unclear, clarify it. The goal is a living document that gets better with each use.

## Origin

Developed from the experience of planning the 2D correlation spectroscopy feature. The patterns in the plan template and workflow steps emerged from that work and were generalized for reuse.
