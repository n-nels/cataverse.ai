# graph-node

Builds the cataverse Neo4j graph from experiment output and loads it into Aura.

Today this is a manual, offline process: `original/scripts/load_graph.py` reads
JSON + CSV off the `X:\` share drive and writes `exports/nodes.csv` and
`exports/relationships.csv`, which a human then imports through the Aura UI. The
goal of this package is to close that loop so the graph updates itself after an
experiment finishes.

See [spec.md](spec.md) for the design, the current state, and what is still open.

## Layout

```
src/graph_node/
  common/     Bolt connection, MERGE helpers, deterministic ID builders
  data/       Data graph — what the instruments measured, and derivatives of it
  knowledge/  Knowledge graph — hand-authored concepts, species, functions
original/     The pipeline as transferred from X:\graphDB, unmodified
```

`src/` is a skeleton. The working code is still in `original/`.
