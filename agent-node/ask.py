"""Ask the agent a single question, non-interactively.

This exists mainly as a debugger entry point: unlike the REPL in cli.py it
takes no stdin, so you can set breakpoints and step through one full agent
loop start to finish without fighting the terminal.

    uv run python ask.py "How many pretreatment steps are there?"

Good places to break:
    agent.py   Agent.ask            -> the loop; one pass per model call
    agent.py   Agent._dispatch      -> where a tool call becomes real work
    graph.py   GraphClient.run_read -> where Cypher actually hits Neo4j
"""

from __future__ import annotations

import sys
import time
from typing import Any

from cataverse_agent.agent import Agent
from cataverse_agent.config import load_settings
from cataverse_agent.graph import GraphClient

DEFAULT_QUESTION = (
    "What materials have been studied, and how many experiments exist for each?"
)


def on_event(kind: str, payload: Any) -> None:
    if kind == "step":
        print(f"--- step {payload} ---", flush=True)
    elif kind == "thinking":
        print(f"  [thinking] {str(payload)[:200]}...", flush=True)
    elif kind == "tool_call":
        print(f"  -> {payload['name']}: {str(payload['args'])[:220]}", flush=True)
    elif kind == "tool_result":
        result = payload["result"]
        if "error" in result:
            print(f"     ERROR: {result['error'][:150]}", flush=True)
        else:
            print(
                f"     ok: rows={result.get('row_count', '-')} "
                f"warnings={len(result.get('warnings', []))}",
                flush=True,
            )
        for warning in result.get("warnings", []):
            print(f"     ! {warning[:140]}", flush=True)


def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUESTION

    settings = load_settings()
    graph = GraphClient(settings)
    graph.verify()
    agent = Agent(settings, graph)

    print(
        f"model: {settings.ollama_model} | ctx: {settings.num_ctx} | "
        f"think: {settings.think}"
    )
    print(f"Q: {question}\n", flush=True)

    started = time.time()
    try:
        answer = agent.ask(question, on_event=on_event)
    finally:
        graph.close()

    print(f"\n=== ANSWER ({time.time() - started:.0f}s) ===\n{answer}")


if __name__ == "__main__":
    main()
