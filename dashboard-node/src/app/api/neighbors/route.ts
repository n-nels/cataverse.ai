import { NextResponse } from "next/server";
import neo4j, { Node, Relationship } from "neo4j-driver";
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

export async function GET(request: Request) {
  const id = new URL(request.url).searchParams.get("id");
  if (!id) {
    return NextResponse.json({ error: "Missing ?id" }, { status: 400 });
  }

  const session = driver.session({ database: process.env.NEO4J_DATABASE });

  try {
    const result = await session.executeRead((tx) =>
      tx.run(
        // Undirected: exploration should walk relationships either way. The
        // direction is preserved on each link so arrows still read correctly.
        `MATCH (n) WHERE elementId(n) = $id
         OPTIONAL MATCH (n)-[r]-(m)
         RETURN n, r, m
         LIMIT $limit`,
        // neo4j.int(): a plain JS number arrives as a float, and LIMIT rejects
        // "121.0" — it requires an integer.
        { id, limit: neo4j.int(MAX_NODES + 1) }
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

    const rows = result.records.slice(0, MAX_NODES);
    for (const record of rows) {
      const m = record.get("m") as Node | null;
      const r = record.get("r") as Relationship | null;
      if (m) {
        const gn = nodeToGraphNode(m);
        if (!nodes.has(gn.id)) nodes.set(gn.id, gn);
      }
      if (r) {
        const gl = relToGraphLink(r);
        links.set(gl.id, gl);
      }
    }

    return NextResponse.json({
      nodes: Array.from(nodes.values()),
      links: Array.from(links.values()),
      truncated: result.records.length > MAX_NODES,
      limit: MAX_NODES,
    });
  } catch (error) {
    console.error("Neighbor expansion failed", error);
    const message = error instanceof Error ? error.message : "Expansion failed.";
    return NextResponse.json({ error: message }, { status: 500 });
  } finally {
    await session.close();
  }
}
