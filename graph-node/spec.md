# graph-node — Project Spec

Status: **live.** Both halves of the pipeline - data and knowledge - rebuild
the production graph from source in one pass, verified 2026-09-02. Running it
on a schedule is designed and documented (§5f) but not yet deployed: the lab
machine cannot reach Aura until its firewall allows outbound 7687. Kept current
as work lands; this is the durable record across sessions.

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
k_p, q_inf, q0, time_s) with no knowledge-graph input at all. It shipped in
`knowledge.cypher` because that is where it happened to get written, not because
it belonged there; it and `RELATIVE_TO` are owned by DATA now. That was the
first concrete act of separation, and the reason the boundary is enforced by a
test rather than by intent.

### Keeping the line from blurring

The knowledge graph is going to grow — literature ingestion, and a context graph
that intersects both. A boundary that exists only as an intention will not
survive that.

So: each loader declares the labels and relationship types it owns, and a test
fails if it writes anything outside that set. Cheap, and it would have caught
`DELTA_FROM` on the day it was written.

## 3. Current state

Complete and applied. 3,979 nodes in Aura as of 2026-09-10, rebuilt from S3 by
one command. What remains is in §7, and only two items there block anything.

| Piece | Where | State |
|---|---|---|
| Per-experiment JSON | `orchestration/src/experiments/session.py` | Unchanged by this work, and the schema of record - see §5a. |
| Fit results CSV | `ir-spectro-node` | Unchanged. Source of every AdsParams property. |
| Reading the sources | `data/source.py`, `data/fits.py`, `data/store.py` | From the **bucket**, not the share. `--from-share` remains as a fallback. |
| The data graph | `data/build.py`, `data/drift.py` | Nodes, edges, kinetic chains, reference drift. |
| The knowledge graph | `knowledge/source.py`, `knowledge/build.py` | Vocabulary, attachment to data, and Level 2 - see §5e and §5g. |
| Pointers into S3 | `data/pointers.py` | RawFile and SpectrumSeries, their own sweep scope. |
| Dry run | `data/plan.py` | Per scope, writing nothing. Always run first. |
| Writing | `common/writer.py`, `data/apply.py` | MERGE on identity, stamp, sweep. |
| Backing up the share | `backup.py`, `scripts/backup.ps1` | Nightly on the lab PC. |
| Running the rebuild unattended | `scripts/rebuild.ps1` | **Not scheduled anywhere.** §7.2. |

The rebuild needs S3 on 443 and Aura on 7687, and no share drive - so it runs
wherever both are reachable. The lab PC still cannot reach 7687.

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
Because the source data is on `X:\`, this package runs on any machine with that
drive mounted *and* outbound access to Aura (§5f). `orchestration/` gains no new
responsibility at all — it already writes everything the rebuild needs.

```
experiment ends
  -> orchestration writes <base>_expParams.json        (exists)
  -> ir-spectro writes <base>_CarbonylPeakArea.csv     (exists)

every six hours, independently
  -> graph-node: read the share drive, rebuild, write to Aura
