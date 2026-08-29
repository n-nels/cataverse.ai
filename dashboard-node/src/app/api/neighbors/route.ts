import { NextResponse } from "next/server";
import neo4j, { Node, Relationship } from "neo4j-driver";
import { driver } from "@/lib/neo4j";
import {
  type GraphLink,
  type GraphNode,
  nodeToGraphNode,
  relToGraphLink,
} from "@/lib/neo4jSerialize";

// A single expansion should feel instant and stay readable. Some nodes here are
// very high-degree — one Filename has 1,107 Pretreatment steps hanging off it —
// so an uncapped expansion would both hang the layout and bury the user.
const MAX_NEIGHBORS = 75;

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
        // direction is preserved in the link itself for drawing arrows.
        `MATCH (n) WHERE elementId(n) = $id
         OPTIONAL MATCH (n)-[r]-(m)
         RETURN n, r, m
         LIMIT $limit`,
        // neo4j.int(): a plain JS number arrives as a float, and Cypher's LIMIT
        // rejects "76.0" — it requires an integer.
        { id, limit: neo4j.int(MAX_NEIGHBORS + 1) }
      )
    );

    if (result.records.length === 0) {
      return NextResponse.json({ error: "Node not found" }, { status: 404 });
    }

    const nodes = new Map<string, GraphNode>();
    const links = new Map<string, GraphLink>();

    // The centre node comes back on every row (and on its own if it has no
    // relationships at all, where r and m are null).
    nodes.set(id, nodeToGraphNode(result.records[0].get("n") as Node));

    const rows = result.records.slice(0, MAX_NEIGHBORS);
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
      truncated: result.records.length > MAX_NEIGHBORS,
      limit: MAX_NEIGHBORS,
    });
  } catch (error) {
    console.error("Neighbor expansion failed", error);
    const message = error instanceof Error ? error.message : "Expansion failed.";
    return NextResponse.json({ error: message }, { status: 500 });
  } finally {
    await session.close();
  }
}
