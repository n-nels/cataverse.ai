"use client";

import { useState } from "react";
import GraphView, { type GraphData } from "./GraphView";
import StatsBar from "./StatsBar";
import OntologyView from "./OntologyView";
import QueryView from "./QueryView";
import AgentPreview from "./AgentPreview";

const TABS = [
  { id: "graph", label: "Graph" },
  { id: "query", label: "Query" },
  { id: "ontology", label: "Ontology" },
  { id: "agent", label: "Ask the Agent" },
] as const;

type Tab = (typeof TABS)[number]["id"];

export default function AppShell() {
  const [tab, setTab] = useState<Tab>("graph");
  const [data, setData] = useState<GraphData | null>(null);

  return (
    <div className="flex flex-1 flex-col overflow-hidden bg-black">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 px-4 py-3">
        <div className="flex items-baseline gap-2">
          <h1 className="text-base font-semibold tracking-tight text-zinc-100">
            cataverse<span className="text-orange-500">.ai</span>
          </h1>
          <span className="text-xs text-zinc-500">
            Autonomous catalyst discovery — graph explorer
          </span>
        </div>
        <nav className="flex gap-1 rounded-lg border border-zinc-800 bg-zinc-950 p-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                tab === t.id
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      {tab === "graph" && <StatsBar data={data} />}

      <div className="flex flex-1 overflow-hidden">
        {/* Keep GraphView mounted across tab switches so the force layout
            doesn't re-simulate from scratch every time you tab back. */}
        <div className={tab === "graph" ? "flex flex-1" : "hidden"}>
          <GraphView onData={setData} />
        </div>
        {tab === "query" && <QueryView />}
        {tab === "ontology" && <OntologyView />}
        {tab === "agent" && <AgentPreview />}
      </div>
    </div>
  );
}
