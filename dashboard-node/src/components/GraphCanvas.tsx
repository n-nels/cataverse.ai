"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ForceGraphMethods } from "react-force-graph-2d";
import { colorForLabels } from "@/lib/labelColors";
import { nodeDisplayLabel } from "@/lib/nodeLabel";
import { useElementSize } from "@/lib/useElementSize";
import type { GraphData, GraphLink, GraphNode } from "./GraphView";

// Above this many nodes, labels only appear once you have zoomed in — drawing
// 1,875 of them at once is both unreadable and slow.
const ALWAYS_LABEL_BELOW = 150;
const LABEL_ZOOM_THRESHOLD = 1.2;

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
  onRemove,
  expandedIds,
  busyId,
}: {
  data: GraphData;
  /** When given, the detail panel offers an "Expand" action for that node. */
  onExpand?: (node: GraphNode) => void;
  /** When given, the detail panel offers a "Remove" action for that node. */
  onRemove?: (node: GraphNode) => void;
  expandedIds?: Set<string>;
  busyId?: string | null;
}) {
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const fgRef = useRef<ForceGraphMethods>(undefined);
  const [containerRef, { width, height }] = useElementSize<HTMLDivElement>();

  const hasFitted = useRef(false);

  const fitView = useCallback(() => {
    fgRef.current?.zoomToFit(400, 40);
  }, []);

  // Where the graph can be expanded (the Explore tab), fit only the first time
  // it settles: every expansion reheats the simulation, and re-fitting on each
  // settle yanked the viewport away from whatever the user had zoomed in on.
  // Elsewhere nothing reheats except the initial layout finding its shape, so
  // fitting on each settle is what centres the view — suppressing it there left
  // the landing graph stranded off to one side.
  const handleEngineStop = useCallback(() => {
    if (onExpand && hasFitted.current) return;
    hasFitted.current = true;
    fitView();
  }, [fitView, onExpand]);

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
          // "after" so the library still paints the node and we only add text.
          nodeCanvasObjectMode={() => "after"}
          nodeCanvasObject={(node, ctx, globalScale) => {
            const n = node as GraphNode & { x?: number; y?: number };
            if (n.x == null || n.y == null) return;
            if (
              data.nodes.length > ALWAYS_LABEL_BELOW &&
              globalScale < LABEL_ZOOM_THRESHOLD
            ) {
              return;
            }

            const text = nodeDisplayLabel(n.labels, n.properties);
            const fontSize = 11 / globalScale;
            ctx.font = `${fontSize}px ui-sans-serif, system-ui, sans-serif`;
            ctx.textAlign = "center";
            ctx.textBaseline = "top";

            // Outline first so the text stays readable over links and nodes.
            ctx.strokeStyle = "rgba(0,0,0,0.9)";
            ctx.lineWidth = 3 / globalScale;
            ctx.lineJoin = "round";
            const y = n.y + 6 + 3 / globalScale;
            ctx.strokeText(text, n.x, y);
            ctx.fillStyle = "#d4d4d8";
            ctx.fillText(text, n.x, y);
          }}
          // Disconnected nodes have no link force damping them, so they drift
          // for the full default 15s cooldown — long enough that you aim at a
          // node and it has moved by the time you click. Settle sparse graphs
          // faster and damp their motion harder.
          cooldownTime={data.links.length === 0 ? 2500 : 15000}
          d3VelocityDecay={data.links.length === 0 ? 0.6 : 0.4}
          linkLabel={(link) => (link as GraphLink).type}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={1}
          linkColor={() => "rgba(255,255,255,0.25)"}
          onNodeClick={(node) => setSelected(node as GraphNode)}
          onEngineStop={handleEngineStop}
          backgroundColor="#000000"
        />
      )}

      <button
        onClick={fitView}
        title="Fit the whole graph in view"
        // Offset from the left edge to clear Next.js's dev-mode indicator,
        // which sits bottom-left and would otherwise cover this while
        // developing or recording locally.
        className="fixed bottom-3 left-20 z-10 rounded-md border border-zinc-700 bg-zinc-900/80 px-2.5 py-1 text-xs text-zinc-400 transition-colors hover:border-zinc-500 hover:text-white"
      >
        Fit view
      </button>

      {selectedLive && (
        // Anchored to the bottom, not the top: pinned top-right it sat on top
        // of the Explore toolbar, hiding the node counts and the Undo button —
        // and Undo is exactly what you reach for while a node is selected.
        <div className="fixed bottom-4 right-4 z-10 max-h-[70vh] w-80 overflow-auto rounded-lg border border-zinc-700 bg-zinc-900/95 p-4 text-sm text-zinc-100 shadow-xl">
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

          {onRemove && (
            <button
              onClick={() => {
                onRemove(selectedLive);
                setSelected(null);
              }}
              className="mb-3 w-full rounded-md border border-zinc-700 px-3 py-1.5 text-xs text-zinc-400 transition-colors hover:border-red-800 hover:bg-red-950/40 hover:text-red-300"
            >
              Remove from view
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