```

## 5. Rebuild with mark and sweep — DECIDED (2026-08-29)

**Option (c), mark and sweep.** Implemented in `common/rebuild.py`; the scope it
is allowed to delete within is declared in `common/ownership.py`. The reasoning
below is kept because it is why, not just what.

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

### Hashing — complementary, not an alternative

Nick raised hashing each experiment run so the graph is *verified*. Worked through
2026-08-29: it solves a real problem, but a different one from the sweep, and the
two compose.

A hash answers **"did the inputs change?"** The sweep answers **"should this node
still exist?"** Neither implies the other. If an experiment folder is deleted off
`X:\`, its input has not changed — it is absent, and nothing on the source side
fires. Noticing requires enumerating every experiment that exists and comparing
against every node in the graph, which is the sweep. So hashing cannot replace it.

What hashing does add, if the hash is stored **on the graph node**: verification
without rebuilding. Compare each source's hash to the hash on its node and you
learn immediately whether the graph is consistent with its source. That catches
the failed-write case cleanly — the node is missing or its hash is stale, visible
in one query. It also makes a future incremental rebuild safe, if throughput ever
matters, because deletions are still caught by enumeration.

Two constraints on where the hash is computed:

1. **`orchestration/` cannot see everything that feeds a node.** AdsParams comes
   from ir-spectro's `*_CarbonylPeakArea.csv`, produced after the run and
   regenerable if fits are redone. A hash computed in `orchestration/` at
   end-of-run covers the JSON but not the fits, so it would report "unchanged"
   while the fits changed underneath. The hash belongs in `graph-node`, over the
   actual inputs it reads.
2. **Hashes are per-experiment; chains are not.** KineticChain and NEXT_EXP depend
   on the ordering of all experiments. Every individual hash can match while chain
   boundaries are wrong. Only recomputation fixes that.

Suggested order: rebuild + sweep first — it is small, and it is what makes
"rebuild" mean rebuild. Add node hashes when a `verify` command is wanted.
Neither forecloses the other.

## 5a. Schema of record

**`orchestration/src/experiments/session.py` defines the field names, not
`original/`.** The vendored instructions predate the current writer and carry
names that are already stale (they still say `pd_loading` / `ceo2_sa`, renamed
long ago to `metal_loading` / `support_sa`, flagged in their own §9c as "update
on next spec pass" and never updated). Build against what the code emits.

Verified field-by-field against the live graph on 2026-08-29. `Filename`,
`Material`, `Pretreatment` and `ExpConditions` all match `session.py` exactly,
with two intended differences and one rename:

| Difference | Resolution |
|---|---|
| `material.mass_g` is in the JSON but not on `:Material` | Intended. It lives on `:KineticChain`, one per chain, constant within a chain. |
| Every node has an `id` not present in the JSON | Intended. Deterministic, built by `common/ids.py`. |
| JSON says `pressure_meas_mfld` / `pressure_meas_cell`; graph says `pressure_meas_g1` / `pressure_meas_g2` | **Rename. The JSON names win.** |

### The pressure rename

`session.py` normalises the recorded pressure tuple to
`(pressure_meas_mfld, pressure_meas_cell)` from `(values[0], values[1])`. The
old `md_to_json.py` wrote the same two positions as `pressure_meas_g1` /
`pressure_meas_g2`. So:

```
pressure_meas_g1  ->  pressure_meas_mfld     (manifold)
pressure_meas_g2  ->  pressure_meas_cell     (cell)
```

**Confirmed by Nick 2026-08-29.** Worth recording because it was not
self-evident: `dashboard-node/spec.md`'s rename action item guesses the
*opposite* order (`g1/g2 -> cell/mfld`, marked "exact names TBC"), and that
entry needs correcting. Getting it backwards would silently mislabel 1,342
pressure readings rather than fail loudly.

Supporting evidence from the live graph, for the record: on `:Pretreatment`,
g1 averages 1.264 (max 8.778, n=1104) while g2 averages 0.014 (max 1.012,
n=810) — consistent with g1 being the dosing volume.

The loader should accept both key spellings while historical JSONs on `X:\`
still carry the old ones, mapping them as above.

## 5b. Data integrity — found during verification

- ~~**One hollow `:Pretreatment` node.**~~ **Resolved 2026-09-02 by the first
  rebuild.** `pre_20250802_073857_pd_ceo2_003-001_1` had an `id` and nothing
  else. The source turned out to hold a perfectly good step 1, so this was a
  bug in the original load rather than bad data, and the rebuild filled the
  node in. Kept here because it is the reason `source.load()` warns on a null
  `step_index` instead of passing it through.
- ~~**`is_reference` wrong on `20250313_093410_pd_ceo2_000-004`.**~~ **Resolved
  2026-09-02.** Nick confirmed the source was right and the database wrong. The
  rebuild corrected it, and the §11.2 invariant query now returns zero rows.

## 5c. Rules inherited from the original pipeline — audit

The original pipeline was developed in detail and encodes real decisions. It
also encodes scaffolding that has since been overtaken. Audited 2026-08-29,
every rule in both instruction files classified.

**The ported scripts and YAML copies were deleted on 2026-09-02**, once every
rule had been either built or consciously dropped. The two instruction
documents remain in `original/` as the historical record — they are the only
place the original reasoning exists in full.

**Keep — still true, already built**

| Rule | Where it lives now |
|---|---|
| Material key is `{metal, metal_loading, support, support_sa}` | `common/ids.py` |
| Filename keyed on `base_name`; AdsParams on `(base_name, peak_name)` | `common/ids.py` |
| `chain_id` = md5(`material_key`\|`started_at`)[:12] | `common/ids.py` |
| Per peak, take the row with the largest `Time (s)`; no delta-window grouping | `data/fits.py` |
| v1 loads `monomer_sum` only, schema forward-compatible with other peaks | `data/fits.py` |
| Experiments with no CSV stay in scope: Filename and upstream nodes, no AdsParams | `data/build.py` |
| Those experiments still participate in the kinetic chain | `data/build.py` |
| Chains break on `is_new`, ordered by datetime | `data/build.py` |
| **`mass_g` must be constant within a chain; disagreement is fatal** | `data/build.py` |
| `is_new` null is fatal — never coerced to false | `data/build.py` |
| Never guess a missing value | throughout |
| `HAS_STEP {order}` and `NEXT_STEP` both kept, deliberately redundant | `data/build.py` |
| The whole §11 drift layer: `RELATIVE_TO` to the most recent prior reference in the same chain, references pointing at the previous reference, nothing before the first reference, `DELTA_FROM` only on matching peaks, deltas as `source - target` with no thresholding | `data/drift.py` |
| Exclude source subfolders whose name contains `_test` | `data/source.py` |
| Exclude experiments whose base name contains `iso` (isotopic exchange) | `data/source.py` |

**Keep — still true, not yet built:** none. Every applicable rule is built,
which is what allowed the ported scripts to be deleted.

**Adapt — the intent holds, the mechanism changed**

| Original rule | Now |
|---|---|
| A material change implies `is_new`, so no separate check is needed | Assumption is no longer taken on trust — a chain continuing onto a different material is warned about. It was never verified, and there is now a third sample. |
| Missing values recorded in `review/missing_values_review.txt` | Collected as warnings on the run and printed by the dry run. Same purpose, no side-car file to go stale. |
| Silent nulls for `chiller` on older records, and for ExpConditions / pretreatments when `has_csv=false` | Kept as *do not warn about these*. Absent conditions on an abandoned run are normal. |
| Pressure tuples split into two properties, `'Off'` becomes null | Superseded upstream: `session.py` already normalises this before the JSON is written. Nothing for the loader to do. |
| `exp_type` inferred from `iso` in the filename | `session.py` now sets `exp_type` directly. Keep the rule only as a cross-check, not as the source. |
| `exp_success` forced false whenever `has_csv` is false | `session.py` couples them at the source (`mark_success` sets both). Worth a warning if they ever disagree, rather than a silent override. |

**Drop — served its purpose**

| Rule | Why |
|---|---|
| **"Expected count: 2 materials. Assert and flag if violated."** | Nick's confidence check during the original build. There are now three — `mat_pd_0p06645_ceo2_54` appeared in 2026. A hard assertion here would block every future sample. |
| Stage B writes files only and never connects to Neo4j | Superseded by the Bolt write path and mark-and-sweep. |
| Load into Aura by CSV import through the UI | Same. |
| "Present every script for human review before running it" | A working protocol for the original build, not a property of the pipeline. |
| The §10 "drafted without direct access, STOP if reality differs" caveats | Written when the author could not see `X:\`. Superseded: the schema is now verified directly against the database and against real source files. |
| **J=0 pretreatments with `has_csv=true` must be flagged** | Nick's call, 2026-09-02: not applicable. Zero cases in the graph; the only two J=0 experiments are aborted runs with no CSV, which is the legitimate shape. |

### The exclusions are prospective, not cleanup

Built 2026-09-02. Nothing out of scope is in the graph today - zero `iso`
experiments, zero `_test` files, every Filename is `exp_type: adsorption`.
That is not because the rules were enforced; it is because `md_to_json.py` only
ever produced JSON for in-scope experiments, so the scope was implicit in which
files existed.

**That protection expired when `session.py` became the writer.** It emits
`_expParams.json` for every run, and `orchestration/src/experiments/isotopic_exchange.py`
exists. The next isotopic-exchange run would have been discovered and loaded as
an adsorption experiment, silently. The rules matter going forward, not
backwards.

Exclusions are reported by the dry run rather than applied quietly: a file
skipped here is a node the sweep deletes later.

### One invariant this audit surfaced

§11.2 guarantees that the target of a `DELTA_FROM` edge is *always* a
reference. Two edges in the current graph point at
`20250313_093410_pd_ceo2_000-004`, whose `is_reference` is **false** — noted
earlier in `dashboard-node/spec.md` as a probable mislabel and never resolved.
It is now a checkable invariant rather than an observation, and the rebuild
should assert it. *Owner: Nick — decide whether the flag or the edge is wrong.*

## 5d. Standing procedure for a rebuild

The first live rebuild ran 2026-09-02 and took the data graph from 1,840 nodes
to 2,179, deleting nothing. Current counts are in §3; the before/after is not
worth keeping.

**One lesson from it is.** It ran twice, because the first run had a bug:
`_as_float` coerced `step_index` to `1.0`, which disagreed with the `order`
property on its own `HAS_STEP` edge and made the dashboard render "step 1.0".
The fix was one line in `source.py` and a re-run - the database was never edited
by hand. That is the argument for rebuild over append, exercised on day one, and
it is why `INTEGER_FIELDS` exists.

The procedure, which has not changed:

1. **Dry run first, every time.** Read the delete column.
2. **The source must be complete.** A partial source means the sweep deletes
   everything it does not account for. Reading from the bucket makes this
   harder to get wrong than a `--source-root` subset did, and two guards back
   it up - the 20% mass-deletion threshold and the unreadable-source threshold
   (§5g) - but neither is a substitute for reading the plan.
3. **Verify after.** The single most useful check is that `_run` has exactly one
   distinct value across every node in a scope. Two values means a partial
   write.

## 5e. Knowledge graph port — 2026-09-02

Ported from the original `load_knowledge.py` into `knowledge/`, and the
hand-authored YAML moved to `graph-node/knowledge/` where it belongs - it is
repo content, edited by hand, not instrument output.

**`DELTA_FROM` and `RELATIVE_TO` were removed from this loader**, per the §2
provenance rule. They are arithmetic on AdsParams and are emitted by
`data/drift.py`. Both being emitted twice would mean two loaders writing the
same edges under different run stamps, and whichever swept last deleting the
other's work. A test asserts their absence here.

### Attachment is computed against the intended data, not the stored data

`INSTANCE_OF` and `FIT_BY` are built from the data graph the same run is about
to write, so new nodes get their concepts in the rebuild that creates them.
This is not theoretical: the first data-only rebuild created 190 Pretreatment
nodes, and every one of them had no concept attached until the knowledge port
landed.

Ordering follows from that - data first, knowledge second, under one shared run
id. Knowledge edges attach to data nodes, so the nodes must exist first.

### Verified after the live run

| | |
|---|---|
| Run stamps | One value across every node in a scope |
| Vocabulary | Reproduces the stored graph exactly: 15/8/5/1/6 nodes, SUBTYPE_OF 8, PARAMETER_OF 6, IMPLEMENTS 12, USES_SPECIES 12 |
| Pretreatment concepts | 1,297 / 1,297 — the 190-node gap closed |
| AdsParams `FIT_BY` | 283 / 283 |
| Reference marking | Filename 141/141, AdsParams 138/138 |
| Relationship ownership | Every type in the graph claimed by exactly one scope; none unclaimed |
| Drift edges | Stamped once, by the data run |
| §11.2 invariant | 0 violations |

### The 11 uncovered ExpConditions are correct

Eleven `:ExpConditions` have no `INSTANCE_OF`. All eleven are aborted runs -
`exp_success=false`, `has_csv=false`, `gas=null`, `temp=null`. Rule E1 needs a
CO isotope in the gas, and an experiment that never ran recorded none. There is
no measurement to call an `adsorption_measurement`.

Real coverage is 283/283. Worth writing down because the naive check - concepts
per ExpConditions node - reads as a gap and is not one.

## 5f. The trigger — a scheduled rebuild, and no change to `orchestration/`

Decided 2026-09-02. Written up for the machine it runs on in
[SCHEDULING.md](SCHEDULING.md).

**There is no trigger.** A rebuild enumerates its sources and works out what
changed by comparing; it does not need telling that an experiment finished. So a
scheduled run suffices and `orchestration/` is untouched. The lab PC's
experiment code keeps knowing nothing about Neo4j, and no database problem can
reach a running experiment.

Two things have changed since this was decided and neither undoes it. The
sources are now the S3 bucket rather than the share (§5g), so the rebuild no
longer needs a mapped drive. And **it is still not scheduled anywhere** - see
§7.2. The argument for scheduling over triggering stands; the scheduling has not
happened.

Nick's instinct was to trigger from `finalize()` in `orchestration/adsorption.py`
— which is where the `_expParams.json` is copied to the share drive, so it is
the right place if a signal were needed. The reason not to: the last spectrum
fit can take up to six minutes after the run ends, so a trigger there has to be
coordinated with a queue it cannot see. Under a rebuild it does not matter. A
run that happens mid-fit loads the experiment without its AdsParams and the
next run adds it — running early is self-correcting, which is the same property
that made rebuild-over-append worth choosing in §5.

### Network requirements, learned the hard way

The first attempt on the lab PC failed three times, each further along:

| Symptom | Cause |
|---|---|
| `Timed out ... 7687` | Outbound 7687 blocked by the lab firewall |
| `certificate verify failed: self-signed certificate in chain` on :443 | The network terminates and re-signs TLS. Windows trusts the appliance's authority; Python ships its own CA bundle and does not |
| `Cannot connect to Bolt service ... (looks like HTTP)` on :443 | **Aura does not serve Bolt on 443.** 443 is the browser console and Query API; Bolt is 7687 only |

Two lasting consequences:

- `common/tls.py` verifies TLS against the OS trust store, so a machine behind
  an inspecting proxy still connects. Deliberately not `neo4j+ssc://`, which
  accepts *any* certificate and would defeat the point of verifying.
