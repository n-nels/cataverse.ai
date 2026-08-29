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

*(Status reviewed 2026-08-23.)*

| # | Piece | Status |
|---|-------|--------|
| 1 | Web app + graph viewer | Done |
| 2 | Neo4j-backed API | Done |
| 3 | Vercel deploy + custom domain | Done |
| 4 | Ontology/schema view | **Done** — schema meta-graph + detail panel |
| 4b | Cypher query tab (Bloom-style) | **Done** 2026-08-23 — type Cypher, results drawn on the same canvas |
| 5 | Terminal agent (NL → Cypher → answer) | **Done, v1** — `agent-node/`, local Ollama, hand-written loop |
| 6 | Agent in the web UI | Not started — `AgentPreview.tsx` is still a scripted mockup |
| 7 | Cost tracking + BYOK | Not started — and the local-LLM decision may remove the need entirely |
| 8 | Raw-data access gate (decoupled from page) | Not started |
| 9 | Plotting (pre-built + agent-generated) | Not started |
| 10 | Video transcript ingestion | Not started, later |
| — | DB keep-alive + snapshot fallback | **Shelved** 2026-08-23 |
| — | repo → Neo4j ingestion pipeline | **Shelved** 2026-08-23 |

**Phased plan (matches Nick's "start simple, iterate on real deficiencies" learning goal):**

- **Phase A — Terminal agent, v1. ✅ DONE (2026-08-23).** Lives in `agent-node/` (Python,
  uv, matching `orchestration/` conventions). Runs against a **local LLM via Ollama**, not
  the Anthropic API — see Decision Log. Hand-written tool-use loop, no framework, as per
  the §2.1 learning goal. Two tools: `get_graph_schema` and `run_cypher`. Read-only is
  enforced by `session.execute_read()` (server-side, the real guarantee) plus a keyword
  scan for fast feedback. Entry points: `cli.py` (REPL) and `ask.py` (single question,
  debugger-friendly). Verified end-to-end against the live graph.
  *Note:* the earlier plan here required dual-typed-property handling from §5.1. That code
  was written, then removed once the underlying bad row was fixed — see §5.1.
- **Phase A0 — Keep-alive + cached snapshot. SHELVED 2026-08-23.** Nick's call: it kept
  displacing the agent work, which is the actual learning goal and the CV-relevant skill.
  The AuraDB free tier will keep auto-pausing in the meantime — acceptable while the site
  is gated to Nick, but this must be revisited before going public. Design notes retained
  in Decision Log 2026-08-23.
- **Phase B — Ontology/schema view. ✅ DONE (2026-08-23).** Third tab in the dashboard.
  Renders the schema as a meta-graph (labels as nodes sized by count, relationship types
  as edges) plus a detail panel of each label's properties and connections. Derived live
  from Neo4j via `/api/schema`, so it shows the ontology *as instantiated* rather than as
  declared. Nick's external ontology docs were not needed to build it, and can still
  enrich it later.
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

**→ Running to-do list lives in [Section 10, Open Action Items](#10-open-action-items).**

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
     7. Non-goal is to let users input commentary. This would be the 'peer-review' mechanism and be incororated into the context graph. Or user could submit publication that would go into the knowledge graph. At some point this will be a goal. Users ask questions and if the agent cannot find direct answer in the graph it asks user to provide a response/justification and that I will get back to them.
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

**As built (2026-08-23).** Next.js (App Router) + TypeScript + Tailwind, deployed on
Vercel, in `dashboard-node/`. Five tabs:

| Tab | What it does |
|---|---|
| **Graph** | Landing view. Loads the whole graph (~1.9k nodes) and renders it force-directed. |
| **Explore** | Start from one label, click nodes to pull in their neighbours. Per-label workspaces, undo, remove-from-view. |
| **Query** | Cypher box → results drawn on the same canvas. Scalars fall back to a table. |
| **Ontology** | The schema as a meta-graph: labels as nodes, relationship types as edges. |
| **Ask the Agent** | Still a scripted mockup. The real agent lives in `agent-node/`. |

API routes (all server-side; Neo4j credentials never reach the browser):

```
/api/graph    whole graph as {nodes, links}
/api/schema   labels, relationship triples, property types
/api/query    runs user-supplied Cypher — READ-ONLY, see §6
```

Rendering is shared: `GraphCanvas` draws any `{nodes, links}`, and both the Graph tab and
the Query tab use it, so results look identical to the landing view rather than drifting
into a second style.

### 4.2 Database (Neo4j AuraDB)
<!-- Instance tier, connection model, who holds credentials, how the app talks to it. -->

     We already did this. 

### 4.3 Agent
<!-- The centerpiece for learning. Architecture of the agent loop: model, tools,
     how it turns natural language into Cypher, how results flow back.
     Built from primitives (raw API calls) vs. framework — decision recorded here. -->

     Yes, this is the part I am most interested in learning and designing. We will deep dive here when the time is right. I prefer to have a very simple agent to begin with so I can learn, use, and iterate based off the deficiencies I see when using. So start very simple, then progress to Langchain(?), etc. 

**Built 2026-08-23 — `agent-node/` (v1).** Deliberately no framework, per the above.

```
ask.py / cli.py          entry points (single question / REPL)
  └─ agent.py            the loop + tool schemas + system prompt
       ├─ ollama Client  local model, tool calling
       └─ graph.py       the ONLY path to Neo4j; read-only enforced here
```

The loop: send conversation + tool list → if the reply has no tool calls it's the answer,
stop → otherwise run each tool, append its result as a `tool` message, repeat. Bounded by
`AGENT_MAX_ITERATIONS`.

The model never touches the database. It only *names* a tool and supplies arguments;
`_dispatch` decides what actually runs. That separation is what makes it safe to let a
model compose queries at all.

Deficiencies observed so far are recorded in §5.2 — that iterate-on-real-failures loop is
working as intended. LangChain remains deliberately unused; revisit only when the
hand-written loop becomes the bottleneck.

### 4.4 Domain & DNS
<!-- Where cataverse.ai is registered, what DNS records are needed,
     Cloudflare or registrar-direct, how it connects to hosting.
     ❓ Need to know current registrar and whether Cloudflare is already involved. -->

     I believe we did this too.

## 5. Data
<!-- Placeholder — deliberately deferred. Will cover: what the dataset is,
     schema (node labels, relationship types), how it gets loaded and updated. -->

     This should be accessible in the graph hosted on neo4j and exposed at https://cataverse.ai. I think a postgreSQL backend or liteSQL backend should be good. But I do want to keep costs down.

### 5.1 Mixed property types — RESOLVED, but the failure mode is worth keeping

**Status 2026-08-23: resolved.** Nick repaired the offending row directly in the database.
`pressure_meas_g1` now types as `FLOAT` only (verified: 1,342 values, no strings), and
`pressure_meas_g2` was always clean. The harness guard written for this
(`DUAL_TYPED_PROPERTIES` in `agent-node/.../graph.py`) has been **removed** — with no
string left in the data it did nothing useful, and worse, its caveat keyed on the property
*name* rather than its *type*, so it kept asserting something false to the model.

Remaining benign case: `temp`, `duration`, `pressure_calc` are typed `FLOAT | INTEGER`.
The instrument code accepts `temp=400` or `temp=400.0`. Harmless — Cypher compares
INTEGER and FLOAT numerically.

**Keep the lesson, not the code.** The general hazard is real and will recur:

> In Cypher, comparing a STRING to a NUMBER returns `null` rather than raising. A row with
> an unexpected type is **silently excluded** from a range filter, and the agent reports a
> confident answer computed over a subset it never knew was reduced.

The same silent-null semantics bit us a second way — see §5.2 — which is the stronger
argument that this belongs in the harness rather than the prompt. But build the guard when
a real instance appears, not speculatively.

### 5.2 Unknown property names fail silently too (open)

Observed 2026-08-23 while beta-testing the agent. Asked about gauge pressure, the model
invented property names (`gauge_1_pressure`, `temperature`; the real ones are
`pressure_meas_g1`, `temp`) and ran:

```cypher
MATCH (p:Pretreatment) WHERE p.gauge_1_pressure > 5 RETURN count(p) ...
```

Neo4j treats an unknown property as `null`, so this is not an error — it returns a
legitimate-looking count of 0. The agent answered *"No pretreatment steps had a pressure
above 5."* Confidently, and wrongly.

**The information to catch this already exists and is being discarded.** The driver
emitted a notification:

```
gql_status='01N52'  warn: property key does not exist.
The property `gauge_1_pressure` does not exist in database
```

`GraphClient.run_read()` returns only `records` and never reads
`result.consume().summary.notifications`. Surfacing those as tool warnings would catch
this class for free — typos, missing labels, cartesian products.

Contributing cause: the model **skipped `get_graph_schema`** on that run, though the system
prompt instructs it to call it first. It obeyed on other runs. That inconsistency is
precisely why this belongs in the harness — prompting was tried and observed to fail.

#### 5.1.1 Historical record — what the bad row actually was

*(Kept for the pipeline work: this is what a serialization escape looks like in practice,
and the ingestion pipeline should be designed so it cannot recur. **The row itself is
already fixed in the database.**)*

Nick expected the sentinel to be the string `'Off'`. Querying every value showed something
different, and it mattered:

```
pressure_meas_g1 :  FLOAT   x1341
                    STRING  x1     value = "(4.2, off)"
pressure_meas_g2 :  FLOAT   x1047   (no strings at all)
```

There is exactly **one** non-numeric value in the whole database, and it is not `'Off'`
— it is the string `"(4.2, off)"`. That looks like a Python tuple of
`(reading, status)` that reached Neo4j via `str()` instead of being unpacked, so the
gauge reading and its status were flattened into one string field.

**The offending record** (located 2026-08-23):

| | |
|---|---|
| Filename | `20241126_112801_pd_ceo2_000-003` |
| Datetime | 2024-11-26T11:28:01, `exp_type` adsorption |
| Material | `mat_pd_0p0339_ceo2_54` (pd / ceo2) |
| Node | `pre_20241126_112801_pd_ceo2_000-003_3` — `:Pretreatment`, `step_index` 3 |

That node has **no `pressure_meas_g2` property at all** (nor `chiller` / `pressure_calc`,
which its siblings carry) — consistent with both gauge readings being written into `g1`
before the split existed. Correct repair: `pressure_meas_g1 = 4.2`, `g2` null/absent
(the cell gauge was off).

**The current code cannot produce this**, confirmed by reading
`orchestration/src/hardware/pressure.py`:

- `p1` (manifold → `g1`): a non-numeric reading **raises** `HardwareReadError` — never stored.
- `p2` (cell → `g2`): a non-numeric reading becomes `None`, with the comment
  *"Cell gauge returns 'Off' when inactive (below range / valve closed)"* — never stored
  as a string either.

So the `FLOAT | STRING` typing was **stale** — an artifact of one legacy row, not of
current behaviour. **Confirmed fixed 2026-08-23:** Nick corrected the row in the database
and re-querying shows `FLOAT` only.

The takeaway for the pipeline: a single `str()` of a `(reading, status)` tuple, three
years of otherwise-clean data, and one silently wrong agent answer. Ingestion should
validate types on write rather than trusting the producer.

❓ Still open: the per-gauge max pressures.

## 6. Security & Abuse Prevention
<!-- A public endpoint that executes database queries is an attack surface.
     Query sandboxing (read-only?), rate limiting, API key protection,
     cost controls on the Claude API (a public agent = someone else spending your money). -->

**Current state (as of 2026-08-08):** `cataverse.ai` is gated behind Vercel Authentication
("Standard Protection") — visitors must be logged into Vercel and be a project member.
This protects the page *and* `/api/graph` uniformly (confirmed: both return a 302 to
Vercel's login when unauthenticated). Free, but all-or-nothing per deployment — no way to
make the page public while keeping data gated, or vice versa, using this mechanism alone.

**`/api/query` executes Cypher typed by the user (added 2026-08-23).** That is a real
attack surface, so read-only is enforced in two places and only one of them counts:

1. **`session.executeRead()`** — opens a READ-mode transaction, so the *server* rejects
   writes no matter what is sent. Verified directly: attempting `CREATE` inside one returns
   `Neo.ClientError.Statement.AccessMode`, "Writing in read access mode not allowed."
   **This is the guarantee.**
2. A keyword regex (`CREATE|MERGE|DELETE|SET|…`) in front of it. Only there to fail fast
   with a message a human can act on. **Not** the boundary — do not rely on it, and do not
   remove (1) on the grounds that (2) exists.

Results are capped at 300 rows. Still unaddressed: there is no rate limiting, so an
expensive query (a large cartesian product) could tie up the AuraDB free tier. Acceptable
while the site is gated to Nick; **revisit before going public**.

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

*(Reviewed 2026-08-23 — both below are still genuinely open.)*

- **Still open.** Should page access and data-API access ever be decoupled (public page,
  separately-gated `/api/graph`)? See §6 for the mechanism. Not needed while the whole site
  is gated behind Vercel Authentication, which it still is.
- **Still open, still deferred.** Should Vercel's Root Directory be switched from
  `dashboard-node` to the repo root (with build/install commands pointed at
  `dashboard-node`)? Would remove the cosmetic failed-check noise on unrelated
  `ir-spectro-node`/`orchestration` PRs — see Decision Log 2026-08-21. Doesn't block merges,
  so not worth a build-config change without time to test it.
- **New (2026-08-23).** If visitors are expected to bring their own local LLM (§3), how does
  a page served from `cataverse.ai` reach an Ollama instance on the visitor's `localhost`?
  Technically possible — Ollama's `OLLAMA_ORIGINS` permits cross-origin calls — but it means
  every visitor must install Ollama, pull a model, and configure CORS. That is a steep ask
  for a public research site, and it interacts with whether §7 (cost tracking + BYOK) is
  needed at all. Unresolved; does not block the terminal agent.
- **New (2026-08-23).** Where should `spec.md` live? It now describes `dashboard-node/` *and*
  `agent-node/`, but sits inside `dashboard-node/`. Repo root is the more honest home.

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
- **2026-08-23 — Local LLM via Ollama, not the Anthropic API.** Nick's call. Consequences,
  all favourable for the learning goal: Phase A stopped being blocked on an API key
  (Claude Pro does not include API access); there is no per-query cost, so the §7 cost cap
  became optional rather than a prerequisite; and iteration is free, which matters when the
  point is to observe failures and tune the harness. Trade-off: an 8B local model is weaker
  than a frontier model at composing Cypher, so some observed failures are model capability
  rather than harness design — worth keeping in mind before over-fitting the prompt to
  them. Intended to extend to visitors bringing their own local LLM (see §8 for the
  unresolved browser→localhost problem).
- **2026-08-23 — Agent is Python in `agent-node/`, terminal-first.** Chosen over TypeScript
  inside `dashboard-node/`. Reasons: matches §7's own milestone ("agent working in a
  terminal — the learning core"), matches the Python instrument code, and agent work in
  Python is the stronger signal for Nick's job search. Cost: the web UI integration will
  need either a port or a small HTTP service later. Accepted deliberately.
- **2026-08-23 — Keep-alive/snapshot and the ingestion pipeline both shelved.** Nick:
  *"It seems like there is always something else to do."* Both are infrastructure that kept
  displacing the agent, which is the actual learning objective. Neither blocks agent work.
  Revisit the keep-alive before going public; revisit the pipeline when stale data starts
  to hurt.
- **2026-08-23 — Removed the dual-typed-property guard rather than keeping it "just in
  case."** Nick, correctly: *"I feel like you are handling edge cases that we have not
  encountered."* The guard was built for a single row that was then fixed at source, and
  its schema caveat had become actively wrong. General rule adopted: build guards for
  failures actually observed, not anticipated ones.
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

- **2026-08-29 - Tabs stay mounted once visited; switching tabs no longer discards work.**
  The shell used to render only the active tab, so every tab switch unmounted the other
  four and threw away their state - an Explore session built up over a dozen expansions, a
  typed query and its results, the whole layout the force simulation had settled into. Now
  a tab is mounted on first visit and thereafter hidden with CSS (`hidden` +
  `aria-hidden`), never unmounted. Lazy on first visit, so an unopened tab still costs
  nothing. This needed one supporting change: `useElementSize` ignores 0x0 measurements,
  because a hidden panel measures zero and `GraphCanvas` only renders its canvas at
  non-zero size - without it every hidden tab tore its canvas down and re-simulated from
  scratch on return, which is the thing being fixed. Verified on Explore (14 nodes, undo
  depth, open detail panel all survived a round trip), Query (Cypher text + result table),
  and Ontology (still lays out correctly on first click).

## 10. Open Action Items
<!-- Running to-do list. Unlike Section 8 (Open Questions, which are decisions to make),
     these are concrete pieces of work with an owner. Check off / delete as done. -->

### Data integrity

- [x] ~~**Repair the malformed pressure record.**~~ Done 2026-08-23 — Nick fixed it directly
  in the database.
- [x] ~~**Re-verify property typing.**~~ Done 2026-08-23 — `pressure_meas_g1` now types as
  `FLOAT` only across 1,342 values; no strings remain. `pressure_meas_g2` also clean.
- [ ] **Record the per-gauge max pressures** in §5.1 once known — needed for the agent to
  reason about out-of-range readings. *Owner: Nick.*
- [ ] **Property rename lands on the next reload.** Renamed in the source `.json` only:
  `pressure_meas_g1` / `pressure_meas_g2` → `pressure_measure_cell` / `pressure_measure_mfld`
  (exact names TBC). **The database still has the old names** (verified 2026-08-23: 1,342
  nodes). Arrives when the data is reloaded. Revisit then: any saved Cypher, the Ontology
  tab's colour map, and docs referencing the old names. Note for the pipeline design —
  a rename is a schema migration, and the pipeline needs a story for them.

### Agent

- [ ] **Surface Neo4j notifications as tool warnings** in `GraphClient.run_read()`. Would
  catch invented property names, missing labels, and cartesian products — see §5.2. The
  driver already reports them via `result.consume().summary.notifications`; we discard
  them. Highest-value known fix.
- [ ] **Decide how to stop the model skipping `get_schema`.** Prompting was tried and
  observed to fail. Options: inject the schema into the system prompt at startup, or
  validate property names before executing. See §5.2.
- [ ] **Compare models on the same questions.** Downloaded: `qwen3:8b`, `llama3.1:8b`,
  `ministral-3:8b`, `qwen3:14b`. Measured 2026-08-23: all three 8B models run 100% on GPU
  at `num_ctx=32768` (~9.7 GB of 12 GB); 65536 spills to CPU. `ministral-3:8b` answered the
  materials question correctly in 19s vs 45–77s for `qwen3:14b`. Use `agent-node/ctx_probe.py`
  for any new model.
- [ ] **`AGENT_MAX_ROWS=50` is now conservative** given 4× the context. 150–200 would fit.
- [x] ~~**Commit `agent-node/`**~~ — done 2026-08-23, branch `feature/agent-node`, pushed.

### Explore tab — beta-test findings (2026-08-23, Claude driving the UI)

Ordered by how much they get in the way. **Items 1–3 were fixed on 2026-08-23** and are
kept here because the reasoning is worth having; 4–7 remain open.

1. ~~**Nodes have no labels.**~~ **FIXED.** `lib/nodeLabel.ts` picks a display property per
   label (`name`, `formula`, `base_name`, `id`…), falling back gracefully for labels added
   later. Long ids are truncated from the *front*, because siblings share a prefix
   (`pre_20241126_112801_…`) and it is the tail that distinguishes them. Bare numbers get
   a unit ("step 3", "402 K"). On graphs over 150 nodes labels only appear once zoomed in,
   so the 1,875-node landing view stays legible.
   <br>*Original report:* Seeding 12 `ChemConcept` nodes gives twelve identical purple
   dots — the only way to tell them apart is to click each one and read the panel. Colour
   encodes the label, but nothing identifies the *node*. The Ontology tab already draws
   text labels on its canvas, so the technique is proven; it needs a sensible per-label
   choice of which property to show (`name` for ChemConcept, `base_name` for Filename,
   `id` for Material…), probably shown only when zoomed in or when the node is selected.
2. ~~**The detail panel covers the toolbar.**~~ **FIXED** — moved to bottom-right, and
   "Fit view" to bottom-left (offset to clear Next.js's dev indicator).
   <br>*Original report:* It is `fixed top-4 right-4`, which sits on top
   of the node counts and the Undo / Clear buttons. To press Undo you must first close the
   panel — which is exactly when you want Undo. Move the panel to the bottom-right, or make
   the toolbar taller than it.
3. ~~**Nodes are a moving target.**~~ **FIXED** — sparse graphs (no links, i.e. a fresh
   seed) now use `cooldownTime` 2500ms instead of the default 15000 and a higher
   `d3VelocityDecay`, so they settle almost immediately. Verified by clicking a node
   straight after a screenshot and hitting it first try.
   <br>*Original report:* After a seed the simulation keeps nudging disconnected
   nodes for ~15s; aim at one and it has drifted by the time you click. Measured: two
   `Material` nodes moved from (528,505) and (268,638) to (717,407) and (79,735) between a
   screenshot and the click that followed. Worst with disconnected seed nodes, where no
   link force damps the motion. Likely fix: shorter `cooldownTime`, or higher
   `d3VelocityDecay`, for sparse graphs.

Also noticed, lower priority:

4. No hover affordance — the cursor does not change over a node, so nothing suggests
   clicking does anything.
5. No preview of expansion size. Expanding is a coin flip between 1 new node and the 75
   cap; showing the degree in the panel first would let you decide.
6. Removing a node can leave neighbours stranded with no visible connection. "Collapse"
   (drop what this node brought in) is probably the action people actually want, alongside
   the current "remove just this one".
7. A seed is N disconnected dots, which reads as an odd starting state. Seeding with the
   relationships *between* the seed nodes, where any exist, would look less arbitrary.

### App — candidates for what's next

- [ ] **Click-to-expand graph exploration.** Today the landing graph is an impressive but
  unnavigable hairball, and the only way to see a *subset* is to know Cypher. Bloom's core
  move is: start from one node, click to pull in its neighbours. Would make the graph
  usable by a scientist who has never written Cypher — currently the widest gap between the
  app and the §1 vision.
- [ ] **Better node detail panel.** Clicking a node shows raw JSON. Could show typed
  properties, its relationships, and a button to expand from it.
- [ ] **Plotting** (§2 goal 3). `AdsParams` carries genuinely plottable science —
  `pfo_sec_k_a`, `q_e`, `q_inf`, `r2`, `rmse`, `time_s`. Fitted kinetic parameters across
  experiments is the first chart a catalysis reader would want.
- [ ] **Shareable query links.** Encode the Cypher in the URL so a query can be linked from
  a tutorial video or a paper.
- [ ] **Rate limiting on `/api/query`.** Required before the site goes public — see §6.

### Shelved 2026-08-23 (Nick's call — kept displacing the agent work)

- [ ] **SHELVED — repo → Neo4j ingestion pipeline.** The graph is loaded by hand, so
  `cataverse.ai` shows a snapshot that silently goes stale as new experiments land. Not
  yet designed; open questions when it resumes: what triggers it (push webhook / scheduled
  poll / the instrument writing directly), incremental vs. full rebuild, idempotency on
  reruns, where it runs (GitHub Actions / Vercel cron / instrument host), and how it
  handles schema migrations like the pending property rename. Revisit when stale data
  starts to hurt.
- [ ] **SHELVED — DB keep-alive + cached snapshot.** AuraDB free tier keeps auto-pausing
  (twice in ~2 weeks). Tolerable while the site is gated to Nick; **must be revisited
  before going public**, or visitors will hit "Failed to load graph." Design in Decision
  Log 2026-08-23.

### Deferred / low priority

- [ ] Switch Vercel's Root Directory off `dashboard-node` to silence the cosmetic failed
  build check on unrelated PRs (see Decision Log 2026-08-21). Non-blocking.
- [ ] Move `spec.md` to the repo root — it now covers `agent-node/` too (see §8).
- [ ] Update `agent-node/.env.example` — its VRAM comment still cites the old
  qwen3:14b / 8192-context math.

### No longer needed

- [x] ~~**Get an Anthropic API key.**~~ Obsoleted 2026-08-23 by the switch to local Ollama.
