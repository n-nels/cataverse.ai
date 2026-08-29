"use client";

import { useCallback, useEffect, useState } from "react";
import GraphCanvas from "./GraphCanvas";
import type { GraphData, GraphNode } from "./GraphView";
import { colorForLabels } from "@/lib/labelColors";

const SEED_LIMIT = 12;
const MAX_HISTORY = 20;

/**
 * Labels small enough to show in full. Each has at most ~15 nodes, so an
 * arbitrary sample of 12 hid part of a set that fits on screen comfortably —
 * and for these the complete set is the useful thing to see.
 */
const SEED_ALL_LABELS = new Set([
  "ChemConcept",
  "ChemSpecies",
  "KineticChain",
  "ModelParameter",
  "PyFunction",
  "Material",
  "KineticModel",
]);

/**
 * Hand-picked starting points for the two labels people actually explore from.
 *
 * A dozen arbitrary nodes is a poor way in: they share a label but nothing else,
 * so there is no reason to click one rather than another. Two contrasting
 * experiments — both successful, one a reference measurement and one not — give
 * an immediate comparison to explore, and the pair is small enough to read at a
 * glance.
 *
 * Deliberately deterministic (`ORDER BY` before `LIMIT`): the same two nodes
 * every time, so a tutorial recorded today still matches what a viewer sees.
 */
const SEED_QUERIES: Record<string, { query: string; note: string }> = {
  Filename: {
    query: `MATCH (f:Filename) WHERE f.exp_success AND f.is_reference
WITH f ORDER BY f.datetime LIMIT 1
RETURN f AS n
UNION ALL
MATCH (f:Filename) WHERE f.exp_success AND NOT f.is_reference
WITH f ORDER BY f.datetime LIMIT 1
RETURN f AS n`,
    note: "Two successful experiments — one a reference measurement, one not. Click either, then Expand.",
  },
  Pretreatment: {
    // Step 1 of those same two experiments, so expanding walks the pretreatment
    // sequence forward from the beginning via NEXT_STEP.
    query: `MATCH (f:Filename)-[:HAS_STEP]->(p:Pretreatment)
WHERE f.exp_success AND f.is_reference AND p.step_index = 1
WITH p ORDER BY p.id LIMIT 1
RETURN p AS n
UNION ALL
MATCH (f:Filename)-[:HAS_STEP]->(p:Pretreatment)
WHERE f.exp_success AND NOT f.is_reference AND p.step_index = 1
WITH p ORDER BY p.id LIMIT 1
RETURN p AS n`,
    note: "Step 1 of two successful experiments — one a reference measurement, one not. Expand to walk the sequence forward.",
  },
  // Single node each: these sit downstream in the chain, so one is enough to
  // start from and expanding immediately reveals the surrounding context. Both
  // resolve to the same reference run as the seeds above, so every entry point
  // leads into the same experiment.
  ExpConditions: {
    query: `MATCH (f:Filename)-[:CONDUCTED_UNDER]->(e:ExpConditions)
WHERE f.exp_success AND f.is_reference
WITH e, f ORDER BY f.datetime LIMIT 1
RETURN e AS n`,
    note: "The conditions of one successful reference measurement. Expand to see the experiment it belongs to and what it yielded.",
  },
  AdsParams: {
    query: `MATCH (f:Filename)-[:CONDUCTED_UNDER]->(:ExpConditions)-[:YIELDS]->(a:AdsParams)
WHERE f.exp_success AND f.is_reference
WITH a, f ORDER BY f.datetime LIMIT 1
RETURN a AS n`,
    note: "Fitted adsorption parameters from one successful reference measurement. Expand to see the conditions that produced them.",
  },
};

type LabelInfo = { label: string; count: number };

type Snapshot = { nodes: GraphData["nodes"]; links: GraphData["links"]; expanded: Set<string> };

/** Everything that makes up one label's exploration, stashed on switch. */
type Session = {
  graph: GraphData;
  expandedIds: Set<string>;
  history: Snapshot[];
};

/**
 * A link's endpoint is a node id at first, but react-force-graph replaces it
 * with the node object once it has processed the data. Both shapes turn up.
 */
function endpointId(end: unknown): string {
  return typeof end === "string" ? end : (end as GraphNode).id;
}

