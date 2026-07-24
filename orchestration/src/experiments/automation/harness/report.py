"""Generate the final campaign report (``report.md``)."""

from __future__ import annotations

from pathlib import Path


REPORT_RECOMMENDATIONS = (
    "retain for human review",
    "no improvement found",
    "experiment failed",
    "needs human decision",
)


def build_report(
    experiment_id: str,
    branch: str,
    starting_commit: str,
    ending_commit: str,
    model_name: str,
    baseline_experiment: str,
    dataset_fingerprint: dict,
    split_fingerprint: dict,
    trials_attempted: int,
    successful_trials: int,
    failed_trials: int,
    best_validation: float | None,
    baseline_validation: float | None,
    best_test: float | None,
    baseline_test: float | None,
    best_config: dict | None,
    recommendation: str,
    changed_source_files: list[str],
    protected_files_unchanged: list[str],
) -> str:
    if recommendation not in REPORT_RECOMMENDATIONS:
        raise ValueError(
            f"invalid recommendation {recommendation!r}; "
            f"must be one of {REPORT_RECOMMENDATIONS}"
        )

    def fmt(v: float | None) -> str:
        return "n/a" if v is None else f"{v:.6f}"

    lines = [
        f"# Experiment Report: {experiment_id}",
        "",
        f"- **Branch:** {branch}",
        f"- **Starting commit:** {starting_commit}",
        f"- **Ending commit:** {ending_commit}",
        f"- **Model tested:** {model_name}",
        f"- **Baseline used:** {baseline_experiment}",
        f"- **Dataset fingerprint:** {dataset_fingerprint.get('hash', 'n/a')}",
        f"- **Split fingerprint:** {split_fingerprint.get('hash', 'n/a')}",
        "",
        "## Trials",
        "",
        f"- Trials attempted: {trials_attempted}",
        f"- Successful trials: {successful_trials}",
        f"- Failed trials: {failed_trials}",
        "",
        "## Results",
        "",
        f"- Best validation avg RMSE: {fmt(best_validation)}",
        f"- Baseline validation avg RMSE: {fmt(baseline_validation)}",
        f"- Best test avg RMSE: {fmt(best_test)}",
        f"- Baseline test avg RMSE: {fmt(baseline_test)}",
        "",
        "## Best retained configuration",
        "",
        "```yaml" if best_config else "_none_",
    ]
    if best_config:
        import yaml
        lines.append(yaml.safe_dump(best_config, sort_keys=False).strip())
        lines.append("```")
    lines += [
        "",
        "## Recommendation",
        "",
        f"**{recommendation}**",
        "",
        "## Changed source files",
        "",
    ]
    lines += [f"- {f}" for f in changed_source_files] or ["_none_"]
    lines += [
        "",
        "## Protected files confirmed unchanged",
        "",
    ]
    lines += [f"- {f}" for f in protected_files_unchanged] or ["_none_"]
    lines.append("")
    return "\n".join(lines)


def write_report(dir_path: str | Path, report_text: str) -> None:
    Path(dir_path).joinpath("report.md").write_text(report_text, encoding="utf-8")