- **Outbound TCP 7687 is a hard requirement.** There is no alternative port, so
  the host must be a machine with both share-drive access and that egress. As
  of 2026-09-02 the lab PC has the first and not the second.

## 5g. Raw data on S3

### The decision

**Bulk data goes to AWS S3. The graph holds pointers, never payloads.**

The requirement is that a user can plot anything they choose, with the agent
turning a question into the right data. That rules out curating a subset: every
column has to be reachable. The volumes then make the store obvious:

| Data | Size | Where |
|---|---|---|
| Derived CSVs (seven kinds per experiment) | 519 MB measured | S3 |
| Pressure time series (`pressureData/`) | 644 MB measured | S3 |
| Raw spectra (`.0000`, 89-180 per experiment) | 1.2 GB measured - the pre-upload estimate of ~7 GB counted archived runs | S3 |
| Pointers and metadata | kilobytes | Graph |

An earlier plan also put a plottable time series in the graph. Dropped: it would
mean the same numbers in two representations, and it does not scale to the
spectra, which were never going in the graph. One store for bulk data, one for
structure. The cost is an S3 round trip per plot — a few hundred milliseconds —
which is a fair trade for not maintaining two truths.

AWS specifically, rather than the cheaper Cloudflare R2, because Nick wants
cloud experience that transfers. R2 is S3-compatible so the code would be nearly
identical, but IAM, policies and presigned URLs are the skills worth having and
they are AWS-native. At ~7 GB the cost is around $0.20/month.

