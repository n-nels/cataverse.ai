# original/ — the pipeline as transferred, unmodified

These are the scripts and specs that built the graph currently living in Aura,
copied verbatim from `X:\graphDB\` on 2026-08-29. They were developed on the work
PC outside version control; this folder is the first time they have been tracked.

**Nothing here has been refactored.** They are kept as-is for three reasons:

1. They are the de-facto specification. Every decision about how an experiment
   becomes nodes is encoded here, and several were resolved through review
   (see the `## 9. Open Items` sections, which record the answers).
2. They are the reference for correctness. Whatever replaces them must produce
   the same graph from the same inputs.
3. They still run. Until the new pipeline works end to end, this is how the
   graph gets rebuilt.

Not copied over, per Nick — superseded or one-shot:

| File | Why not |
|---|---|
| `md_to_json.py` | Stage A, `.md` README to JSON. `orchestration/` now writes that JSON natively, so this only matters for pre-orchestration backfill. |
| `fix_is_new.py` | One-shot correction of 6 JSON files. |
| `backfill_is_new_sample.py` | One-shot backfill into old READMEs. |
| `review/` | Generated output, currently 0 records. |
| `exports/` | Generated output, 4 MB, reproducible by a rebuild. |
