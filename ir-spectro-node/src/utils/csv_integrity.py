"""Detect torn or partially written analysis CSVs.

Read-only. Two kinds of damage are looked for:

- **Torn lines**: a line whose field count differs from the header, or a file
  that does not end in a newline. This is what a partial write looks like
  before anything reads the file back.
- **Garbage keys**: a row whose key column is not a valid value (``File`` not
  ``deltaN.NNNN``, a blank ``Peak_Name``, ...). This is what a torn line looks
  like after live's read-concat-write (``output.save_data``) has read it back
  and rewritten it as a full-width row. That is how the three nn1120-3_003
  fragments were found (docs/spec-live-migration.md §2.2, O2).

Duplicate ``(File, Peak_Name)`` rows in a params CSV are reported too: they
mean a spectrum was saved twice.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

FILE_RE = re.compile(r"delta\d+\.\d+")
#: Pre-2025-02 residual files hold fit/residual/data columns per delta group.
LEGACY_RESIDUAL_COLUMN_RE = re.compile(r"delta\d+_(fit|residual|data)")
DELTA_GROUP_RE = re.compile(r"delta\d+")
PEAK_NAME_RE = re.compile(r"Peak_\d+(\.\d+)?")
SUM_NAMES = frozenset({"monomer_sum", "cluster_sum"})

PARAMS = "_CarbonylPeakFitParams.csv"
AREA = "_CarbonylPeakArea.csv"
RESIDUAL = "_CarbonylFitResidual.csv"
BASELINE = "_CarbonylFitBaseline.csv"
KINETIC_PARAMS = "_CarbonylKineticParams.csv"
KINETIC_FEATURES = "_CarbonylKineticFeatures.csv"
WAVENUMBER = "Wavenumber (cm-1)"


@dataclass
class Issue:
    path: Path
    line: int | None
    kind: str
    detail: str


def check_lines(path: Path) -> list[Issue]:
    """Field count per line against the header, and the trailing newline."""
    issues: list[Issue] = []
    raw = path.read_bytes()
    if not raw:
        return [Issue(path, None, "empty", "file is empty")]
    if not raw.endswith(b"\n"):
        issues.append(Issue(path, None, "no_trailing_newline", "last line is incomplete"))
    reader = csv.reader(raw.decode("utf-8", errors="replace").splitlines())
    header = next(reader, [])
    for line_no, fields in enumerate(reader, start=2):
        if not fields:
            # A whole-line tail of a longer, overlapping write looks like this.
            issues.append(Issue(path, line_no, "blank_line", "empty line"))
            continue
        if len(fields) != len(header):
            preview = ",".join(fields)[:80]
            issues.append(
                Issue(
                    path,
                    line_no,
                    "field_count",
                    f"{len(fields)} fields, header has {len(header)}: {preview}",
                )
            )
    return issues


def _bad_rows(
    path: Path, df: pd.DataFrame, column: str, valid, kind: str
) -> list[Issue]:
    if column not in df.columns:
        return [Issue(path, None, "missing_column", column)]
    issues = []
    for index, value in df[column].items():
        if not isinstance(value, str) or not valid(value):
            # +2: 1-based, plus the header line.
            issues.append(Issue(path, int(index) + 2, kind, f"{column}={value!r}"))
    return issues


def _is_peak(value: str) -> bool:
    return bool(PEAK_NAME_RE.fullmatch(value))


def _is_peak_or_sum(value: str) -> bool:
    return value in SUM_NAMES or _is_peak(value)


def check_long(path: Path, sums: bool) -> list[Issue]:
    """Params and area CSVs: one row per (File, Peak_Name)."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    issues = _bad_rows(path, df, "File", lambda v: bool(FILE_RE.fullmatch(v)), "bad_file")
    issues += _bad_rows(
        path,
        df,
        "Delta_Group",
        lambda v: bool(DELTA_GROUP_RE.fullmatch(v)),
        "bad_delta_group",
    )
    issues += _bad_rows(
        path, df, "Peak_Name", _is_peak_or_sum if sums else _is_peak, "bad_peak_name"
    )
    if {"File", "Peak_Name"} <= set(df.columns):
        duplicated = df.duplicated(subset=["File", "Peak_Name"], keep="first")
        for index in df.index[duplicated]:
            issues.append(
                Issue(
                    path,
                    int(index) + 2,
                    "duplicate_row",
                    f"File={df.at[index, 'File']} Peak_Name={df.at[index, 'Peak_Name']}",
                )
            )
    return issues


