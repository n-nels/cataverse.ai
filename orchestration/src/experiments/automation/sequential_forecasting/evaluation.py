"""Phase 8 evaluation, plots, and report generation."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.metrics import r2_score
from xml.sax.saxutils import escape

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ModuleNotFoundError:  # pragma: no cover - exercised by minimal environments
    plt = None

from .data.adapter import build_examples_from_artifacts
from .data.contract import AREA_COLUMN, TARGET_COLUMNS, TIME_COLUMN
from .data.examples import SequentialExample
from .data.observations import flatten_monomer_rows
from .models.secondary_pfo import remaining_curve_rmse


METHOD_ORDER = ("rf_only", "current_ode", "rf_ode_blend", "selected_model")
PROGRESS_ORDER = ("early", "middle", "late")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read one JSON object per line."""
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _example_index(
    examples: Iterable[SequentialExample],
) -> dict[tuple[str, str], SequentialExample]:
    """Index examples by their immutable experiment/cutoff identity."""
    indexed: dict[tuple[str, str], SequentialExample] = {}
    for example in examples:
        key = (example.experiment_id, example.cutoff_id)
        if key in indexed:
            raise ValueError(f"Duplicate example key: {key}")
        indexed[key] = example
    return indexed


def _load_observations(
    examples: Iterable[SequentialExample],
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Load flattened complete timelines for strict future-curve scoring."""
    observations: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for example in examples:
        if example.experiment_id in observations:
            continue
        if example.csv_path is None:
            raise ValueError(f"CSV provenance is missing for {example.experiment_id}")
        flattened, _ = flatten_monomer_rows(pd.read_csv(example.csv_path))
        timeline = flattened.loc[flattened[TIME_COLUMN] <= example.final_time_s]
        observations[example.experiment_id] = (
            timeline[TIME_COLUMN].to_numpy(dtype=float),
            timeline[AREA_COLUMN].to_numpy(dtype=float),
        )
    return observations


def _fraction_group(value: float) -> str:
    """Bucket a progress fraction without assuming identical schedules."""
    if value < 1.0 / 3.0:
        return "early"
    if value < 2.0 / 3.0:
        return "middle"
    return "late"


def _remaining_group(example: SequentialExample) -> str:
    """Bucket remaining time into long, middle, and short horizons."""
    duration = example.final_time_s - example.observation_times_s[0]
    if duration <= 0.0:
        return "short"
    fraction = example.time_remaining_s / duration
    if fraction < 1.0 / 3.0:
        return "short"
    if fraction < 2.0 / 3.0:
        return "middle"
    return "long"


def _normalise_record(
    method: str,
    record: dict[str, Any],
    example: SequentialExample,
    observations: dict[str, tuple[np.ndarray, np.ndarray]],
) -> dict[str, Any]:
    """Attach canonical references and calculate inference curve RMSE."""
    prediction = record.get("prediction")
    reference = np.asarray(example.reference_target, dtype=float)
    prediction_array = (
        np.asarray(prediction, dtype=float)
        if prediction is not None
        else np.empty(0, dtype=float)
    )
    if prediction_array.size == len(TARGET_COLUMNS) and np.isfinite(prediction_array).all():
        parameter_errors = prediction_array - reference
        valid_prediction = True
    else:
        parameter_errors = None
        valid_prediction = False

    curve_rmse = record.get("curve_rmse")
    curve_status = record.get("curve_status", "prediction_invalid")
    if method == "selected_model":
        curve_times = record.get("curve_times_s")
        predicted_area = record.get("curve_predicted_area")
        if curve_times is not None and predicted_area is not None:
            times = np.asarray(curve_times, dtype=float)
            predicted = np.asarray(predicted_area, dtype=float)
            observed_times, observed_area = observations[example.experiment_id]
            if not np.array_equal(times, observed_times):
                raise ValueError(f"Inference curve times do not match source for {example.cutoff_id}")
            curve_rmse = remaining_curve_rmse(
                times,
                observed_area,
                predicted,
                example.cutoff_time_s,
            )
            curve_status = "valid" if curve_rmse is not None else "no_remaining_points"

    return {
        "method": method,
        "experiment_id": example.experiment_id,
        "cutoff_id": example.cutoff_id,
        "assignment": example.assignment,
        "progress_group": _fraction_group(example.observation_fraction),
        "observation_count": example.observation_count,
        "observation_fraction_group": _fraction_group(example.observation_fraction),
        "elapsed_time_fraction_group": _fraction_group(example.elapsed_time_fraction),
        "time_remaining_group": _remaining_group(example),
        "reference": reference,
        "prediction": prediction_array if valid_prediction else None,
        "parameter_errors": parameter_errors,
        "valid_prediction": valid_prediction,
        "curve_rmse": float(curve_rmse) if curve_rmse is not None else None,
        "curve_status": curve_status,
        "prediction_source": record.get("prediction_source"),
        "fallback_reason": record.get("fallback_reason"),
    }


def _metric_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate parameter, scale-aware, and remaining-curve metrics."""
    valid_rows = [row for row in rows if row["valid_prediction"]]
    if valid_rows:
        references = np.vstack([row["reference"] for row in valid_rows])
        errors = np.vstack([row["parameter_errors"] for row in valid_rows])
        rmse = np.sqrt(np.mean(errors**2, axis=0))
        reference_scale = np.std(references, axis=0)
        normalized = np.divide(
            rmse,
            reference_scale,
            out=np.full_like(rmse, np.nan),
            where=reference_scale > 0.0,
        )
        r2_values: list[float | None] = []
        for index in range(len(TARGET_COLUMNS)):
            if len(references) < 2:
                r2_values.append(None)
                continue
            try:
                r2_values.append(float(r2_score(references[:, index], references[:, index] + errors[:, index])))
            except ValueError:
                r2_values.append(None)
        parameter_metrics = {
            "rmse_by_target": dict(zip(TARGET_COLUMNS, (float(value) for value in rmse), strict=True)),
            "r2_by_target": dict(zip(TARGET_COLUMNS, r2_values, strict=True)),
            "normalized_rmse_by_target": {
                target: (None if not np.isfinite(value) else float(value))
                for target, value in zip(TARGET_COLUMNS, normalized, strict=True)
            },
            "aggregate": {
                "avg_rmse": float(np.mean(rmse)),
                "avg_r2": (
                    float(np.mean([value for value in r2_values if value is not None]))
                    if any(value is not None for value in r2_values)
                    else None
                ),
                "avg_normalized_rmse": (
                    float(np.nanmean(normalized)) if np.isfinite(normalized).any() else None
                ),
            },
        }
    else:
        parameter_metrics = {
            "rmse_by_target": None,
            "r2_by_target": None,
            "normalized_rmse_by_target": None,
            "aggregate": {"avg_rmse": None, "avg_r2": None, "avg_normalized_rmse": None},
        }

    curve_values = [row["curve_rmse"] for row in rows if row["curve_rmse"] is not None]
    return {
        "count": len(rows),
        "experiment_count": len({row["experiment_id"] for row in rows}),
        "valid_prediction_count": len(valid_rows),
        "valid_curve_count": len(curve_values),
        "parameter": parameter_metrics,
        "curve_rmse": float(np.mean(curve_values)) if curve_values else None,
        "prediction_source_counts": dict(Counter(row["prediction_source"] for row in rows)),
        "fallback_count": sum(row["fallback_reason"] is not None for row in rows),
        "curve_status_counts": dict(Counter(row["curve_status"] for row in rows)),
    }


def _grouped_metrics(
    rows: list[dict[str, Any]],
    key: str,
) -> dict[str, Any]:
    """Aggregate one metric view by a reporting dimension."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(row)
    return {group: _metric_summary(group_rows) for group, group_rows in sorted(grouped.items())}


def evaluate_records(
    examples: tuple[SequentialExample, ...],
    observations: dict[str, tuple[np.ndarray, np.ndarray]],
    method_records: dict[str, list[dict[str, Any]]],
    *,
    assignment: str = "test",
) -> dict[str, Any]:
    """Evaluate methods on identical experiment/cutoff rows."""
    indexed = _example_index(examples)
    expected_keys = {
        key for key, example in indexed.items() if example.assignment == assignment
    }
    normalised: dict[str, list[dict[str, Any]]] = {}
    key_sets: dict[str, set[tuple[str, str]]] = {}
    for method, records in method_records.items():
        rows: list[dict[str, Any]] = []
        keys: set[tuple[str, str]] = set()
        for record in records:
            key = (str(record["experiment_id"]), str(record["cutoff_id"]))
            if key in keys:
                raise ValueError(f"Duplicate {method} prediction key: {key}")
            if key not in indexed:
                raise ValueError(f"Prediction has no canonical example: {key}")
            if indexed[key].assignment != assignment:
                continue
            keys.add(key)
            rows.append(_normalise_record(method, record, indexed[key], observations))
        key_sets[method] = keys
        normalised[method] = rows
    if key_sets and any(keys != expected_keys for keys in key_sets.values()):
        raise ValueError("Evaluation methods do not share identical experiment/cutoff coverage")

    summary: dict[str, Any] = {}
    for method, rows in normalised.items():
        summary[method] = {
            "overall": _metric_summary(rows),
            "by_progress_group": _grouped_metrics(rows, "progress_group"),
            "by_observation_count": _grouped_metrics(rows, "observation_count"),
            "by_observation_fraction": _grouped_metrics(rows, "observation_fraction_group"),
            "by_elapsed_time_fraction": _grouped_metrics(rows, "elapsed_time_fraction_group"),
            "by_time_remaining": _grouped_metrics(rows, "time_remaining_group"),
        }
    return {"assignment": assignment, "methods": summary, "rows": normalised}


def _comparison(summary: dict[str, Any]) -> dict[str, Any]:
    """Compare the frozen candidate with required baselines by progress."""
    candidate = summary["methods"].get("selected_model")
    if candidate is None:
        return {}
    comparisons: dict[str, Any] = {}
    for baseline in ("rf_only", "current_ode"):
        baseline_summary = summary["methods"].get(baseline)
        if baseline_summary is None:
            continue
        by_group: dict[str, Any] = {}
        for group in PROGRESS_ORDER:
            candidate_group = candidate["by_progress_group"].get(group, {})
            baseline_group = baseline_summary["by_progress_group"].get(group, {})
            candidate_parameter = candidate_group.get("parameter", {}).get("aggregate", {}).get("avg_rmse")
            baseline_parameter = baseline_group.get("parameter", {}).get("aggregate", {}).get("avg_rmse")
            candidate_curve = candidate_group.get("curve_rmse")
            baseline_curve = baseline_group.get("curve_rmse")
            by_group[group] = {
                "parameter_rmse_delta_candidate_minus_baseline": (
                    candidate_parameter - baseline_parameter
                    if candidate_parameter is not None and baseline_parameter is not None
                    else None
                ),
                "curve_rmse_delta_candidate_minus_baseline": (
                    candidate_curve - baseline_curve
                    if candidate_curve is not None and baseline_curve is not None
                    else None
                ),
                "candidate_beats_parameter": (
                    candidate_parameter < baseline_parameter
                    if candidate_parameter is not None and baseline_parameter is not None
                    else None
                ),
                "candidate_beats_curve": (
                    candidate_curve < baseline_curve
                    if candidate_curve is not None and baseline_curve is not None
                    else None
                ),
            }
        comparisons[baseline] = {
            "by_progress_group": by_group,
            "first_parameter_win": next(
                (group for group in PROGRESS_ORDER if by_group[group]["candidate_beats_parameter"]),
                None,
            ),
            "first_curve_win": next(
                (group for group in PROGRESS_ORDER if by_group[group]["candidate_beats_curve"]),
                None,
            ),
        }
    return comparisons


def _trend(summary: dict[str, Any]) -> dict[str, Any]:
    """Report aggregate parameter and curve trends by observation count."""
    trends: dict[str, Any] = {}
    for method, method_summary in summary["methods"].items():
        points: list[tuple[int, float | None, float | None]] = []
        for count, values in method_summary["by_observation_count"].items():
            parameter = values["parameter"]["aggregate"]["avg_rmse"]
            points.append((int(count), parameter, values["curve_rmse"]))
        points.sort()
        result: dict[str, Any] = {"points": points}
        for metric_index, name in ((1, "parameter_rmse"), (2, "curve_rmse")):
            valid = [(x, point[metric_index - 1]) for x, *point in points if point[metric_index - 1] is not None]
            if len(valid) >= 2:
                slope = float(np.polyfit([x for x, _ in valid], [y for _, y in valid], 1)[0])
                result[f"{name}_slope"] = slope
                result[f"{name}_generally_improves"] = slope < 0.0
            else:
                result[f"{name}_slope"] = None
                result[f"{name}_generally_improves"] = None
        trends[method] = result
    return trends


def _status_summary(
    examples: tuple[SequentialExample, ...],
    evaluated: dict[str, list[dict[str, Any]]],
    *,
    assignment: str,
) -> dict[str, Any]:
    """Collect fit, invalid-prediction, fallback, and exclusion status."""
    selected_examples = [example for example in examples if example.assignment == assignment]
    return {
        "fit_status_counts": dict(Counter(example.fit_status for example in selected_examples)),
        "reference_status_counts": dict(Counter(example.reference_status for example in selected_examples)),
        "methods": {
            method: {
                "invalid_prediction_count": sum(not row["valid_prediction"] for row in rows),
                "fallback_count": sum(row["fallback_reason"] is not None for row in rows),
                "curve_failure_count": sum(row["curve_status"] not in {"valid", "no_remaining_points"} for row in rows),
            }
            for method, rows in evaluated.items()
        },
    }


def _write_svg_plot(
    path: Path,
    title: str,
    x_labels: list[str],
    series: dict[str, list[float | None]],
    *,
    x_title: str,
    y_title: str,
    horizontal: float | None = None,
) -> None:
    """Write a small dependency-free line plot as SVG."""
    width, height = 960, 540
    left, right, top, bottom = 90, 880, 55, 445
    values = [value for values in series.values() for value in values if value is not None]
    if horizontal is not None:
        values.append(horizontal)
    lower, upper = (min(values), max(values)) if values else (0.0, 1.0)
    if lower == upper:
        padding = max(abs(lower) * 0.05, 1.0)
        lower -= padding
        upper += padding
    else:
        padding = (upper - lower) * 0.05
        lower -= padding
        upper += padding

    def point(index: int, value: float) -> str:
        x = left if len(x_labels) == 1 else left + index * (right - left) / (len(x_labels) - 1)
        y = bottom - (value - lower) * (bottom - top) / (upper - lower)
        return f"{x:.2f},{y:.2f}"

    colors = ("#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c")
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        f'<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width / 2:.0f}" y="28" text-anchor="middle" font-size="18">{escape(title)}</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="black"/>',
        f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="black"/>',
        f'<text x="20" y="{(top + bottom) / 2:.0f}" transform="rotate(-90 20 {(top + bottom) / 2:.0f})" text-anchor="middle">{escape(y_title)}</text>',
        f'<text x="{(left + right) / 2:.0f}" y="510" text-anchor="middle">{escape(x_title)}</text>',
        f'<text x="{left - 10}" y="{bottom + 5}" text-anchor="end" font-size="11">{lower:.4g}</text>',
        f'<text x="{left - 10}" y="{top + 5}" text-anchor="end" font-size="11">{upper:.4g}</text>',
    ]
    for index, label in enumerate(x_labels):
        x = left if len(x_labels) == 1 else left + index * (right - left) / (len(x_labels) - 1)
        lines.append(f'<text x="{x:.2f}" y="465" text-anchor="middle" font-size="11">{escape(label)}</text>')
    if horizontal is not None:
        y = bottom - (horizontal - lower) * (bottom - top) / (upper - lower)
        lines.append(f'<line x1="{left}" y1="{y:.2f}" x2="{right}" y2="{y:.2f}" stroke="#111827" stroke-dasharray="5,4"/>')
    for series_index, (name, values_for_series) in enumerate(series.items()):
        color = colors[series_index % len(colors)]
        segments: list[str] = []
        for index, value in enumerate(values_for_series):
            if value is None:
                if segments:
                    lines.append(f'<polyline points="{" ".join(segments)}" fill="none" stroke="{color}" stroke-width="2"/>')
                    segments = []
                continue
            segments.append(point(index, float(value)))
        if segments:
            lines.append(f'<polyline points="{" ".join(segments)}" fill="none" stroke="{color}" stroke-width="2"/>')
        legend_x = left + series_index * 175
        lines.extend([
            f'<line x1="{legend_x}" y1="{height - 20}" x2="{legend_x + 22}" y2="{height - 20}" stroke="{color}" stroke-width="3"/>',
            f'<text x="{legend_x + 28}" y="{height - 16}" font-size="12">{escape(name)}</text>',
        ])
    lines.append("</svg>")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_svg_plots(
    output_dir: Path,
    summary: dict[str, Any],
    rows: dict[str, list[dict[str, Any]]],
) -> list[str]:
    """Write the required plots without an optional plotting dependency."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    progress_labels = list(PROGRESS_ORDER)
    parameter_series = {
        method: [
            summary["methods"][method]["by_progress_group"].get(group, {}).get("parameter", {}).get("aggregate", {}).get("avg_rmse")
            for group in progress_labels
        ]
        for method in METHOD_ORDER
        if method in summary["methods"]
    }
    path = output_dir / "parameter_rmse_by_progress.svg"
    _write_svg_plot(path, "Parameter RMSE by progress group", progress_labels, parameter_series, x_title="Progress group", y_title="RMSE")
    written.append(path.name)

    curve_series = {
        method: [
            summary["methods"][method]["by_progress_group"].get(group, {}).get("curve_rmse")
            for group in progress_labels
        ]
        for method in METHOD_ORDER
        if method in summary["methods"]
    }
    path = output_dir / "remaining_curve_rmse_by_progress.svg"
    _write_svg_plot(path, "Remaining-curve RMSE by progress group", progress_labels, curve_series, x_title="Progress group", y_title="RMSE")
    written.append(path.name)

    for target_index, target in enumerate(TARGET_COLUMNS):
        series: dict[str, list[float | None]] = {}
        for method in METHOD_ORDER:
            method_rows = [row for row in rows.get(method, []) if row["valid_prediction"]]
            grouped: dict[int, list[float]] = defaultdict(list)
            for row in method_rows:
                grouped[int(row["observation_count"])].append(float(row["prediction"][target_index]))
            series[method] = [float(np.mean(grouped[count])) if count in grouped else None for count in sorted(grouped)]
        counts = sorted({int(row["observation_count"]) for method in rows for row in rows[method] if row["valid_prediction"]})
        series = {
            method: [
                float(np.mean([row["prediction"][target_index] for row in rows.get(method, []) if row["valid_prediction"] and row["observation_count"] == count]))
                if any(row["valid_prediction"] and row["observation_count"] == count for row in rows.get(method, []))
                else None
                for count in counts
            ]
            for method in METHOD_ORDER
            if method in rows
        }
        reference_rows = [row for row in rows.get("selected_model", []) if row["valid_prediction"]]
        reference = float(np.mean([row["reference"][target_index] for row in reference_rows])) if reference_rows else None
        path = output_dir / f"parameter_predictions_{target}.svg"
        _write_svg_plot(path, f"Predicted {target} by observation count", [str(count) for count in counts], series, x_title="Observation count", y_title=target, horizontal=reference)
        written.append(path.name)

    selected_rows = [row for row in rows.get("selected_model", []) if row.get("curve_rmse") is not None and row.get("curve_times") is not None]
    if selected_rows:
        series: dict[str, list[float | None]] = {}
        for index, row in enumerate(selected_rows[:3]):
            times = np.asarray(row["curve_times"], dtype=float)
            prediction = np.asarray(row["curve_prediction"], dtype=float)
            series[f"forecast_{index + 1}"] = [float(value) for value in prediction]
            series[f"observed_{index + 1}"] = [float(value) for value in row["observations"][1]]
        max_length = max(len(values) for values in series.values())
        series = {
            name: values + [None] * (max_length - len(values))
            for name, values in series.items()
        }
        path = output_dir / "remaining_curve_examples.svg"
        _write_svg_plot(path, "Observed and predicted remaining curves", [str(index + 1) for index in range(max_length)], series, x_title="Timeline point", y_title="Area")
        written.append(path.name)
    return written


def _write_plots(
    output_dir: Path,
    summary: dict[str, Any],
    rows: dict[str, list[dict[str, Any]]],
) -> list[str]:
    """Write required progress, parameter, and remaining-curve plots."""
    if plt is None:
        return _write_svg_plots(output_dir, summary, rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    figure, axis = plt.subplots(figsize=(8, 5))
    for method in METHOD_ORDER:
        if method not in summary["methods"]:
            continue
        values = [
            summary["methods"][method]["by_progress_group"].get(group, {}).get("parameter", {}).get("aggregate", {}).get("avg_rmse")
            for group in PROGRESS_ORDER
        ]
        axis.plot(PROGRESS_ORDER, values, marker="o", label=method)
    axis.set(title="Parameter RMSE by progress group", xlabel="Progress group", ylabel="RMSE")
    axis.legend()
    figure.tight_layout()
    path = output_dir / "parameter_rmse_by_progress.png"
    figure.savefig(path, dpi=150)
    plt.close(figure)
    written.append(path.name)

    figure, axis = plt.subplots(figsize=(8, 5))
    for method in METHOD_ORDER:
        if method not in summary["methods"]:
            continue
        values = [
            summary["methods"][method]["by_progress_group"].get(group, {}).get("curve_rmse")
            for group in PROGRESS_ORDER
        ]
        axis.plot(PROGRESS_ORDER, values, marker="o", label=method)
    axis.set(title="Remaining-curve RMSE by progress group", xlabel="Progress group", ylabel="RMSE")
    axis.legend()
    figure.tight_layout()
    path = output_dir / "remaining_curve_rmse_by_progress.png"
    figure.savefig(path, dpi=150)
    plt.close(figure)
    written.append(path.name)

    targets = list(TARGET_COLUMNS)
    figure, axes = plt.subplots(2, 3, figsize=(14, 8), squeeze=False)
    for index, target in enumerate(targets):
        axis = axes[index // 3][index % 3]
        for method in METHOD_ORDER:
            method_rows = [row for row in rows.get(method, []) if row["valid_prediction"]]
            if not method_rows:
                continue
            x = [row["observation_count"] for row in method_rows]
            y = [row["prediction"][index] for row in method_rows]
            axis.scatter(x, y, s=4, alpha=0.15, label=method)
        reference_rows = [row for row in rows.get("selected_model", []) if row["valid_prediction"]]
        if reference_rows:
            axis.axhline(float(np.mean([row["reference"][index] for row in reference_rows])), color="black", linestyle="--", linewidth=1)
        axis.set_title(target)
        axis.set_xlabel("Observation count")
        axis.set_ylabel("Parameter value")
    handles, labels = axes[0][0].get_legend_handles_labels()
    if handles:
        figure.legend(handles, labels, loc="upper center", ncol=4)
    figure.tight_layout(rect=(0, 0, 1, 0.95))
    path = output_dir / "parameter_predictions_by_progress.png"
    figure.savefig(path, dpi=150)
    plt.close(figure)
    written.append(path.name)

    selected_rows = [row for row in rows.get("selected_model", []) if row["curve_rmse"] is not None]
    if selected_rows:
        chosen = selected_rows[: min(3, len(selected_rows))]
        figure, axes = plt.subplots(len(chosen), 1, figsize=(10, 4 * len(chosen)), squeeze=False)
        for index, row in enumerate(chosen):
            axis = axes[index][0]
            example = row["example"]
            times, observed = row["observations"]
            curve_times = row["curve_times"]
            predicted = row["curve_prediction"]
            axis.plot(times, observed, label="observed", color="black")
            axis.plot(curve_times, predicted, label="selected forecast", color="tab:blue")
            axis.axvline(example.cutoff_time_s, linestyle="--", color="tab:red", label="cutoff")
            axis.set_title(f"{example.experiment_id} / {example.cutoff_id}")
            axis.set_xlabel("Time (s)")
            axis.set_ylabel("Area")
            axis.legend()
        figure.tight_layout()
        path = output_dir / "remaining_curve_examples.png"
        figure.savefig(path, dpi=150)
        plt.close(figure)
        written.append(path.name)
    return written


def _report_markdown(report: dict[str, Any], plot_names: list[str]) -> str:
    """Render a concise auditable evaluation report."""
    lines = [
        "# Sequential Forecasting Evaluation Report",
        "",
        f"- **Assignment:** `{report['assignment']}`",
        f"- **Selected candidate:** `{report['selection']['selected_candidate']}`",
        f"- **Test used for selection:** `{report['selection']['test_used_for_selection']}`",
        f"- **Evaluated experiments:** {report['metrics']['methods']['selected_model']['overall']['experiment_count']}",
        f"- **Evaluated cutoff records:** {report['metrics']['methods']['selected_model']['overall']['count']}",
        f"- **Source experiments:** {report['data']['experiment_count']}",
        f"- **Source cutoff records:** {report['data']['cutoff_count']}",
        "",
        "## Data and exclusions",
        "",
        f"- Data root: `{report['data']['data_root']}`",
        f"- Excluded folders: {', '.join(report['data']['exclude_folders'])}",
        f"- Excluded-by-folder records: {report['data']['excluded_by_folder_count']}",
        f"- Collision clusters: {report['data']['collision_count']}",
        "",
        "## Aggregate results",
        "",
        "| Method | Parameter RMSE | Parameter R² | Curve RMSE | Valid predictions | Valid curves |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for method in METHOD_ORDER:
        values = report["metrics"].get("methods", {}).get(method)
        if values is None:
            continue
        overall = values["overall"]
        aggregate = overall["parameter"]["aggregate"]
        lines.append(
            f"| {method} | {aggregate['avg_rmse']:.6f} | {aggregate['avg_r2']:.6f} | "
            f"{overall['curve_rmse']:.6f} | {overall['valid_prediction_count']} | {overall['valid_curve_count']} |"
        )
    lines.extend(["", "## Candidate comparison", "", "```json", json.dumps(report["comparison"], indent=2), "```", ""])
    lines.extend(["## Status and fallbacks", "", "```json", json.dumps(report["status"], indent=2), "```", ""])
    lines.extend(["## Plots", ""])
    lines.extend(f"- `{name}`" for name in plot_names)
    lines.extend(["", "## Constraints", "", "```json", json.dumps(report["constraints"], indent=2), "```", ""])
    lines.extend(["## Reproducibility", "", "```json", json.dumps(report["selection"], indent=2), "```", ""])
    return "\n".join(lines)


def run_evaluation(
    artifact_dir: str | Path,
    *,
    baseline_dir: str | Path | None = None,
    inference_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    assignment: str = "test",
) -> Path:
    """Evaluate frozen predictions and write JSON, plots, and Markdown."""
    artifact_path = Path(artifact_dir)
    baseline_path = Path(baseline_dir) if baseline_dir is not None else artifact_path / "baselines"
    inference_path = Path(inference_dir) if inference_dir is not None else artifact_path / "inference"
    output_path = Path(output_dir) if output_dir is not None else artifact_path / "evaluation"

    examples = build_examples_from_artifacts(artifact_path)
    observations = _load_observations(examples)
    baseline_records = _read_jsonl(baseline_path / "predictions.jsonl")
    inference_records = _read_jsonl(inference_path / "predictions.jsonl")
    baseline_manifest = json.loads((baseline_path / "manifest.json").read_text(encoding="utf-8"))
    model_manifest = json.loads((artifact_path / "sequential_model" / "manifest.json").read_text(encoding="utf-8"))
    if model_manifest.get("test_used_for_selection"):
        raise ValueError("Cannot run final evaluation: test data was used for selection")

    method_records = {
        "rf_only": [record for record in baseline_records if record.get("baseline") == "rf_only"],
        "current_ode": [record for record in baseline_records if record.get("baseline") == "current_ode"],
        "rf_ode_blend": [record for record in baseline_records if record.get("baseline") == "rf_ode_blend"],
        "selected_model": inference_records,
    }
    evaluated = evaluate_records(examples, observations, method_records, assignment=assignment)
    plot_rows = {
        method: [
            {
                **row,
                "example": _example_index(examples)[(row["experiment_id"], row["cutoff_id"])],
                "observations": observations[row["experiment_id"]],
                "curve_times": np.asarray(
                    next(
                        record.get("curve_times_s")
                        for record in inference_records
                        if record.get("cutoff_id") == row["cutoff_id"]
                    ),
                    dtype=float,
                )
                if method == "selected_model" and any(record.get("cutoff_id") == row["cutoff_id"] for record in inference_records)
                else np.empty(0),
                "curve_prediction": np.asarray(
                    next(
                        record.get("curve_predicted_area")
                        for record in inference_records
                        if record.get("cutoff_id") == row["cutoff_id"]
                    ),
                    dtype=float,
                )
                if method == "selected_model" and any(record.get("cutoff_id") == row["cutoff_id"] for record in inference_records)
                else np.empty(0),
            }
            for row in rows
        ]
        for method, rows in evaluated["rows"].items()
    }
    plot_names = _write_plots(output_path / "plots", evaluated, plot_rows)

    run_config = json.loads((artifact_path / "run_config.json").read_text(encoding="utf-8"))
    validation_report = json.loads((artifact_path / "phase1" / "validation_report.json").read_text(encoding="utf-8"))
    report = {
        "assignment": assignment,
        "selection": {
            "selected_candidate": model_manifest.get("selected_candidate"),
            "learned_model_selected": model_manifest.get("learned_model_selected", False),
            "test_used_for_selection": model_manifest.get("test_used_for_selection", False),
            "training_experiment_count": model_manifest.get("training_experiment_count"),
            "validation_experiment_count": model_manifest.get("validation_experiment_count"),
            "training_example_fingerprint": model_manifest.get("training_example_fingerprint"),
            "validation_example_fingerprint": model_manifest.get("validation_example_fingerprint"),
            "validation_selected_blend_weight": baseline_manifest.get("blend_weight"),
        },
        "data": {
            "data_root": run_config.get("data_root"),
            "exclude_folders": run_config.get("exclude_folders", []),
            "excluded_by_folder_count": validation_report.get("excluded_by_folder_count"),
            "experiment_count": validation_report.get("experiment_count"),
            "cutoff_count": validation_report.get("cutoff_count"),
            "collision_count": validation_report.get("collision_count"),
            "fit_status_counts": validation_report.get("fit_status_counts", {}),
        },
        "constraints": {
            "target_order": run_config.get("target_order", list(TARGET_COLUMNS)),
            "q0": "passed through from the first observation; not learned",
            "parameter_bounds": {
                "k_a": [0.0, 0.01],
                "k_s": [0.0, 0.01],
                "k_p": "[0, k_a]",
                "q_e": "non-negative; fit-dependent upper bound 2 * q_guess",
                "q_inf": "non-negative; fit-dependent upper bound 2 * q_guess",
            },
            "solver": "solve_ivp RK45, rtol=1e-8, configured timeout",
            "timestamp_tolerance_s": run_config.get("time_tolerance_s"),
            "remaining_curve_metric": "RMSE on observed points strictly after each cutoff",
        },
        "metrics": {"assignment": assignment, "methods": evaluated["methods"]},
        "comparison": _comparison(evaluated),
        "trends": _trend(evaluated),
        "status": _status_summary(examples, evaluated["rows"], assignment=assignment),
        "plots": plot_names,
    }
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "report.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
    )
    (output_path / "report.md").write_text(
        _report_markdown(report, plot_names), encoding="utf-8"
    )
    return output_path
