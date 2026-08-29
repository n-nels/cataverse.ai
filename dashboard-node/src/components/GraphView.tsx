"use client";

import { useEffect, useState } from "react";
import GraphCanvas from "./GraphCanvas";

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

/**
 * The landing view: loads the whole graph once and renders it.
 * Rendering lives in GraphCanvas so the Cypher query view can reuse it.
 */
export default function GraphView({
  onData,
}: {
  onData?: (data: GraphData) => void;
}) {
  const [data, setData] = useState<GraphData | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  return <GraphCanvas data={data} />;
}