### Built and run - 2026-09-05

`graph_node.backup` copied the share to the bucket. It needs no database: what
to upload is decided by comparing the share against a `ListBucket` listing, so
it ran from the lab PC while Bolt on 7687 was still blocked (§5f).

| Root | Files | Size |
|---|---|---|
| `OpusConvert_lgRfl` | 29,731 | 1.2 GB |
| `peakFit` | 2,857 | 519 MB |
| `pressureData` | 224 | 644 MB |
| `OpusReadParams` | 970 | 21 MB |
| **Total uploaded** | **33,782** | **2.4 GB** |
| Skipped - `_test` and `archive` directories | 36,742 | - |

**More files were excluded than uploaded.** That is the whole reason the total
came to 2.4 GB against an expected ~50 GB: the archived runs are the bulk of the
share. A bare count could not show that, so the plan now attributes every skipped
file to the directory that caused it and prints the largest first. Without it,
"36,742 skipped" is indistinguishable from a bug in the exclusion rule - the same
silence this project keeps designing against.

**The backup's scope is deliberately wider than the graph's.** Everything under
the four roots goes up, including the files the "Out of scope" table below keeps
out of *plotting*. The two scopes answer different questions: a backup you have
to curate is a backup you will regret, and modelling more of it later then needs
no re-upload. Only `_test` and `archive` directories are skipped, and only
because Nick asked for them to be.

### What the sources actually look like

Verified on the share, 2026-09-02. Counts exclude the `_test` folder.

```
X:\peakFit\<notebook folder>\
    <base>_expParams.json              already in the graph, not uploaded
    <base>_CarbonylPeakArea.csv        284    avg 332 KB, 92 MB total
    <base>_CarbonylPeakFitParams.csv   285
    <base>_CarbonylFitResidual.csv     284
    <base>_CarbonylFitBaseline.csv     284
    <base>_Params.csv                  240
    <base>_pressureLog.csv

X:\OpusConvert_lgRfl\
    <base>.0000 .. <base>.0129         two-column text, 1660 points, ~44 KB each
                                       89-180 per experiment, ~7 GB in total
X:\OpusReadParams\
    <base>.txt                         one line per spectrum: path, date, time, ...
```

**Out of scope for the graph and for plotting**, decided 2026-09-02. All of
these are still backed up to S3 - the table is about what gets modelled, not
what gets stored:

| Excluded | Why |
|---|---|
| `*_PeakHeight.csv` (860), `*_PeakHeight_binned.csv` (35) | Inputs to a forecasting ML model, not experiment results. Three per experiment, which is why the count does not match the others. |
| `<base>_README.md` (259) | Working notes. |
| `<base>_subIFGfiles.txt` | Working notes — which spectra pair into each delta. |
| `<base>_expParams.json` | Already loaded into the graph as nodes; no value as a blob. |

The spectra are **plain text**, not OPUS binary — `3997.75357884,-0.00052956`.
A browser can parse and plot them directly, so no conversion layer is needed.

A finding worth recording: the fit-parameter columns in the peak-area CSV
**vary per row** — `pfo-sec_k_a` has 83 distinct values across 147 rows. Each
row is the fit as of that time point, so the file carries the fit converging,
not a repeated final answer. `AdsParams` in the graph holds only the final row.
That is why the whole file is worth keeping rather than a reduction of it.

### Object key layout

**Keys mirror the share.** An object's key is its path relative to the share
root:

```
X:\peakFit\nn1120-3_pd_ceo2_004\x.csv  ->  peakFit/nn1120-3_pd_ceo2_004/x.csv
X:\OpusConvert_lgRfl\<folder>\a.0000   ->  OpusConvert_lgRfl/<folder>/a.0000
```

