"""Neo4j access for the agent: schema introspection and read-only queries.

Two jobs:
  1. Give the model an accurate picture of the graph (labels, relationships,
     properties) so it can write Cypher that actually runs.
  2. Execute the Cypher it writes, safely, and hand back results small enough
     to fit in a context window.

"Safely" means read-only, and that is enforced twice on purpose. The strong
guarantee is `execute_read`, which opens a READ-mode transaction — the *server*
rejects writes, so it holds no matter what the model sends. The keyword scan on
top of it is not the security boundary; it just fails fast with a message the
model can actually learn from, instead of a driver stack trace.
"""

from __future__ import annotations

import re
from typing import Any

import neo4j
from neo4j import GraphDatabase
from neo4j.graph import Node, Path, Relationship
from neo4j.time import Date, DateTime, Duration, Time

from .config import Settings

_WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|FOREACH|"
    r"CALL\s*\{[^}]*\b(CREATE|MERGE|DELETE|SET)\b)",
    re.IGNORECASE,
)


class ReadOnlyViolation(RuntimeError):
    """Raised when a query looks like it intends to modify the graph."""


def _jsonable(value: Any) -> Any:
    """Convert Neo4j driver types into something json.dumps can handle."""
    if isinstance(value, Node):
        return {
            "_type": "node",
            "labels": list(value.labels),
            "properties": {k: _jsonable(v) for k, v in dict(value).items()},
        }
    if isinstance(value, Relationship):
        return {
            "_type": "relationship",
            "relType": value.type,
            "properties": {k: _jsonable(v) for k, v in dict(value).items()},
        }
    if isinstance(value, Path):
        return {"_type": "path", "length": len(value)}
    if isinstance(value, (Date, DateTime, Time, Duration)):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


class GraphClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
        )

    def close(self) -> None:
        self._driver.close()

    def _session(self) -> neo4j.Session:
        return self._driver.session(database=self._settings.neo4j_database)

    def verify(self) -> None:
        """Fail early and clearly if the database is unreachable or asleep."""
        self._driver.verify_connectivity()

    # ---------------------------------------------------------------- schema

    def schema(self) -> dict[str, Any]:
        """Labels with counts, the relationship patterns actually present, and
        property types — plus the quirks the model needs to reason correctly."""
        with self._session() as session:
            labels = session.execute_read(
                lambda tx: [
                    {"label": r["label"], "count": r["count"]}
                    for r in tx.run(
                        "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count "
                        "ORDER BY count DESC"
                    )
                ]
            )
            triples = session.execute_read(
                lambda tx: [
                    {
                        "from": r["from"],
                        "rel": r["rel"],
                        "to": r["to"],
                        "count": r["count"],
                    }
                    for r in tx.run(
                        "MATCH (a)-[r]->(b) "
                        "RETURN labels(a)[0] AS from, type(r) AS rel, "
                        "labels(b)[0] AS to, count(*) AS count ORDER BY count DESC"
                    )
                ]
            )
            raw_props = session.execute_read(
                lambda tx: [
                    {
                        "labels": list(r["nodeLabels"]),
                        "property": r["propertyName"],
                        "types": list(r["propertyTypes"] or []),
                    }
                    for r in tx.run("CALL db.schema.nodeTypeProperties()")
                ]
            )

        properties: dict[str, list[dict[str, Any]]] = {}
        for row in raw_props:
            if not row["labels"] or not row["property"]:
                continue
            label = row["labels"][0]
            types = [t.replace(" NOT NULL", "") for t in row["types"]]
            properties.setdefault(label, []).append(
                {"name": row["property"], "types": types}
            )

        return {
            "labels": labels,
            "relationships": triples,
            "properties": properties,
        }

    # ----------------------------------------------------------------- query

    def run_read(self, query: str) -> dict[str, Any]:
        """Run a read-only Cypher query and return rows plus any warnings."""
        if _WRITE_KEYWORDS.search(query):
            raise ReadOnlyViolation(
                "This query looks like it would modify the graph. Only read "
                "queries (MATCH / RETURN / WITH / UNWIND / CALL for reads) are "
                "allowed. Rewrite it as a read."
            )

        max_rows = self._settings.max_rows
        with self._session() as session:
            # READ-mode transaction: the server refuses writes regardless of
            # what slipped past the keyword scan above.
            records = session.execute_read(
                lambda tx: [r.data() for r in tx.run(query)][: max_rows + 1]
            )

        truncated = len(records) > max_rows
        rows = [_jsonable(r) for r in records[:max_rows]]

        warnings: list[str] = []
        if truncated:
            warnings.append(
                f"Result truncated to the first {max_rows} rows. If you need a "
                "total, ask the database for one with count() instead of "
                "counting rows yourself."
            )

        return {"rows": rows, "row_count": len(rows), "warnings": warnings}

