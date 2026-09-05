r"""Backing the share drive up to S3.

Scope is deliberately wider than the graph's. The graph models a handful of
file kinds; this copies everything, on the grounds that a backup you have to
curate is a backup you will regret. Modelling more of it later needs no
re-upload.

**Keys mirror the share.** An object's key is its path relative to the share
root, so `D:\peakFit\nn1120-3_pd_ceo2_004\x.csv` becomes
`peakFit/nn1120-3_pd_ceo2_004/x.csv`.

That is a change from the first design in spec.md §5g, which keyed by
`base_name` and deliberately left the notebook folder out so that reorganising
a folder would not change its key. The scope changed and so did the reasoning:
that argument was about pointers to files the graph models, but a backup should
look like the thing it backs up. Mirroring also handles the files that belong
to no single experiment, which a `base_name` scheme has nowhere to put.

Nothing here touches Neo4j. What needs uploading is decided by comparing the
share against a listing of the bucket, so this runs on a machine that can reach
S3 but not Aura - which is the lab PC today.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .common import s3 as s3mod
from .common.config import Settings
from .common.tls import use_system_trust_store

logger = logging.getLogger(__name__)

#: The directories beneath the share root that are backed up, in the order they
#: are walked. Anything else on the drive is ignored.
UPLOAD_ROOTS = (
    "peakFit",
    "OpusConvert_lgRfl",
    "OpusReadParams",
    "pressureData",
)

#: A directory whose name *contains* one of these is skipped, along with
#: everything beneath it. `_test` is not real data; `archive` is superseded
#: material Nick keeps but does not want published.
#:
#: Substring rather than exact match, matching `data/source.py` and the
#: original pipeline's rule ("exclude the one whose name contains `_test`").
#: The two were briefly inconsistent - this one required an exact `_test` and
#: would have uploaded a folder named `nn1120-3_pd_ceo2_test`.
EXCLUDED_DIRECTORY_MARKERS = ("_test", "archive")


def is_excluded(relative: Path) -> str | None:
    """Why `relative` is out of scope, or None.

    Only directory components are examined, never the filename - a file called
    `..._test.csv` is real data.
    """
    for part in relative.parts[:-1]:
        lowered = part.lower()
        for marker in EXCLUDED_DIRECTORY_MARKERS:
            if marker in lowered:
                return part
    return None


@dataclass
class Candidate:
    path: Path
    key: str
    bytes: int
    reason: str  # "new" | "size differs"


@dataclass
class Plan:
    to_upload: list[Candidate] = field(default_factory=list)
    already_present: int = 0
    already_bytes: int = 0
    excluded: int = 0
    #: Files skipped, counted by the directory that caused it. A bare total is
    #: not enough: when more files are excluded than uploaded - 36,742 against
    #: 33,782 on the real share - you need to see *which* directories account
    #: for it before trusting the run.
    excluded_by_directory: dict[str, int] = field(default_factory=dict)
    missing_roots: list[str] = field(default_factory=list)

    @property
    def upload_bytes(self) -> int:
        return sum(c.bytes for c in self.to_upload)

    def by_root(self) -> dict[str, tuple[int, int]]:
        counts: dict[str, tuple[int, int]] = {}
        for candidate in self.to_upload:
            root = candidate.key.split("/", 1)[0]
            files, size = counts.get(root, (0, 0))
            counts[root] = (files + 1, size + candidate.bytes)
        return counts


def build_plan(share_root: Path, stored: dict[str, s3mod.StoredObject]) -> Plan:
    """Compare the share against the bucket. Reads no file contents.

    Size is the only comparison. Every file here is written once by an
    instrument and never edited, so a same-size file is the same file. Hashing
    would mean reading ~5 GB on every run to learn nothing.
    """
    plan = Plan()

    for root_name in UPLOAD_ROOTS:
        root = share_root / root_name
        if not root.is_dir():
            plan.missing_roots.append(root_name)
            continue

        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(share_root)
            cause = is_excluded(relative)
            if cause:
                plan.excluded += 1
                where = f"{relative.parts[0]}/.../{cause}"
                plan.excluded_by_directory[where] = (
                    plan.excluded_by_directory.get(where, 0) + 1
                )
                continue

            key = relative.as_posix()
            size = path.stat().st_size
            existing = stored.get(key)

            if existing is None:
                plan.to_upload.append(Candidate(path, key, size, "new"))
            elif existing.bytes != size:
                plan.to_upload.append(Candidate(path, key, size, "size differs"))
            else:
                plan.already_present += 1
                plan.already_bytes += size

    return plan


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n:.1f} GB"


def render(plan: Plan, share_root: Path, bucket: str) -> str:
    lines = [
        f"Backup plan: {share_root}  ->  s3://{bucket}",
        "=" * 60,
        "",
        f"{'root':<22}{'to upload':>12}{'size':>12}",
        "-" * 46,
    ]
    for root, (files, size) in sorted(plan.by_root().items()):
        lines.append(f"{root:<22}{files:>12}{_human(size):>12}")
    lines += [
        "",
        f"already in the bucket : {plan.already_present} file(s), {_human(plan.already_bytes)}",
        f"skipped (excluded)    : {plan.excluded} file(s)",
        f"to upload             : {len(plan.to_upload)} file(s), {_human(plan.upload_bytes)}",
    ]
    if plan.excluded_by_directory:
        lines.append("")
        lines.append("excluded, by the directory that matched:")
        for where, count in sorted(
            plan.excluded_by_directory.items(), key=lambda kv: -kv[1]
        ):
            lines.append(f"    {where:<44}{count:>8}")

    if plan.missing_roots:
        lines += ["", f"roots not found under {share_root}:"]
        lines += [f"    {r}" for r in plan.missing_roots]
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="graph-node-backup",
        description="Copy the share drive to S3. Dry run unless --apply.",
    )
    parser.add_argument(
        "--share-root",
        type=Path,
        help="Drive or directory holding peakFit, OpusConvert_lgRfl, etc. "
        "Defaults to SHARE_ROOT.",
    )
    parser.add_argument("--env", type=Path, default=None)
    parser.add_argument(
        "--apply", action="store_true", help="Actually upload. Off by default."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Upload at most this many files. For a first cautious run.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    use_system_trust_store()

    settings = Settings.from_env(args.env)
    if not settings.s3_bucket:
        print("S3_BUCKET is not set; see .env.example.", file=sys.stderr)
        return 2

    share_root = args.share_root or settings.share_root
    if share_root is None or not share_root.is_dir():
        print(
            f"Share root not found: {share_root}. Set SHARE_ROOT in .env or "
            "pass --share-root.",
            file=sys.stderr,
        )
        return 2

    s3 = s3mod.client(settings.aws_region)
    print(f"Listing s3://{settings.s3_bucket} ...")
    stored = s3mod.list_objects(s3, settings.s3_bucket)
    print(f"  {len(stored)} object(s) already there\n")

    plan = build_plan(share_root, stored)
    print(render(plan, share_root, settings.s3_bucket))

    if not plan.to_upload:
        print("\nNothing to upload.")
        return 0

    if not args.apply:
        print("\nDry run. Nothing was uploaded. Pass --apply to upload.")
        return 0

    candidates = plan.to_upload[: args.limit] if args.limit else plan.to_upload
    print(f"\nUploading {len(candidates)} file(s)...")
    done = 0
    failed: list[tuple[str, str]] = []
    for candidate in candidates:
        try:
            s3mod.upload(s3, settings.s3_bucket, candidate.path, candidate.key)
            done += 1
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the run
            failed.append((candidate.key, f"{type(exc).__name__}: {exc}"))
        if done and done % 200 == 0:
            print(f"  {done}/{len(candidates)}")

    print(f"\nUploaded {done} file(s).")
    if failed:
        print(f"{len(failed)} failed:")
        for key, error in failed[:10]:
            print(f"    {key} - {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