This replaces the original `peakfit/<base_name>/<filename>` scheme. The reasoning
changed with the scope rather than being overturned: that scheme deliberately
left the notebook folder out of the key so that reorganising a folder would not
change it. But that argument was about *pointers to files the graph models*.
Once this became a backup of the whole share, a backup should look like the thing
it backs up - and mirroring gives the files belonging to no single experiment
somewhere to live, which a `base_name` scheme has nowhere to put.

The cost is real and accepted: moving a folder on the share does produce a
re-upload and an orphan. Nothing deletes, so an orphan is wasted pennies, and
`base_name` stays the graph's join key regardless of where the object sits.

- **Filenames are kept verbatim** rather than normalised to `PeakArea.csv`. No
  mapping can then be wrong, and a downloaded file is self-describing.
- The spectra have numeric extensions (`.0000`) that no MIME table knows, so
  `Content-Type: text/plain` is set explicitly on upload; otherwise a browser
  downloads them instead of displaying them and nothing can plot them.
- **Size is the only comparison** for deciding what to re-upload. Every file is
  written once by an instrument and never edited, so a same-size file is the same
  file; hashing would mean reading gigabytes each run to learn nothing.

`index.json` is the one generated artifact: the file list for an experiment with
each spectrum's timestamp, parsed from `OpusReadParams/<base>.txt`. The dashboard
fetches it first, to know what exists before requesting any spectra. **Not built**
- it belongs to the graph-pointer work below, not to the backup.

### The pressure log

**It is its own instrument stream.** The transducers log continuously and
independently; nothing in this file comes from the IR pipeline that produces the
`Carbonyl*` CSVs. It shares only the experiment it belongs to and the
`base_name` convention that names it. That is why it is its own `DataFileType`
rather than another product of the peak fit - worth remembering when reading the
`kind` list on `RawFile`, where it sits beside five files that *are* peak-fit
output.

All logs live under `pressureData/`, one per run, and the loader reads nowhere
else. Not every run has one: of 34 runs with spectra on the sample checked, 31
had a log.

**Runs last days, and the graph holds only the start.** `ExpConditions` carries
the pressure from `_expParams.json`, which is the value at the beginning; the
log is a multi-day trace sampled about every 5 seconds. A setpoint and a trace
are not two representations of one thing, which is the whole reason this is
modelled separately.

**One consequence for plotting.** The three derived columns are recomputed from
`p_mfld` on every row, so they carry nothing it does not and can be downsampled
hard. `p_cell` cannot - it is the finest-grained column in the file.

Columns, units and roles are in `knowledge/data_file_types.yaml`, which is what
the graph is built from. They are not repeated here.

### Graph additions — the schema

Pointers and descriptions. No file contents enter the graph.

Two levels. Level 1 is the minimum that works and is needed regardless. Level 2
is what makes the agent able to answer a question rather than hand back a list
of files; it can follow later without changing Level 1.

#### Level 1 — where the files are (data scope)

```
(:Filename {base_name})
    -[:HAS_RAW_FILE]-->  (:RawFile)
                             key            S3 object key, the identity property
                             kind           "CarbonylPeakArea" | "CarbonylFitResidual"
                                            | "CarbonylPeakFitParams"
                                            | "CarbonylFitBaseline" | "Params"
                                            | "pressureLog"
                             base_name      the experiment it belongs to
                             bytes          file size, for the skip check
                             source_mtime   last-modified on the share, for the skip check
                             content_type   "text/csv"
                             uploaded_at    when this run put it there

    -[:HAS_SPECTRA]-->   (:SpectrumSeries)
                             base_name      identity property
                             prefix         "OpusConvert_lgRfl/<folder>/<base_name>."
                             index_key      "OpusConvert_lgRfl/<folder>/<base_name>.index.json"
                             count          number of spectra
                             bytes          total across the series
```

Roughly 1,400 `RawFile` nodes (five CSV kinds plus pressure logs across ~285
experiments) and ~300 `SpectrumSeries`, so about 1,700 new nodes. Aura Free
allows 200,000, which is far more headroom than this will use.

`prefix` is a *filename* prefix, not a folder. One notebook folder holds every
experiment for that sample - 5,729 spectra across 35 `base_name`s in the one
checked - so the spectra for a single run are selected by
`ListObjectsV2 Prefix=OpusConvert_lgRfl/<folder>/<base_name>.` rather than by
listing a directory. This is a direct cost of mirroring the share: the old
`spectra/<base_name>/` scheme gave each run its own clean folder. S3 prefixes
are plain string matches, so it works, but the graph must now store the notebook
folder instead of deriving the key from `base_name`.

**One node per spectrum *series*, not per spectrum.** 130 spectra x ~300
experiments would be 39,000 nodes to describe files nothing queries
individually — a spectrum is only ever fetched as part of a series. The series
node points at the prefix; `index.json` in S3 carries the per-file detail.

`kind` is doing real work here: it is what lets a query ask "which experiments
have a residual file" without opening anything.

#### Level 1, built - `data/pointers.py`

Built from a bucket listing, not from the share, so a pointer cannot promise a
file that was never uploaded - which is also why reconciling S3 against the
graph is not a job that needs doing. It opens no object, so `ListBucket` is
enough.

**A third scope, `POINTERS`, and the sweep is the reason.** A pointer run writes
no Material, Filename or Pretreatment, so if those labels were in its scope the
first run from a machine without the share would find every one of them
unstamped and delete the lot. Splitting the scope means each sweep can only
reach what its own loader wrote. It is the same provenance rule as everywhere
else: DATA from the share, KNOWLEDGE from YAML, POINTERS from the listing.
`HAS_RAW_FILE` and `HAS_SPECTRA` start on a `Filename` and end here; POINTERS
owns them because POINTERS creates them, exactly as KNOWLEDGE owns
`INSTANCE_OF`.

**`uploaded_at` replaces `source_mtime`.** A listing knows when S3 accepted an
object, not when the instrument wrote it. Recording `LastModified` under the
name `source_mtime` would be a different fact wearing the same label.

