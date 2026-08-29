import { NextResponse } from "next/server";
import neo4j, { Node, Relationship } from "neo4j-driver";
import { driver } from "@/lib/neo4j";
import {
  type GraphLink,
  type GraphNode,
  nodeToGraphNode,
  relToGraphLink,
} from "@/lib/neo4jSerialize";

// Keep an expansion readable. Some nodes are very high-degree — one Filename
// has 1,107 Pretreatment steps hanging off it — so an uncapped expansion would
// bury the user and stall the layout.
const DEFAULT_MAX_NODES = 25;

// Labels where the whole neighbourhood *is* the point, so a cap would hide the
// thing you expanded to see. `null` means no cap at all.
//   KineticChain groups the experiments run on one sample / campaign — capping
//     it at 25 hides the comparison it exists to make.
//   Material is the sample itself. Expanding one answers "how many experiments
//     were run on this catalyst", and a capped answer to that question is a
//     wrong answer, not a truncated one — so it must not be bounded at all.
const MAX_NODES_BY_LABEL: Record<string, number | null> = {
  KineticChain: 300,
  Material: null,
};

/** The cap for a node, given its labels. `null` means no cap. */
function capFor(labels: string[]): number | null {
  const first = labels[0];
  return first in MAX_NODES_BY_LABEL
    ? MAX_NODES_BY_LABEL[first]
    : DEFAULT_MAX_NODES;
}

export async function GET(request: Request) {
  const id = new URL(request.url).searchParams.get("id");
  if (!id) {
    return NextResponse.json({ error: "Missing ?id" }, { status: 400 });
  }

  const session = driver.session({ database: process.env.NEO4J_DATABASE });

  try {
    // Two statements in one read transaction. The cap depends on the centre
    // node's label, and LIMIT takes a parameter but cannot be derived from a
    // value found earlier in the same query — so look the node up first, then
    // ask for its neighbours with the right limit (or none). The lookup is an
    // elementId hit, so the extra round trip is negligible.
    const { centreNode, records } = await session.executeRead(async (tx) => {
      const centreResult = await tx.run(
        `MATCH (n) WHERE elementId(n) = $id RETURN n`,
        { id }
      );
      if (centreResult.records.length === 0) return { centreNode: null, records: [] };

      const node = centreResult.records[0].get("n") as Node;
      const cap = capFor(node.labels);

      // Undirected: exploration should walk relationships either way. The
      // direction is preserved on each link so arrows still read correctly.
      const base = `MATCH (n) WHERE elementId(n) = $id
         OPTIONAL MATCH (n)-[r]-(m)
         RETURN r, m`;

      const neighbourResult = await tx.run(
        // Fetch one more than the cap so `truncated` can be reported honestly
        // without a second counting query.
        cap === null ? base : `${base} LIMIT $limit`,
        // neo4j.int(): a plain JS number arrives as a float, and LIMIT rejects
        // "26.0" — it requires an integer.
        cap === null ? { id } : { id, limit: neo4j.int(cap + 1) }
      );
      return { centreNode: node, records: neighbourResult.records };
    });

    if (!centreNode) {
      return NextResponse.json({ error: "Node not found" }, { status: 404 });
    }

    const nodes = new Map<string, GraphNode>();
    const links = new Map<string, GraphLink>();

    const centre = nodeToGraphNode(centreNode);
    nodes.set(id, centre);

    const maxNodes = capFor(centreNode.labels);
    const rows = maxNodes === null ? records : records.slice(0, maxNodes);
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
      truncated: maxNodes !== null && records.length > maxNodes,
      limit: maxNodes,
    });
  } catch (error) {
    console.error("Neighbor expansion failed", error);
    const message = error instanceof Error ? error.message : "Expansion failed.";
    return NextResponse.json({ error: message }, { status: 500 });
  } finally {
    await session.close();
  }
}
