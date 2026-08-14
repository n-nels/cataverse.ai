"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ForceGraphMethods } from "react-force-graph-2d";
import { colorForLabels } from "@/lib/labelColors";

// react-force-graph-2d draws to a <canvas>, which doesn't exist during
// server-side rendering — load it only in the browser.
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
});

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

export type GraphData = {
  nodes: GraphNode[];
  links: GraphLink[];
};

export default function GraphView({
  onData,
}: {
  onData?: (data: GraphData) => void;
}) {
  const [data, setData] = useState<GraphData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const fgRef = useRef<ForceGraphMethods>(undefined);

  useEffect(() => {
    fetch("/api/graph")
      .then((res) => {
        if (!res.ok) throw new Error(`Request failed: ${res.status}`);
        return res.json();
      })
      .then((d: GraphData) => {
        setData(d);
        onData?.(d);
      })
      .catch((err: Error) => setError(err.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleNodeClick = useCallback((node: object) => {
    setSelected(node as GraphNode);
  }, []);

  const handleEngineStop = useCallback(() => {
    fgRef.current?.zoomToFit(400, 40);
  }, []);

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center text-red-500">
        Failed to load graph: {error}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex flex-1 items-center justify-center text-zinc-400">
        Loading graph…
      </div>
    );
  }

  return (
    // Not `relative` here: react-force-graph's hover tooltip absolute-positions
    // itself against the nearest positioned ancestor, and expects that to be
    // the viewport/body — a `relative` wrapper throws its coordinates off.
    <div className="flex flex-1 overflow-hidden bg-black">
      <ForceGraph2D
        ref={fgRef}
        graphData={data}
        nodeId="id"
        nodeLabel={(node) => (node as GraphNode).labels.join(", ")}
        nodeColor={(node) => colorForLabels((node as GraphNode).labels)}
        nodeRelSize={5}
        linkLabel={(link) => (link as GraphLink).type}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={1}
        linkColor={() => "rgba(255,255,255,0.25)"}
        onNodeClick={handleNodeClick}
        onEngineStop={handleEngineStop}
        backgroundColor="#000000"
      />
      {selected && (
        <div className="fixed right-4 top-4 max-h-[80vh] w-80 overflow-auto rounded-lg border border-zinc-700 bg-zinc-900/95 p-4 text-sm text-zinc-100 shadow-xl">
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
