"use client";

import type { GraphData } from "./GraphView";
import { LABEL_COLORS, FALLBACK_COLOR } from "@/lib/labelColors";

export default function StatsBar({ data }: { data: GraphData | null }) {
  if (!data) return null;

  const counts = new Map<string, number>();
  for (const n of data.nodes) {
    const label = n.labels[0] ?? "(unlabeled)";
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  const labels = Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-zinc-800 bg-zinc-950/80 px-4 py-2 text-xs text-zinc-400">
      <span>
        <span className="font-semibold text-zinc-200">{data.nodes.length.toLocaleString()}</span> nodes
      </span>
      <span>
        <span className="font-semibold text-zinc-200">{data.links.length.toLocaleString()}</span> relationships
      </span>
      <span className="hidden h-4 w-px bg-zinc-800 sm:block" />
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        {labels.map(([label, count]) => (
          <span key={label} className="flex items-center gap-1.5">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: LABEL_COLORS[label] ?? FALLBACK_COLOR }}
            />
            {label} ({count})
          </span>
        ))}
      </div>
    </div>
  );
}
