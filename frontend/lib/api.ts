const API_BASE = "/api/v1";

export interface LayerResult {
  layer: string;
  score: number;
  confidence: number;
  flags: string[];
  details: Record<string, any>;
  error?: string;
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
  layer_results: LayerResult[];
  hash_matches: HashMatch[];
  ela_heatmap_b64?: string;
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
