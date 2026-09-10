"""Settings, loaded from the environment.

Credentials live in `graph-node/.env` (gitignored), never in code. The same
four variables the dashboard and the agent use, so one Aura instance is
described one way everywhere.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    uri: str
    username: str
    password: str
    database: str
    #: Root of the instrument output on the share drive. Every experiment is a
    #: `<base>_expParams.json` plus an optional `<base>_CarbonylPeakArea.csv`
    #: somewhere beneath this.
    source_root: Path
    #: Where the raw files go. None when S3 is not configured on this machine -
    #: a rebuild still works, it just does not upload. Credentials are read by
    #: boto3 from AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY directly, so they
    #: are deliberately not held here or passed around.
    s3_bucket: str | None
    aws_region: str
    #: Drive or directory holding peakFit, OpusConvert_lgRfl, OpusReadParams and
    #: pressureData. The backup mirrors everything beneath it. Distinct from
    #: `source_root`, which points at peakFit alone for the graph rebuild.
    share_root: Path | None
    #: Per-identity S3 keys, when one machine runs both jobs. None means the
    #: plain AWS_ACCESS_KEY_ID pair is used, which is right for a machine that
    #: only does one of them.
    uploader_credentials: dict[str, str] | None
    builder_credentials: dict[str, str] | None

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "Settings":
        load_dotenv(env_file)
        missing = [
            name
            for name in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD")
            if not os.environ.get(name)
        ]
        if missing:
            raise RuntimeError(
                f"Missing required environment variable(s): {', '.join(missing)}. "
                "Copy .env.example to .env and fill it in."
            )
        return cls(
            uri=os.environ["NEO4J_URI"],
            username=os.environ["NEO4J_USERNAME"],
            password=os.environ["NEO4J_PASSWORD"],
            # Aura's default database name. Only differs on self-hosted.
            database=os.environ.get("NEO4J_DATABASE", "neo4j"),
            source_root=Path(os.environ.get("SOURCE_ROOT", r"X:\peakFit")),
            s3_bucket=os.environ.get("S3_BUCKET") or None,
            aws_region=os.environ.get("AWS_REGION", "us-east-2"),
            share_root=Path(os.environ["SHARE_ROOT"])
            if os.environ.get("SHARE_ROOT")
            else None,
            uploader_credentials=_named_credentials("UPLOADER"),
            builder_credentials=_named_credentials("BUILDER"),
        )


def _named_credentials(prefix: str) -> dict[str, str] | None:
    """`<PREFIX>_AWS_ACCESS_KEY_ID` and its secret, or None if absent.

    The lab PC will eventually run both the backup and the rebuild, and boto3
    reads only one AWS_ACCESS_KEY_ID from the environment. Naming the pairs
    lets one machine hold both identities without either job borrowing the
    other's permissions.

    Absent is the normal case on a machine that does one job: it falls back to
    the plain AWS_ACCESS_KEY_ID pair, so nothing has to change to keep working.
    """
    key = os.environ.get(f"{prefix}_AWS_ACCESS_KEY_ID")
    secret = os.environ.get(f"{prefix}_AWS_SECRET_ACCESS_KEY")
    if not key or not secret:
        return None
    return {"aws_access_key_id": key, "aws_secret_access_key": secret}
