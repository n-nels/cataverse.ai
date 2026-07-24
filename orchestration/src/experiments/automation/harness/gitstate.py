"""Git state capture and discard-via-reset for the autoresearch branch.

The harness records git state (branch, commit, dirty flag) for traceability and
implements the discard mechanism as ``git reset --hard <prev>`` on the dedicated
autoresearch branch.

Destructive operations are permitted ONLY on the autoresearch branch; this module
refuses to run them on any other branch.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path

AUTORESEARCH_PREFIX = "autoresearch/"


class GitError(RuntimeError):
    pass


def _run(args: list[str], cwd: str | Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip()


@dataclass
class GitState:
    branch: str
    commit: str
    dirty: bool

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


def is_autoresearch_branch(branch: str) -> bool:
    return branch.startswith(AUTORESEARCH_PREFIX)


def current_state(cwd: str | Path) -> GitState:
    branch = _run(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    commit = _run(["rev-parse", "HEAD"], cwd)
    status = _run(["status", "--porcelain"], cwd)
    return GitState(branch=branch, commit=commit, dirty=bool(status))


def assert_clean_tree(cwd: str | Path) -> None:
    state = current_state(cwd)
    if state.dirty:
        raise GitError(f"working tree is not clean on branch {state.branch!r}")


def assert_autoresearch_branch(cwd: str | Path) -> GitState:
    state = current_state(cwd)
    if not is_autoresearch_branch(state.branch):
        raise GitError(
            f"current branch {state.branch!r} is not an autoresearch branch; "
            f"destructive operations are only permitted on {AUTORESEARCH_PREFIX}* branches"
        )
    return state


def commit_all(cwd: str | Path, message: str) -> str:
    """Stage all changes and commit. Returns the new commit hash."""
    _run(["add", "-A"], cwd)
    _run(["commit", "-m", message, "--allow-empty"], cwd)
    return _run(["rev-parse", "HEAD"], cwd)


def discard_to(cwd: str | Path, prev_commit: str) -> None:
    """Hard-reset the current autoresearch branch to ``prev_commit``.

    Refuses unless the current branch is an autoresearch branch.
    """
    assert_autoresearch_branch(cwd)
    _run(["reset", "--hard", prev_commit], cwd)


def create_branch(cwd: str | Path, branch_name: str) -> None:
    if not is_autoresearch_branch(branch_name):
        raise GitError(
            f"refusing to create non-autoresearch branch {branch_name!r}"
        )
    _run(["checkout", "-b", branch_name], cwd)