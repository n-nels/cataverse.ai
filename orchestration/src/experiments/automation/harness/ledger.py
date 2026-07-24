"""Append-only results ledger (``automation/results.tsv``).

The ledger is the durable record of every trial in a campaign, including
discarded and crashed trials. It is untracked by git and never overwritten.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

LEDGER_COLUMNS = (
    "commit",
    "experiment_id",
    "model",
    "validation_avg_rmse",
    "validation_avg_r2",
    "test_avg_rmse",
    "test_avg_r2",
    "runtime_minutes",
    "status",
    "description",
)

ALLOWED_STATUSES = {"keep", "discard", "crash", "invalid"}


@dataclass
class LedgerRow:
    commit: str
    experiment_id: str
    model: str
    validation_avg_rmse: str
    validation_avg_r2: str
    test_avg_rmse: str
    test_avg_r2: str
    runtime_minutes: str
    status: str
    description: str

    def as_row(self) -> list[str]:
        return [
            self.commit, self.experiment_id, self.model,
            self.validation_avg_rmse, self.validation_avg_r2,
            self.test_avg_rmse, self.test_avg_r2,
            self.runtime_minutes, self.status, self.description,
        ]


def _fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def make_row(
    commit: str,
    experiment_id: str,
    model: str,
    status: str,
    description: str,
    runtime_minutes: float | None = None,
    validation_avg_rmse: float | None = None,
    validation_avg_r2: float | None = None,
    test_avg_rmse: float | None = None,
    test_avg_r2: float | None = None,
) -> LedgerRow:
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"invalid status {status!r}; allowed: {sorted(ALLOWED_STATUSES)}")
    return LedgerRow(
        commit=commit,
        experiment_id=experiment_id,
        model=model,
        validation_avg_rmse=_fmt(validation_avg_rmse),
        validation_avg_r2=_fmt(validation_avg_r2),
        test_avg_rmse=_fmt(test_avg_rmse),
        test_avg_r2=_fmt(test_avg_r2),
        runtime_minutes="" if runtime_minutes is None else f"{runtime_minutes:.2f}",
        status=status,
        description=description,
    )


def ledger_path(automation_dir: str | Path) -> Path:
    return Path(automation_dir) / "results.tsv"


def init_ledger(automation_dir: str | Path) -> None:
    """Create the ledger with a header row if it does not exist."""
    path = ledger_path(automation_dir)
    if path.exists():
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(LEDGER_COLUMNS)


def append_row(automation_dir: str | Path, row: LedgerRow) -> None:
    path = ledger_path(automation_dir)
    if not path.exists():
        init_ledger(automation_dir)
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(row.as_row())


def read_rows(automation_dir: str | Path) -> list[LedgerRow]:
    path = ledger_path(automation_dir)
    if not path.exists():
        return []
    rows: list[LedgerRow] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            rows.append(LedgerRow(**{c: r.get(c, "") for c in LEDGER_COLUMNS}))
    return rows


def best_kept_row(automation_dir: str | Path) -> LedgerRow | None:
    """Return the kept row with the lowest validation_avg_rmse, or None."""
    kept = [r for r in read_rows(automation_dir) if r.status == "keep"]
    kept = [r for r in kept if r.validation_avg_rmse not in ("", "0.000000")]
    if not kept:
        return None
    return min(kept, key=lambda r: float(r.validation_avg_rmse))