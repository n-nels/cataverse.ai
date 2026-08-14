"use client";

import { useState, useRef, useEffect } from "react";

type Message = {
  role: "user" | "agent";
  text: string;
  cypher?: string;
};

const EXAMPLES = [
  "Which pretreatments used RoughPump gas?",
  "Show me experiments on Pd/CeO2",
  "What's the average pressure across ExpConditions?",
  "Summarize the KineticModel results",
];

const SCRIPTED: Record<string, { text: string; cypher: string }> = {
  "Which pretreatments used RoughPump gas?": {
    text: "Found 1 pretreatment step using RoughPump gas: pre_20241215_104930_pd_ceo2_000-007_1 (402.9 K, rate 20).",
    cypher: "MATCH (p:Pretreatment)\nWHERE 'RoughPump' IN p.gas\nRETURN p",
  },
  "Show me experiments on Pd/CeO2": {
    text: "Found 6 KineticChain records with material_key referencing pd / ceo2.",
    cypher: "MATCH (k:KineticChain)\nWHERE k.material_key CONTAINS 'ceo2'\nRETURN k",
  },
  "What's the average pressure across ExpConditions?": {
    text: "Across 238 ExpConditions nodes, mean pressure is ~0.024 bar.",
    cypher: "MATCH (e:ExpConditions)\nRETURN avg(e.pressure) AS avgPressure",
  },
  "Summarize the KineticModel results": {
    text: "1 KineticModel node found, referencing fitted rate constants for the pretreatment sequence.",
    cypher: "MATCH (m:KineticModel)\nRETURN m",
  },
};

const FALLBACK = {
  text: "This is a preview of the agent interface — natural language in, Cypher out, results back. Full reasoning connects once the agent is wired up.",
  cypher: "MATCH (n)\nWHERE ...\nRETURN n\nLIMIT 25",
};

export default function AgentPreview() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  const ask = (question: string) => {
    if (!question.trim() || thinking) return;
    setMessages((m) => [...m, { role: "user", text: question }]);
    setInput("");
    setThinking(true);
    const reply = SCRIPTED[question] ?? FALLBACK;
    setTimeout(() => {
      setThinking(false);
      setMessages((m) => [...m, { role: "agent", text: reply.text, cypher: reply.cypher }]);
    }, 900);
  };

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col px-4 py-6">
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-lg font-semibold text-zinc-100">Ask the Agent</h2>
        <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-400">
          Preview — not yet connected
        </span>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto rounded-lg border border-zinc-800 bg-zinc-950/60 p-4">
        {messages.length === 0 && (
          <div className="space-y-3">
            <p className="text-sm text-zinc-400">
              Natural-language questions over the graph, powered by Claude. Try an example:
            </p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  onClick={() => ask(ex)}
                  className="rounded-full border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 transition-colors hover:border-zinc-500 hover:text-white"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div
              className={
                m.role === "user"
                  ? "max-w-[80%] rounded-2xl rounded-br-sm bg-orange-500/90 px-4 py-2 text-sm text-white"
                  : "max-w-[85%] space-y-2 rounded-2xl rounded-bl-sm bg-zinc-800 px-4 py-3 text-sm text-zinc-100"
              }
            >
              <p>{m.text}</p>
              {m.cypher && (
                <pre className="overflow-x-auto rounded-md bg-black/40 p-2 font-mono text-xs text-emerald-300">
                  {m.cypher}
                </pre>
              )}
            </div>
          </div>
        ))}

        {thinking && (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-sm bg-zinc-800 px-4 py-2 text-sm text-zinc-400">
              thinking…
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
        className="mt-3 flex gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about your catalyst experiments…"
          className="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={thinking}
          className="rounded-lg bg-orange-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-orange-400 disabled:opacity-50"
        >
          Send
        </button>
      </form>
      <p className="mt-2 text-center text-xs text-zinc-600">
        Simulated response for demo purposes — no live model call.
      </p>
    </div>
  );
}
