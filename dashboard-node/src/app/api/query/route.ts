import { NextResponse } from "next/server";
import neo4j, { Node, Relationship, Path } from "neo4j-driver";
import { driver } from "@/lib/neo4j";
import {
  type GraphLink,
  type GraphNode,
  nodeToGraphNode,
  relToGraphLink,
  toPlain,
} from "@/lib/neo4jSerialize";

// This endpoint runs Cypher typed by whoever is using the page, so read-only is
// not a nicety. `session.executeRead` opens a READ-mode transaction and the
// *server* rejects any write, which is the actual guarantee. The keyword scan
// below is only there to fail fast with a message a human can act on, rather
// than a driver stack trace — it is not the security boundary.
const WRITE_KEYWORDS =
  /\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|FOREACH)\b/i;

const MAX_ROWS = 300;

export async function POST(request: Request) {
  let query: string;
  try {
    const body = await request.json();
    query = typeof body?.query === "string" ? body.query : "";
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }

  if (!query.trim()) {
    return NextResponse.json({ error: "Query is empty." }, { status: 400 });
  }

  if (WRITE_KEYWORDS.test(query)) {
    return NextResponse.json(
      {
        error:
          "Only read-only queries are allowed. Remove CREATE / MERGE / DELETE / SET / REMOVE / DROP.",
      },
      { status: 400 }
    );
  }

  const session = driver.session({ database: process.env.NEO4J_DATABASE });

  try {
    const result = await session.executeRead((tx) => tx.run(query));

    const nodes = new Map<string, GraphNode>();
    const links = new Map<string, GraphLink>();

    const addNode = (n: Node) => {
      if (!nodes.has(n.elementId)) nodes.set(n.elementId, nodeToGraphNode(n));
    };

    const addRel = (r: Relationship) => {
      links.set(r.elementId, relToGraphLink(r));
    };

    // Walk every value the query returned, at any nesting depth, pulling out
    // anything graph-shaped. This is what lets `RETURN n`, `RETURN collect(n)`
    // and `RETURN path` all light up the canvas without special-casing.
    const collect = (value: unknown) => {
      if (value === null || value === undefined) return;
      if (neo4j.isNode(value)) return addNode(value as Node);
      if (neo4j.isRelationship(value)) return addRel(value as Relationship);
      if (neo4j.isPath(value)) {
        const path = value as Path;
        addNode(path.start);
        addNode(path.end);
        for (const seg of path.segments) {
          addNode(seg.start);
          addNode(seg.end);
          addRel(seg.relationship);
        }
        return;
      }
      if (Array.isArray(value)) return value.forEach(collect);
      if (typeof value === "object" && !neo4j.isInt(value)) {
        Object.values(value as Record<string, unknown>).forEach(collect);
      }
    };

    const columns = result.records[0]?.keys.map(String) ?? [];
    const rows: Record<string, unknown>[] = [];

    for (const record of result.records.slice(0, MAX_ROWS)) {
      for (const key of record.keys) collect(record.get(key));
      rows.push(
        Object.fromEntries(
          record.keys.map((k) => [String(k), toPlain(record.get(k))])
        )
      );
    }

    // react-force-graph throws if a link points at a node it wasn't given, which
    // happens whenever a query returns relationships without both endpoints.
    const linkList = Array.from(links.values()).filter(
      (l) => nodes.has(l.source) && nodes.has(l.target)
    );

    return NextResponse.json({
      nodes: Array.from(nodes.values()),
      links: linkList,
      columns,
      rows,
      rowCount: result.records.length,
      truncated: result.records.length > MAX_ROWS,
    });
  } catch (error) {
    // Neo4j's own message is the most useful thing we can show — it names the
    // syntax error position, the unknown label, etc.
    const message =
      error instanceof Error ? error.message : "Query failed.";
    return NextResponse.json({ error: message }, { status: 400 });
  } finally {
    await session.close();
  }
}
