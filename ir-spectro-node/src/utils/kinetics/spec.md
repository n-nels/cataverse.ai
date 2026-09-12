# src/utils/kinetics — offline reprocessing CLIs

This package has **two separate CLIs**, deliberately kept apart:

| CLI | Script | Job | Underlying API |
|---|---|---|---|
| Classify | `scripts/run_kinetics_classification.py` | Label a `cluster_sum` trajectory `continuous`/`discontinuous` | `src/utils/kinetics/classify_cli.py` → `api.classify_file` / `api.classify_folder` |
| Fit | `scripts/run_kinetics_fit.py` | Fit a PFO/secondary-PFO kinetic model and produce rate constants | `src/utils/kinetics/fit_cli.py` → `api.fit_file` / `api.fit_folder` |

They were split apart after a reprocessing attempt that mixed the two: redefining
`monomer_sum` has nothing to do with classification (only `cluster_sum` is ever
classified), and the classify CLI never fits kinetic parameters at all — its
`pfo_*`/`pfo-sec_*` output columns are NaN by design. Use the fit CLI for
anything involving PFO/secondary-PFO parameters.

Both CLIs only orchestrate existing `src/utils/kinetics/{utils,writer,api}.py`
logic — neither adds new fitting or classification behavior.

Neither CLI touches `src/analysis/` (the live, real-time server pipeline) or
`config/analysis.yaml`'s `monomer_peaks_base`/`cluster_peaks_base` (the config
that pipeline reads). Redefining sums here is scoped entirely to one offline
CLI run; it never changes what the instrument computes live.

## Fit CLI — `scripts/run_kinetics_fit.py`

### Target (required, mutually exclusive)

