"use client";

import { useState } from "react";
import GraphView, { type GraphData } from "./GraphView";
import StatsBar from "./StatsBar";
import OntologyView from "./OntologyView";
import ExploreView from "./ExploreView";
import QueryView from "./QueryView";
import AgentPreview from "./AgentPreview";

const TABS = [
  { id: "graph", label: "Graph" },
  { id: "explore", label: "Explore" },
  { id: "query", label: "Query" },
  { id: "ontology", label: "Ontology" },
  { id: "agent", label: "Ask the Agent" },
] as const;

type Tab = (typeof TABS)[number]["id"];

export default function AppShell() {
  const [tab, setTab] = useState<Tab>("graph");
  const [data, setData] = useState<GraphData | null>(null);
  // Tabs are mounted on first visit and kept mounted thereafter.
  const [visited, setVisited] = useState<Set<Tab>>(() => new Set<Tab>(["graph"]));

  const selectTab = (id: Tab) => {
    setTab(id);
    setVisited((prev) => (prev.has(id) ? prev : new Set(prev).add(id)));
  };

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
              onClick={() => selectTab(t.id)}
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
        {/* Every tab visited stays mounted and is hidden with CSS rather than
            unmounted. Unmounting threw away whatever the user had built —
            an Explore session, a typed query and its results, an agent
            conversation — just for looking at another tab. Tabs are mounted
            lazily on first visit so an unopened one costs nothing. */}
        {TABS.filter((t) => visited.has(t.id)).map((t) => (
          <div
            key={t.id}
            className={tab === t.id ? "flex flex-1" : "hidden"}
            // Hidden panels are inert for assistive tech and tab order too,
            // not just invisible.
            aria-hidden={tab !== t.id}
          >
            {t.id === "graph" && <GraphView onData={setData} />}
            {t.id === "explore" && <ExploreView />}
            {t.id === "query" && <QueryView />}
            {t.id === "ontology" && <OntologyView />}
            {t.id === "agent" && <AgentPreview />}
          </div>
        ))}
      </div>
    </div>
  );
}
