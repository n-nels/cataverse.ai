You are solving this problem directly, not building a framework for solving it.
No runner scripts, no config systems.

Work in iterations. At the end of each one, append to JOURNAL_monomer-kinetics.md:
what you tried, what actually happened, what you're trying next and why. Append
only — never revise earlier entries, including wrong ones.

Write the journal for someone with no memory of this session, because that's what
will read it. Enough detail that they could pick up where you left off.
Keep each entry to roughly 500 characters. That's a hard budget, not a suggestion
to pad toward — say the decision and the one fact that explains it, not a
transcript.

---

## X — what to do

Investigate whether the existing monomer/secondary-process kinetic model
(`dM/dt = k_a(q_eq - q) - k_s*p`, `dp/dt = k_p(q_eq - q_inf - p)`, already fit
via the `pfo-sec_*` columns baked into the source CSVs) can be related to the
LaMer nucleation-growth picture (accumulation -> burst nucleation -> growth),
for `monomer_sum` trajectories in the 34 files under
`C:\Data\peakFit\nn1120-4_pd_ceo2_000\*_CarbonylPeakArea.csv`. Background: the
two chat exports in `X:\` ("chat-🧪 LaMer Nucleation Growth Kinetics.txt" and
"chat-🧪 Adsorption p and dp_dt (1).txt") give the LaMer theory and the
derivation of the two-term ODE model already implemented here. That model
itself is considered correct and out of scope to change.

Central questions to pursue, not a fixed method:
- Does mapping the model (or the raw curve) onto LaMer's stages tell us when
  nucleation began and when growth began/ended?
- What else might such a mapping reveal — e.g. a supersaturation proxy, burst
  duration, a growth-rate regime change, anything else physically meaningful?

There is no "one technique per round" rule. A round can combine curve
analysis, the already-fit parameters (`k_a`, `k_s`, `k_p`, `q_inf`, `q_e`,
`q0`), and reasoning about the ODE model however is most informative, and can
report more than one angle in the same round if several seem worth it.
Peak-maximum features (time, amplitude of the `monomer_sum` maximum) remain a
baseline to report regardless of what else a round explores.

Out of scope for this loop:
- Do not build an actual nucleation/growth detector or classifier from these
  features — deferred to a future, separate loop once candidate features are
  known to be worth building on.
- Do not touch `cluster_sum`'s own detector code or the nuc-clf loop
  (`docs/prompt_nuc-clf.md`) — including its `growth_onset_s`/classification
  output, which must not be used as a reference value here. `cluster_sum`'s
  own raw data series is in scope for plotting and for this loop's own
  metrics derived directly from it.
- Do not modify the pfo-sec fitting code itself, or the fit CLI
  (`scripts/run_kinetics_fit.py`) — read its output, don't change it.

**Development location:** a new standalone module,
`src/utils/kinetics/monomer_features.py` — plain functions plus an
editable-constants `if __name__ == "__main__":` block, no argparse CLI (that
can come later once a technique stabilizes, the same path `classification.py`
took). Reuse `src/utils/kinetics/utils.py`'s existing CSV I/O helpers rather
than re-deriving CSV loading.

**Plots (required every round):** for each source file, a matplotlib PNG
saved to that file's `_test/` folder overlaying `monomer_sum` and `cluster_sum`
on the same axes (a twin y-axis is likely needed given differing scales —
implementation detail, not prescribed here), with whatever features that
round extracted marked on the curve. This is the actual check on the round,
not a table of numbers alone.

**Saved tabular output:** technique-dependent, same `_test/` location as
plots. A scalar-per-file result (peak time/amplitude, a single onset estimate,
etc.) goes into one shared catalog CSV, e.g.
`monomer_features_<round-topic>.csv`, one row per source file. A curve-shaped
result (a derivative trace, a residual series) gets written as extra columns
on a per-file copy of that file's CSV in its own `_test/` folder — the same
pattern `fit_cli.py`/`classify_cli.py` already use for their own output.

## Y — success criterion, and how to check it

There is no ground-truth file for `monomer_sum` onset times (unlike
`ground_truth.json` for the cluster classifier), so Y is **human-judged and
exploratory, not numeric**, by explicit decision during round-1 alignment.

**Y is met, per round, when:** the round reports real evidence bearing on the
LaMer-relation question above — actual numbers, not "looks reasonable" — with
a PNG per file (or a clearly-stated representative subset, with reasons for
excluding any file) showing `monomer_sum` and `cluster_sum` overlaid and that
round's extracted feature(s) marked, plus physical reasoning that ties the
result back to LaMer's stages and/or the p/dp-dt model's parameters.

**How to check it:** there's no pass/fail computation to run. The check is
that the entry and its saved output are legible and complete: which files were
processed, the actual feature values, the saved PNGs/CSV(s) in `_test/`, and
reasoning connecting the result to physical nucleation/growth behavior. A
round that produces numbers with no plot, or a plot with no physical
reasoning, has not met Y.

**No loop-wide numeric target.** The human reviews each round's catalog and
decides when enough candidate features/insight exist, or whether a promising
feature is worth pursuing with real validation labels later.
