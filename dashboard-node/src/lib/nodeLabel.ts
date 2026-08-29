/**
 * Picking the text to draw on a node.
 *
 * Colour tells you a node's *type*; this tells you *which* node. Without it a
 * seed of 12 ChemConcepts is twelve identical dots and the only way to identify
 * one is to click it.
 *
 * Each label gets an ordered list of properties to try, most human-meaningful
 * first, with a generic fallback for labels not listed (including any added to
 * the graph later).
 */

const PREFERRED_PROPERTIES: Record<string, string[]> = {
  ChemConcept: ["name"],
  ChemSpecies: ["formula"],
  PyFunction: ["name"],
  KineticModel: ["name"],
  ModelParameter: ["name"],
  Material: ["id"],
  Filename: ["base_name"],
  KineticChain: ["chain_id"],
  // These carry no human-friendly name — a step number or peak reads better
  // than a long generated id.
  Pretreatment: ["step_index"],
  AdsParams: ["peak_name"],
  ExpConditions: ["temp"],
};

const FALLBACK_PROPERTIES = ["name", "id", "base_name", "title"];

const MAX_LENGTH = 22;

export function nodeDisplayLabel(
  labels: string[],
  properties: Record<string, unknown>
): string {
  const primary = labels[0];
  const candidates = [
    ...(PREFERRED_PROPERTIES[primary] ?? []),
    ...FALLBACK_PROPERTIES,
  ];

  for (const key of candidates) {
    const value = properties[key];
    if (value === null || value === undefined || value === "") continue;
    if (typeof value === "object") continue;

    let text = String(value);
    // Ids are often prefixed with their own type and datetime
    // ("pre_20241126_112801_pd_ceo2_000-003_3"); the tail distinguishes them
    // far better than the head, which is identical across siblings.
    if (text.length > MAX_LENGTH) text = "…" + text.slice(-(MAX_LENGTH - 1));

    // A bare number means nothing on its own — say what it is.
    if (primary === "Pretreatment" && key === "step_index") return `step ${text}`;
    if (primary === "ExpConditions" && key === "temp") {
      // Recorded to four decimals ("44.9008"); that precision is noise in a
      // label and is still visible in the detail panel.
      const numeric = Number(value);
      return Number.isFinite(numeric)
        ? `${Math.round(numeric * 10) / 10} K`
        : `${text} K`;
    }
    // Reference vs. sample is the distinction people compare experiments on,
    // and two base_names side by side do not reveal which is which.
    if (primary === "Filename" && properties.is_reference === true) {
      return `${text} (ref)`;
    }
    return text;
  }

  return primary ?? "node";
}
