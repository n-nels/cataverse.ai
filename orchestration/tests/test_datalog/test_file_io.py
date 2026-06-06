from __future__ import annotations

import csv

from src.datalog.file_io import (
    create_directory,
    log_to_csv,
)


def test_create_directory_makes_missing_path(tmp_path: Path) -> None:
    target_dir = tmp_path / "new_dir"
    assert not target_dir.exists()

    create_directory(str(target_dir))

    assert target_dir.exists()
    assert target_dir.is_dir()


def test_create_directory_is_idempotent_when_path_exists(tmp_path: Path) -> None:
    target_dir = tmp_path / "existing"
    target_dir.mkdir()

    create_directory(str(target_dir))

    assert target_dir.exists()
    assert target_dir.is_dir()


def test_log_to_csv_writes_headers_then_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    headers = ["A", "B"]
    rows = [[1, 2], [3, 4]]

    log_to_csv(str(csv_path), headers, rows)

    with csv_path.open("r", newline="") as f:
        content = list(csv.reader(f))

    assert content == [["A", "B"], ["1", "2"], ["3", "4"]]


def test_log_to_csv_appends_rows_without_duplicate_header(tmp_path: Path) -> None:
    csv_path = tmp_path / "append.csv"
    headers = ["A", "B"]

    log_to_csv(str(csv_path), headers, [[1, 2]])
    log_to_csv(str(csv_path), headers, [[3, 4]])

    with csv_path.open("r", newline="") as f:
        content = list(csv.reader(f))

    assert content == [["A", "B"], ["1", "2"], ["3", "4"]]



