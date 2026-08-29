"""The agent loop.

This is the whole idea, and it is deliberately small enough to read in one
sitting — no framework, no abstractions to peel back:

    1. Send the conversation to the model, along with a list of tools it may call.
    2. If the reply contains no tool calls, it is the final answer. Stop.
    3. Otherwise run each requested tool, append its result to the conversation
       as a `tool` message, and go back to step 1.

Everything else here is supporting cast: the tool schemas that tell the model
what it may call, the system prompt that tells it how to behave, and a bound on
the loop so a confused model cannot spin forever.

Worth internalising: the model never touches the database. It only ever *asks*
for a tool to run. Every actual query goes through graph.py, which is where the
read-only guarantee lives. That separation is what makes it safe to let a model
compose queries at all.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ollama import Client

from .config import Settings
from .graph import GraphClient, ReadOnlyViolation

# Tool schemas, in the JSON-Schema shape Ollama expects. The `description`
# fields are not documentation — they are the only thing the model reads to
# decide what to call and with what arguments. Vague descriptions here are the
# single most common cause of an agent misbehaving.
TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_graph_schema",
            "description": (
                "Return the structure of the Neo4j graph: node labels with "
                "counts, the relationship patterns that actually exist, and the "
                "properties on each label with their types. Call this before "
                "writing Cypher against labels or properties you have not seen "
                "yet."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_cypher",
            "description": (
                "Execute a READ-ONLY Cypher query against the graph and return "
                "the rows. Writes are rejected. Results are capped, so use "
                "count() / avg() / collect() in the query rather than pulling "
                "raw rows and aggregating them yourself. Prefer several small "
                "focused queries over one large one."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A read-only Cypher query.",
                    }
                },
                "required": ["query"],
            },
        },
    },
]

SYSTEM_PROMPT = """\
You are a research assistant for cataverse, a catalyst-discovery project. You
answer questions about a Neo4j graph holding experimental data (materials,
pretreatments, experimental conditions, adsorption parameters, kinetic models)
and the chemistry concepts those records instantiate.

Rules:
- Never invent data. Every factual claim about the graph must come from a
  run_cypher result in this conversation. If you have not queried it, say so.
- Call get_graph_schema before writing Cypher against anything unfamiliar.
  Guessing label or property names wastes turns.
- Let the database aggregate. Use count(), avg(), min(), max(), collect() in
  Cypher instead of pulling rows back and doing arithmetic yourself.
- When grouping, group by a unique identifier (an `id` property, or the node
  itself) — never by descriptive properties like a metal or support name. Those
  repeat across genuinely distinct entities, and grouping on them silently
  merges rows that should stay separate.
- If a result contradicts something you already know (for example, fewer groups
  came back than there are nodes of that label), suspect your own query first.
  Re-query with a unique key. Do not invent an explanation for the discrepancy.
- If a tool returns warnings, take them seriously and reflect them in your
  answer. A warning that rows were excluded or truncated means your answer is
  about a subset, and you must say which subset.
- If a query errors, read the error, fix the Cypher, and try again.
- Answer in plain prose for a scientist. Include the numbers you found. Do not
  paste raw JSON unless asked.
"""


class Agent:
    def __init__(self, settings: Settings, graph: GraphClient) -> None:
        self._settings = settings
        self._graph = graph
        self._client = Client(host=settings.ollama_host)
        # Not every model accepts the `think` parameter. Assume it does, and
        # latch this off permanently the first time Ollama objects.
        self._supports_think = True
        self.messages: list[Any] = [{"role": "system", "content": SYSTEM_PROMPT}]

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # ------------------------------------------------------------ tool calls

    def _dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Run one tool call and return a JSON-serialisable result.

        Errors are returned to the model rather than raised. A tool that fails
        loudly *to the model* gives it a chance to correct itself; a tool that
        raises just kills the run.
        """
        try:
            if name == "get_graph_schema":
                return self._graph.schema()
            if name == "run_cypher":
                query = args.get("query")
                if not isinstance(query, str) or not query.strip():
                    return {"error": "run_cypher requires a non-empty 'query' string."}
                return self._graph.run_read(query)
            return {"error": f"Unknown tool '{name}'."}
        except ReadOnlyViolation as exc:
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - surface anything to the model
            return {"error": f"{type(exc).__name__}: {exc}"}

    # ------------------------------------------------------------- the loop

    def ask(
        self,
        question: str,
        on_event: Callable[[str, Any], None] | None = None,
    ) -> str:
        """Answer one question, running tools as needed. Returns final text."""

        def emit(kind: str, payload: Any) -> None:
            if on_event:
                on_event(kind, payload)

        self.messages.append({"role": "user", "content": question})
        nudged = False

        for step in range(1, self._settings.max_iterations + 1):
            emit("step", step)

            chat_kwargs: dict[str, Any] = {
                "model": self._settings.ollama_model,
                "messages": self.messages,
                "tools": TOOLS,
                "options": {"num_ctx": self._settings.num_ctx},
            }
            # Pass `think` explicitly even when disabling it. Omitting it lets a
            # reasoning model (qwen3) think by default, which quietly spends
            # latency and context — turning it "off" in config has to actually
            # send think=False to take effect.
            if self._supports_think:
                chat_kwargs["think"] = self._settings.think

            try:
                response = self._client.chat(**chat_kwargs)
            except Exception as exc:  # noqa: BLE001
                if self._supports_think and "think" in str(exc).lower():
                    self._supports_think = False
                    chat_kwargs.pop("think", None)
                    response = self._client.chat(**chat_kwargs)
                else:
                    raise
            message = response.message
            self.messages.append(message)

            thinking = getattr(message, "thinking", None)
            if thinking:
                emit("thinking", thinking)

            tool_calls = message.tool_calls or []

            # No tool calls means the model is done reasoning and this is the
            # answer. This is the loop's only successful exit.
            if not tool_calls:
                answer = (message.content or "").strip()
                if not answer and not nudged:
                    # Reasoning models sometimes spend their whole turn in the
                    # thinking stream and stop without emitting anything for the
                    # user. Ask once, plainly, rather than returning silence.
                    nudged = True
                    self.messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Give your final answer now, in plain prose, "
                                "using the tool results above."
                            ),
                        }
                    )
                    continue
                emit("answer", answer)
                return answer

            for call in tool_calls:
                name = call.function.name
                args = dict(call.function.arguments or {})
                emit("tool_call", {"name": name, "args": args})

                result = self._dispatch(name, args)
                emit("tool_result", {"name": name, "result": result})

                self.messages.append(
                    {
                        "role": "tool",
                        "tool_name": name,
                        "content": json.dumps(result, default=str),
                    }
                )

        # Fell out of the loop: the model kept calling tools without concluding.
        # Usually a sign the question is ambiguous or a tool keeps erroring.
        give_up = (
            f"Stopped after {self._settings.max_iterations} tool-calling rounds "
            "without reaching an answer. Try a narrower question, or raise "
            "AGENT_MAX_ITERATIONS."
        )
        emit("answer", give_up)
        return give_up
