import { NextResponse } from "next/server";
import { Node, Relationship } from "neo4j-driver";
import { driver } from "@/lib/neo4j";

type GraphNode = {
  id: string;
  labels: string[];
  properties: Record<string, unknown>;
};

type GraphLink = {
  id: string;
  source: string;
  target: string;
  type: string;
  properties: Record<string, unknown>;
};

export async function GET() {
  const session = driver.session({
    database: process.env.NEO4J_DATABASE,
  });

  try {
    // Full graph: grab every node plus any relationship between them.
    // OPTIONAL MATCH keeps nodes that have no relationships at all instead
    // of dropping them. ~1.9k nodes / ~6.8k relationships as of 2026-08 —
    // revisit with pagination/filtering if this grows enough to feel slow.
    const result = await session.run(
      `MATCH (n)
       OPTIONAL MATCH (n)-[r]->(m)
       RETURN n, r, m`
    );

    const nodes = new Map<string, GraphNode>();
    const links = new Map<string, GraphLink>();

    const addNode = (node: Node) => {
      if (!nodes.has(node.elementId)) {
        nodes.set(node.elementId, {
          id: node.elementId,
          labels: node.labels,
          properties: node.properties,
        });
      }
    };

    for (const record of result.records) {
      const n = record.get("n") as Node;
      const r = record.get("r") as Relationship | null;
      const m = record.get("m") as Node | null;

      addNode(n);
      if (m) addNode(m);

      if (r) {
        links.set(r.elementId, {
          id: r.elementId,
          source: r.startNodeElementId,
          target: r.endNodeElementId,
          type: r.type,
          properties: r.properties,
        });
      }
    }

    return NextResponse.json({
      nodes: Array.from(nodes.values()),
      links: Array.from(links.values()),
    });
  } catch (error) {
    console.error("Neo4j query failed", error);
    return NextResponse.json(
      { error: "Failed to query graph" },
      { status: 500 }
    );
  } finally {
    await session.close();
  }
}
