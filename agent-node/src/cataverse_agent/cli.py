"""Terminal REPL for the agent.

Deliberately shows its work. Every tool call and every tool result is printed,
because the point of running this in a terminal first is to watch the loop
actually turn — where it guesses wrong, where it re-queries, where the schema
caveats change its behaviour. Use `/quiet` once that stops being interesting.
"""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from .agent import Agent
from .config import load_settings
from .graph import GraphClient

console = Console()

BANNER = """[bold]cataverse agent[/bold] — ask questions about the graph in plain English.

  [dim]/schema[/dim]   print the graph schema the model sees
  [dim]/reset[/dim]    clear the conversation
  [dim]/verbose[/dim]  show tool calls and results (default)
  [dim]/quiet[/dim]    hide them, just show answers
  [dim]/exit[/dim]     quit
"""


def _print_event(kind: str, payload: Any) -> None:
    if kind == "step":
        console.print(f"[dim]— step {payload} —[/dim]")

    elif kind == "thinking":
        text = str(payload).strip()
        if len(text) > 600:
            text = text[:600] + " […]"
        console.print(f"[dim italic]{text}[/dim italic]")

    elif kind == "tool_call":
        name = payload["name"]
        args = payload["args"]
        if name == "run_cypher" and "query" in args:
            console.print(f"[cyan]→ {name}[/cyan]")
            console.print(
                Syntax(str(args["query"]).strip(), "cypher", theme="ansi_dark")
            )
        else:
            shown = json.dumps(args, default=str)
            console.print(f"[cyan]→ {name}[/cyan] [dim]{shown}[/dim]")

    elif kind == "tool_result":
        result = payload["result"]
        if "error" in result:
            console.print(f"[red]  ✗ {result['error']}[/red]")
            return
        if "row_count" in result:
            console.print(f"[green]  ✓ {result['row_count']} row(s)[/green]")
        elif payload["name"] == "get_graph_schema":
            labels = len(result.get("labels", []))
            rels = len(result.get("relationships", []))
            console.print(
                f"[green]  ✓ schema: {labels} labels, {rels} relationship patterns[/green]"
            )
        for warning in result.get("warnings", []):
            console.print(f"[yellow]  ! {warning}[/yellow]")


def main() -> None:
    settings = load_settings()

    console.print(BANNER)
    console.print(
        f"[dim]model {settings.ollama_model} · ctx {settings.num_ctx} · "
        f"think {'on' if settings.think else 'off'} · "
        f"max {settings.max_iterations} rounds[/dim]\n"
    )

    graph = GraphClient(settings)
    try:
        graph.verify()
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Cannot reach Neo4j:[/red] {exc}")
        console.print(
            "[yellow]If this is the AuraDB free tier it may have auto-paused — "
            "resume it at console.neo4j.io and retry.[/yellow]"
        )
        graph.close()
        raise SystemExit(1) from exc

    agent = Agent(settings, graph)
    verbose = True

    try:
        while True:
            try:
                question = console.input("[bold green]you ›[/bold green] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                break

            if not question:
                continue

            lowered = question.lower()
            if lowered in {"/exit", "/quit"}:
                break
            if lowered == "/reset":
                agent.reset()
                console.print("[dim]conversation cleared[/dim]\n")
                continue
            if lowered == "/verbose":
                verbose = True
                console.print("[dim]verbose on[/dim]\n")
                continue
            if lowered == "/quiet":
                verbose = False
                console.print("[dim]verbose off[/dim]\n")
                continue
            if lowered == "/schema":
                try:
                    console.print_json(json.dumps(graph.schema(), default=str))
                except Exception as exc:  # noqa: BLE001
                    console.print(f"[red]{exc}[/red]")
                continue

            try:
                answer = agent.ask(
                    question, on_event=_print_event if verbose else None
                )
            except KeyboardInterrupt:
                console.print("\n[dim]interrupted[/dim]\n")
                continue
            except Exception as exc:  # noqa: BLE001
                console.print(f"[red]Agent error:[/red] {type(exc).__name__}: {exc}")
                console.print(
                    "[yellow]If Ollama is not running, start it and confirm the "
                    f"model is pulled: `ollama pull {settings.ollama_model}`[/yellow]\n"
                )
                continue

            console.print(Panel(answer or "[dim](empty response)[/dim]", title="answer"))
            console.print()
    finally:
        graph.close()


if __name__ == "__main__":
    main()
