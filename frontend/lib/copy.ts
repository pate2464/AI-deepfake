import type { AnalysisResponse } from "@/lib/api";

export const PRODUCT = {
  name: "Image Signal Review",
  tagline: "Authenticity & manipulation risk screening",
  eyebrow: "Trust & safety screening",
} as const;

export const ROLE_LABELS_DETAIL: Record<string, string> = {
  "core-score": "Primary factor",
  "supporting-score": "Supporting check",
  "other-layer": "Additional check",
};

export const ROLE_LABELS_SHORT: Record<string, string> = {
  "core-score": "Primary",
  "supporting-score": "Supporting",
  "other-layer": "Additional",
};

export const GROUP_SECTION = {
  core: {
    title: "Primary checks",
    subtitle: "Strongest influence on the overall result",
  },
  supporting: {
    title: "Supporting checks",
    subtitle: "Extra context and corroboration",
  },
  other: {
    title: "Additional checks",
    subtitle: "Specialized signals and file traces",
  },
} as const;

export function tierVerdictHeadline(tier: AnalysisResponse["risk_tier"]): string {
  switch (tier) {
    case "high":
      return "Elevated risk — review recommended";
    case "medium":
      return "Moderate concern — worth a closer look";
    default:
      return "Lower concern — looks broadly consistent";
  }
}

export function tierVerdictSubtext(tier: AnalysisResponse["risk_tier"]): string {
  switch (tier) {
    case "high":
      return "Several signals suggest editing, synthetic content, or inconsistencies. This is triage guidance—not proof.";
    case "medium":
      return "Some checks flagged uncertainty or mixed signals. Use this to prioritize review, not as a final judgment.";
    default:
      return "Most checks look calm relative to our thresholds. Unusual cases still happen—use context you trust.";
  }
}

export function tierLabelPlain(tier: AnalysisResponse["risk_tier"]): string {
  switch (tier) {
    case "high":
      return "Elevated";
    case "medium":
      return "Moderate";
    default:
      return "Lower";
  }
}
