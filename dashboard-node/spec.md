# cataverse.ai — Project Spec

> Status: DRAFT — topology only. Each section gets filled in collaboratively; sections marked ❓ have open questions to resolve before they can be written.

---

## 0. Technical Implementation Plan (draft — 2026-08-21)
<!-- Synthesized from Nick's answers in Sections 1-5 below. This is a proposal, not a
     locked decision — flagged judgment calls throughout are Claude's best guess at the
     technical shape of what Nick described in plain language, meant to be corrected. -->

**The point of this project, in one line:** research data usually stays locked up until
publication, and even then only the polished conclusions surface. `cataverse.ai` flips
that — the whole DOE-funded research program (data, reasoning, Nick's own findings)
represented as a living, queryable graph, so an LLM can answer real scientist-level
questions directly. Publications become a byproduct, not the interface.

**Status of each piece:**

| # | Piece | Status |
|---|-------|--------|
| 1 | Web app + graph viewer | Done |
| 2 | Neo4j-backed API | Done |
| 3 | Vercel deploy + custom domain | Done |
| 4 | Real agent (NL → Cypher → answer) | **Blocked** — needs an Anthropic API key (console.anthropic.com; separate from Claude Pro, which doesn't include API access) |
| 4b | DB keep-alive + snapshot fallback | Not started — **must precede going public**, see Phase A0 |
| 5 | Ontology/schema overview view | Not started |
| 6 | Cost tracking + BYOK fallback | Not started |
| 7 | Raw-data access gate (decoupled from page) | Not started |
| 8 | Plotting (pre-built + agent-generated) | Not started |
| 9 | Video transcript ingestion | Not started, later |

**Phased plan (matches Nick's "start simple, iterate on real deficiencies" learning goal):**

- **Phase A — Real agent, v1.** Raw Claude API tool-use loop (no framework yet). Two
  tools to start: run a read-only Cypher query, fetch the graph schema. Replaces the
  current `AgentPreview.tsx` mockup. *Blocked on API key.*
- **Phase A0 — Keep-alive + cached snapshot.** *(Infrastructure; must land before Phase D
  makes the site public.)* Scheduled daily Vercel cron job that (a) runs a trivial query
  against Neo4j to reset the free tier's inactivity clock so the instance never
  auto-pauses, and (b) refreshes a stored snapshot of the graph that `/api/graph` can fall
  back to if Neo4j is unavailable anyway. See Decision Log 2026-08-23 for why. Note the
  snapshot needs a persistent store, which is the *same* need Phase C has for usage
  counters and the Phase D allowlist — pick one store that serves all three.
- **Phase B — Ontology/schema view.** New tab (alongside Graph / Ask the Agent) showing
  node labels, relationship types, and the external ontology info Nick has outside this
  repo — needs that content handed over before this can be built. Much of it can be
  derived straight from Neo4j (label/relationship-type inventory, and the real
  `(:A)-[:REL]->(:B)` triples the data actually contains), so Nick's external docs
  enrich this rather than block it.
- **Phase C — Cost tracking + BYOK.** Per-visitor $ cap on agent usage (estimated from
  Claude token usage × pricing), then prompt for the visitor's own API key beyond that.
  Needs a small persistent store beyond Neo4j — not a full Postgres, since Neo4j already
  covers the science data. Something like Vercel KV or a small SQLite/Turso instance for
  usage counters and the raw-data allowlist (Phase D) is enough, and keeps cost near zero.
- **Phase D — Decouple raw-data access from page access.** Resolves the open question in
  Section 8 below: the page becomes publicly viewable (Vercel Authentication comes off),
  but `/api/graph`'s raw dump stays behind its own gate — an allowlist of tokens Nick
  issues manually after an email request, checked in middleware independent of the page.
- **Phase E — Plotting.** Leaning toward the agent generating chart specs from query
  results, rendered client-side with a JS charting library, rather than running Nick's
  Python plot scripts server-side (Vercel's runtime is Node-first; shelling out to Python
  is real added infrastructure). If specific existing scripts need to be preserved as-is
  rather than reimplemented, that changes this — flag it.
- **Phase F — Video transcript ingestion.** Nick records explainer videos → transcribed →
  ingested as new graph nodes linked to relevant existing nodes. Later; no design yet.

**Explicit non-goal for v1** (Nick's call, may become a goal later): users submitting
commentary, peer review, or publications into the graph.

---

## 1. Vision & Purpose
<!-- One paragraph: what cataverse.ai is, who it's for, why it exists.
     Includes the dual purpose: a public-facing product AND a learning vehicle
     for Nick (agent development). These goals sometimes trade off — name that here. -->

     https://cataverse.ai hosts a graph database that users/agents can query. The data in the graph is collected by an autonomous catalyst discovery platform on https://github.com/n-nels/cataverse.ai. The big idea is that the academic community is a decentralized workforce that doesn't even surface unverified data and worth is still valued by publications. LLM's make publications a byproduct of verified experimental data. The application demonstrates a new path forward: Surface data, knowledge, context for a DOE funded project as a graph. Essentially, reperesent your research program digitally instead of some group page with a list of publications and schemes.

## 2. Goals & Non-Goals
<!-- Explicit list of what v1 does and — just as important — what it deliberately
     does not do. Non-goals prevent scope creep. -->

     Goals:
     1. I want the user to be able to make general queries about what the project is about, data types, insights, conclusions, etc. The things that a scientist would ask. My personal findings and insights will be captured in the context graph, along with the core science that is being addressed.
     2. We will also want to showscase the ontology of the graph (I have some of this information outside the repo). This will provide users a high-level overview of the project data structure.
     3. We will also want to include skills that allow users to plot data. I will provide a handful of the plot scripts I think users will want, but there should be some adaptibility here to develop plots users request. We might need some type of postgreSQL backend to host the data?
     4. I am willing to allow a certain dollar limit user query amount, but beyond that they need to bring their own api keys
     5. Raw data access through api is permissioned (they must contact me by email)
     6. Deploy through cloud provider.
     7. Non-goal is to let users input commentary. This would be the 'peer-review' mechanism and be incororated into the context graph. Or user could submit publication that would go into the knowledge graph. At some point this will be a goal.
     8. This is probably a non-exhaustive list of goals but good for v1

### 2.1 Learning Goals
<!-- Separate from product goals: what Nick wants to understand by the end
     (agent loops, tool use, prompt design, eval, etc.). These shape HOW we build,
     not just what. E.g., "no black-box agent frameworks" might be a constraint here. -->

     Yes, I think what you said is fine. I have never built an agentic application. So start simple so that the learning curve is less steep and we build from there. I would also like to deploy through a cloud platform and begin learning how to use cloud

## 3. Users & Access Model
<!-- Who visits the site? Anonymous public? Friends with a link?
     ❓ Public write access to a database is a real security question — do visitors
     get read-only queries? Rate limits? This section defines the trust model. -->

     Eventually I want it to be made public. We put behind Vercel which is permissioned. We may consider moving this more public and protect certain aspects (e.g., raw data). Defintely not public write access. Read-only queries and dollar limits before brining their api. 

## 4. System Architecture
<!-- The big picture diagram: browser → web app → agent → database.
     One diagram + a paragraph per component explaining its responsibility
     and why it exists as a separate piece. -->

     Yes, we already have something on vercel. Basically a website the host the neo4j instance with a backend that hosts the data so that users can use the llm to surface information about the project. I will also have a series of videos that I will make explaining the science and approach. We can generate the transcipt from there and put into the context graph.

### 4.1 Web Application
<!-- Frontend + backend framework choice, what pages/views exist, hosting target. -->

     I have no idea. I have never done these type of things before.

### 4.2 Database (Neo4j AuraDB)
<!-- Instance tier, connection model, who holds credentials, how the app talks to it. -->

     We already did this. 

### 4.3 Agent
<!-- The centerpiece for learning. Architecture of the agent loop: model, tools,
     how it turns natural language into Cypher, how results flow back.
     Built from primitives (raw API calls) vs. framework — decision recorded here. -->

     Yes, this is the part I am most interested in learning and designing. We will deep dive here when the time is right. I prefer to have a very simple agent to begin with so I can learn, use, and iterate based off the deficiencies I see when using. So start very simple, then progress to Langchain(?), etc. 

### 4.4 Domain & DNS
<!-- Where cataverse.ai is registered, what DNS records are needed,
     Cloudflare or registrar-direct, how it connects to hosting.
     ❓ Need to know current registrar and whether Cloudflare is already involved. -->

     I believe we did this too.

## 5. Data
<!-- Placeholder — deliberately deferred. Will cover: what the dataset is,
     schema (node labels, relationship types), how it gets loaded and updated. -->

     This should be accessible in the graph hosted on neo4j and exposed at https://cataverse.ai. I think a postgreSQL backend or liteSQL backend should be good. But I do want to keep costs down.

## 6. Security & Abuse Prevention
<!-- A public endpoint that executes database queries is an attack surface.
     Query sandboxing (read-only?), rate limiting, API key protection,
     cost controls on the Claude API (a public agent = someone else spending your money). -->

**Current state (as of 2026-08-08):** `cataverse.ai` is gated behind Vercel Authentication
("Standard Protection") — visitors must be logged into Vercel and be a project member.
This protects the page *and* `/api/graph` uniformly (confirmed: both return a 302 to
Vercel's login when unauthenticated). Free, but all-or-nothing per deployment — no way to
make the page public while keeping data gated, or vice versa, using this mechanism alone.

**Future idea, not built — page/data split:** When ready to make the site public, the
page and the `/api/graph` data endpoint don't have to share one gate. Vercel's own
protection is deployment-wide, but nothing stops us from adding our own app-level check
in front of just `/api/graph` (e.g. Next.js Middleware requiring a shared secret, API key
header, or session cookie) independent of whether Vercel Authentication is on. That would
let the page be publicly viewable while the underlying data dump stays restricted — worth
revisiting once "make the site public" actually comes up, especially if the data is still
pre-publication at that point.

## 7. Milestones
<!-- Phased build order. Rough shape:
     Phase 0: accounts/credentials/DNS groundwork
     Phase 1: database live with data, queryable locally
     Phase 2: agent working in a terminal (no web yet) — the learning core
     Phase 3: web app wrapping the agent, deployed to cataverse.ai
     Phase 4: polish (graph viz, cypher console, etc.)
     Each phase has a "done when" criterion. -->

## 8. Open Questions
<!-- Running list. Questions move out of here and into sections as they're answered. -->

- Should page access and data-API access ever be decoupled (public page, separately-gated
  `/api/graph`)? See Section 6 for the mechanism if/when this matters. Not needed while
  the whole site is gated behind Vercel Authentication.
- Should Vercel's Root Directory be switched from `dashboard-node` to the repo root (with
  custom build/install commands pointed at `dashboard-node`)? Would eliminate the cosmetic
  failed-check noise on every unrelated `ir-spectro-node`/`orchestration` PR — see Decision
  Log 2026-08-21. Deferred: current noise doesn't block merges, not worth the risk of a
  build-config change without time to test it properly.

## 9. Decision Log
<!-- Append-only record of decisions + why (e.g., "AuraDB free tier over self-hosted
     because zero ops burden; revisit if we outgrow limits"). Useful for learning —
     you can see why the system is shaped the way it is. -->

- **2026-08-08 — Access model, round one: public, no gate.** Query is strictly read-only
  (`MATCH`/`RETURN`), so this was a data-exposure decision, not a data-integrity one.
- **2026-08-08 — Access model, round two: gated.** Once actually live at `cataverse.ai`
  (vs. a scratch preview URL), Nick reversed the above and gated it via Vercel
  Authentication — free, requires visitors to have a Vercel account and be a project
  member. Reversible any time (just toggle it off) when ready to go public; see Section 6
  for the page/data-split idea to revisit at that point.
- **2026-08-08 — `cataverse.ai` points at the `feature/dashboard-node` branch, not
  Production/`main`.** Nick didn't want to merge to `main` yet. Vercel supports attaching
  a custom domain to a specific git branch (via the Preview environment), so the domain
  tracks that branch directly without touching Production. `main` still has no working
  deploy at all — that's expected, not a bug, until the PR merges.
- **2026-08-23 — AuraDB free tier auto-pauses, and that threatens the core premise.**
  The instance went unreachable (`getaddrinfo ENOTFOUND` on the Aura hostname) for the
  second time in ~2 weeks — free-tier instances pause after a few days of inactivity, and
  are eventually *deleted* if left paused. Today this is invisible because the site is
  gated to Nick alone, but `cataverse.ai` is meant to be an always-queryable view of the
  research program: once public (Phase D), visitors arriving between Nick's working
  sessions would hit "Failed to load graph." Decision: **keep-alive cron + cached
  snapshot** (Phase A0) rather than paying for a higher Aura tier — a daily scheduled
  query resets the inactivity clock, and a stored snapshot keeps the site readable even
  during a genuine Aura outage. Chosen over cron-only (no outage protection) and over
  upgrading (recurring cost, and Nick wants costs near zero). Nice side effect: the
  snapshot needs a persistent store, which Phases C and D independently need too.
- **2026-08-21 — Connecting Vercel to the whole monorepo means every branch/PR gets a
  build attempt, including unrelated `ir-spectro-node`/`orchestration` work.** Since
  Project Settings → Root Directory = `dashboard-node`, any branch without that folder
  (i.e. everything except `feature/dashboard-node`, and `main` until it merges) fails
  with "The specified Root Directory does not exist." This check happens as a hard gate
  right after clone — *before* Ignored Build Step logic runs, so a branch-allowlist script
  there (tried first) does not prevent it. Confirmed harmless: this repo has no required
  status checks configured, so the failing/red Vercel check does not block merging any PR
  (verified on PR #23 and #24 — "Able to merge" / "No conflicts with base branch" shown
  regardless). Left as cosmetic noise for now; see Open Questions for the real fix if it's
  ever worth doing.
