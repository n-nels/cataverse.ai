"""
Exploratory Data Analysis: Compare predicted ODE solutions with actual data.

For each test sample:
1. Predict 6 PFO-Sec params using the trained model
2. Solve coupled ODE with predicted params → q(t), p(t)
3. Solve coupled ODE with fitted params from CSV → q(t), p(t) (baseline)
4. Plot both against raw Cumulative_Peak_Area from CSV
"""

import json
import logging
from pathlib import Path
from threading import Thread
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray
import pandas as pd
from scipy.integrate import solve_ivp

from load import load_dataset, split_dataset
from model import load_model, DEFAULT_MODEL_DIR, sanitize_feature_names, inverse_target_transforms
from transform import TARGET_COLUMNS

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path(__file__).parent / "outputs"
DEFAULT_CACHE_PATH = Path(__file__).parent / "experiment_cache.json"


def coupled_pfo_odes(
    t: float,
    y: NDArray[np.float64],
    k_a: float,
    q_e: float,
    k_s: float,
    k_p: float,
    q_inf: float,
) -> list[float]:
    """Coupled ODE system for secondary PFO model."""
    q, p = y
    dq = k_a * (q_e - q) - k_s * p
    dp = k_p * (q - q_inf - p)
    return [dq, dp]


def solve_pfo(
    time_s: NDArray[np.float64],
    k_a: float,
    q_e: float,
    k_s: float,
    k_p: float,
    q_inf: float,
    q_0: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64]] | None:
    """Return q(t) and p(t) for secondary PFO model.

    Uses threading with timeout as a guard against solver hangs.
    Handles duplicate time points and interpolates back to the original grid.
    """
    _, unique_indices = np.unique(time_s, return_index=True)
    time_s_unique = np.sort(time_s[unique_indices])

    result_container: dict[str, Any] = {"sol": None, "error": None}

    def solve_ode() -> None:
        try:
            result_container["sol"] = solve_ivp(
                coupled_pfo_odes,
                t_span=(time_s_unique[0], time_s_unique[-1]),
                y0=[q_0, 0.0],
                args=(k_a, q_e, k_s, k_p, q_inf),
                t_eval=time_s_unique,
                method="RK45",
                rtol=1e-8,
            )
        except Exception as exc:
            result_container["error"] = exc

    thread = Thread(target=solve_ode)
    thread.start()
    thread.join(timeout=0.1)

    if thread.is_alive():
        logger.warning("solve_ivp timed out for secondary PFO")
        return None

    if result_container["error"] is not None:
        logger.error("solve_ivp failed: %s", result_container["error"])
        return None

    sol = result_container["sol"]
    if sol is None or not sol.success:
        logger.warning("solve_ivp solver did not converge")
        return None

    q_unique = sol.y[0]
    p_unique = sol.y[1]

    interp_q = np.interp(time_s, time_s_unique, q_unique)
    interp_p = np.interp(time_s, time_s_unique, p_unique)
    return interp_q, interp_p


def _map_to_ode_params(p: dict[str, float]) -> dict[str, float]:
    """Map TARGET_COLUMNS names to ODE parameter names."""
    return {
        "k_a": p["pfo-sec_k_a_s-1"],
        "q_e": p["pfo-sec_q_e_au"],
        "k_s": p["pfo-sec_k_s_s-1"],
        "k_p": p["pfo-sec_k_p_s-1"],
        "q_inf": p["pfo-sec_q_inf_au"],
        "q_0": p["pfo-sec_q0_au"],
    }


def load_records_from_cache(
    cache_path: Path = DEFAULT_CACHE_PATH,
) -> dict[str, Any]:
    """Load experiment records from cache, indexed by base_name."""
    cache_data = json.loads(cache_path.read_text())
    return {rec["base_name"]: rec for rec in cache_data["records"]}


