import { NextResponse } from "next/server";
import { driver } from "@/lib/neo4j";

type LabelInfo = {
  label: string;
  count: number;
  properties: { name: string; types: string[] }[];
};

type Triple = {
  from: string;
  rel: string;
  to: string;
  count: number;
};

export async function GET() {
  const session = driver.session({
    database: process.env.NEO4J_DATABASE,
  });

  try {
    // Node counts per label. Uses labels(n)[0] to match how the rest of the app
    // treats a node's "primary" label (see lib/labelColors).
    const countsResult = await session.run(
      `MATCH (n)
       RETURN labels(n)[0] AS label, count(*) AS count
       ORDER BY count DESC`
    );

    // The actual (:A)-[:REL]->(:B) patterns present in the data. This is the real
    // ontology as instantiated, rather than a declared-but-unused schema.
    const triplesResult = await session.run(
      `MATCH (a)-[r]->(b)
       RETURN labels(a)[0] AS from, type(r) AS rel, labels(b)[0] AS to, count(*) AS count
       ORDER BY count DESC`
    );

    // Property keys and their types, per label.
    const propsResult = await session.run(`CALL db.schema.nodeTypeProperties()`);

    const propsByLabel = new Map<string, { name: string; types: string[] }[]>();
    for (const record of propsResult.records) {
      const label = (record.get("nodeLabels") as string[])[0];
      const name = record.get("propertyName") as string | null;
      if (!label || !name) continue;
      if (!propsByLabel.has(label)) propsByLabel.set(label, []);
      propsByLabel.get(label)!.push({
        name,
        types: (record.get("propertyTypes") as string[]) ?? [],
      });
    }

    const labels: LabelInfo[] = countsResult.records.map((record) => {
      const label = record.get("label") as string;
      return {
        label,
        count: record.get("count") as number,
        properties: propsByLabel.get(label) ?? [],
      };
    });

    const triples: Triple[] = triplesResult.records.map((record) => ({
      from: record.get("from") as string,
      rel: record.get("rel") as string,
      to: record.get("to") as string,
      count: record.get("count") as number,
    }));

    return NextResponse.json({ labels, triples });
  } catch (error) {
    console.error("Neo4j schema query failed", error);
    return NextResponse.json(
      { error: "Failed to query schema" },
      { status: 500 }
    );
  } finally {
    await session.close();
  }
}
