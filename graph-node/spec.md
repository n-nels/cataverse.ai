# graph-node — Project Spec

Status: **planning**. Nothing in `src/` is implemented yet. Kept current as work
lands; this is the durable record across sessions.

Related: `dashboard-node/spec.md` covers the website that reads this graph, and
`agent-node/` the terminal agent that queries it. Neither is a dependency —
graph-node writes the graph, they read it.

---

## 1. Purpose

Get the Neo4j graph to maintain itself. Today the graph is built by hand: run a
script on the work PC, get CSVs, import them through the Aura UI. That works, but
it means the graph is only as current as the last time Nick remembered to do it.

The target: an experiment finishes, and the graph reflects it without anyone
clicking anything.

## 2. The three graphs

These are deliberately kept separate. They have different sources, different
change rates, and different owners.

| Graph | Contents | Source | Changes when |
|---|---|---|---|
| **Data** | Material, Filename, Pretreatment, ExpConditions, AdsParams, KineticChain, and relationships derived from them (NEXT_EXP, DELTA_FROM, RELATIVE_TO) | Instrument output on `X:\` | An experiment finishes |
| **Knowledge** | ChemConcept, ChemSpecies, PyFunction, ModelParameter, KineticModel | Hand-authored YAML, later literature | Nick edits a YAML or ingests a paper |
| **Context** | The intersection of the two | TBD | Not designed yet — do not build for it |

The dividing line is **provenance, not node type**: anything computed from
measurements is data, even when it is a derived relationship rather than a
measured fact.

`DELTA_FROM` is the worked example. It is arithmetic on AdsParams properties
(`delta_ka = source.pfo_sec_k_a - target.pfo_sec_k_a`, and the same for q_e, k_s,
k_p, q_inf, q0, time_s) with no knowledge-graph input at all. It currently ships
in `knowledge.cypher` because that is where it happened to get written, not
because it belongs there. **Moving it to the data side is the first concrete act
of separation.** `RELATIVE_TO` comes from the same routine and moves with it.

### Keeping the line from blurring

The knowledge graph is going to grow — literature ingestion, and a context graph
that intersects both. A boundary that exists only as an intention will not
survive that.

So: each loader declares the labels and relationship types it owns, and a test
fails if it writes anything outside that set. Cheap, and it would have caught
`DELTA_FROM` on the day it was written.

## 3. Current state (as of 2026-08-29)

Everything below already exists and works. The gap is narrower than it looks.

| Piece | Where | State |
|---|---|---|
| Per-experiment JSON (`material`, `filename_flags`, `pretreatments`, `exp_conditions`) | `orchestration/src/experiments/session.py` | **Done.** `build_exp_params_payload()` assembles it; `_persist_exp_params_json()` writes it beside the experiment. Maps 1:1 onto the graph's node labels. |
| Fit results CSV (`*_CarbonylPeakArea.csv`) | `ir-spectro-node`, analysis + file I/O | **Done.** Source of every AdsParams property. |
| JSON + CSV to graph artifacts | `original/scripts/load_graph.py` | **Done.** Emits `exports/nodes.csv`, `relationships.csv`, `graph.cypher`, `schema.arrows.json`. Dry run: 1840 nodes, 3422 edges, 6 chains, 0 review records. |
| YAML to knowledge artifacts | `original/scripts/load_knowledge.py` | **Done.** Also emits DELTA_FROM / RELATIVE_TO, which belong to data (see §2). |
| Deterministic node IDs | `load_graph.py` `_id_mat`, `_id_fn`, `_id_pre`, `_id_ec`, `_id_ap`, `_id_kc` | **Done.** These are already MERGE keys — idempotency is solved, not open. |
| **Artifacts into Neo4j** | — | **Missing.** Done by hand through the Aura UI. This is the actual gap. |
| **A trigger** | — | **Missing.** Nothing tells the loader an experiment finished. |

Source data root is `X:\peakFit\` (share drive), which is why this does not need
to live in `orchestration/` — see §4.

## 4. Placement

**A package in the `cataverse.ai` monorepo, not a separate repo, and not inside
`orchestration/`.**

Not a separate repo: this code reads a JSON shape that `orchestration/` writes and
a CSV shape that `ir-spectro-node` writes. Split across repos, those three drift
apart silently and the breakage surfaces at load time months later. Same repo
means a format change and the loader that consumes it land in one commit.

Not inside `orchestration/`: `orchestration/` runs on the lab PC beside the
hardware. Putting Neo4j credentials and network egress there buys nothing, and it
would make `orchestration/` implicitly depend on `ir-spectro-node`'s CSV format.
Because the source data is on `X:\`, this package can run from any machine with
that drive mounted. `orchestration/`'s only new responsibility is to signal that
an experiment finished.

```
experiment ends
  -> orchestration writes <base>_expParams.json        (exists)
  -> ir-spectro writes <base>_CarbonylPeakArea.csv     (exists)
  -> orchestration signals "done"                      (new, small)
       |
  graph-node: read JSON + CSV -> write to Aura         (new)
