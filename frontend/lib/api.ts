const API_BASE = "/api/v1";

export interface LayerResult {
  layer: string;
  score: number;
  confidence: number;
  flags: string[];
  details: Record<string, any>;
  error?: string;
  evidence_family?: string;
  implementation_kind?: string;
  configured_weight?: number;
  effective_weight?: number;
  weighted_contribution?: number;
  duration_ms?: number;
  score_role?: string;
  suppressed?: boolean;
  suppression_reason?: string;
}

export interface ScoringSummary {
  scoring_version: string;
  method: string;
  weighted_score: number;
  final_score: number;
  risk_tier: "low" | "medium" | "high";
  override_applied: boolean;
  override_reason?: string;
  consensus_floor_applied: boolean;
  consensus_floor_score?: number;
  contributing_layers: string[];
  consensus_signal_families: string[];
  conflicting_signals: string[];
  scoring_notes: string[];
}

export interface HashMatch {
  matched_claim_id: number;
  hamming_distance: number;
  hash_type: string;
}

export interface AnalysisResponse {
  id: number;
  filename: string;
  risk_score: number;
  risk_tier: "low" | "medium" | "high";
  scoring_summary: ScoringSummary;
  layer_results: LayerResult[];
  hash_matches: HashMatch[];
  ela_heatmap_b64?: string;
  trufor_heatmap_b64?: string;
  gemini_reasoning?: string;
  processing_time_ms: number;
  created_at: string;
}

export interface HistoryItem {
  id: number;
  filename: string;
  risk_score: number;
  risk_tier: "low" | "medium" | "high";
  created_at: string;
}

export interface Stats {
  total_scans: number;
  flagged_count: number;
  avg_risk_score: number;
  layer_trigger_counts: Record<string, number>;
}

export async function analyzeImage(
  file: File,
  context?: {
    account_id?: string;
    device_fingerprint?: string;
    delivery_lat?: number;
    delivery_lon?: number;
    order_value?: number;
    claim_description?: string;
  }
): Promise<AnalysisResponse> {
  const formData = new FormData();
  formData.append("file", file);

  if (context) {
    Object.entries(context).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        formData.append(key, String(value));
      }
    });
  }

  const res = await fetch(`${API_BASE}/analyze`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Analysis failed");
  }

  return res.json();
}

export async function getHistory(
  limit = 50,
  offset = 0
): Promise<HistoryItem[]> {
  const res = await fetch(
    `${API_BASE}/history?limit=${limit}&offset=${offset}`
  );
  if (!res.ok) throw new Error("Failed to fetch history");
  return res.json();
}

export async function getStats(): Promise<Stats> {
  const res = await fetch(`${API_BASE}/stats`);
  if (!res.ok) throw new Error("Failed to fetch stats");
  return res.json();
}
