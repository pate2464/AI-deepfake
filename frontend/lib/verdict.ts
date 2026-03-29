import type { AnalysisResponse, LayerResult } from "@/lib/api";
import { layerLabel } from "@/lib/utils";

function clampReasons(items: string[], max = 5): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of items) {
    const trimmed = item.trim();
    if (!trimmed || seen.has(trimmed)) continue;
    seen.add(trimmed);
    out.push(trimmed);
    if (out.length >= max) break;
  }
  return out;
}

function topLayersByContribution(layers: LayerResult[], n: number): LayerResult[] {
  return [...layers]
    .filter((l) => !l.suppressed)
    .sort(
      (a, b) =>
        Math.abs(b.weighted_contribution ?? b.score) -
        Math.abs(a.weighted_contribution ?? a.score)
    )
    .slice(0, n);
}

/**
 * Plain-language bullets for the main results view (non-technical).
 */
export function buildTopReasons(result: AnalysisResponse): string[] {
  const s = result.scoring_summary;
  const reasons: string[] = [];

  if (s.override_applied && s.override_reason) {
    reasons.push(s.override_reason);
  }

  for (const note of s.scoring_notes) {
    reasons.push(note);
  }

  for (const signal of s.conflicting_signals) {
    reasons.push(`Mixed signals: ${signal}`);
  }

  if (s.consensus_floor_applied && s.consensus_signal_families.length > 0) {
    const families = s.consensus_signal_families.join(", ");
    reasons.push(`Multiple signal families aligned (${families}), which increased the overall score.`);
  }

  const top = topLayersByContribution(result.layer_results, 2);
  for (const layer of top) {
    if (layer.score >= 0.45) {
      const name = layerLabel(layer.layer);
      reasons.push(
        `Notable signal from “${name}” (about ${Math.round(layer.score * 100)} on this check).`
      );
    }
  }

  if (result.hash_matches.length > 0) {
    reasons.push(
      `Possible duplicate matches (${result.hash_matches.length})—this image may have appeared before in connected records.`
    );
  }

  if (reasons.length === 0) {
    reasons.push("No strong caveats were recorded for this run—overall risk is driven mainly by the blended score.");
  }

  return clampReasons(reasons, 5);
}

export type ConfidenceBand = "high" | "medium" | "low";

export function aggregateConfidenceBand(result: AnalysisResponse): {
  band: ConfidenceBand;
  label: string;
  detail: string;
} {
  const layers = result.layer_results.filter((l) => !l.suppressed);
  if (layers.length === 0) {
    return {
      band: "medium",
      label: "Medium",
      detail: "Not enough per-check data to refine confidence.",
    };
  }

  const sum = layers.reduce((acc, l) => acc + l.confidence, 0);
  const avg = sum / layers.length;

  if (avg >= 0.72) {
    return {
      band: "high",
      label: "Higher",
      detail: "Checks mostly agreed on how confident to be about their own signals.",
    };
  }
  if (avg >= 0.42) {
    return {
      band: "medium",
      label: "Medium",
      detail: "Some checks were uncertain or disagreed—treat the summary as directional.",
    };
  }
  return {
    band: "low",
    label: "Lower",
    detail: "Several checks had low confidence—favor human review and extra context.",
  };
}
