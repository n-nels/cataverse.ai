from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import patch

from src.datalog.file_io import (
    copy_to_share_drive,
    create_directory,
    log_to_csv,
    write_material_parameters,
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


def test_write_material_parameters_creates_readme_sections(tmp_path: Path) -> None:
    readme_path = tmp_path / "exp_README.md"

    write_material_parameters(
        path_readme=str(readme_path),
        notebook="nn1120-3",
        mass=0.0164,
        metal="pd",
        metal_load=0.04983,
        metal_density=0.523,
        support="ceo2",
        support_sa=54.0,
        v_tot=0.201552,
    )

    content = readme_path.read_text(encoding="utf-8")
    assert "## notebook" in content
    assert "- Value: nn1120-3" in content
    assert "## mass" in content
    assert "## pd_loading" in content
    assert "## mfldVol" in content


def test_write_material_parameters_noop_when_readme_exists(tmp_path: Path) -> None:
    readme_path = tmp_path / "exp_README.md"
    readme_path.write_text("existing content\n", encoding="utf-8")

    write_material_parameters(
        path_readme=str(readme_path),
        notebook="nn1120-3",
        mass=0.0164,
        metal="pd",
        metal_load=0.04983,
        metal_density=0.523,
        support="ceo2",
        support_sa=54.0,
        v_tot=0.201552,
    )

    assert readme_path.read_text(encoding="utf-8") == "existing content\n"


def test_copy_to_share_drive_copies_file_to_suffixed_destination(tmp_path: Path) -> None:
    src = tmp_path / "source.txt"
    src.write_text("hello", encoding="utf-8")

    dest_folder = tmp_path / "share"
    file_name = "exp001"
    suffix = "README.md"

    with patch("src.datalog.file_io.time.sleep") as sleep_mock:
        copy_to_share_drive(
            src_path=str(src),
            dest_folder=str(dest_folder),
            file_name=file_name,
            suffix=suffix,
        )

    sleep_mock.assert_called_once_with(10)

    copied = dest_folder / f"{file_name}_{suffix}"
    assert copied.exists()
    assert copied.read_text(encoding="utf-8") == "hello"


def test_copy_to_share_drive_ioerror_is_handled(tmp_path: Path) -> None:
    src = tmp_path / "source.txt"
    src.write_text("hello", encoding="utf-8")

    dest_folder = tmp_path / "share"

    with (
        patch("src.datalog.file_io.shutil.copy", side_effect=IOError("copy failed")),
        patch("src.datalog.file_io.logger") as logger_mock,
    ):
        copy_to_share_drive(
            src_path=str(src),
            dest_folder=str(dest_folder),
            file_name="exp001",
            suffix="README.md",
        )

    logger_mock.error.assert_called_once()
