/**
 * One distinct colour per node label.
 *
 * Spread around the hue wheel rather than picked ad hoc: several labels
 * previously fell through to the grey fallback (ChemSpecies, ModelParameter,
 * PyFunction) or were grey by choice (Filename), which made them
 * indistinguishable from each other on the canvas.
 *
 * Grey is reserved for labels this map does not know about, so a label added to
 * the graph later shows up as obviously unstyled rather than silently colliding
 * with an existing one.
 */
export const LABEL_COLORS: Record<string, string> = {
  KineticModel: "#ef4444", // red
  KineticChain: "#f97316", // orange
  Pretreatment: "#eab308", // amber
  PyFunction: "#84cc16", // lime
  Material: "#22c55e", // green
  ChemSpecies: "#14b8a6", // teal
  ModelParameter: "#06b6d4", // cyan
  ExpConditions: "#0ea5e9", // sky
  Filename: "#6366f1", // indigo
  ChemConcept: "#a855f7", // purple
  AdsParams: "#ec4899", // pink
};

export const FALLBACK_COLOR = "#71717a";

export function colorForLabels(labels: string[]): string {
  return LABEL_COLORS[labels[0]] ?? FALLBACK_COLOR;
}
