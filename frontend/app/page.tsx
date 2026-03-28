"use client";

import { useState, useCallback } from "react";
import ImageUpload from "@/components/ImageUpload";
import RiskGauge from "@/components/RiskGauge";
import LayerCard from "@/components/LayerCard";
import { analyzeImage, type AnalysisResponse } from "@/lib/api";
import { riskBg, riskColor, scoreToPercent } from "@/lib/utils";

export default function Home() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Optional context fields
  const [showContext, setShowContext] = useState(false);
  const [accountId, setAccountId] = useState("");
  const [deviceFp, setDeviceFp] = useState("");
  const [orderValue, setOrderValue] = useState("");
  const formatFamily = (family: string) =>
    family
      .replace(/_/g, " ")
      .replace(/^./, (value) => value.toUpperCase());

  const handleFileSelect = useCallback(
    async (file: File) => {
      setIsAnalyzing(true);
      setError(null);
      setResult(null);

      try {
        const response = await analyzeImage(file, {
          account_id: accountId || undefined,
          device_fingerprint: deviceFp || undefined,
          order_value: orderValue ? parseFloat(orderValue) : undefined,
        });
        setResult(response);
      } catch (err: any) {
        setError(err.message || "Analysis failed");
      } finally {
        setIsAnalyzing(false);
      }
    },
    [accountId, deviceFp, orderValue]
  );

  // Sort layers by actual scoring impact first, then raw score.
  const sortedLayers = result
    ? [...result.layer_results].sort(
        (a, b) =>
          (b.weighted_contribution ?? b.score) -
            (a.weighted_contribution ?? a.score) ||
          b.score - a.score
      )
    : [];
  const groupedLayers = {
    core: sortedLayers.filter((layer) => layer.score_role === "core-score"),
    supporting: sortedLayers.filter((layer) => layer.score_role === "supporting-score"),
    other: sortedLayers.filter((layer) => layer.score_role === "other-layer"),
  };
  const layerSections = [
    { key: "core", title: "Core Scoring Backbone", layers: groupedLayers.core },
    { key: "supporting", title: "Supporting Score Layers", layers: groupedLayers.supporting },
    { key: "other", title: "Other Layers", layers: groupedLayers.other },
  ];

  return (
    <main className="max-w-5xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold tracking-tight">
          🛡️ AI Fraud Detector
        </h1>
        <p className="text-[#a0a0a0] mt-2">
          Core scoring backbone plus grouped 21-layer evidence for
          AI-generated fraudulent images
        </p>
      </div>

      {/* Upload Section */}
      <div className="mb-6">
        <ImageUpload onFileSelect={handleFileSelect} isAnalyzing={isAnalyzing} />
      </div>

      {/* Optional Context */}
      <div className="mb-6">
        <button
          onClick={() => setShowContext(!showContext)}
          className="text-sm text-[#a0a0a0] hover:text-white transition-colors"
        >
          {showContext ? "▲" : "▶"} Optional: Add claim context (account,
          device, order)
        </button>
        {showContext && (
          <div className="mt-3 grid grid-cols-3 gap-3">
            <input
              type="text"
              placeholder="Account ID"
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
              className="bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg px-3 py-2 text-sm focus:border-blue-500 outline-none"
            />
            <input
              type="text"
              placeholder="Device Fingerprint"
              value={deviceFp}
              onChange={(e) => setDeviceFp(e.target.value)}
              className="bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg px-3 py-2 text-sm focus:border-blue-500 outline-none"
            />
            <input
              type="number"
              placeholder="Order Value ($)"
              value={orderValue}
              onChange={(e) => setOrderValue(e.target.value)}
              className="bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg px-3 py-2 text-sm focus:border-blue-500 outline-none"
            />
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="mb-6 bg-red-950/30 border border-red-900/50 rounded-xl p-4 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-6 animate-in fade-in duration-500">
          {/* Summary Bar */}
          <div
            className={`flex items-center justify-between rounded-2xl border p-6 ${riskBg(result.risk_tier)}`}
          >
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-3">
                <h2 className="text-xl font-bold">{result.filename}</h2>
                <span
                  className={`text-xs font-bold px-2 py-1 rounded-full uppercase tracking-wider ${
                    result.risk_tier === "high"
                      ? "bg-red-500/20 text-red-400"
                      : result.risk_tier === "medium"
                        ? "bg-amber-500/20 text-amber-400"
                        : "bg-green-500/20 text-green-400"
                  }`}
                >
                  {result.risk_tier} risk
                </span>
              </div>
              <div className="flex gap-6 text-sm text-[#a0a0a0]">
                <span>
                  ⏱️ {result.processing_time_ms}ms
                </span>
                <span>
                  📊 {result.layer_results.length} layers analyzed
                </span>
                <span>
                  🔗 {result.hash_matches.length} hash matches
                </span>
              </div>
            </div>
            <RiskGauge score={result.risk_score} tier={result.risk_tier} />
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-4">
              <div className="text-xs font-semibold uppercase tracking-wider text-[#777]">
                Score Path
              </div>
              <p className="mt-2 text-sm text-[#d6d6d6] leading-relaxed">
                {result.scoring_summary.override_applied
                  ? result.scoring_summary.override_reason
                  : result.scoring_summary.consensus_floor_applied
                    ? `Cross-family consensus (${result.scoring_summary.consensus_signal_families.map(formatFamily).join(" + ")}) raised the backbone score from ${scoreToPercent(result.scoring_summary.weighted_score)} to ${scoreToPercent(result.scoring_summary.final_score)}.`
                    : `Backbone ensemble score: ${scoreToPercent(result.scoring_summary.weighted_score)}.`}
              </p>
            </div>

            <div className="rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-4">
              <div className="text-xs font-semibold uppercase tracking-wider text-[#777]">
                Scoring Metadata
              </div>
              <div className="mt-2 space-y-2 text-sm text-[#d6d6d6]">
                <div>
                  <span className="text-[#888]">Method:</span>{" "}
                  {result.scoring_summary.method}
                </div>
                <div>
                  <span className="text-[#888]">Backbone layers:</span>{" "}
                  {groupedLayers.core.length + groupedLayers.supporting.length}
                </div>
                <div>
                  <span className="text-[#888]">Other layers:</span>{" "}
                  {groupedLayers.other.length}
                </div>
                <div>
                  <span className="text-[#888]">Version:</span>{" "}
                  {result.scoring_summary.scoring_version}
                </div>
              </div>
              {result.scoring_summary.scoring_notes.length > 0 && (
                <ul className="mt-3 space-y-2 text-sm text-amber-100">
                  {result.scoring_summary.scoring_notes.map((note, index) => (
                    <li key={index} className="flex items-start gap-2">
                      <span className="text-amber-400">•</span>
                      <span>{note}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-4">
              <div className="text-xs font-semibold uppercase tracking-wider text-[#777]">
                Conflicting Signals
              </div>
              {result.scoring_summary.conflicting_signals.length > 0 ? (
                <ul className="mt-2 space-y-2 text-sm text-[#d6d6d6]">
                  {result.scoring_summary.conflicting_signals.map((signal, index) => (
                    <li key={index} className="flex items-start gap-2">
                      <span className="text-amber-400">•</span>
                      <span>{signal}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-[#a0a0a0]">
                  No strong contradictions surfaced for this run.
                </p>
              )}
            </div>
          </div>

          {/* Hash Matches Warning */}
          {result.hash_matches.length > 0 && (
            <div className="bg-red-950/30 border border-red-900/50 rounded-xl p-4">
              <h3 className="text-red-400 font-bold text-sm mb-2">
                ⚠️ Duplicate Images Detected
              </h3>
              <ul className="space-y-1">
                {result.hash_matches.map((m, i) => (
                  <li key={i} className="text-sm text-red-300">
                    Matched claim #{m.matched_claim_id} — {m.hash_type} hamming
                    distance: {m.hamming_distance}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Layer Results */}
          <div>
            <h3 className="text-lg font-semibold mb-3">
              Layer-by-Layer Breakdown
            </h3>
            <div className="space-y-4">
              {layerSections.map((section) =>
                section.layers.length > 0 ? (
                  <section key={section.key} className="space-y-2">
                    <div className="flex items-center justify-between">
                      <h4 className="text-sm font-semibold uppercase tracking-wider text-[#9a9a9a]">
                        {section.title}
                      </h4>
                      <span className="text-xs text-[#666]">
                        {section.layers.length} layers
                      </span>
                    </div>
                    {section.layers.map((lr) => (
                      <LayerCard
                        key={lr.layer}
                        result={lr}
                        elaHeatmap={
                          lr.layer === "ela" ? result.ela_heatmap_b64 ?? undefined : undefined
                        }
                        truforHeatmap={
                          lr.layer === "trufor" ? result.trufor_heatmap_b64 ?? undefined : undefined
                        }
                        geminiReasoning={
                          lr.layer === "gemini"
                            ? result.gemini_reasoning ?? undefined
                            : undefined
                        }
                      />
                    ))}
                  </section>
                ) : null
              )}
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="mt-12 text-center text-xs text-[#666] pb-8">
        <p>HackyIndy 2026 — AI Fraud Detection Pipeline</p>
        <p className="mt-1">
          Grouped evidence model: core scoring backbone, supporting score layers, and other forensic checks across 21 layers.
        </p>
      </footer>
    </main>
  );
}
