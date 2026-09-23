# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                          # install deps (uv is the package manager; Python >=3.12)

python scripts\run_server.py     # OPUS ZMQ instrument server (production entry point)
python scripts\run_norhoff.py    # Norhof LN2 pump control loop (separate process)
python scripts\run_analysis.py   # batch/offline analysis — see note below
python scripts\run_kinetics_classification.py  # batch classification CLI — see note below
python scripts\run_baseline_experiment.py      # baseline experiment CLI — see note below

uvx ruff check .                 # lint (ruff is not a declared dependency; run via uvx)
uvx ruff format .
```

There is no test suite and no pytest dependency. Validation is done by running a
module against real data on disk and diffing the CSV output against a prior run.
Most modules carry an `if __name__ == "__main__":` block with an editable
`file_directory` / `name` constant at the top — that block, not CLI arguments, is
how batch work is run (`scripts/run_analysis.py`, `src/analysis/main.py`).
To run a single file through the pipeline, edit those constants rather than
adding argparse.

**Two CLIs are the exceptions.** The first is batch classification:
`scripts/run_kinetics_classification.py`
(wrapping `src/utils/kinetics/classify_cli.py`) is an argparse CLI, added because the
classification algorithm itself is under active iteration (see
`src/utils/kinetics/classification.py` and `docs/spec.md`) and needs a
`--classifier` flag to A/B candidate detectors and run the ground-truth check
(`--validate`) without editing source. `--classifier` defaults to `combined`
(`classify_trajectory_combined`, 285/288 per `docs/spec.md` §6.2) — the plain
original detector is still available as `--classifier default` (264/288) for
comparison. Batch *fitting* (`fit_file`/`fit_folder`/`fit_folder_by_sum_models`)
is **not** covered by this CLI and still follows the edit-constants convention,
via `src/utils/kinetics/api.py`'s own `__main__` block.

The second is **baseline experiments**: `scripts/run_baseline_experiment.py`
(wrapping `src/utils/ir_fitting/baseline_cli.py`), for the same reason — the
baseline recipe is under active iteration and needs A/B flags. With no arguments
it runs the default recipe on the eight judged files. That is §14.22's form with upper
anchors `2240 2006 1955 1955 1955` and lower anchors `1955 1800 1820`, under
`--run-name default`. `src/utils/ir_fitting/spec.md` §16.5 gives the flags that
reproduce §14.22 itself. The flags are the inputs §14 actually introduced — `--window`,
`--anchors`, `--lower-split`, `--lower-anchors` and the two anchor-guard
thresholds — plus `--with-twin`, which adds the uncut twin that makes
`upper_max_abs_diff` a real check rather than `NOT CHECKED`. The full inventory,
including why the `std_distribution` settings are deliberately *not* a flag, is
spec.md §16. Batch **fitting** in `ir_fitting` is not covered and still follows
edit-constants, via that package's `api.py` `__main__`.

`src/utils/kinetics/` is the tidier programmatic wrapper over the batch writer:
`from src.utils.kinetics import fit_file, fit_folder, classify_file`. It defaults
to writing into a `_test` output subfolder — keep that default when
experimenting; never overwrite source data in place.

## Architecture

Two halves that meet at a directory on disk, not at a function call.

**Instrument half (`src/instrument/`)** — a ZMQ REP server (`server.py`) polls for
JSON commands from the cataverse.ai orchestrator. `acquisition.py::opus_acquire`
runs one measurement, then `subtract_ifg_files` subtracts every interferogram
pair at delta steps 1..10 and writes each subtracted IFG to
`utility.subtract_ifg.sub_ifg_output`. Each new subtracted-IFG file is handed to
`dispatch.py::dispatch_analysis`, which enqueues it onto per-type single-threaded
daemon queues (`spectral_fit`, `peak_heights`, `iso_xchg`) so acquisition never
blocks on fitting. `client.py` is the only module that talks the OPUS named pipe
(`\.\pipe\OPUS`); commands are raw strings whose exact text matters.

Server state is a module-level singleton (`state.py::OpusState`, reached via
`get_state()` / `ensure_paths()` / `ensure_queues()`), not passed as parameters.
`paths.py::define_paths` must run after `foldername`/`filename` are set on the
state and before any path is used; it also `mkdir`s every output directory.

**Analysis half (`src/analysis/`)** — `main.py::DataAnalysisRunner` orchestrates
one subIFG file: resolve paths → load subIFG/FSD/log/exp-params (`io.py`) →
baseline + multi-peak Voigt fit (`spectral_fitting.py`) → **compute phase** of
pure DataFrame builders → **I/O phase** of `save_*` calls (`output.py`) →
kinetics (`kinetics_fitting.py`). That compute/I/O split in `run_spectral_fit` is
deliberate; keep new work on the correct side of it.

Files carry state between steps. `*_CarbonylPeakFitParams.csv` is appended to on
every fit and re-read as the fit history; cumulative peak areas are recomputed
from that whole history, and `*_CarbonylPeakArea.csv` is re-read to carry prior
kinetics results forward. Deleting or reformatting those CSVs mid-run corrupts
the run.

**Real-time vs. batch kinetics.** `append_fit_results(..., latest_only=True)` is
the live path: only the newest time point per peak group is fitted and earlier
kinetics rows are merged in from the saved CSV. `latest_only=False` (via
`run_kinetics_fit`) refits everything from scratch. Both must produce the same
column set.

**Two kinetics implementations exist — check which one you are editing.**
`src/analysis/kinetics_fitting.py` is the live/real-time implementation used by
the server pipeline. `src/utils/kinetics/{models,classification,utils,writer}.py`
is a parallel class-based (`MODELS` / `CLASSIFIER` / `WRITER`, wired together at
the bottom of `writer.py`) implementation used for offline reprocessing —
`models.py` holds the PFO/secondary-PFO model strategies, `classification.py`
holds `KineticClassification` (the default detector plus several in-progress
detection candidates — see below), `utils.py` holds dataframe/CSV helpers, and
`writer.py` holds `KineticWriter`, the row-preparation/writing orchestration,
plus the module-level singletons. This offline copy duplicates the models, the
classification thresholds (`FLAT_WINDOW_S`, `MIN_FLAT_START_S`, `EPS_FLAT_DEFAULT`,
`RISE_DELTA_DEFAULT`) and the parameter-name lists found in
`kinetics_fitting.py`. A change to model or classification behavior usually has
to land in both, or the two paths silently disagree. Porting a validated
offline classifier into the live path is tracked as separate, future,
out-of-scope work in `docs/spec.md` §8 — do not do it as a side effect of
editing one side.

**Models.** Cluster peaks get PFO `q(t) = q_0 + q_e(1 - exp(-k t))`; monomer peaks
get a coupled-ODE secondary PFO solved with `solve_ivp`. Peak membership is not
hardcoded — `_get_peak_names` reads `cluster_peaks_base` / `monomer_peaks_base`
from `config/analysis.yaml` and applies the isotope shift. `monomer_sum` and
`cluster_sum` rows are synthesized before fitting and are grouped by `Peak_Name`
only, aggregating across all `Delta_Group` values.

**Classification** (`classify_trajectory`) labels a trajectory `continuous` or
`discontinuous` by finding a flat window followed by a sustained rise; a
discontinuous trajectory also gets `pre_`/`post_` breakpoint PFO fits around
`growth_onset_s`. The offline `KineticClassification` (`src/utils/kinetics/classification.py`)
additionally carries `classify_trajectory_sustained_rise`, `classify_trajectory_drawdown`,
and `classify_trajectory_combined` — active detection candidates being scored
against `ground_truth.json`, not dead alternatives; select one via
`scripts\run_kinetics_classification.py --classifier {sustained_rise,drawdown,combined}`.

### Configuration

All paths, filename suffixes, peak lists, Voigt parameter rules, baseline
settings and isotope shifts live in `config/paths.yaml` and
`config/analysis.yaml`, read through `src/core/config.py` by dotted key
(`get_setting`, `get_analysis_setting`, `get_path`). Both configs are cached in
module globals on first read. Do not hardcode a path, a peak wavenumber, or a
fit bound that belongs in YAML.

## Constraints carried over from `.opencode/foundations.md`

- **Parity-safe control flow.** Do not add early returns that let the code skip
  output generation where the legacy path would have continued — that silently
  drops `*_Carbonyl*` files.
- **Output stability.** Output filenames, CSV schemas, and OPUS command strings
  are treated as a public contract; changing one is a breaking change.
- **Secondary PFO model, current iteration:** `q_0` is fixed to the first observed
  point (not fitted); `k_a > k_p` is enforced by `k_p = k_a * k_p_ratio` with
  `k_p_ratio ∈ (1e-6, 0.999999)`; `q_inf` is fit freely (no `q_inf < q_e`
  constraint) and capped at `2 * q_e_upper`; `p` is clamped to `>= 0` inside the
  ODE RHS; solver is `RK45, rtol=1e-8` with a 0.1 s timeout; optimizer is
  single-start `L-BFGS-B` (multistart disabled).
- Peak-name strings derived from numeric centers must match the `Peak_Name`
  column formatting exactly — do not truncate decimals.
- Prototype scripts operate on one explicitly named dataset folder until
  reviewed, and write to a `_test` subfolder before touching source data.

## Environment notes

- Windows-only in practice: the OPUS named pipe, `C:\Data\...` and the `X:\` share
  paths in `config/paths.yaml`. Use raw strings for Windows paths.
- The ZMQ server binds a fixed host/port from `opus.server` — it is the lab
  machine's address, not localhost.
- `scripts/run_server.py` forces `MPLBACKEND=Agg`; plotting from the server path
  must stay non-interactive.

## Git

Commits are restricted to the `feature/nucleation-classifier` branch by a
`PreToolUse` hook in `.claude/settings.local.json`. It inspects every Bash call,
and denies the tool call when the command contains `git commit` while
`git branch --show-current` reports anything else (a detached HEAD is also
denied). This is deliberate enforcement, not an accident — if it blocks
something legitimate, change the branch name in that file rather than deleting
the hook. `.claude/settings.json` separately denies `git push` and `pip install`.

Verify the branch with `git branch --show-current` immediately before committing.
The git status supplied at session start is a snapshot and does not update as the
session goes on.

## Graphify

This repo has a graphify knowledge graph in `graphify-out/` (gitignored, but
present locally — `graph.json`, `GRAPH_REPORT.md`, `graph.html`, `wiki/` when
built). The graphify skill is installed at user level
(`~/.claude/skills/graphify/`), so `/graphify` and its query flows are available
without reinstalling per project.

**Prefer the graph over a broad grep for codebase questions.** When
`graphify-out/graph.json` exists, a natural-language question about architecture,
relationships, or data flow should go through the graph first — it returns a
scoped subgraph, usually far smaller than `GRAPH_REPORT.md` or raw grep output:

```bash
graphify query "<question>"           # BFS: what is X connected to
graphify query "<question>" --dfs     # DFS: how does X reach Y
graphify path "<A>" "<B>"             # shortest path between two concepts
graphify explain "<concept>"          # plain-language node + neighbors
graphify update .                     # refresh after code changes (AST-only, no LLM cost)
```

Caveats worth knowing here:

- The query matcher is case-folded substring + IDF — **no stemming, no synonyms**.
  Domain vocabulary in this repo is specific (`subIFG`, `pfo-sec`, `Delta_Group`,
  `lgRefl`), so match the graph's own labels or the query returns noise.
- Dirty `graphify-out/` files after a hook or incremental update are expected and
  are not a reason to skip the graph. Skip it only when the task is about stale or
  wrong graph output, or the user says not to.
- Grep is still the right tool for exact-string work: finding every caller of a
  symbol, config keys, or a literal that must match byte-for-byte.

## Other agent configuration

`AGENTS.md` and `.opencode/` hold the OpenCode agent setup (personas, session
protocol, `memory.md` handoff notes). The OpenCode-specific workflow — persona
switching, compliance checkpoints, `@subagent` invocation — does not apply to
Claude Code; `.opencode/foundations.md` and `.opencode/conventions.md` are the
parts worth reading, and their durable rules are summarized above.
