"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ForceGraphMethods } from "react-force-graph-2d";
import { colorForLabels } from "@/lib/labelColors";
import { useElementSize } from "@/lib/useElementSize";
import type { GraphData, GraphLink, GraphNode } from "./GraphView";

// react-force-graph-2d draws to a <canvas>, which doesn't exist during
// server-side rendering — load it only in the browser.
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
});

/**
 * The force-directed graph itself, given data. Extracted from GraphView so the
 * landing page and the Cypher query view render results identically instead of
 * drifting apart.
 *
 * Sizing is measured rather than left to the library: react-force-graph renders
 * into a div with no intrinsic width, which collapses to 0 as a flex item. It
 * happens to look right when the graph is full-bleed (it falls back to the
 * window size) but not when it shares the screen with a query editor.
 */
export default function GraphCanvas({
  data,
  onExpand,
  expandedIds,
  busyId,
  autoFit = true,
}: {
  data: GraphData;
  /** When given, the detail panel offers an "Expand" action for that node. */
  onExpand?: (node: GraphNode) => void;
  /** Nodes already expanded — drawn with a ring so you can see where you've been. */
  expandedIds?: Set<string>;
  busyId?: string | null;
  /**
   * Re-fit the view when the simulation settles. Wanted on first render, but
   * not after an expansion — refitting mid-exploration yanks the viewport away
   * from whatever the user was looking at.
   */
  autoFit?: boolean;
}) {
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const fgRef = useRef<ForceGraphMethods>(undefined);
  const [containerRef, { width, height }] = useElementSize<HTMLDivElement>();

  const handleEngineStop = useCallback(() => {
    if (autoFit) fgRef.current?.zoomToFit(400, 40);
  }, [autoFit]);

  // Bound how far the repulsion force reaches, but ONLY where it is needed.
  // Seed nodes in the Explore tab have no relationships yet, so nothing pulls
  // back against the charge force: they drift apart until zoom-to-fit shrinks
  // them to sub-pixel, which looks like an empty canvas rather than an obvious
  // bug. Applying this to the ~1.9k-node landing view instead broke it
  // outright, so it is deliberately scoped to sparse graphs.
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || width === 0) return;
    if (data.links.length > 0 || data.nodes.length > 60) return;
    (
      fg.d3Force("charge") as { distanceMax?: (d: number) => void } | undefined
    )?.distanceMax?.(300);
  }, [width, data]);

  // Keep the panel in sync with incoming data: after an expansion the selected
  // node is a new object, and its stale copy would show outdated properties.
  const selectedLive = selected
    ? data.nodes.find((n) => n.id === selected.id) ?? selected
    : null;

  return (
    // Deliberately not `relative`: react-force-graph's hover tooltip positions
    // itself against the nearest positioned ancestor and expects that to be the
    // viewport — a `relative` wrapper throws its coordinates off.
    <div ref={containerRef} className="flex flex-1 overflow-hidden bg-black">
      {width > 0 && height > 0 && (
        <ForceGraph2D
          ref={fgRef}
          width={width}
          height={height}
          graphData={data}
          nodeId="id"
          nodeLabel={(node) => (node as GraphNode).labels.join(", ")}
          nodeColor={(node) => colorForLabels((node as GraphNode).labels)}
          nodeRelSize={5}
          linkLabel={(link) => (link as GraphLink).type}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={1}
          linkColor={() => "rgba(255,255,255,0.25)"}
          onNodeClick={(node) => setSelected(node as GraphNode)}
          onEngineStop={handleEngineStop}
          backgroundColor="#000000"
        />
      )}
      {selectedLive && (
        <div className="fixed right-4 top-4 z-10 max-h-[80vh] w-80 overflow-auto rounded-lg border border-zinc-700 bg-zinc-900/95 p-4 text-sm text-zinc-100 shadow-xl">
          <div className="mb-2 flex items-start justify-between gap-2">
            <span className="font-semibold text-orange-400">
              {selectedLive.labels.join(", ")}
            </span>
            <button
              onClick={() => setSelected(null)}
              className="text-zinc-400 hover:text-white"
            >
              ✕
            </button>
          </div>

          {onExpand && (
            <button
              onClick={() => onExpand(selectedLive)}
              disabled={busyId === selectedLive.id}
              className="mb-3 w-full rounded-md bg-orange-500 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-orange-400 disabled:opacity-50"
            >
              {busyId === selectedLive.id
                ? "Expanding…"
                : expandedIds?.has(selectedLive.id)
                  ? "Expand again"
                  : "Expand neighbours"}
            </button>
          )}

          <pre className="whitespace-pre-wrap break-words font-mono text-xs text-zinc-300">
            {JSON.stringify(selectedLive.properties, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
