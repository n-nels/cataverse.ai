# graph-node

Rebuilds the cataverse Neo4j graph from experiment output.

Reads the per-experiment JSON that `orchestration/` writes and the fit CSVs that
`ir-spectro-node` writes, both off the `X:\` share drive, plus the hand-authored
knowledge YAML in this package. Computes the whole graph those sources imply,
diffs it against what is stored, and writes the difference.

See [spec.md](spec.md) for the design, what has been verified, and what is open.

## Running it

```
uv run python -m graph_node.cli --source-root "X:\peakFit"
```

Dry run by default — it reports what would change and writes nothing. Add
`--apply` to write, and read the delete column before you do.

Needs a `.env` next to `.env.example`. It is gitignored, so a fresh clone or a
scheduled job needs one written. Requires the share drive to be mounted.

The installed `graph-node` console script is blocked by Application Control on
some Windows machines, hence `python -m`.

## How a rebuild works

Every rebuild recomputes the whole graph rather than appending the newest
experiment. Kinetic chains and reference drift are not computable from one
experiment in isolation, and a rebuild self-heals from a failed write or a
corrected source file — see spec.md §5.

Nodes and relationships are stamped with the run's id as they are written, and
anything left carrying an older stamp is swept afterwards. Each loader declares
which labels and relationship types it may touch, which is what stops the data
rebuild deleting knowledge nodes it never wrote.

## Layout

```
src/graph_node/
  common/     connection, ids, ownership, the writer, mark-and-sweep
  data/       instrument output -> Material, Filename, Pretreatment,
              ExpConditions, AdsParams, KineticChain, and reference drift
  knowledge/  YAML -> concepts, species, functions, kinetic model, and the
              INSTANCE_OF / FIT_BY edges attaching them to data
knowledge/    the hand-authored YAML itself
original/     the original pipeline's instruction documents, kept as the
              historical record
tests/        including real experiment files as fixtures
```