def check_wide(path: Path) -> list[Issue]:
    """Residual and baseline CSVs: a wavenumber column plus one column per File."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    issues = []
    if WAVENUMBER not in df.columns:
        return [Issue(path, None, "missing_column", WAVENUMBER)]
    for column in df.columns:
        # pandas renames a repeated column to "<name>.1", which no longer
        # matches the deltaN.NNNN form.
        if column == WAVENUMBER or FILE_RE.fullmatch(column):
            continue
        if not LEGACY_RESIDUAL_COLUMN_RE.fullmatch(column):
            issues.append(Issue(path, None, "bad_column", repr(column)))
    wavenumbers = pd.to_numeric(df[WAVENUMBER], errors="coerce")
    for index in df.index[wavenumbers.isna()]:
        issues.append(
            Issue(path, int(index) + 2, "bad_wavenumber", repr(df.at[index, WAVENUMBER]))
        )
    return issues


def check_kinetic(path: Path, suffix: str, one_row: bool) -> list[Issue]:
    """Kinetic params/features: every row names this measurement."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    measurement = path.name.removesuffix(suffix)
    issues = _bad_rows(
        path, df, "Measurement", lambda v: v == measurement, "bad_measurement"
    )
    if one_row and len(df) != 1:
        issues.append(Issue(path, None, "row_count", f"{len(df)} rows, expected 1"))
    if not one_row:
        issues += _bad_rows(path, df, "Peak_Name", _is_peak_or_sum, "bad_peak_name")
    return issues


def check_file(path: Path) -> list[Issue]:
    """All checks that apply to one CSV, chosen by its suffix."""
    path = Path(path)
    try:
        issues = check_lines(path)
        name = path.name
        if name.endswith(PARAMS):
            issues += check_long(path, sums=False)
        elif name.endswith(AREA):
            issues += check_long(path, sums=True)
        elif name.endswith((RESIDUAL, BASELINE)):
            issues += check_wide(path)
        elif name.endswith(KINETIC_PARAMS):
            issues += check_kinetic(path, KINETIC_PARAMS, one_row=False)
        elif name.endswith(KINETIC_FEATURES):
            issues += check_kinetic(path, KINETIC_FEATURES, one_row=True)
    except Exception as exc:  # unreadable is itself a finding
        issues = [Issue(path, None, "unreadable", f"{type(exc).__name__}: {exc}")]
    return issues


def find_csvs(folder: Path, recursive: bool = False) -> list[Path]:
    """The ``*_Carbonyl*.csv`` files in a folder (and below, if recursive)."""
    pattern = "**/*_Carbonyl*.csv" if recursive else "*_Carbonyl*.csv"
    return sorted(p for p in Path(folder).glob(pattern) if p.is_file())


def check_folder(folder: Path, recursive: bool = False) -> tuple[int, list[Issue]]:
    """Check every carbonyl CSV in a folder. Returns (files checked, issues)."""
    files = find_csvs(folder, recursive)
    issues: list[Issue] = []
    for path in files:
        issues += check_file(path)
    return len(files), issues


def main(argv: list[str] | None = None) -> int:
    """CLI: check datasets under ``data.peak_fit``, or any folder path."""
    import argparse

    from src.core import config

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--folder",
        nargs="+",
        help="dataset name(s) under data.peak_fit, or folder path(s)",
    )
    target.add_argument(
        "--all", action="store_true", help="every dataset under data.peak_fit"
    )
    parser.add_argument(
        "--subfolder",
        default="",
        help="check this subfolder of each dataset, e.g. _reprocess",
    )
    parser.add_argument(
        "--recursive", action="store_true", help="also check every folder below"
    )
    args = parser.parse_args(argv)

    root = Path(config.get_path("data.peak_fit"))
    if args.all:
        folders = sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith("nn"))
    else:
        folders = [Path(f) if Path(f).is_absolute() else root / f for f in args.folder]

    total_files = 0
    total_issues: list[Issue] = []
    for folder in folders:
        folder = folder / args.subfolder if args.subfolder else folder
        if not folder.is_dir():
            print(f"{folder}: not found")
            continue
        n_files, issues = check_folder(folder, args.recursive)
        total_files += n_files
        total_issues += issues
        status = "OK" if not issues else f"{len(issues)} issue(s)"
        print(f"{folder}: {n_files} files, {status}")
        for issue in issues:
            where = f":{issue.line}" if issue.line else ""
            print(f"  {issue.kind:<20} {issue.path.relative_to(folder)}{where}  {issue.detail}")

    print(f"Checked {total_files} files: {len(total_issues)} issue(s).")
    return 1 if total_issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
