"""Talking to S3.

Deliberately independent of Neo4j. The backup decides what to upload by
comparing the share drive against what is already in the bucket, so it needs no
database at all - which matters, because the lab machine can reach S3 on 443
while Bolt on 7687 is still blocked (§5f). Backing up can start before the
graph side is reachable.
"""

from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

#: Content types for the extensions the share uses. Spectra are `.0000`-style
#: numeric extensions that nothing recognises; without an explicit type a
#: browser downloads them instead of reading them, which breaks plotting.
CONTENT_TYPES = {
    ".csv": "text/csv",
    ".json": "application/json",
    ".txt": "text/plain",
    ".md": "text/markdown",
}
DEFAULT_CONTENT_TYPE = "text/plain"


def content_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in CONTENT_TYPES:
        return CONTENT_TYPES[suffix]
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or DEFAULT_CONTENT_TYPE


@dataclass(frozen=True)
class StoredObject:
    key: str
    bytes: int


def client(region: str):
    """A boto3 S3 client. Credentials come from the environment, not from here."""
    import boto3

    return boto3.client("s3", region_name=region)


def list_objects(s3, bucket: str, prefix: str = "") -> dict[str, StoredObject]:
    """Every object already in the bucket, keyed by object key.

    One paginated listing rather than a HeadObject per file: at tens of
    thousands of files that is the difference between a few seconds and a few
    thousand round trips.
    """
    stored: dict[str, StoredObject] = {}
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            stored[item["Key"]] = StoredObject(key=item["Key"], bytes=item["Size"])
    logger.debug("bucket holds %d object(s) under %r", len(stored), prefix)
    return stored


def upload(s3, bucket: str, path: Path, key: str) -> None:
    """Put one file. Overwrites whatever is at `key`."""
    s3.upload_file(
        Filename=str(path),
        Bucket=bucket,
        Key=key,
        ExtraArgs={"ContentType": content_type_for(path)},
    )
