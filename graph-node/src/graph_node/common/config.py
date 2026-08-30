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
        )