```

## 5. Rebuild vs incremental append — OPEN

**Not yet decided. Nick wants to work through this before it is settled.**

The existing pipeline is a whole-world batch rebuild. `build_chains()` sorts every
experiment and walks the list; DELTA_FROM needs each reference's neighbours.
Neither is computable from one experiment alone.

The case for rebuilding everything on every run: it is always consistent, every
MERGE key already exists, and it eliminates a class of bug rather than solving it.
An experiment takes three days, so cost is irrelevant.

That bug class, concretely:

- **A failed write nobody notices.** Experiment 249 finishes while Aura is paused;
  the write fails. Three days later 250 appends itself to the chain. The chain is
  now missing 249 and has a NEXT_EXP edge that skips it. Nothing errors.
- **Corrected upstream data.** A bad `is_new` flag gets fixed in an old file —
  exactly what `fix_is_new.py` did to 6 of them. With append, nothing recomputes;
  chain boundaries stay wrong permanently, because the code that decides them ran
  once, at append time.

A rebuild reads current truth and recomputes, so both self-heal.

### The open part: what "rebuild" means with MERGE

MERGE never deletes. Rebuilding with MERGE adds and updates, but a node whose
source disappeared upstream — a renamed or deleted experiment — stays in the graph
forever. So "rebuild" is really a choice between:

- **(a) Accept it.** Stale nodes linger. Fine if experiments are never renamed or
  removed. Nothing to build.
- **(b) Wipe and reload.** Delete everything this loader owns, then write it
  fresh. Simple and exact. The graph is briefly empty, and a crash mid-load leaves
  it that way.
- **(c) Mark and sweep.** Stamp every node and relationship written by a run with
  that run's id, then delete anything the newest run did not touch. Never empty,
  self-correcting on deletions, and the stamp doubles as an audit trail of when
  each node was last confirmed by source data. Costs one extra property per node
  and one sweep query.

Nick has raised **hashing each experiment run in `orchestration/`** as a possible
answer here. Not yet worked through — see §7.

## 6. Decisions made

- **2026-08-29 — graph-node is its own package in the monorepo.** Reasoning in §4.
- **2026-08-29 — Data and knowledge graphs stay separate, split by provenance.**
  Enforced by per-loader label ownership plus a test, not by convention alone. §2.
- **2026-08-29 — DELTA_FROM and RELATIVE_TO belong to the data graph** and move out
  of `load_knowledge.py`. They are arithmetic on measurements. §2.
- **2026-08-29 — `original/` is vendored unmodified** rather than refactored in
  place, so there is a known-good reference to check the rewrite against.
- **Inherited, from `original/data_graph_instructions.txt` §9** — these were
  resolved during the original build and are not reopened here:
  - Pressure tuples become two flat properties, `pressure_meas_g1` /
    `pressure_meas_g2`; the string `Off` becomes null.
  - Material uniqueness key is `{metal, metal_loading, support, support_sa}`;
    expected count 2.
  - AdsParams uniqueness is composite: `(Filename.base_name, peak_name)`.
  - KineticChain properties are `{chain_id, material_key, started_at, length}` —
    nothing further.
  - Loading into Aura is via CSV import; `graph.cypher` is kept as backup/audit.

## 7. Open questions

1. **Rebuild semantics** — (a), (b), or (c) in §5. Blocks everything else.
2. **Does per-run hashing in `orchestration/` change the answer to #1?** Nick's
   idea. Needs working through: a hash detects whether an experiment's inputs
   changed, which is a different question from whether the graph was correctly
   written from them.
3. **The "done" signal.** End of `session.py`? A watcher on the share drive? A
   scheduled sweep? Three days per experiment makes latency a non-issue, which
   argues for whatever is simplest to reason about.
4. **What happens when Aura is paused.** Free tier auto-pauses. The experiment
   must never fail because the database is asleep.
5. **Where this runs.** Any machine with `X:\` mounted — but which one, and
   started by what?
6. **AdsParams timing.** Fit results come from post-processing, not the run
   itself. Does the graph update once, when fits are ready, or twice?

## 8. Non-goals for now

- The context graph (§2). Nick has flagged it as coming; do not design for it yet.
- Literature ingestion into the knowledge graph.
- Reshaping the graph based on agent performance.
- Backfilling pre-orchestration experiments from `.md` READMEs — `md_to_json.py`
  did that once and is not part of the ongoing pipeline.
