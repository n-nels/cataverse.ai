import neo4j, { Node, Relationship } from "neo4j-driver";

/**
 * Converting Neo4j driver values into JSON the browser can use.
 *
 * The driver returns its own classes — Integer (64-bit, so not a JS number),
 * temporal types, spatial Points, Nodes, Relationships — none of which survive
 * JSON.stringify meaningfully. Everything crossing the API boundary goes
 * through here.
 */

export type GraphNode = {
  id: string;
  labels: string[];
  properties: Record<string, unknown>;
};

export type GraphLink = {
  id: string;
  source: string;
  target: string;
  type: string;
  properties: Record<string, unknown>;
};

export function toPlain(value: unknown): unknown {
  if (value === null || value === undefined) return null;
  if (neo4j.isInt(value)) return value.toNumber();
  if (
    neo4j.isDate(value) ||
    neo4j.isDateTime(value) ||
    neo4j.isLocalDateTime(value) ||
    neo4j.isTime(value) ||
    neo4j.isLocalTime(value) ||
    neo4j.isDuration(value) ||
    neo4j.isPoint(value)
  ) {
    return value.toString();
  }
  if (Array.isArray(value)) return value.map(toPlain);
  // A node or relationship appearing in a *table* cell gets a short label; the
  // full object is delivered separately in the nodes/links arrays.
  if (neo4j.isNode(value)) return `(:${(value as Node).labels.join(":")})`;
  if (neo4j.isRelationship(value)) return `[:${(value as Relationship).type}]`;
  if (typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => [
        k,
        toPlain(v),
      ])
    );
  }
  return value;
}

export function plainProps(
  props: Record<string, unknown>
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(props).map(([k, v]) => [k, toPlain(v)])
  );
}

export function nodeToGraphNode(n: Node): GraphNode {
  return {
    id: n.elementId,
    labels: n.labels,
    properties: plainProps(n.properties),
  };
}

export function relToGraphLink(r: Relationship): GraphLink {
  return {
    id: r.elementId,
    source: r.startNodeElementId,
    target: r.endNodeElementId,
    type: r.type,
    properties: plainProps(r.properties),
  };
}
