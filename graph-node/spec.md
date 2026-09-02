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

## 3. Current state (as of 2026-09-02)

The pipeline is complete except for its trigger.

| Piece | Where | State |
|---|---|---|
| Per-experiment JSON (`material`, `filename_flags`, `pretreatments`, `exp_conditions`) | `orchestration/src/experiments/session.py` | **Done**, and unchanged by this work. `build_exp_params_payload()` assembles it; `_persist_exp_params_json()` writes it beside the experiment. It is the schema of record — see §5a. |
| Fit results CSV (`*_CarbonylPeakArea.csv`) | `ir-spectro-node`, analysis + file I/O | **Done**, unchanged. Source of every AdsParams property. |
| Reading both | `data/source.py`, `data/fits.py` | **Done.** Tested against real files from both ends of the dataset. |
| Assembling the data graph | `data/build.py`, `data/drift.py` | **Done.** Nodes, edges, kinetic chains, and the §11 reference-drift layer. |
| Assembling the knowledge graph | `knowledge/source.py`, `knowledge/build.py` | **Done 2026-09-02.** Vocabulary from YAML plus the attachment to data — see §5e. |
| Deterministic node ids | `common/ids.py` | **Done.** Carried over unchanged from the original pipeline, so a rebuild matches the nodes already stored rather than duplicating them. |
| Dry run | `data/plan.py` | **Done.** Diffs the intended graph against the database, per scope, writing nothing. |
| Writing to Neo4j | `common/writer.py`, `data/apply.py` | **Done 2026-09-02.** MERGE on the per-label identity property, stamp, then sweep. Replaced the manual Aura CSV import. |
| Running it unattended | Windows Task Scheduler, `scripts/rebuild.ps1` | **Designed, not deployed.** No trigger and no change to `orchestration/` — see §5f. Blocked on the lab network allowing outbound 7687. |

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
experiments, zero `_test` files, all 295 Filenames are `exp_type: adsorption`.
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

## 5d. First live rebuild — 2026-09-02

Ran twice. Both runs wrote every data node and deleted nothing.

| | Before | After |
|---|---|---|
| Pretreatment | 1,107 | 1,297 |
| Filename | 249 | 295 |
| ExpConditions | 238 | 294 |
| AdsParams | 238 | 283 |
| KineticChain | 6 | 7 |
| Material | 2 | 3 |
| **Total data nodes** | 1,840 | **2,179** |

Everything §5a and §5b predicted happened: `pressure_meas_g1`/`g2` gone and
`mfld`/`cell` in their place, the hollow Pretreatment filled in, `is_reference`
corrected, four months of missing experiments loaded, the third material
appearing, and six uniqueness constraints created. Knowledge nodes were
untouched — 35 before, 35 after — so the ownership boundary held under a real
write.

**The second run existed because the first had a bug**, and that is the part
worth remembering. `_as_float` coerced `step_index` to `1.0`, leaving it
disagreeing with the `order` property on its own `HAS_STEP` edge and making the
dashboard render "step 1.0". Nothing broke functionally; Cypher compares across
numeric types. The fix was a one-line change in `source.py` plus a re-run — the
database was never edited by hand. That is the whole argument for rebuild over
append, exercised for real on the first day.

### Standing procedure

1. Dry run first, every time. Read the delete column.
2. `--source-root` must cover the whole of `X:\peakFit`. A subset means the
   sweep deletes everything the subset does not account for. The 20% guard is a
   backstop for that mistake, not a substitute for reading the plan.
3. Verify after. The single most useful check is that `_run` has exactly one
   distinct value covering every data node - two values means a partial write.

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
| Run stamps | One value across 2,179 data and 35 knowledge nodes |
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

**There is no trigger.** A rebuild reads the share drive and works out what
changed by comparing; it does not need telling that an experiment finished. So
Windows Task Scheduler runs it every six hours and `orchestration/` is
untouched. The lab PC's experiment code keeps knowing nothing about Neo4j, and
no database problem can reach a running experiment.

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

## 5g. Raw data on S3 — design (2026-09-02, not built)

### The decision

**Bulk data goes to AWS S3. The graph holds pointers, never payloads.**

The requirement is that a user can plot anything they choose, with the agent
turning a question into the right data. That rules out curating a subset: every
column has to be reachable. The volumes then make the store obvious:

| Data | Size | Where |
|---|---|---|
| Derived CSVs (seven kinds per experiment, plus pressure logs) | ~92 MB for the peak areas alone; more across all kinds | S3 |
| Raw spectra (`.dpt`, 89–180 per experiment) | **~7 GB** | S3 |
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

### What the sources actually look like

Verified on the share, 2026-09-02:

