"""Where the rebuild reads its sources from.

Two implementations of one idea: something that can list files by suffix and
read one. `LocalStore` walks a directory; `S3Store` reads the bucket.

**S3 is the source of truth.** The share is where instruments write, but the
bucket is what the graph is built from, and that has a consequence worth being
explicit about: a deletion only reaches the graph once the object is gone from
S3. Removing a file from `X:` does nothing on its own - the next backup simply
does not re-upload it, and the object stays. Deleting it in the S3 console is
what makes the removal real, because the next rebuild then does not see it,
does not stamp it, and the sweep takes its nodes.

That is one deliberate action instead of two, and it keeps `DeleteObject` off
every programmatic key: nothing automated can destroy the record.

The local store is kept for `--from-share`, for tests, and for the case where
S3 is unreachable but the share is not.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Ref:
    """One source file, wherever it lives.

    `relative` is the path below the source root - the same shape for both
    stores, so the exclusion rules do not have to know which one they are
    looking at. `handle` is whatever the store needs to open it again.
    """

    handle: str
    relative: PurePosixPath

    @property
    def name(self) -> str:
        return self.relative.name

    def __str__(self) -> str:
        return str(self.relative)


class LocalStore:
    """A directory on disk, historically the peakFit folder on the share."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def describe(self) -> str:
        return str(self.root)

    def exists(self) -> bool:
        return self.root.is_dir()

    def find(self, suffix: str) -> list[Ref]:
        refs = []
        for path in sorted(self.root.rglob(f"*{suffix}")):
            refs.append(
                Ref(
                    handle=str(path),
                    relative=PurePosixPath(path.relative_to(self.root).as_posix()),
                )
            )
        return refs

    def read_text(self, ref: Ref) -> str:
        return Path(ref.handle).read_text(encoding="utf-8")

    def sibling(self, ref: Ref, name: str) -> Ref | None:
        """A file in the same folder. Fit CSVs sit beside their JSON."""
        candidate = Path(ref.handle).parent / name
        if not candidate.is_file():
            return None
        return Ref(
            handle=str(candidate),
            relative=PurePosixPath(candidate.relative_to(self.root).as_posix()),
        )


class S3Store:
    """The bucket. Keys mirror the share, so `relative` is the key itself.

    The listing is taken once and held: a rebuild asks about tens of thousands
    of objects and one paginated listing is the difference between that and
    tens of thousands of round trips.
    """

    def __init__(self, client, bucket: str, listing: dict[str, object]):
        self.client = client
        self.bucket = bucket
        self.listing = listing

    def describe(self) -> str:
        return f"s3://{self.bucket}"

    def exists(self) -> bool:
        return bool(self.listing)

    def find(self, suffix: str) -> list[Ref]:
        return [
            Ref(handle=key, relative=PurePosixPath(key))
            for key in sorted(self.listing)
            if key.endswith(suffix)
        ]

    def read_text(self, ref: Ref) -> str:
        body = self.client.get_object(Bucket=self.bucket, Key=ref.handle)["Body"]
        return body.read().decode("utf-8")

    def sibling(self, ref: Ref, name: str) -> Ref | None:
        key = str(PurePosixPath(ref.relative).parent / name)
        if key not in self.listing:
            return None
        return Ref(handle=key, relative=PurePosixPath(key))
