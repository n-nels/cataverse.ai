"""Trial sampling, training, and per-trial timeout enforcement.

A "trial" is one candidate hyperparameter configuration. The trial change is the
config itself (recorded as ``trial_params.yaml``), not a source-code edit.

Per-trial timeout is enforced by running each trial in a hermetic subprocess
that rebuilds the dataset + split from the cached parquet (deterministic with
seed 42) and writes a structured JSON result. The parent waits with a timeout
and terminates the subprocess on expiry.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

# This file lives in harness/, so the automation package dir is its parent.
_AUTOMATION_DIR = Path(__file__).resolve().parent.parent


@dataclass
class TrialResult:
    """Structured result of one trial."""
    status: str  # "success" | "crash" | "invalid" | "timeout"
    params: dict
    validation_avg_rmse: float | None = None
    validation_avg_r2: float | None = None
    per_target: dict | None = None
    runtime_minutes: float | None = None
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def sample_params(manifest, rng: random.Random) -> dict:
    """Sample one candidate configuration via bounded random search."""
    params: dict[str, Any] = {}
    for hp in manifest.allowed_hyperparameters:
        if hp.type == "numeric":
            lo, hi = hp.range  # type: ignore[misc]
            if isinstance(lo, int) and isinstance(hi, int):
                params[hp.name] = rng.randint(lo, hi)
            else:
                params[hp.name] = round(rng.uniform(lo, hi), 6)
        else:  # categorical
            params[hp.name] = rng.choice(hp.choices)  # type: ignore[union-attr]
    return params


def build_model_config(params: dict) -> ModelConfig:
    """Build a ModelConfig from a params dict, keeping only known fields.

    Option A: the harness only sets current ModelConfig fields. Hyperparameters
    that are not ModelConfig fields are ignored here; when the loop-agent later
    wants new knobs it extends ModelConfig + the model implementation (non-ETL)
    and declares them in the manifest.
    """
    ModelConfig = _ModelConfig()
    fields = set(ModelConfig._fields)
    kwargs = {k: v for k, v in params.items() if k in fields}
    return ModelConfig(**kwargs)


def _ModelConfig():
    # Lazy import so this module is importable without the ML env.
    from model import ModelConfig
    return ModelConfig


def get_strategy(params: dict) -> str:
    return str(params.get("strategy", "shared"))


# ---------------------------------------------------------------------------
# In-process training (used by the worker and by smoke mode)
# ---------------------------------------------------------------------------

def train_trial_inprocess(
    data_dir: str | Path,
    model_name: str,
    params: dict,
) -> TrialResult:
    """Train one trial in-process and return structured validation metrics."""
    start = time.time()
    # Imports are local so the parent process does not require ML deps to import
    # this module for sampling/ledger logic.
    import pipeline  # noqa: E402

    X, y = pipeline.prepare_dataset(data_dir)
    splits = pipeline.prepare_splits(X, y)
    config = build_model_config(params)
    strategy = get_strategy(params)
    trained = pipeline.train_model(splits, model_name, config, strategy)
    val_rmse = pipeline.validation_avg_rmse(trained)
    val_r2 = pipeline.validation_avg_r2(trained)
    runtime = (time.time() - start) / 60.0
    return TrialResult(
        status="success",
        params=params,
        validation_avg_rmse=val_rmse,
        validation_avg_r2=val_r2,
        per_target=trained.metrics,
        runtime_minutes=runtime,
    )


def eval_finalist_inprocess(
    data_dir: str | Path,
    model_name: str,
    params: dict,
) -> dict:
    """Train a finalist and evaluate on the test set. Returns test metrics dict."""
    import pipeline  # noqa: E402

    X, y = pipeline.prepare_dataset(data_dir)
    splits = pipeline.prepare_splits(X, y)
    config = build_model_config(params)
    strategy = get_strategy(params)
    trained = pipeline.train_model(splits, model_name, config, strategy)
    tm = pipeline.test_metrics(trained, splits)
    return tm


# ---------------------------------------------------------------------------
# Subprocess trial execution with timeout
# ---------------------------------------------------------------------------

def run_trial_subprocess(
    data_dir: str | Path,
    model_name: str,
    params: dict,
    timeout_minutes: float,
    python_exe: str | None = None,
) -> TrialResult:
    """Run a trial in a hermetic subprocess with a hard timeout.

    The subprocess rebuilds dataset + split from ``data_dir`` (deterministic),
    trains, and writes a JSON result to a temp file. On timeout or crash the
    parent returns a failed TrialResult.
    """
    import tempfile

    python = python_exe or sys.executable
    spec = {
        "data_dir": str(data_dir),
        "model_name": model_name,
        "params": params,
    }
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    ) as spec_f:
        json.dump(spec, spec_f)
        spec_path = spec_f.name
    out_path = spec_path.replace(".json", ".out.json")

    cmd = [python, "-m", "harness.trial", spec_path, out_path]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_AUTOMATION_DIR) + os.pathsep + env.get("PYTHONPATH", "")

    timeout_s = timeout_minutes * 60.0
    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return TrialResult(
            status="timeout",
            params=params,
            reason=f"exceeded per-trial timeout of {timeout_minutes} minutes",
        )

    runtime = (time.time() - start) / 60.0
    out = Path(out_path)
    if proc.returncode != 0 or not out.exists():
        stderr_tail = (proc.stderr or "")[-500:]
        return TrialResult(
            status="crash",
            params=params,
            runtime_minutes=runtime,
            reason=f"subprocess exit {proc.returncode}: {stderr_tail}",
        )

    try:
        payload = json.loads(out.read_text(encoding="utf-8"))
    except Exception as exc:
        return TrialResult(
            status="crash",
            params=params,
            runtime_minutes=runtime,
            reason=f"could not parse result json: {exc}",
        )
    finally:
        try:
            out.unlink()
            Path(spec_path).unlink()
        except OSError:
            pass

    payload["runtime_minutes"] = payload.get("runtime_minutes") or runtime
    return TrialResult(**payload)


# ---------------------------------------------------------------------------
# Worker entrypoint (invoked as ``python -m harness.trial spec.json out.json``)
# ---------------------------------------------------------------------------

def _worker_main(spec_path: str, out_path: str) -> None:
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    result = train_trial_inprocess(spec["data_dir"], spec["model_name"], spec["params"])
    Path(out_path).write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python -m harness.trial <spec.json> <out.json>", file=sys.stderr)
        sys.exit(2)
    _worker_main(sys.argv[1], sys.argv[2])