def generate_eda_plots(
    X_test: pd.DataFrame,
    y_pred: np.ndarray,
    records: dict[str, Any],
    output_dir: Path,
) -> list[Path]:
    """Generate EDA plots for all test samples."""
    saved_paths = []

    for i, (idx, _) in enumerate(X_test.iterrows()):
        rec = records.get(idx)
        if rec is None:
            logger.warning("No record found for %s, skipping", idx)
            continue

        csv_path = Path(rec["csv_path"])
        if not csv_path.exists():
            logger.warning("CSV not found: %s, skipping", csv_path)
            continue

        df = pd.read_csv(csv_path)
        monomer = df[df["Peak_Name"] == "monomer_sum"].copy()
        if monomer.empty:
            logger.warning("No monomer_sum rows in %s, skipping", csv_path)
            continue

        time_actual = monomer["Time (s)"].values.astype(np.float64)
        q_actual = monomer["Cumulative_Peak_Area"].values

        # Fitted params from CSV (last fully-populated row)
        if not all(c in monomer.columns for c in TARGET_COLUMNS):
            logger.warning("CSV %s missing target columns, skipping", csv_path)
            continue
        fitted_row = monomer.dropna(subset=TARGET_COLUMNS)
        if fitted_row.empty:
            logger.warning("No fitted params in %s, skipping", csv_path)
            continue
        fitted_row = fitted_row.iloc[-1]
        fitted_params = {col: float(fitted_row[col]) for col in TARGET_COLUMNS}

        # Predicted params from model
        pred_values = y_pred[i]
        predicted_params = {
            TARGET_COLUMNS[j]: float(pred_values[j]) for j in range(len(TARGET_COLUMNS))
        }

        fitted_p = _map_to_ode_params(fitted_params)
        predicted_p = _map_to_ode_params(predicted_params)

        # Solve ODEs
        fitted_result = solve_pfo(
            time_actual,
            fitted_p["k_a"], fitted_p["q_e"], fitted_p["k_s"],
            fitted_p["k_p"], fitted_p["q_inf"], fitted_p["q_0"],
        )
        predicted_result = solve_pfo(
            time_actual,
            predicted_p["k_a"], predicted_p["q_e"], predicted_p["k_s"],
            predicted_p["k_p"], predicted_p["q_inf"], predicted_p["q_0"],
        )

        # --- Plot ---
        fig, ax = plt.subplots(figsize=(10, 6))

        ax.scatter(
            time_actual / 3600, q_actual,
            s=8, alpha=0.6, label="Actual data",
        )

        if fitted_result is not None:
            q_fitted, _ = fitted_result
            ax.scatter(
                time_actual / 3600, q_fitted,
            s=8, alpha=0.6, label="Fitted ODE (CSV params)",
            )

        if predicted_result is not None:
            q_pred, _ = predicted_result
            ax.scatter(
                time_actual / 3600, q_pred,
            s=8, alpha=0.6, label="Predicted ODE (model)",
            )

        ax.set_xlabel("Time (h)")
        ax.set_ylabel("Cumulative Peak Area (au)")
        ax.set_title(f"Test sample: {idx}")
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        safe_name = str(idx).replace("/", "_").replace("\\", "_")
        save_path = output_dir / f"eda_{safe_name}.tiff"
        fig.savefig(save_path, format="tiff", bbox_inches="tight")
        plt.close(fig)
        saved_paths.append(save_path)
        logger.info("Saved EDA plot: %s", save_path)

    logger.info("Generated %d EDA plots", len(saved_paths))
    return saved_paths


def main() -> None:
    """Entry point: load dataset, model, split, predict, and generate EDA plots."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    output_dir = DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=== Loading dataset ===")
    X, y = load_dataset(output_dir)

    print("\n=== Loading records from cache ===")
    records = load_records_from_cache()
    print(f"Loaded {len(records)} records")

    print("\n=== Loading model ===")
    model_path = DEFAULT_MODEL_DIR / "lightgbm.joblib"
    trained = load_model(model_path)

    print("\n=== Splitting dataset ===")
    splits = split_dataset(X, y)
    print(f"Test samples: {len(splits.X_test)}")

    print("\n=== Predicting on test set ===")
    clean_names = sanitize_feature_names(list(splits.X_test.columns))
    X_test_clean = splits.X_test.copy()
    X_test_clean.columns = clean_names
    y_pred_tfm = trained.model.predict(X_test_clean)  # transformed space
    y_pred = inverse_target_transforms(y_pred_tfm, trained.target_names, trained.lambdas)  # original scale

    print("\n=== Generating EDA plots ===")
    paths = generate_eda_plots(splits.X_test, y_pred, records, output_dir)
    print(f"\nGenerated {len(paths)} EDA plots in {output_dir}")
    for p in paths:
        print(f"  {p}")


if __name__ == "__main__":
    main()