| Flag | Meaning |
|---|---|
| `--path PATH` | Fit one `*_CarbonylPeakArea.csv` file. |
| `--folder FOLDER` | Fit every matching file under a dataset folder (absolute path, or a name relative to `SEARCH_ROOT` = `config/paths.yaml`'s `data.peak_fit`). |

### Kwargs

| Flag | Default | Maps to (`api.fit_file`/`fit_folder`) | Meaning |
|---|---|---|---|
| `--model {pfo,secondary_pfo}` | `secondary_pfo` | `model` | Which kinetic model to fit. `pfo`: `q(t) = q_0 + q_e(1 - exp(-k t))`. `secondary_pfo`: coupled-ODE secondary PFO (`k_a`, `q_e`, `k_s`/`k_p`, `q_inf`) — see `CLAUDE.md` for the current-iteration constraints (`q_0` fixed, `k_p_ratio` bound, `q_inf` cap, etc.). |
| `--peak-names NAME [NAME ...]` | `None` (all peaks) | `peak_names` | Restrict fitting to these `Peak_Name` values, e.g. `monomer_sum`, `cluster_sum`, or an explicit `Peak_<value>`. This is a **row filter** — which rows get fit — not the sum definition. |
| `--mode {full_series,rolling}` | `rolling` | `mode` | `rolling`: fit at every time point using an expanding window (all points up to and including that time) — one result row per time point. `full_series`: fit once using the whole trajectory; result is written to the row at the max time only, every earlier row's kinetic columns stay NaN. |
| `--min-points N` | `4` | `min_points` | Minimum data points required before a trajectory slice is fit. Below this, the row is skipped. |
| `--init V [V ...]` | `None` (built-in defaults) | `init` | Initial parameter guess (p0) for the optimizer. Length must match the model: `pfo` takes 3 values (`k`, `q_e`, `q_0`); `secondary_pfo` takes 5 (`k_a`, `q_e`, `k_s`, `k_p_ratio`, `q_inf`). |
| `--use-prior-p0` / `--no-use-prior-p0` | `--use-prior-p0` (True) | `use_prior_p0` | `secondary_pfo` + `rolling` only. When on, a time point's successful p0 seeds the next time point's search (only carried forward if r² improved by > 0.01). `--no-use-prior-p0` restarts from `--init`/defaults at every row. |
| `--output-folder NAME` | `_test` | `output_folder` | Output subfolder name, created alongside the source file. Source is never overwritten. |
| `--monomer-sum-peaks NAME [NAME ...]` | `None` | `monomer_sum_peaks` | **Redefine `monomer_sum`** for this run — see below. |
| `--cluster-sum-peaks NAME [NAME ...]` | `None` | `cluster_sum_peaks` | Same, for `cluster_sum`. |

### Why `rolling` is the default: relationship to the live pipeline's `latest_only`

The live server pipeline (`src/analysis/kinetics_fitting.py`) doesn't use
`mode` at all — it has its own flag, `append_fit_results(..., latest_only: bool
= True)`. The two aren't the same knob, but they're closely related, and
knowing the mapping explains why this CLI now defaults to `rolling` instead of
`full_series`:

| Live pipeline | Offline fit CLI equivalent | Behavior |
|---|---|---|
| `latest_only=True` (real-time default) | closest to `rolling`, built incrementally | Each time a new point arrives, fit *only* the newest time point (using all preceding points as the window) and merge with previously-saved kinetics rows carried forward. Over the life of a run this produces the same end state as running `rolling` once over the complete file: one fit per time point. |
| `latest_only=False` (batch/offline path, via `run_kinetics_fit` per `CLAUDE.md`) | `rolling` | Refits every time point from scratch in one pass, ignoring prior kinetics columns. This is what this CLI's `rolling` mode does. |
| — | `full_series` | Has **no live-pipeline equivalent**. It fits once over the whole trajectory and writes the result to a single row (the final time point), discarding what an earlier point's fit would have been — the live pipeline never does this. |

Because `full_series` has no analog in production and `rolling` is what
actually matches how kinetics get fit in real time, `rolling` is the default
here. Use `--mode full_series` only when you deliberately want a single
end-of-run fit summary rather than a per-row trajectory of fits.

### Redefining `monomer_sum` / `cluster_sum`

`monomer_sum` and `cluster_sum` are synthetic rows: the sum of `Cumulative_Peak_Area`
across a group of atomic peaks, at each `(Time (s), Delta_Group, File)`. Which
peaks belong to each group is normally `config/analysis.yaml`'s
`monomer_peaks_base` / `cluster_peaks_base` (isotope-shifted at read time) —
and in practice, the source CSV usually already has `monomer_sum`/`cluster_sum`
rows baked in by the live pipeline (`src/analysis/output.py`), computed with
that config definition.

`--monomer-sum-peaks` / `--cluster-sum-peaks` let you override the peak group
for one offline run, without touching `config/analysis.yaml`:

```
--monomer-sum-peaks Peak_2113 Peak_2103 Peak_2093
```

Pass the **final `Peak_Name` values as they appear in the CSV** — the same
units as `--peak-names` — not raw base wavenumbers (no isotope-shift math
happens here). To find the current shifted names for a peak group, read them
off any `*_CarbonylPeakArea.csv`'s `Peak_Name` column, or compute them from
`config/analysis.yaml`'s base list plus `isotope_shift_cm1`.

When either override is given:
1. Any existing `monomer_sum`/`cluster_sum` row of that type is dropped from
   the loaded data first.
2. It's rebuilt from scratch by summing exactly the peaks you listed.
3. The other sum (if not overridden) is left as-is — either the baked-in row
   from the source CSV, or rebuilt from the config default if the source CSV
   didn't have one.

Omitting a flag leaves that sum untouched (whatever's already in the CSV, or
the config default). This is why the flags default to `None` rather than an
empty list — there's a real difference between "don't touch this sum" and
"sum zero peaks."

### Examples

```
# Fit secondary_pfo on monomer_sum for one file, using the config's monomer definition
uv run python scripts/run_kinetics_fit.py --path <file>_CarbonylPeakArea.csv --model secondary_pfo --peak-names monomer_sum

# Same, but redefine monomer_sum to drop one peak for this run only
uv run python scripts/run_kinetics_fit.py --path <file>_CarbonylPeakArea.csv --model secondary_pfo --peak-names monomer_sum --monomer-sum-peaks Peak_2113 Peak_2103 Peak_2093

# Batch-fit pfo on cluster_sum across a whole dataset folder, rolling window
uv run python scripts/run_kinetics_fit.py --folder nn1120-2_pd_ceo2_000 --model pfo --peak-names cluster_sum --mode rolling

# Redefine both sums for a batch run, starting fresh p0 every row
uv run python scripts/run_kinetics_fit.py --folder nn1120-2_pd_ceo2_000 --model secondary_pfo --peak-names monomer_sum --monomer-sum-peaks Peak_2113 Peak_2103 Peak_2093 --cluster-sum-peaks Peak_2073 Peak_2062 Peak_2050 --no-use-prior-p0
```

Output for `--path` prints the written file path, row count, and (when
present) `median_r2`/`median_rmse` across the fitted rows. Output for
`--folder` prints `N/M files fit under <folder>` plus one `FAILED <file>: <error>`
line per failure.

## Classify CLI — `scripts/run_kinetics_classification.py`

Unrelated to fitting — no kinetic parameters (`pfo_*`/`pfo-sec_*`) are ever
produced here. This CLI answers one question per `cluster_sum` trajectory:
did nucleation growth start ("`discontinuous`", with a `growth_onset_s`
breakpoint) or not ("`continuous`")?

### What classification does

`classify_trajectory` (and its variants, see below) look at a `cluster_sum`
trajectory (`Time (s)` vs. `Cumulative_Peak_Area`) and try to find a flat
lead-in window followed by a sustained rise:

1. `find_flat_transition` scans forward for a window (`flat_window_s`,
   `min_flat_start_s` from `config/analysis.yaml`'s `kinetics_classification`)
   where the local slope stays within `eps_flat` of zero, then finds where
   that flat window ends (the slope stops being flat).
2. The trajectory is `discontinuous` only if it's still meaningfully elevated
   above that flat baseline (by more than `rise_delta`) at its final points —
   otherwise it's `continuous`.
3. If `discontinuous`, `growth_onset_s` is set to the transition point (or a
   smoothed version of it), and a PFO model is fit separately on the
   before/after slices (`pre_pfo_*` / `post_pfo_*` columns) — **this is a
   diagnostic PFO summary fit for classification purposes only**, distinct
   from the fit CLI's `pfo`/`secondary_pfo` output columns.

Only `Peak_Name == "cluster_sum"` is ever run through this logic — `monomer_sum`
and every atomic `Peak_<value>` row pass through with `classification`/
`growth_onset_s` left as NaN, whether or not `--peak-names` restricts to them.

### Classifier variants (`--classifier`)

Several detectors live side by side in `classification.py` as active,
scored candidates (see `docs/spec.md`), not dead alternatives:

| `--classifier` value | Method | Approach |
|---|---|---|
| `combined` (default) | `classify_trajectory_combined` | Fires `discontinuous` if *either* the flat-then-rise rule *or* the drawdown rule (below) fires. Current best performer — 285/288 per `docs/spec.md` §6.2. |
| `default` | `classify_trajectory` | The original flat-then-rise-only detector (264/288). Rejects a trajectory that has decayed back toward baseline by its final ~5% of points, no matter how large the rise was in between. |
| `sustained_rise` | `classify_trajectory_sustained_rise` | Like `default`, but doesn't require the trajectory to still be elevated at the very end — checks whether a *sustained* (smoothed) elevation above baseline ever occurred anywhere after the flat-window transition, tolerating a later decay. |
| `drawdown` | `classify_trajectory_drawdown` | A different shape entirely: no flat-window search. Detects a rise-then-decay "hump" by comparing the running max so far against the pre-peak minimum (`rise_magnitude`) and against the current value (`drawdown`). Built for trajectories with no flat lead-in that rise sharply from the first point, peak, then decay. |

### `--validate`

Ignores `--path`/`--folder` entirely. Recomputes classification from raw
`Time (s)`/`Cumulative_Peak_Area` `cluster_sum` rows (never trusts a
`classification` column already baked into the CSV) for every file listed in
`ground_truth.json`, and scores the chosen `--classifier` against each file's
known label. Correctness uses **monotonic-once-triggered aggregation**: for
each file, the detector is swept over every growing prefix of the trajectory
(`ever_fires`); a `discontinuous`-labeled file is correct iff the detector
fires `discontinuous` for `REQUIRED_CONSECUTIVE_FIRES` (3) consecutive
prefixes at *some* point; a `continuous`-labeled file is correct iff that
never happens. `report.print_summary()` prints overall accuracy, a
confusion-matrix-style breakdown (`tp`/`fn`/`tn`/`fp`), per-folder accuracy,
and every mismatch. See `validation.py` and `docs/spec.md`/`docs/prompt.md`
for the full definition.

### Kwargs

| Flag | Default | Maps to (`api.classify_file`/`classify_folder`) | Meaning |
|---|---|---|---|
| `--path` / `--folder` | — | `path` / `dataset_folder` | Same target semantics as the fit CLI. |
| `--validate` | off | (bypasses `api`, calls `validation.run_validation`) | See above. |
| `--classifier {default,sustained_rise,drawdown,combined}` | `combined` | `classify_fn` | Which detector labels `cluster_sum` — see table above. |
| `--peak-names NAME [NAME ...]` | `None` (all peaks) | `peak_names` | Row filter, same meaning as the fit CLI — but only `cluster_sum` rows ever get a `classification` value regardless of this filter. |
| `--min-points N` | `4` | `min_points` | Minimum points required before classification runs on a `cluster_sum` group. |
| `--output-folder NAME` | `_test` | `output_folder` | Same semantics as the fit CLI — created alongside the source file, source never overwritten. |

This CLI has no `--monomer-sum-peaks`/`--cluster-sum-peaks` — redefining sums
is a fitting concern, not a classification one, and only the fit CLI exposes it.

### Examples

```
# Classify every cluster_sum trajectory in a dataset folder with the default (best) detector
uv run python scripts/run_kinetics_classification.py --folder nn1120-3_pd_ceo2_004

# Classify one file with a specific detector variant
uv run python scripts/run_kinetics_classification.py --path <file>_CarbonylPeakArea.csv --classifier drawdown

# Score a detector against ground_truth.json instead of writing output
uv run python scripts/run_kinetics_classification.py --validate --classifier combined
```

Output for `--path` prints the written file path and row count. Output for
`--folder` prints `N/M files classified under <folder>` plus one
`FAILED <file>: <error>` line per failure. Output for `--validate` prints the
`ValidationReport` summary described above.
