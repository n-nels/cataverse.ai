# cataverse.ai — Project Spec

> Status: DRAFT — topology only. Each section gets filled in collaboratively; sections marked ❓ have open questions to resolve before they can be written.

---

## 1. Vision & Purpose
<!-- One paragraph: what cataverse.ai is, who it's for, why it exists.
     Includes the dual purpose: a public-facing product AND a learning vehicle
     for Nick (agent development). These goals sometimes trade off — name that here. -->

## 2. Goals & Non-Goals
<!-- Explicit list of what v1 does and — just as important — what it deliberately
     does not do. Non-goals prevent scope creep. -->

### 2.1 Learning Goals
<!-- Separate from product goals: what Nick wants to understand by the end
     (agent loops, tool use, prompt design, eval, etc.). These shape HOW we build,
     not just what. E.g., "no black-box agent frameworks" might be a constraint here. -->

## 3. Users & Access Model
<!-- Who visits the site? Anonymous public? Friends with a link?
     ❓ Public write access to a database is a real security question — do visitors
     get read-only queries? Rate limits? This section defines the trust model. -->

## 4. System Architecture
<!-- The big picture diagram: browser → web app → agent → database.
     One diagram + a paragraph per component explaining its responsibility
     and why it exists as a separate piece. -->

### 4.1 Web Application
<!-- Frontend + backend framework choice, what pages/views exist, hosting target. -->

### 4.2 Database (Neo4j AuraDB)
<!-- Instance tier, connection model, who holds credentials, how the app talks to it. -->

### 4.3 Agent
<!-- The centerpiece for learning. Architecture of the agent loop: model, tools,
     how it turns natural language into Cypher, how results flow back.
     Built from primitives (raw API calls) vs. framework — decision recorded here. -->

### 4.4 Domain & DNS
<!-- Where cataverse.ai is registered, what DNS records are needed,
     Cloudflare or registrar-direct, how it connects to hosting.
     ❓ Need to know current registrar and whether Cloudflare is already involved. -->

## 5. Data
<!-- Placeholder — deliberately deferred. Will cover: what the dataset is,
     schema (node labels, relationship types), how it gets loaded and updated. -->

## 6. Security & Abuse Prevention
<!-- A public endpoint that executes database queries is an attack surface.
     Query sandboxing (read-only?), rate limiting, API key protection,
     cost controls on the Claude API (a public agent = someone else spending your money). -->

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

## 9. Decision Log
<!-- Append-only record of decisions + why (e.g., "AuraDB free tier over self-hosted
     because zero ops burden; revisit if we outgrow limits"). Useful for learning —
     you can see why the system is shaped the way it is. -->
