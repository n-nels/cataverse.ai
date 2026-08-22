@AGENTS.md

# cataverse.ai dashboard

Public website at cataverse.ai for viewing/interacting with Nick's Neo4j graph database (the same graph this repo's instruments write into). Longer-term: a learning project for building an AI agent over the graph (see spec.md — deliberately incomplete, filled in collaboratively; do NOT one-shot it). Lives at `dashboard-node/` in the `n-nels/cataverse.ai` monorepo, alongside `ir-spectro-node/` and `orchestration/` (real instrument-control code — be careful not to touch those).

## Current goal (as of 2026-08-21)
The "ship the minimum" goal (navigate to cataverse.ai → see and interact with the graph)
is done and deployed. Vision/Goals/Architecture sections of spec.md are now filled in —
see spec.md Section 0 for the synthesized technical implementation plan and phased order.
Next real milestone is Phase A there (the real agent) — **blocked on Nick getting an
Anthropic API key** (console.anthropic.com; his Claude Pro subscription does not include
API access, common point of confusion, he doesn't have one as of 2026-08-21).

## Plan
1. ~~Scaffold Next.js (TypeScript + Tailwind) app~~ — done
2. ~~API route queries Neo4j AuraDB server-side (`neo4j-driver`); credentials in `.env.local`, never sent to the browser~~ — done
3. ~~Interactive graph view (react-force-graph-2d)~~ — done, loads the full graph (no artificial cap; ~1.9k nodes/~6.8k rels as of 2026-08, revisit if growth makes it feel slow)
4. ~~Deploy to Vercel (free tier)~~ — done, `cataverse.ai` tracks `feature/dashboard-node` branch (not merged to main)
5. ~~DNS~~ — done, points at Vercel
6. App shell + real stats bar + mockup "Ask the Agent" tab — done (for a presentation; mockup is scripted/canned, not live)
7. See spec.md Section 0 for what's next (real agent, ontology view, cost tracking, raw-data gate, plotting, video ingestion)

## Decisions made
- **Access control: public, no gate.** `/api/graph` is an unauthenticated read-only endpoint — anyone with the URL can pull the full graph as JSON. Nick confirmed this is acceptable (2026-08-07). Query is strictly read-only (`MATCH`/`RETURN`, no writes), so this is a data-exposure question, not a data-integrity one.
- **Data scope: show everything, no pagination/filtering.** Revisit only if the dataset grows enough to make the browser-side force simulation feel sluggish.
- **Repo placement: `dashboard-node/`** inside `n-nels/cataverse.ai`, matching the `-node` naming convention of `ir-spectro-node/`. Developed on branch `feature/dashboard-node`, merged to `main` via PR (matching this repo's existing workflow).

## Working style (important)
- Nick is learning: explain what's under the hood, don't just deliver finished product — especially for the future agent work
- Spec-first, iterative; Nick provides context incrementally
- Data model details deliberately deferred; database is AuraDB free tier, custom dataset
- Nick does not yet have a Claude API key (needed later for agent phase, not for graph viewer)