export default function ExploreView() {
  const [labels, setLabels] = useState<LabelInfo[]>([]);
  const [graph, setGraph] = useState<GraphData>({ nodes: [], links: [] });
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [busyId, setBusyId] = useState<string | null>(null);
  const [history, setHistory] = useState<Snapshot[]>([]);
  // Bumped on each new seed so GraphCanvas remounts and fits the fresh graph.
  // Expansions deliberately keep the same key: remounting there would reset the
  // layout and the viewport the user has zoomed to.
  const [seedKey, setSeedKey] = useState(0);
  const [seeding, setSeeding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  // Each "start from" is its own workspace. Switching stashes what you built
  // and restores whatever that label had, so you can compare two lines of
  // exploration without either polluting or destroying the other.
  const [activeLabel, setActiveLabel] = useState<string | null>(null);
  const [sessions, setSessions] = useState<Record<string, Session>>({});

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

  /** Remember the current view so an expansion that blows up can be undone. */
  const pushHistory = useCallback(() => {
    setHistory((h) => [
      ...h.slice(-(MAX_HISTORY - 1)),
      { nodes: graph.nodes, links: graph.links, expanded: expandedIds },
    ]);
  }, [graph, expandedIds]);

  const undo = useCallback(() => {
    if (history.length === 0) return;
    const prev = history[history.length - 1];
    setGraph({ nodes: prev.nodes, links: prev.links });
    setExpandedIds(prev.expanded);
    setHistory((h) => h.slice(0, -1));
    setError(null);
    setNote(null);
  }, [history]);

  const removeNode = useCallback(
    (node: GraphNode) => {
      pushHistory();
      setGraph((prev) => ({
        nodes: prev.nodes.filter((n) => n.id !== node.id),
        links: prev.links.filter(
          (l) =>
            endpointId(l.source) !== node.id && endpointId(l.target) !== node.id
        ),
      }));
      setExpandedIds((prev) => {
        const next = new Set(prev);
        next.delete(node.id);
        return next;
      });
      setNote(`Removed one ${node.labels[0] ?? "node"} from the view.`);
    },
    [pushHistory]
  );

  /** Load a label's starting nodes into an empty workspace. */
  const seedFresh = useCallback(async (label: string) => {
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
          query:
            SEED_QUERIES[label]?.query ??
            (SEED_ALL_LABELS.has(label)
              ? `MATCH (n:${label}) RETURN n`
              : `MATCH (n:${label}) RETURN n LIMIT ${SEED_LIMIT}`),
        }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error ?? "Could not load starting nodes.");
        return;
      }
      setGraph({ nodes: body.nodes, links: body.links });
      setExpandedIds(new Set());
      setHistory([]);
      // Remount so the fresh graph gets fitted. Only done here — remounting on
      // an expansion or a restore would reset the layout.
      setSeedKey((k) => k + 1);
      setNote(
        SEED_QUERIES[label]?.note ??
          `Starting from ${body.nodes.length} ${label} node${body.nodes.length === 1 ? "" : "s"}. Click one, then Expand.`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed.");
    } finally {
      setSeeding(false);
    }
  }, []);

  /**
   * Switch workspaces. Each label keeps its own graph, expansions and undo
   * history: leaving one stashes it untouched, and coming back restores exactly
   * what was there — including node positions, since the layout lives on the
   * node objects themselves and we deliberately do not remount on a restore.
   */
  const selectLabel = useCallback(
    async (label: string) => {
      if (seeding || label === activeLabel) return;

      if (activeLabel) {
        setSessions((prev) => ({
          ...prev,
          [activeLabel]: { graph, expandedIds, history },
        }));
      }
      setActiveLabel(label);
      setError(null);

      const saved = sessions[label];
      if (saved) {
        setGraph(saved.graph);
        setExpandedIds(saved.expandedIds);
        setHistory(saved.history);
        setNote(
          `Back to your ${label} exploration — ${saved.graph.nodes.length} node${saved.graph.nodes.length === 1 ? "" : "s"}.`
        );
        return;
      }
      await seedFresh(label);
    },
    [seeding, activeLabel, graph, expandedIds, history, sessions, seedFresh]
  );

  const expand = useCallback(
    async (node: GraphNode) => {
      if (busyId) return;
      setBusyId(node.id);
      setError(null);
      setNote(null);
      pushHistory();
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
        if (body.nodes.length <= 1) {
          setNote(
            "Nothing further from here — this node has no other relationships."
          );
        } else if (body.truncated) {
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
    [busyId, merge, pushHistory]
  );

  /** Discard the active workspace so that label starts fresh next time. */
  const reset = () => {
    setGraph({ nodes: [], links: [] });
    setExpandedIds(new Set());
    setHistory([]);
    if (activeLabel) {
      setSessions((prev) => {
        const next = { ...prev };
        delete next[activeLabel];
        return next;
      });
    }
    setActiveLabel(null);
    setError(null);
    setNote(null);
  };

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="border-b border-zinc-800 bg-zinc-950 px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="text-xs text-zinc-500">Start from</span>
          {labels.map((l) => {
            const isActive = l.label === activeLabel;
            const hasSession = Boolean(sessions[l.label]);
            return (
              <button
                key={l.label}
                onClick={() => selectLabel(l.label)}
                disabled={seeding}
                title={
                  hasSession && !isActive
                    ? `Return to your ${l.label} exploration`
                    : undefined
                }
                className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors disabled:opacity-50 ${
                  isActive
                    ? "border-zinc-400 bg-zinc-800 text-white"
                    : "border-zinc-700 text-zinc-300 hover:border-zinc-500 hover:text-white"
                }`}
              >
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ backgroundColor: colorForLabels([l.label]) }}
                />
                {l.label}
                {/* A saved-but-inactive workspace is invisible otherwise, and
                    knowing it is there is the point of keeping it. */}
                {hasSession && !isActive && (
                  <span className="text-zinc-500">•</span>
                )}
              </button>
            );
          })}

          {graph.nodes.length > 0 && (
            <span className="ml-auto flex items-center gap-3 text-xs">
              <span className="text-zinc-400">
                {graph.nodes.length} nodes · {graph.links.length} relationships ·{" "}
                {expandedIds.size} expanded
              </span>
              <button
                onClick={undo}
                disabled={history.length === 0}
                title="Undo the last expansion or removal"
                className="rounded px-2 py-0.5 text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-white disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-zinc-500"
              >
                Undo{history.length > 0 ? ` (${history.length})` : ""}
              </button>
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
          key={seedKey}
          data={graph}
          onExpand={expand}
          onRemove={removeNode}
          expandedIds={expandedIds}
          busyId={busyId}
        />
      )}
    </div>
  );
}
