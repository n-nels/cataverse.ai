"use client";

import { useCallback, useState } from "react";
import GraphCanvas from "./GraphCanvas";
import type { GraphData } from "./GraphView";

type QueryResult = GraphData & {
  columns: string[];
  rows: Record<string, unknown>[];
  rowCount: number;
  truncated: boolean;
};

// Starting points that exercise the real schema — handy for demos, and they
// save anyone new from having to learn the label names before seeing anything.
const EXAMPLES: { label: string; query: string }[] = [
  {
    label: "Materials → experiments",
    query:
      "MATCH (m:Material)-[r:HAS_EXPERIMENT]->(f:Filename)\nRETURN m, r, f\nLIMIT 25",
  },
  {
    label: "A pretreatment sequence",
    query:
      "MATCH p = (f:Filename)-[:HAS_STEP]->(:Pretreatment)-[:NEXT_STEP*..3]->()\nRETURN p\nLIMIT 5",
  },
  {
    label: "Concepts and what instantiates them",
    query:
      "MATCH (c:ChemConcept)<-[r:INSTANCE_OF]-(n)\nRETURN c, r, n\nLIMIT 50",
  },
  {
    label: "Conditions → adsorption params",
    query:
      "MATCH (e:ExpConditions)-[r:YIELDS]->(a:AdsParams)\nRETURN e, r, a\nLIMIT 25",
  },
  {
    label: "Count by label (table)",
    query:
      "MATCH (n)\nRETURN labels(n)[0] AS label, count(*) AS count\nORDER BY count DESC",
  },
];

function cellText(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function QueryView() {
  const [query, setQuery] = useState(EXAMPLES[0].query);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [tab, setTab] = useState<"graph" | "table">("graph");

  const run = useCallback(async (q: string) => {
    if (!q.trim() || running) return;
    setRunning(true);
    setError(null);
    try {
      const res = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error ?? `Request failed: ${res.status}`);
        setResult(null);
      } else {
        setResult(body as QueryResult);
        // A query returning only scalars has nothing to draw — show the table
        // rather than an empty canvas.
        setTab(body.nodes.length > 0 ? "graph" : "table");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed.");
      setResult(null);
    } finally {
      setRunning(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running]);

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="border-b border-zinc-800 bg-zinc-950 p-3">
        <div className="mb-2 flex flex-wrap gap-1.5">
          {EXAMPLES.map((ex) => (
            <button
              key={ex.label}
              onClick={() => {
                setQuery(ex.query);
                run(ex.query);
              }}
              className="rounded-full border border-zinc-700 px-2.5 py-1 text-xs text-zinc-400 transition-colors hover:border-zinc-500 hover:text-white"
            >
              {ex.label}
            </button>
          ))}
        </div>

        <div className="flex gap-2">
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                e.preventDefault();
                run(query);
              }
            }}
            spellCheck={false}
            rows={4}
            className="flex-1 resize-y rounded-md border border-zinc-700 bg-black px-3 py-2 font-mono text-sm text-zinc-100 outline-none focus:border-orange-500"
            placeholder="MATCH (n) RETURN n LIMIT 25"
          />
          <div className="flex flex-col gap-2">
            <button
              onClick={() => run(query)}
              disabled={running}
              className="rounded-md bg-orange-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-orange-400 disabled:opacity-50"
            >
              {running ? "Running…" : "Run"}
            </button>
            <span className="text-center text-[10px] text-zinc-600">
              Ctrl+Enter
            </span>
          </div>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
          <span className="text-zinc-600">Read-only — writes are rejected.</span>
          {result && (
            <>
              <span className="text-zinc-400">
                {result.nodes.length} nodes · {result.links.length} relationships
                · {result.rowCount} row{result.rowCount === 1 ? "" : "s"}
              </span>
              {result.truncated && (
                <span className="text-yellow-500">
                  showing first {result.rows.length} rows
                </span>
              )}
              <span className="ml-auto flex gap-1">
                {(["graph", "table"] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTab(t)}
                    className={`rounded px-2 py-0.5 capitalize transition-colors ${
                      tab === t
                        ? "bg-zinc-800 text-white"
                        : "text-zinc-500 hover:text-zinc-300"
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </span>
            </>
          )}
        </div>

        {error && (
          <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap rounded-md border border-red-900 bg-red-950/40 p-2 font-mono text-xs text-red-300">
            {error}
          </pre>
        )}
      </div>

      {!result ? (
        <div className="flex flex-1 items-center justify-center text-sm text-zinc-600">
          Run a query to see results.
        </div>
      ) : tab === "graph" ? (
        result.nodes.length > 0 ? (
          <GraphCanvas
            // Remount on new results so the force simulation restarts cleanly
            // instead of animating from the previous layout.
            key={`${result.nodes.length}-${result.links.length}-${result.rowCount}`}
            data={{ nodes: result.nodes, links: result.links }}
          />
        ) : (
          <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-zinc-600">
            No nodes or relationships returned. Return whole nodes (e.g.{" "}
            <code className="mx-1 font-mono text-zinc-500">RETURN n</code>)
            rather than properties to draw a graph — or switch to Table.
          </div>
        )
      ) : (
        <div className="flex-1 overflow-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead className="sticky top-0 bg-zinc-900">
              <tr>
                {result.columns.map((c) => (
                  <th
                    key={c}
                    className="border-b border-zinc-700 px-3 py-2 font-medium text-zinc-300"
                  >
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row, i) => (
                <tr key={i} className="hover:bg-zinc-900/50">
                  {result.columns.map((c) => (
                    <td
                      key={c}
                      className="border-b border-zinc-800/60 px-3 py-1.5 font-mono text-zinc-400"
                    >
                      {cellText(row[c])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