**`first_at` and `last_at` were dropped, `index_key` kept.** Build nothing the
agent does not need: the two timestamps would have cost 289 file reads a run to
store what no query asks for. `index_key` stays because a dashboard needs a file
list before it can request anything - it is still unbuilt, §7.4.

**Every object is either modelled or reported**, and a test pins it. A file that
is silently neither is how the two stores drift apart unnoticed. The report also
names what it skipped, which is how `OpusConvert_lgRfl/.../test.0000` surfaced:
test data that escaped the `_test` rule, because that rule only examines
directory names.

#### Level 2 — what is inside the files (knowledge scope)

```
(:RawFile)-[:OF_TYPE]-->(:DataFileType)
                            name         "CarbonylPeakArea"
                            description  "Fitted uptake per peak, refit at each
                                          time point as data accumulates"
                            row_grain    "one row per (peak, time point)"

(:DataFileType)-[:HAS_COLUMN]-->(:DataColumn)
                                    name    "pfo-sec_k_a_s-1"
                                    units   "s^-1"
                                    role    "fitted" | "measured" | "index" | "provenance"

(:DataColumn)-[:MEASURES]-->(:ModelParameter)      already exists, carries definitions
```

The `pressureLog` type can be authored now that a file has been read (see
"The pressure log, read" above). It is the first concrete instance of this level:

```
(:DataFileType {name: "pressureLog"})
    row_grain    "one row per 5-second instrument sample"
    description  "Manifold and cell pressure through the whole run, with
                  adsorption quantities recomputed at each sample"

    -[:HAS_COLUMN]--> (:DataColumn)
        id                          role        units      note
        pressureLog.timestamp       index       -          absolute, microsecond
        pressureLog.relative_time_s index       s          since run start
        pressureLog.p_mfld          measured    Torr       manifold; 65 levels
        pressureLog.p_cell          measured    Torr       cell; finest column
        pressureLog.amount_adsorbed derived     umol/g     f(p_mfld)
        pressureLog.apparent_conversion derived -          f(p_mfld)
        pressureLog.apparent_coverage   derived -          f(p_mfld)
```

Two things this surfaces about the Level 2 design:

- **`role` needs a fourth value, `derived`.** The vocabulary was
  `"fitted" | "measured" | "index" | "provenance"`, and none of them fit a column
  computed per row from another column in the same file. `fitted` would be wrong
  in a way that matters: nothing here was fitted.
- **`units` cannot be bluffed.** The file records none, and the two pressure
  columns only carry `Torr` because Nick said so. Inventing `bar` would have put
  a wrong number on every future plot axis, and nothing downstream would ever
  have contradicted it.
**Authored against every file, not a sample.** `knowledge/data_file_types.yaml`
is the source; it holds the columns, units, roles and definitions and is not
repeated here. Two findings from building it shaped the schema above.

**The column set is not fixed, even for the `long` files.** Reading the header
of all 287 `CarbonylPeakArea` objects found seven distinct shapes, from 22 to 45
columns: 21 columns appear in every file and 26 do not. So a `DataColumn`
carries `optional` and `present_in`. An agent that does not know a column may be
absent writes a plot that works for one experiment and fails on the next.

**Two of the five file types are matrices**, which `HAS_COLUMN` to an enumerated
list could not express. `CarbonylFitBaseline` and `CarbonylFitResidual` are one
row per wavenumber and one *column per spectrum*, named `delta<group>.<index>`,
and the set differs by experiment - 94, 141 and 276 columns seen. Enumerating
them would put thousands of per-experiment nodes into something meant to
describe formats. So `DataFileType` carries a `layout`, and a matrix type
describes its repeating columns by pattern:

```
(:DataFileType {name: "CarbonylFitResidual", layout: "matrix"})
    -[:HAS_COLUMN]-->  (:DataColumn {name: "Wavenumber (cm-1)", role: "index"})
    -[:HAS_COLUMN]-->  (:DataColumn {pattern: "delta<group>.<index>",
                                     matches: "^delta[0-9]+[.][0-9]+$",
                                     role: "fitted"})
```

One `DataColumn` either names a column or matches a family of them. Same label,
because both answer the same question - what is in this file - and a reader
should not have to know which kind it is getting.

**`role` gained a fourth value, `derived`:** a column computed per row from
another column in the same file. `pressureLog` has three. `fitted` would be
wrong in a way that matters, because nothing was fitted.

**Where each lives.** `RawFile` and `SpectrumSeries` are **data** — derived from
what is on the share. `DataFileType` and `DataColumn` are **knowledge** —
hand-authored units and meanings, sourced from a YAML file alongside
`concepts.yaml`. That follows §2's provenance rule, and `OF_TYPE` crosses the
boundary exactly as `INSTANCE_OF` already does, so the knowledge loader owns it.

This is also the first real piece of the "context graph" (§2): the join between
measured data and authored meaning.

#### Built 2026-09-10

`knowledge/data_file_types.yaml`, loaded by the knowledge loader. Against the
live graph: **5 `DataFileType`, 65 `DataColumn`, 3 `PeakGroup`**, with 65
`HAS_COLUMN`, 6 `MEASURES`, 6 `HAS_GROUP` and **1,373 `OF_TYPE`** - one for
every RawFile whose kind is described. Applies cleanly, no deletions.

**A third label the sketch above did not have: `PeakGroup`.** Without it Level 2
gets an agent as far as `CarbonylPeakArea.Cumulative_Peak_Area` and leaves it
there, because "the monomer band" is not a column - it is a set of `Peak_Name`
values, summed. Three nodes carry the sets and both isotope numberings, so a
question asked in 12CO terms finds the 13CO peaks the data actually holds.

**`role` gained `derived`** and `DataFileType` gained `layout`, as designed
above. A matrix type's repeating columns are one `DataColumn` carrying a
`pattern` and a `matches` regex rather than a name.

**The phases were reordered: data, pointers, knowledge.** `OF_TYPE` starts on a
`RawFile`, so the pointer graph has to exist before the knowledge graph can
describe what those files are. Knowledge now runs last and receives the labels
of everything the earlier phases wrote, since its edges reach into both.

