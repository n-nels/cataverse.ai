"""Configuration, loaded from environment / .env.

Kept deliberately boring: one place that knows where secrets and knobs come
from, so nothing else in the package has to think about it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str
    neo4j_database: str | None

    ollama_host: str
    ollama_model: str
    # Ollama defaults to a 4096-token context. An agent conversation carries the
    # system prompt, the schema, and every tool result, so it outgrows that fast.
    # Raising it costs VRAM (KV cache), which is the real constraint on a 12GB
    # card already holding a ~9.6GB model — see README.
    num_ctx: int
    # qwen3 and friends can emit a separate reasoning stream. Usually better
    # Cypher, at the cost of latency and context. Worth toggling to compare.
    think: bool

    # Hard caps so one careless query can't blow up the context window.
    max_rows: int
    max_iterations: int


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    missing = [
        key
        for key in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD")
        if not os.getenv(key)
    ]
    if missing:
        raise SystemExit(
            "Missing required environment variables: "
            + ", ".join(missing)
            + "\nCopy .env.example to .env and fill it in."
        )

    return Settings(
        neo4j_uri=os.environ["NEO4J_URI"],
        neo4j_username=os.environ["NEO4J_USERNAME"],
        neo4j_password=os.environ["NEO4J_PASSWORD"],
        neo4j_database=os.getenv("NEO4J_DATABASE") or None,
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen3:8b"),
        num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "32768")),
        think=_flag("OLLAMA_THINK", False),
        max_rows=int(os.getenv("AGENT_MAX_ROWS", "50")),
        max_iterations=int(os.getenv("AGENT_MAX_ITERATIONS", "8")),
    )
