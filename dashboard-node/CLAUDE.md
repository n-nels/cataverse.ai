@AGENTS.md

# cataverse.ai dashboard

Public website at cataverse.ai for viewing/interacting with Nick's Neo4j graph database (the same graph this repo's instruments write into). Longer-term: a learning project for building an AI agent over the graph (see spec.md — deliberately incomplete, filled in collaboratively; do NOT one-shot it). Lives at `dashboard-node/` in the `n-nels/cataverse.ai` monorepo, alongside `ir-spectro-node/` and `orchestration/` (real instrument-control code — be careful not to touch those).

## Current goal (as of 2026-08-23)
The site is live and deployed. spec.md Section 0 holds the implementation plan and status
table — **read it first, it is kept current**.

Two packages now:
- `dashboard-node/` — this Next.js app (Graph / Query / Ontology / Ask the Agent tabs)
- `agent-node/` — Python terminal agent over the same graph, on branch `feature/agent-node`

**Nick is iterating on the agent loop himself — do not "fix" `agent-node/` unprompted.**
It gives wrong answers sometimes; that is the point, and chasing those failures is his
learning exercise. Known issues are recorded in spec.md §5.2. Keep moving the *app*
forward instead unless he says otherwise.

## Plan
1. ~~Scaffold Next.js (TypeScript + Tailwind) app~~ — done
2. ~~API route queries Neo4j AuraDB server-side (`neo4j-driver`); credentials in `.env.local`, never sent to the browser~~ — done
3. ~~Interactive graph view (react-force-graph-2d)~~ — done, loads the full graph (no artificial cap; ~1.9k nodes/~6.8k rels as of 2026-08, revisit if growth makes it feel slow)
4. ~~Deploy to Vercel (free tier)~~ — done, `cataverse.ai` tracks `feature/dashboard-node` branch (not merged to main)
5. ~~DNS~~ — done, points at Vercel
6. App shell + real stats bar + mockup "Ask the Agent" tab — done (for a presentation; mockup is scripted/canned, not live)
7. See spec.md Section 0 for what's next (real agent, ontology view, cost tracking, raw-data gate, plotting, video ingestion)

## Decisions made
- **Access control: gated** (changed 2026-08-08 from the original "public, no gate"). `cataverse.ai` sits behind Vercel Authentication, which covers the page *and* the API routes. Reversible when Nick wants it public — see spec.md §6.
- **All Cypher execution is read-only, enforced server-side.** `/api/query` runs user-typed Cypher, so this matters: `session.executeRead()` makes the *server* reject writes (verified — `Neo.ClientError.Statement.AccessMode`). The keyword regex beside it is only fast feedback, not the boundary. Do not weaken either.
- **Data scope: show everything, no pagination/filtering.** Revisit only if the dataset grows enough to make the browser-side force simulation feel sluggish.
- **Repo placement: `dashboard-node/`** inside `n-nels/cataverse.ai`. The `-node` suffix was copied from `ir-spectro-node/` and does not really fit a web app — acknowledged, not worth renaming.
- **Branch, not main.** `cataverse.ai` is pinned in Vercel to the `feature/dashboard-node` branch. Pushing that branch redeploys the live site. `main` has neither package yet.

## Working style (important)
- Nick is learning: explain what's under the hood, don't just deliver a finished product. He has asked to be part of debugging rather than handed fixes — explain the mechanism and let him choose.
- **Do not build defenses for problems not yet observed.** Direct feedback from Nick: *"I feel like you are handling edge cases that we have not encountered."* Guards get built when a failure actually happens.
- Keep spec.md current as work lands — it is the durable record across sessions.
- Verify against the live database rather than assuming; several confident assumptions have turned out wrong (see spec.md §5.1.1).
- Spec-first, iterative; Nick provides context incrementally.
