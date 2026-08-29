"use client";

import dynamic from "next/dynamic";
import { useCallback, useRef, useState } from "react";
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
export default function GraphCanvas({ data }: { data: GraphData }) {
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const fgRef = useRef<ForceGraphMethods>(undefined);
  const [containerRef, { width, height }] = useElementSize<HTMLDivElement>();

  const handleEngineStop = useCallback(() => {
    fgRef.current?.zoomToFit(400, 40);
  }, []);

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
      {selected && (
        <div className="fixed right-4 top-4 z-10 max-h-[80vh] w-80 overflow-auto rounded-lg border border-zinc-700 bg-zinc-900/95 p-4 text-sm text-zinc-100 shadow-xl">
          <div className="mb-2 flex items-start justify-between gap-2">
            <span className="font-semibold text-orange-400">
              {selected.labels.join(", ")}
            </span>
            <button
              onClick={() => setSelected(null)}
              className="text-zinc-400 hover:text-white"
            >
              ✕
            </button>
          </div>
          <pre className="whitespace-pre-wrap break-words font-mono text-xs text-zinc-300">
            {JSON.stringify(selected.properties, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
