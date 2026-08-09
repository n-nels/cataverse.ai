"""Repository and dependency provenance collection."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
import subprocess


def _git_metadata(repository: Path) -> dict[str, object]:
    """Read repository revision state without changing the repository."""
    try:
        commit = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "-C", str(repository), "branch", "--show-current"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        git_root = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "-C", str(repository), "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return {
            "path": str(repository),
            "git_root": git_root,
            "commit": commit,
            "branch": branch,
            "dirty": dirty,
        }
    except (OSError, subprocess.CalledProcessError) as error:
        return {"path": str(repository), "error": str(error)}


def collect_provenance() -> dict[str, object]:
    """Collect repository and dependency provenance for a run."""
    orchestration_root = Path(__file__).resolve().parents[5]
    workspace_root = orchestration_root.parent
    sibling_root = workspace_root / "ir-spectro-node"
    package_versions: dict[str, str] = {}
    for package in ("numpy", "pandas", "scipy", "scikit-learn", "joblib"):
        try:
            package_versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            package_versions[package] = "unavailable"
    return {
        "python": __import__("platform").python_version(),
        "repositories": [
            _git_metadata(orchestration_root),
            _git_metadata(sibling_root),
        ],
        "dependencies": package_versions,
    }
