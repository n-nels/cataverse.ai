# original/ — the historical record

Two specification documents from the pipeline that built the first version of
this graph, written on the work PC outside version control and copied here
verbatim on 2026-08-29.

They are kept because they are the only place the original reasoning exists in
full. Several decisions in them were argued out carefully and would have been
re-derived worse from scratch — the reference-drift algorithm in
`knowledge_graph_instructions.txt` §11 especially, where the ordering rule
(emit the edge, *then* advance the reference pointer) is the difference between
a connected subchain of anchors and every reference pointing at itself.

**Nothing here runs, and nothing here is authoritative.** Where these documents
and the code disagree, the code is right:

- Field names are stale by the documents' own admission — §9c notes that §4.1
  and §4.3 still show `pd_loading` and `ceo2_sa`, renamed long ago to
  `metal_loading` and `support_sa`. `orchestration/session.py` is the schema of
  record; see spec.md §5a.
- The pressure properties are `pressure_meas_mfld` / `pressure_meas_cell`, not
  the `g1` / `g2` these documents describe.
- "Expected count: 2" for materials is wrong; there are three.
- Loading is over Bolt with mark-and-sweep, not CSV import through the Aura UI.

Every rule in both files was audited on 2026-08-29 and classified as kept,
adapted, or dropped. That audit is in **spec.md §5c**, and is the thing to read
first — it says which parts of these documents still hold.

## What was removed

Deleted 2026-09-02, once every rule had been built or consciously dropped:

| Removed | Where it went |
|---|---|
| `scripts/load_graph.py` | Ported to `data/source.py`, `data/fits.py`, `data/build.py`, `data/drift.py`, `common/ids.py` |
| `scripts/load_knowledge.py` | Ported to `knowledge/source.py`, `knowledge/build.py` — minus `DELTA_FROM` and `RELATIVE_TO`, which belong to the data graph |
| `knowledge/*.yaml` | Moved to `graph-node/knowledge/`, where they are now edited |

Never copied over, as superseded or one-shot: `md_to_json.py` (Stage A;
`session.py` writes the JSON natively now), `fix_is_new.py`,
`backfill_is_new_sample.py`, `review/`, and `exports/` (generated, ~4 MB,
reproducible by a rebuild).