```
peakFit/<notebook folder>/
    <base>_expParams.json              -> already in the graph
    <base>_CarbonylPeakArea.csv        284 files, 92 MB, avg 332 KB
    <base>_CarbonylPeakFitParams.csv   285
    <base>_CarbonylFitResidual.csv     284
    <base>_CarbonylFitBaseline.csv     284
    <base>_PeakHeight.csv              860
    <base>_Params.csv                  240
    <base>_PeakHeight_binned.csv        35
    <base>_pressureLog.csv
    <base>_README.md                   259

<opus root>/OpusConvert_lgRfl/
    <base>.0000 .. <base>.0129         two-column text, 1660 points, ~44 KB each
<opus root>/OpusReadParams/
    <base>.txt                         one line per spectrum: path, date, time, ...
    <base>_subIFGfiles.txt             which pairs form each delta
```

The spectra are **plain text**, not OPUS binary — `3997.75357884,-0.00052956`.
A browser can parse and plot them directly, so no conversion layer is needed.

A finding worth recording: the fit-parameter columns in the peak-area CSV
**vary per row** — `pfo-sec_k_a` has 83 distinct values across 147 rows. Each
row is the fit as of that time point, so the file carries the fit converging,
not a repeated final answer. `AdsParams` in the graph holds only the final row.
That is why the whole file is worth keeping rather than a reduction of it.

### Object key layout

```
peakfit/<base_name>/<original filename>
spectra/<base_name>/<original filename>
spectra/<base_name>/index.json          (generated, see below)
```

Prefix by source root, then `base_name`, then the source filename verbatim.

- `base_name` is already the `Filename` identity key, so it is unique and
  stable, and it sorts chronologically for browsing.
- The **notebook folder is deliberately not in the key.** It is derivable from
  the graph, and if a file were ever reorganised into a different folder the key
  would change — producing both a re-upload and an orphan.
- **Filenames are kept verbatim** rather than normalised to `PeakArea.csv`. No
  mapping can then be wrong, and a downloaded file is self-describing. The
  `base_name` repeating inside the prefix costs nothing.
- The spectra have numeric extensions (`.0000`) and no MIME type, so
  `Content-Type: text/plain` is set explicitly on upload; otherwise a browser
  downloads them instead of reading them.

`index.json` is the one generated artifact: the file list for an experiment with
each spectrum's timestamp, parsed from `OpusReadParams/<base>.txt`. The dashboard
fetches it first, to know what exists before requesting any spectra.

### Graph additions

Pointers only. Two new labels, both in the DATA scope:

```
(:RawFile {key, kind, base_name, bytes, source_mtime, content_type, uploaded_at})
(:SpectrumSeries {base_name, prefix, index_key, count, first_at, last_at})

(Filename)-[:HAS_RAW_FILE]->(RawFile)
(Filename)-[:HAS_SPECTRA]->(SpectrumSeries)
```

One `RawFile` per derived file — roughly 2,300 nodes. One `SpectrumSeries` per
experiment rather than one node per spectrum: at 130 spectra × ~300 experiments
that would be 39,000 nodes for no benefit, since nothing queries an individual
spectrum on its own. About 2,600 new nodes in total, against Aura Free's 200,000
limit and the 2,214 in use today.

`kind` is what makes the agent able to answer at all — it can see that a
`CarbonylFitResidual` exists for an experiment without guessing filenames.

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

### Deferred

- **gzip on upload.** The spectra are text and compress 3–4×, taking ~7 GB to
  ~2 GB. `Content-Encoding: gzip` makes browsers decompress transparently. Not
  in v1: it complicates hashing, and the storage saving is about ten cents a
  month. Worth revisiting if transfer time becomes noticeable.
- **Reconciling S3 against the graph.** The graph could claim a file is uploaded
  when the object is missing. A periodic `ListBucket` comparison would catch it.
  Not built until it happens.

### Open

- Whether the `README.md` files and `subIFGfiles.txt` are data worth uploading,
  or working notes that are not.
- `PeakHeight.csv` has 860 files against 284 for the other kinds — roughly three
  per experiment, suggesting a naming variant this design has not accounted for.
- Where the Opus roots live on the share. They were inspected from a flash-drive
  copy; their path under `X:\` is not yet known.

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

1. **Getting the scheduled rebuild running.** Designed and documented (§5f,
   SCHEDULING.md); blocked on the lab network allowing outbound 7687.
2. **Noticing if the scheduled task stops.** A job that dies quietly looks
   exactly like a graph with no new experiments. Every run logs, but nothing
   watches the logs. No design yet.
3. ~~Loading the raw data.~~ **Designed 2026-09-02 — see §5g.** Everything
   bulk goes to AWS S3; the graph gains pointers only. Not built: waiting on the
   AWS account and bucket.
4. **Hashing, as a `verify` capability.** Orthogonal to the rebuild (§5), still
   worth having: storing a source hash on each node would let "is the graph
   consistent with its sources?" be answered without rebuilding. Computed in
   `graph-node`, not `orchestration/`, which cannot see the fit CSVs. Deferred
   by Nick, 2026-09-02.

## 8. Non-goals for now

- The context graph (§2). Nick has flagged it as coming; do not design for it yet.
- Literature ingestion into the knowledge graph.
- Reshaping the graph based on agent performance.
- Backfilling pre-orchestration experiments from `.md` READMEs — `md_to_json.py`
  did that once and is not part of the ongoing pipeline.
