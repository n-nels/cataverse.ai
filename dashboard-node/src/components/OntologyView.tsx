"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ForceGraphMethods } from "react-force-graph-2d";
import { colorForLabels } from "@/lib/labelColors";
import { useElementSize } from "@/lib/useElementSize";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
});

type LabelInfo = {
  label: string;
  count: number;
  properties: { name: string; types: string[] }[];
};

type Triple = { from: string; rel: string; to: string; count: number };

type SchemaData = { labels: LabelInfo[]; triples: Triple[] };

type MetaNode = { id: string; count: number; x?: number; y?: number };

// Node counts span three orders of magnitude (1 -> 1107), so scale the radius by
// sqrt to keep the smallest labels visible without the largest swamping the canvas.
function radiusFor(count: number): number {
  return 4 + Math.sqrt(count) * 0.7;
}

function shortType(types: string[]): string {
  if (types.length === 0) return "";
  return types
    .map((t) => t.replace(/ NOT NULL/g, "").replace(/^LIST<(.+)>$/, "$1[]"))
    .join(" | ");
}

export default function OntologyView() {
  const [data, setData] = useState<SchemaData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const fgRef = useRef<ForceGraphMethods>(undefined);
  const [containerRef, { width, height }] = useElementSize<HTMLDivElement>();

  useEffect(() => {
    fetch("/api/schema")
      .then((res) => {
        if (!res.ok) throw new Error(`Request failed: ${res.status}`);
        return res.json();
      })
      .then(setData)
      .catch((err: Error) => setError(err.message));
  }, []);

  const graph = useMemo(() => {
    if (!data) return { nodes: [], links: [] };
    const known = new Set(data.labels.map((l) => l.label));
    return {
      nodes: data.labels.map((l) => ({ id: l.label, count: l.count })),
      links: data.triples
        .filter((t) => known.has(t.from) && known.has(t.to))
        .map((t) => ({
          source: t.from,
          target: t.to,
          rel: t.rel,
          count: t.count,
        })),
    };
  }, [data]);

  const handleEngineStop = useCallback(() => {
    fgRef.current?.zoomToFit(400, 60);
  }, []);

  // The default forces are tuned for many small nodes. Here there are only ~11,
  // sized up to ~27px radius, so without stronger repulsion the big circles (and
  // their text labels) pile on top of each other.
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || width === 0) return;
    (fg.d3Force("charge") as { strength?: (s: number) => void } | undefined)
      ?.strength?.(-350);
    (fg.d3Force("link") as { distance?: (d: number) => void } | undefined)
      ?.distance?.(80);
    fg.d3ReheatSimulation();
    // Reheating restarts the simulation, which can outrun the zoomToFit that
    // onEngineStop already fired. Refit once the new layout has settled.
    const timer = setTimeout(() => fgRef.current?.zoomToFit(400, 50), 1500);
    return () => clearTimeout(timer);
  }, [data, width, height]);

  const drawNode = useCallback(
    (node: object, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const n = node as MetaNode;
      if (n.x == null || n.y == null) return;
      const r = radiusFor(n.count);
      const isSelected = selected === n.id;

      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
      ctx.fillStyle = colorForLabels([n.id]);
      ctx.fill();
      if (isSelected) {
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 2 / globalScale;
        ctx.stroke();
      }

      const fontSize = 11 / globalScale;
      ctx.font = `${isSelected ? "bold " : ""}${fontSize}px ui-sans-serif, system-ui, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillStyle = isSelected ? "#ffffff" : "#d4d4d8";
      ctx.fillText(n.id, n.x, n.y + r + 2 / globalScale);
    },
    [selected]
  );

  const paintPointerArea = useCallback(
    (node: object, color: string, ctx: CanvasRenderingContext2D) => {
      const n = node as MetaNode;
      if (n.x == null || n.y == null) return;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(n.x, n.y, radiusFor(n.count), 0, 2 * Math.PI);
      ctx.fill();
    },
    []
  );

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center text-red-500">
        Failed to load schema: {error}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex flex-1 items-center justify-center text-zinc-400">
        Loading ontology…
      </div>
    );
  }

  const selectedInfo = data.labels.find((l) => l.label === selected);
  const selectedTriples = selected
    ? data.triples.filter((t) => t.from === selected || t.to === selected)
    : [];

  return (
    <div className="flex flex-1 flex-col overflow-hidden lg:flex-row">
      <div ref={containerRef} className="relative flex min-h-[300px] flex-1 bg-black">
        {width > 0 && height > 0 && (
          <ForceGraph2D
            ref={fgRef}
            width={width}
            height={height}
            graphData={graph}
            nodeId="id"
            nodeCanvasObject={drawNode}
            nodePointerAreaPaint={paintPointerArea}
            linkLabel={(link) =>
              `${(link as { rel: string }).rel} (${(link as { count: number }).count})`
            }
            linkDirectionalArrowLength={5}
            linkDirectionalArrowRelPos={1}
            linkCurvature={0.15}
            linkColor={() => "rgba(255,255,255,0.3)"}
            onNodeClick={(node) => setSelected((node as MetaNode).id)}
            onBackgroundClick={() => setSelected(null)}
            onEngineStop={handleEngineStop}
            backgroundColor="#000000"
          />
        )}
        <p className="pointer-events-none absolute bottom-3 left-3 text-xs text-zinc-600">
          Node size ∝ count · hover an edge for its relationship type · click a
          node for details
        </p>
      </div>

      <aside className="w-full shrink-0 overflow-y-auto border-t border-zinc-800 bg-zinc-950 p-4 lg:w-96 lg:border-l lg:border-t-0">
        {!selectedInfo ? (
          <>
            <h2 className="mb-1 text-sm font-semibold text-zinc-100">
              Ontology
            </h2>
            <p className="mb-4 text-xs text-zinc-500">
              {data.labels.length} node types ·{" "}
              {new Set(data.triples.map((t) => t.rel)).size} relationship types.
              Select a type to see its properties and connections.
            </p>
            <ul className="space-y-1">
              {data.labels.map((l) => (
                <li key={l.label}>
                  <button
                    onClick={() => setSelected(l.label)}
                    className="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-sm text-zinc-300 transition-colors hover:bg-zinc-900 hover:text-white"
                  >
                    <span className="flex items-center gap-2">
                      <span
                        className="h-2.5 w-2.5 shrink-0 rounded-full"
                        style={{ backgroundColor: colorForLabels([l.label]) }}
                      />
                      {l.label}
                    </span>
                    <span className="text-xs text-zinc-500">
                      {l.count.toLocaleString()}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <>
            <div className="mb-3 flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <span
                  className="h-3 w-3 shrink-0 rounded-full"
                  style={{ backgroundColor: colorForLabels([selectedInfo.label]) }}
                />
                <h2 className="text-sm font-semibold text-zinc-100">
                  {selectedInfo.label}
                </h2>
                <span className="text-xs text-zinc-500">
                  {selectedInfo.count.toLocaleString()} nodes
                </span>
              </div>
              <button
                onClick={() => setSelected(null)}
                className="text-zinc-500 hover:text-white"
                aria-label="Back to all types"
              >
                ✕
              </button>
            </div>

            <h3 className="mb-1.5 text-xs font-medium uppercase tracking-wide text-zinc-500">
              Properties
            </h3>
            {selectedInfo.properties.length === 0 ? (
              <p className="mb-4 text-xs text-zinc-600">None recorded.</p>
            ) : (
              <ul className="mb-4 space-y-1">
                {selectedInfo.properties.map((p) => (
                  <li key={p.name} className="font-mono text-xs text-zinc-300">
                    {p.name}
                    <span className="text-zinc-600">
                      {" : "}
                      {shortType(p.types)}
                    </span>
                  </li>
                ))}
              </ul>
            )}

            <h3 className="mb-1.5 text-xs font-medium uppercase tracking-wide text-zinc-500">
              Relationships
            </h3>
            <ul className="space-y-1.5">
              {selectedTriples.map((t, i) => (
                <li key={i} className="text-xs">
                  <button
                    onClick={() =>
                      setSelected(t.from === selected ? t.to : t.from)
                    }
                    className="text-left text-zinc-400 transition-colors hover:text-white"
                  >
                    <span
                      className={
                        t.from === selected ? "text-zinc-200" : "text-zinc-500"
                      }
                    >
                      {t.from}
                    </span>
                    <span className="text-emerald-400"> —{t.rel}→ </span>
                    <span
                      className={
                        t.to === selected ? "text-zinc-200" : "text-zinc-500"
                      }
                    >
                      {t.to}
                    </span>
                    <span className="text-zinc-600"> ×{t.count.toLocaleString()}</span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </aside>
    </div>
  );
}