Two things are reported rather than dropped, both being ways a join can go
quietly missing: a `measures` naming a parameter no model defines, and a
`RawFile` kind no `DataFileType` describes.

#### A second kinetic model - 2026-09-10

`model_parameters.yaml` holds a list of models rather than one. `pfo_secondary`
stays primary: `FIT_BY` attaches every `AdsParams` to it, because `AdsParams`
holds the pfo-sec columns and nothing else.

**`pfo` is one model, not two.** The `pfo_*`, `pre_pfo_*` and `post_pfo_*`
column families carry the same three quantities - `k`, `q_e`, `q_0` - because
they are the same equation fitted over different windows. Two `KineticModel`
nodes would mean six `ModelParameter`s behind three physical quantities, and
"the PFO rate constant" would have two answers. Which window a column came from
is a `segment` property on the column.

**`measures` is now `model.parameter`.** Parameter names collide across models -
both have `q_e` - so a bare name cannot say which is meant. A bare name still
resolves against the primary model, which is what every entry meant before a
second model existed, and `pfo.k_a` is reported rather than silently resolved:
`k_a` belongs to `pfo_secondary`.

That takes `MEASURES` from 6 to 15. The seven `pfo_*` columns and the six
pre/post columns can now be reached from the concept a question names.

#### Identity and ownership

| Label | Identity property | Scope |
|---|---|---|
| `RawFile` | `key` (the S3 object key — globally unique and stable) | DATA |
| `SpectrumSeries` | `base_name` | DATA |
| `DataFileType` | `name` | KNOWLEDGE |
| `DataColumn` | `id` (`<file type>.<column name>`, since column names repeat across types) | KNOWLEDGE |

New relationship types: `HAS_RAW_FILE` and `HAS_SPECTRA` in DATA; `OF_TYPE` and
`HAS_COLUMN` and `MEASURES` in KNOWLEDGE. Both scopes' declarations in
`common/ownership.py` need updating, and `ids.IDENTITY` gains four labels — the
existing coverage test fails until they do, which is the intended behaviour.

### S3 is the source of truth - 2026-09-08

The rebuild reads experiments from the bucket, not the share. `--from-share`
still works, for when S3 is unreachable or to compare the two.

This does **not** unblock the lab PC. The firewall blocks 7687, which is Aura,
and the rebuild still has to write to Aura. What changed is the *share*
dependency: a rebuild now needs 443 and 7687 and no mapped drive, so it can run
on any machine that can reach both - which today means the home PC. The firewall
request goes from blocking to merely desirable.

**How a deletion reaches the graph.** No new mechanism - mark and sweep did not
care where the sources came from:

1. Delete the objects in the S3 console.
2. The next rebuild lists the bucket, does not see them, does not stamp them.
3. The sweep deletes exactly what is not stamped.

`_expParams.json` is the object that creates a `Filename` node, so that is the
one whose removal retires an experiment; `DETACH DELETE` takes its
`Pretreatment`, `ExpConditions`, `AdsParams` and `RawFile` nodes with it.
Removing a file from `X:` on its own does nothing - the next backup simply does
not re-upload it and the object stays. That is one deliberate action instead of
two, and it keeps `DeleteObject` off every programmatic key.

**`data/store.py`** holds the two implementations. Both return the same
`relative` path shape, so the exclusion rules do not know which they are
looking at - and a test asserts the two enumerate identically, because a
difference between them would surface as a sweep rather than as an error.

**A guard the first run earned.** Pointed at S3 with the write-only uploader
key, all 299 sources failed `GetObject`. Nothing was built, so the plan offered
to **delete all 2,179 nodes** - and called itself applyable. The sweep's own
20% threshold would have aborted it, but the dry run had already printed a plan
worth applying, and that is the failure: a guard behind another guard is not the
same as one guard.

So `UNREADABLE_SOURCE_THRESHOLD` sits beside `MASS_DELETION_THRESHOLD`. A few
unreadable files stay a warning - a corrupt file is real and its experiment
should leave the graph. More than 20% is not a few bad files; it is the source
itself, and the rebuild refuses rather than treating unread data as deleted
data.

### Knowing what is already uploaded

Re-reading 7 GB every six hours to work out what changed is not an option.

The `RawFile` node stores `bytes` and `source_mtime`. The uploader stats each
source file — cheap — and skips anything whose size and mtime match the node.
Only a mismatch triggers a read and an upload. Raw spectra never change once
written, so in steady state almost nothing is read.

This is where the content-hash idea raised on 2026-08-29 finally earns its
place. It was correctly deferred then, being orthogonal to the rebuild; here it
is load-bearing. A hash is the tiebreaker when size and mtime are ambiguous, and
it is what would catch a file rewritten to an identical size.

Neither IAM user has `DeleteObject`. Nothing in this design deletes, and the
sweep does not extend to S3 — a `RawFile` node can be swept while the object it
pointed at stays. Orphaned objects are a later problem, and a cheap one.

### Access is gated, via presigned URLs

```
graph-node (lab PC)  --PutObject-->  S3 bucket (private, no public access)
                     --writes key + metadata into the graph

browser --> cataverse.ai API route (behind Vercel Authentication)
              --> generates a short-lived presigned URL
        --> browser fetches the object directly from S3
```

The bucket is never public. The dashboard authorises the request and returns a
URL that expires in minutes. Files stream from S3 rather than through Vercel, so
there is no function timeout or bandwidth cost on a 130-file spectrum fetch.

Two IAM identities, least privilege:

| Identity | Permitted | Where its key lives |
|---|---|---|
| `cataverse-uploader` | `PutObject`, `ListBucket` | Lab PC, `graph-node/.env` |
| `cataverse-reader` | `GetObject` | Vercel, dashboard environment |

`ListBucket` on the uploader so it can verify what is present; `GetObject`
withheld from it so a leaked lab-PC key cannot read the data back.

