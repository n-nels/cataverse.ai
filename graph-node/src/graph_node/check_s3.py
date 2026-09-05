"""Prove the S3 credentials and policy work, before anything depends on them.

Uploads one tiny object, lists it, then checks that the things the policy is
supposed to forbid are actually forbidden. A policy typo otherwise surfaces
much later as a confusing "Access Denied" that looks like a bad key.

Read-and-write, but only on one object under `_check/`. Run:

    uv run python -m graph_node.check_s3
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from .common.config import Settings
from .common.tls import use_system_trust_store

CHECK_KEY = "_check/connectivity.txt"


def main(argv: list[str] | None = None) -> int:
    use_system_trust_store()
    settings = Settings.from_env(None)

    if not settings.s3_bucket:
        print(
            "S3_BUCKET is not set. Add these to graph-node/.env:\n"
            "  AWS_ACCESS_KEY_ID=...\n"
            "  AWS_SECRET_ACCESS_KEY=...\n"
            "  AWS_REGION=us-east-2\n"
            "  S3_BUCKET=...",
            file=sys.stderr,
        )
        return 2

    import boto3
    from botocore.exceptions import ClientError

    print(f"bucket : {settings.s3_bucket}")
    print(f"region : {settings.aws_region}\n")

    s3 = boto3.client("s3", region_name=settings.aws_region)
    body = f"cataverse connectivity check {datetime.now(timezone.utc).isoformat()}\n"
    ok = True

    def check(label: str, expected: str, fn) -> None:
        nonlocal ok
        try:
            fn()
            outcome = "allowed"
        except ClientError as exc:
            outcome = exc.response["Error"]["Code"]
        except Exception as exc:  # noqa: BLE001 - reporting, not handling
            outcome = f"{type(exc).__name__}: {exc}"
        passed = outcome == expected
        ok = ok and passed
        print(f"  [{'ok ' if passed else 'FAIL'}] {label:34} {outcome}")

    print("expected to work:")
    check("PutObject", "allowed", lambda: s3.put_object(
        Bucket=settings.s3_bucket, Key=CHECK_KEY,
        Body=body.encode(), ContentType="text/plain"))
    check("ListObjectsV2", "allowed", lambda: s3.list_objects_v2(
        Bucket=settings.s3_bucket, Prefix="_check/"))

    # The uploader key must not be able to read the data back or remove it.
    # If either of these says "allowed", the policy is wider than intended.
    print("\nexpected to be refused (uploader is write-only):")
    check("GetObject", "AccessDenied", lambda: s3.get_object(
        Bucket=settings.s3_bucket, Key=CHECK_KEY))
    check("DeleteObject", "AccessDenied", lambda: s3.delete_object(
        Bucket=settings.s3_bucket, Key=CHECK_KEY))

    print()
    if ok:
        print(
            "All checks passed. The object left at "
            f"s3://{settings.s3_bucket}/{CHECK_KEY} can be deleted from the "
            "console - this key deliberately cannot."
        )
        return 0
    print(
        "Something is not as intended. 'allowed' where a refusal was expected "
        "means the policy grants more than it should; a refusal where work was "
        "expected usually means the ListBucket statement is missing its "
        "bucket-level Resource (no /* suffix)."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
