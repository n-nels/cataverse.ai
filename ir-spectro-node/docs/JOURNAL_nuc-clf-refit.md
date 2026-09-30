## Round 1 — 2026-09-30

Calibration OK: `combined` on `_reprocess` = 257/288. Tried a one-sided CUSUM on
per-group Peak_1988 increments (σ from the first `n_base` increments;
`src/utils/kinetics/baseline_departure.py`; harness got `trajectory_fn`), tuned on
human-labeled files only. Best: n_base 6, k 0.5, h 160 → **256/288**
(30 hit / 18 miss / 14 FP). Failure: in nn1120-4, 10 of 24 positives peak in
monomer before 2.5 h, so the rise sits inside the baseline window.
Label question: 9 algorithm-labeled `continuous` files in 003/004 match
positives (`003_reprocess\_test\nuc-clf-refit_r1_label_pairs.png`).
Next: take σ from high-frequency roughness, not an early window.