Useful accident: **S3 is port 443, which the lab firewall already allows** (§5f).
Uploads work from the lab PC today, even while Bolt on 7687 is blocked.

### Housekeeping

- One orphaned object to delete by hand in the S3 console:
  `peakFit/nn1120-3_pd_ceo2_004/20260522_210041_pd_ceo2_004-024_pressureLog.csv`.
  The file moved on the share, so the backup re-uploaded it under its new key
  and neither IAM user can remove the old one.

### Deferred

- **gzip on upload.** The spectra are text and compress 3-4x, taking the
  measured 1.2 GB to roughly 350 MB. `Content-Encoding: gzip` makes browsers
  decompress transparently. Not
  in v1: it complicates hashing, and the storage saving is about ten cents a
  month. Worth revisiting if transfer time becomes noticeable.
- **Reconciling S3 against the graph.** The graph could claim a file is uploaded
  when the object is missing. A periodic `ListBucket` comparison would catch it.
  Not built until it happens.

### Open

- Whether Level 2 is authored now, while the file formats are fresh, or when
  the agent work starts. Level 1 does not depend on it.

## 6. Decisions made

- **2026-08-29 — graph-node is its own package in the monorepo.** Reasoning in §4.
- **2026-08-29 — Data and knowledge graphs stay separate, split by provenance.**
  Enforced by per-loader label ownership plus a test, not by convention alone. §2.
- **2026-08-29 — DELTA_FROM and RELATIVE_TO belong to the data graph** and move out
  of `load_knowledge.py`. They are arithmetic on measurements. §2.
- **2026-08-29 — `original/` is vendored unmodified** rather than refactored in
  place, so there is a known-good reference to check the rewrite against.
- **2026-09-05 — S3 object keys mirror the share drive.** The
  `base_name` scheme was right for pointers and wrong for a backup. §5g.
- **2026-09-05 — The backup's scope is the whole share,** wider than
  what the graph models. Curating a backup is how you regret it later. §5g.
- **2026-09-05 — `pressureLog` gets its own `DataFileType`.** The graph
  holds the starting setpoint; the log holds the trace across days. §5g.
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

Ordered by what actually blocks something. Each says what is missing, what it
would take, and when it stops being deferrable - so the choice to leave it is a
choice rather than an oversight.

### 7.1 Presigned URLs - the only item that blocks work

**Missing.** The bucket is private with no public access, deliberately (§5g).
Nothing outside AWS can read an object. The graph can resolve a question all the
way to `peakFit/.../x_CarbonylPeakArea.csv` and column `pfo-sec_k_a_s-1`, and
then nothing can open the file.

**What it takes.** An API route that takes a key, checks the caller is
authorised, and returns a short-lived signed URL - `generate_presigned_url`,
minutes not hours. The `cataverse-reader` identity already exists for exactly
this. An hour or so, most of it deciding where the route lives (`dashboard-node`
serves the browser; the agent may want its own path).

**When it stops being deferrable.** The moment anything needs a number rather
than a name. An agent answering "which experiments have a residual file" needs
nothing; one answering "plot k_a over time" needs this first.

### 7.2 Scheduling the rebuild - degrades quietly

**Missing.** The backup runs nightly on the lab PC. The rebuild runs nowhere on
a schedule: the lab PC still needs outbound 7687, and the home PC is not
reliably on. So the graph is a snapshot from whenever it was last run by hand.

**Three ways out**, none blocked on code: get 7687 opened; schedule it on a
machine that is always on and can reach Aura; or keep running it by hand and
accept the drift.

**Why this one is worth a reminder.** It is the only item that gets worse while
nobody is looking, and it fails silently - a month-old graph looks exactly like
a graph with no new experiments. See 7.3.

### 7.3 Noticing when the scheduled task stops

**Missing, no design.** Every run writes a timestamped log to `graph-node\logs\`
and Task Scheduler records a Last Run Result. Nothing reads either. A job that
dies is indistinguishable from a quiet week.

Only matters once 7.2 exists. The cheap version is a habit rather than code:
when cataverse.ai does not show an experiment you know finished, read the newest
file in `logs\` before suspecting anything else.

### 7.4 `index.json` for spectrum series

**Missing.** `SpectrumSeries.index_key` names an object that does not exist. It
would hold the per-spectrum timestamps parsed from `OpusReadParams/<base>.txt`,
so a browser can know what a series contains before fetching 130 spectra.

**What it takes.** Parse 289 `.txt` files, write 289 small JSON objects, one
extra phase in the rebuild. An hour or two.

**Workable substitute meanwhile:** `ListObjectsV2` with the series prefix
returns the file list, just without timestamps.

### 7.5 Hashing, as a `verify` capability

Deferred by Nick 2026-09-02 and still sensible. Storing a source hash on each
node would answer "is the graph consistent with its sources?" without
rebuilding. Cheaper now than it was: the bucket listing returns an `ETag`, which
is an MD5 for single-part uploads, so the hash no longer has to be computed.

### 7.6 Small and genuinely optional

- **One orphaned S3 object** to delete by hand in the console:
  `peakFit/nn1120-3_pd_ceo2_004/20260522_210041_pd_ceo2_004-024_pressureLog.csv`.
  Its file moved on the share, and no IAM identity here can delete.
- **`pfo`'s `q_0`** is marked `fitted: false` by analogy with `pfo_secondary`.
  Unconfirmed.
- **`ka`/`kd`/`Keq` columns** still exist in 14 files. Recorded under
  `ignored_columns` in `data_file_types.yaml`; nothing needs doing unless the
  files are cleaned.
- **`Cumulative_PdCO_mol`** is calibrated from isotopic exchange "with large
  error bars" - worth knowing before anyone plots it as absolute truth.

## 8. Non-goals for now

- The context graph (§2). Nick has flagged it as coming; do not design for it yet.
- Literature ingestion into the knowledge graph.
- Reshaping the graph based on agent performance.
- Backfilling pre-orchestration experiments from `.md` READMEs — `md_to_json.py`
  did that once and is not part of the ongoing pipeline.
