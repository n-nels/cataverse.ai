"""Per-experiment convergence extrapolation, the third sequential candidate.

Every prior candidate (`sequential_model.py`'s Ridge correction,
`gated_blend_model.py`) uses only a single snapshot of the current ODE fit at
the cutoff, plus the RF prior. Neither uses the *shape* of how the current fit
has been changing across earlier cutoffs of the same experiment.

The stored rolling `pfo-sec_*` columns already contain that shape: each row is
an independent least-squares fit of the same underlying ODE to a growing
prefix of observations. As the sample size `n` (`observation_count`) used by
that fit grows, generic least-squares fitting error contracts roughly like
`1/n` — this is a property of the fitting numerics, not evidence that the
final value is knowable from few points. So instead of trusting the single
latest snapshot, this candidate fits `value(n) ~= L + C / n` by ordinary least
squares across every fit-valid row seen so far *in this experiment's own
history* (index/time <= the current cutoff — no cross-experiment learning and
no future information), and uses the extrapolated intercept `L` (the `n -> oo`
limit) as its prediction of the final parameter.

Because each of the five learned parameters is extrapolated independently,
the coupling constraint `0 <= k_p <= k_a` is not guaranteed by construction
(unlike the gated blend's shared-weight convex combination). It is instead
enforced by clipping `k_p` into `[0, k_a]` after `k_a` is extrapolated and
clipped to its own valid range. This is a repair, not a rejection, because the
alternative (rejecting any clipped prediction) would fall back to RF on most
early cutoffs where clipping is most likely to bind, defeating the point of
the candidate. Every output is still re-validated with
`validate_secondary_pfo_parameters` before use, so an unexpected non-finite or
out-of-range result still falls back rather than being trusted silently.

With too few fit-valid historical rows to fit a line (`min_trajectory_points`,
a candidate hyperparameter selected on validation like the Ridge alpha and
gated-blend bin count), no extrapolation is attempted and the model reports an
invalid prediction, which the shared evaluation/inference fallback path
resolves to the RF prediction.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .data.contract import TARGET_COLUMNS
from .data.examples import FIT_VALID, SequentialExample
from .data.observations import flatten_monomer_rows
from .model_prediction import ModelPrediction
from .models.secondary_pfo import SecondaryPfoParameters, validate_secondary_pfo_parameters


MODEL_NAME = "trajectory_extrapolation"
LEARNED_TARGET_COLUMNS = TARGET_COLUMNS[:-1]
DEFAULT_MIN_TRAJECTORY_POINTS = (3, 4, 6, 10)

_K_A_INDEX = TARGET_COLUMNS.index("pfo-sec_k_a_s-1")
_Q_E_INDEX = TARGET_COLUMNS.index("pfo-sec_q_e_au")
_K_S_INDEX = TARGET_COLUMNS.index("pfo-sec_k_s_s-1")
_K_P_INDEX = TARGET_COLUMNS.index("pfo-sec_k_p_s-1")
_Q_INF_INDEX = TARGET_COLUMNS.index("pfo-sec_q_inf_au")


def _ols_intercept(x: np.ndarray, y: np.ndarray) -> float:
    """Return the least-squares intercept of `y ~ intercept + slope * x`."""
    x_mean = float(np.mean(x))
    y_mean = float(np.mean(y))
    denominator = float(np.sum((x - x_mean) ** 2))
    if denominator <= 0.0:
        return y_mean
    slope = float(np.sum((x - x_mean) * (y - y_mean)) / denominator)
    return y_mean - slope * x_mean


@dataclass
class FittedTrajectoryExtrapolationModel:
    """Extrapolates each experiment's own rolling-fit convergence to n -> oo.

    Holds no cross-experiment learned state; `min_trajectory_points` is the
    only hyperparameter, selected on validation like other candidates. The
    timeline cache avoids re-parsing the same CSV for every cutoff of one
    experiment during evaluation/inference.
    """

    min_trajectory_points: int
    _timeline_cache: dict[str, pd.DataFrame] = field(default_factory=dict, repr=False)

    def _prefix_rows(self, example: SequentialExample) -> pd.DataFrame:
        """Return the fit-relevant flattened rows through this cutoff only.

        Reconstructs exactly the prefix `build_sequential_examples` used for
        this cutoff (`timeline.iloc[:observation_count]`), so this never sees
        a row past `example.cutoff_time_s`.
        """
        if example.csv_path is None:
            raise ValueError(f"CSV provenance is missing for {example.experiment_id}")
        cached = self._timeline_cache.get(example.csv_path)
        if cached is None:
            flattened, _ = flatten_monomer_rows(pd.read_csv(example.csv_path))
            cached = flattened.reset_index(drop=True)
            self._timeline_cache[example.csv_path] = cached
        return cached.iloc[: example.observation_count]

    def predict_parameters(self, example: SequentialExample) -> ModelPrediction:
        """Extrapolate the final parameters from this experiment's own history.

        Gated on the current cutoff's own fit status, matching
        `gated_blend_model.py` and `inference.py`'s `_model_candidate`: an
        update is only attempted once the cutoff itself has a valid fit.
        Without this gate, validation scoring would credit predictions at
        cutoffs production inference would never reach with a learned
        candidate at all.
        """
        if example.fit_status != FIT_VALID:
            return ModelPrediction(None, "invalid", f"current_fit_{example.fit_status}")
        try:
            prefix = self._prefix_rows(example)
        except (ValueError, OSError, pd.errors.ParserError) as error:
            return ModelPrediction(None, "invalid", f"prefix_read_failed:{error}")

        target_frame = prefix[list(TARGET_COLUMNS)].apply(pd.to_numeric, errors="coerce")
        complete = target_frame.notna().all(axis=1) & np.isfinite(target_frame.to_numpy(dtype=float)).all(
            axis=1
        )
        valid_rows = target_frame.loc[complete]
        if len(valid_rows) < self.min_trajectory_points:
            return ModelPrediction(None, "invalid", "insufficient_trajectory_points")

        observation_counts = valid_rows.index.to_numpy(dtype=float) + 1.0
        x = 1.0 / observation_counts
        extrapolated = {
            column: _ols_intercept(x, valid_rows[column].to_numpy(dtype=float))
            for column in TARGET_COLUMNS
        }

        k_a = float(np.clip(extrapolated[TARGET_COLUMNS[_K_A_INDEX]], 0.0, 0.01))
        k_s = float(np.clip(extrapolated[TARGET_COLUMNS[_K_S_INDEX]], 0.0, 0.01))
        k_p = float(np.clip(extrapolated[TARGET_COLUMNS[_K_P_INDEX]], 0.0, k_a))
        areas = np.asarray(example.observation_area, dtype=float)
        q_guess = float(np.max(areas)) if areas.size else 0.0
        upper = max(q_guess, 0.0) * 2.0
        q_e = float(np.clip(extrapolated[TARGET_COLUMNS[_Q_E_INDEX]], 0.0, upper))
        q_inf = float(np.clip(extrapolated[TARGET_COLUMNS[_Q_INF_INDEX]], 0.0, upper))

        try:
            parameters = SecondaryPfoParameters.from_values(
                [k_a, q_e, k_s, k_p, q_inf, float(example.q_0)]
            )
            validate_secondary_pfo_parameters(parameters, q_guess=q_guess)
        except (ValueError, TypeError, FloatingPointError) as error:
            return ModelPrediction(None, "invalid", str(error))
        return ModelPrediction(parameters, MODEL_NAME, None)


def fit_trajectory_extrapolation_model(
    *,
    min_trajectory_points: int,
) -> FittedTrajectoryExtrapolationModel:
    """Construct one candidate for a given minimum trajectory length.

    Unlike the Ridge and gated-blend candidates, this performs no fitting
    against training examples: the extrapolation is a deterministic
    per-experiment numerical technique, not a cross-experiment regression, so
    there is nothing to overfit beyond the single `min_trajectory_points`
    hyperparameter chosen on validation evidence.
    """
    if min_trajectory_points < 2:
        raise ValueError("min_trajectory_points must be at least 2")
    return FittedTrajectoryExtrapolationModel(min_trajectory_points=min_trajectory_points)
