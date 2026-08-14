export const LABEL_COLORS: Record<string, string> = {
  KineticChain: "#f97316",
  Material: "#22c55e",
  Filename: "#a1a1aa",
  Pretreatment: "#eab308",
  ChemConcept: "#8b5cf6",
  ExpConditions: "#0ea5e9",
  AdsParams: "#ec4899",
  KineticModel: "#ef4444",
};
export const FALLBACK_COLOR = "#71717a";

export function colorForLabels(labels: string[]): string {
  return LABEL_COLORS[labels[0]] ?? FALLBACK_COLOR;
}
