"use client";

import { useCallback, useEffect, useState } from "react";
import GraphCanvas from "./GraphCanvas";
import type { GraphData, GraphNode } from "./GraphView";
import { colorForLabels } from "@/lib/labelColors";

const SEED_LIMIT = 12;

type LabelInfo = { label: string; count: number };

export default function ExploreView() {
  const [labels, setLabels] = useState<LabelInfo[]>([]);
  const [graph, setGraph] = useState<GraphData>({ nodes: [], links: [] });
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [busyId, setBusyId] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/schema")
      .then((r) => r.json())
      .then((d) => setLabels(d.labels ?? []))
      .catch(() => setLabels([]));
  }, []);

  /**
   * Merge new nodes/links into what's on screen, keeping the *existing* node
   * objects. react-force-graph stores each node's x/y on the object itself, so
   * replacing them would reset the layout and make the whole graph jump on
   * every expansion.
   */
  const merge = useCallback((incoming: GraphData) => {
    setGraph((prev) => {
      const nodes = new Map(prev.nodes.map((n) => [n.id, n]));
      for (const n of incoming.nodes) if (!nodes.has(n.id)) nodes.set(n.id, n);

      const links = new Map(prev.links.map((l) => [l.id, l]));
      for (const l of incoming.links) if (!links.has(l.id)) links.set(l.id, l);

      // Defensive: react-force-graph throws on a link pointing at a node it
      // wasn't given.
      const linkList = Array.from(links.values()).filter((l) => {
        const s = typeof l.source === "string" ? l.source : (l.source as unknown as GraphNode).id;
        const t = typeof l.target === "string" ? l.target : (l.target as unknown as GraphNode).id;
        return nodes.has(s) && nodes.has(t);
      });

      return { nodes: Array.from(nodes.values()), links: linkList };
    });
  }, []);

  const seed = useCallback(
    async (label: string) => {
      if (seeding) return;
      setSeeding(true);
      setError(null);
      setNote(null);
      try {
        const res = await fetch("/api/query", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          // `label` comes from /api/schema, so it is one of the graph's own
          // labels rather than free text.
          body: JSON.stringify({
            query: `MATCH (n:${label}) RETURN n LIMIT ${SEED_LIMIT}`,
          }),
        });
        const body = await res.json();
        if (!res.ok) {
          setError(body.error ?? "Could not load starting nodes.");
          return;
        }
        setGraph({ nodes: body.nodes, links: body.links });
        setExpandedIds(new Set());
        setNote(
          `Starting from ${body.nodes.length} ${label} node${body.nodes.length === 1 ? "" : "s"}. Click one, then Expand.`
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "Request failed.");
      } finally {
        setSeeding(false);
      }
    },
    [seeding]
  );

  const expand = useCallback(
    async (node: GraphNode) => {
      if (busyId) return;
      setBusyId(node.id);
      setError(null);
      setNote(null);
      try {
        const res = await fetch(
          `/api/neighbors?id=${encodeURIComponent(node.id)}`
        );
        const body = await res.json();
        if (!res.ok) {
          setError(body.error ?? "Expansion failed.");
          return;
        }
        merge({ nodes: body.nodes, links: body.links });
        setExpandedIds((prev) => new Set(prev).add(node.id));
        if (body.truncated) {
          setNote(
            `That node has more neighbours than shown — capped at ${body.limit}.`
          );
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Request failed.");
      } finally {
        setBusyId(null);
      }
    },
    [busyId, merge]
  );

  const reset = () => {
    setGraph({ nodes: [], links: [] });
    setExpandedIds(new Set());
    setError(null);
    setNote(null);
  };

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="border-b border-zinc-800 bg-zinc-950 px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="text-xs text-zinc-500">Start from</span>
          {labels.map((l) => (
            <button
              key={l.label}
              onClick={() => seed(l.label)}
              disabled={seeding}
              className="flex items-center gap-1.5 rounded-full border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300 transition-colors hover:border-zinc-500 hover:text-white disabled:opacity-50"
            >
              <span
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: colorForLabels([l.label]) }}
              />
              {l.label}
            </button>
          ))}

          {graph.nodes.length > 0 && (
            <span className="ml-auto flex items-center gap-3 text-xs">
              <span className="text-zinc-400">
                {graph.nodes.length} nodes · {graph.links.length} relationships ·{" "}
                {expandedIds.size} expanded
              </span>
              <button
                onClick={reset}
                className="rounded px-2 py-0.5 text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-white"
              >
                Clear
              </button>
            </span>
          )}
        </div>

        {(note || error) && (
          <p
            className={`mt-1.5 text-xs ${error ? "text-red-400" : "text-zinc-500"}`}
          >
            {error ?? note}
          </p>
        )}
      </div>

      {graph.nodes.length === 0 ? (
        <div className="flex flex-1 items-center justify-center px-8 text-center">
          <p className="max-w-md text-sm leading-relaxed text-zinc-600">
            Pick a node type above to start from a handful of nodes, then click
            any node and press{" "}
            <span className="text-zinc-400">Expand neighbours</span> to pull in
            what it connects to.
            <br />
            <br />
            Build up only the part of the graph you care about, instead of
            starting from all 1,875 nodes at once.
          </p>
        </div>
      ) : (
        <GraphCanvas
          data={graph}
          onExpand={expand}
          expandedIds={expandedIds}
          busyId={busyId}
        />
      )}
    </div>
  );
}
