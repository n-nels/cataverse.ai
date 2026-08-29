import { NextResponse } from "next/server";
import neo4j, { Node, Path, Relationship } from "neo4j-driver";
import { driver } from "@/lib/neo4j";
import {
  type GraphLink,
  type GraphNode,
  nodeToGraphNode,
  relToGraphLink,
} from "@/lib/neo4jSerialize";

// A single expansion should stay readable. Some nodes are very high-degree —
// one Filename has 1,107 Pretreatment steps hanging off it — so an uncapped
// expansion would bury the user and stall the layout.
const MAX_NODES = 120;
// Paths, not nodes: at depth > 1 the number of paths grows much faster than the
// number of distinct nodes they touch.
const MAX_PATHS = 400;
const MAX_DEPTH = 3;

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const id = params.get("id");
  if (!id) {
    return NextResponse.json({ error: "Missing ?id" }, { status: 400 });
  }

  // Cypher requires literal bounds on a variable-length pattern, so depth is
  // interpolated rather than parameterised. Clamped to a small integer first —
  // it must never be able to carry anything but a number into the query.
  const requested = Number.parseInt(params.get("depth") ?? "1", 10);
  const depth = Number.isFinite(requested)
    ? Math.min(Math.max(requested, 1), MAX_DEPTH)
    : 1;

  const session = driver.session({ database: process.env.NEO4J_DATABASE });

  try {
    const result = await session.executeRead((tx) =>
      tx.run(
        // Undirected: exploration should walk relationships either way. The
        // direction is preserved on each link so arrows still read correctly.
        `MATCH (n) WHERE elementId(n) = $id
         OPTIONAL MATCH path = (n)-[*1..${depth}]-(m)
         RETURN n, path
         LIMIT $limit`,
        // neo4j.int(): a plain JS number arrives as a float, and LIMIT rejects
        // "401.0" — it requires an integer.
        { id, limit: neo4j.int(MAX_PATHS) }
      )
    );

    if (result.records.length === 0) {
      return NextResponse.json({ error: "Node not found" }, { status: 404 });
    }

    const nodes = new Map<string, GraphNode>();
    const links = new Map<string, GraphLink>();

    // The centre node is on every row, and is the only thing on the row when it
    // has no relationships at all.
    nodes.set(id, nodeToGraphNode(result.records[0].get("n") as Node));

    let hitCap = false;
    for (const record of result.records) {
      const path = record.get("path") as Path | null;
      if (!path) continue;

      // Stop adding once full, but keep scanning so links between nodes we
      // already have are not missed.
      for (const segment of path.segments) {
        for (const end of [segment.start, segment.end]) {
          const gn = nodeToGraphNode(end as Node);
          if (nodes.has(gn.id)) continue;
          if (nodes.size >= MAX_NODES) {
            hitCap = true;
            continue;
          }
          nodes.set(gn.id, gn);
        }
      }
      for (const segment of path.segments) {
        const gl = relToGraphLink(segment.relationship as Relationship);
        if (nodes.has(gl.source) && nodes.has(gl.target)) links.set(gl.id, gl);
      }
    }

    return NextResponse.json({
      nodes: Array.from(nodes.values()),
      links: Array.from(links.values()),
      truncated: hitCap || result.records.length >= MAX_PATHS,
      limit: MAX_NODES,
      depth,
    });
  } catch (error) {
    console.error("Neighbor expansion failed", error);
    const message = error instanceof Error ? error.message : "Expansion failed.";
    return NextResponse.json({ error: message }, { status: 500 });
  } finally {
    await session.close();
  }
}
