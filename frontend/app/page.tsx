"use client";

import { useState, useCallback } from "react";
import ImageUpload from "@/components/ImageUpload";
import RiskGauge from "@/components/RiskGauge";
import LayerCard from "@/components/LayerCard";
import { analyzeImage, type AnalysisResponse } from "@/lib/api";
import { riskBg, riskColor } from "@/lib/utils";

export default function Home() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Optional context fields
  const [showContext, setShowContext] = useState(false);
  const [accountId, setAccountId] = useState("");
  const [deviceFp, setDeviceFp] = useState("");
  const [orderValue, setOrderValue] = useState("");

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

  // Sort layers by score descending for impact
  const sortedLayers = result
    ? [...result.layer_results].sort((a, b) => b.score - a.score)
    : [];

  return (
    <main className="max-w-5xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold tracking-tight">
          🛡️ AI Fraud Detector
        </h1>
        <p className="text-[#a0a0a0] mt-2">
          21-layer deep analysis pipeline for detecting AI-generated fraudulent
          images
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
            <div className="space-y-2">
              {sortedLayers.map((lr) => (
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
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="mt-12 text-center text-xs text-[#666] pb-8">
        <p>HackyIndy 2026 — AI Fraud Detection Pipeline</p>
        <p className="mt-1">
          19 layers: EXIF · ELA · Hashing · FFT · C2PA · Behavioral · Vision AI ·
          PRNU · CLIP · CNN · Watermark · TruFor · DIRE · Gradient · LSB · DCT · GAN · Attention · Texture
        </p>
      </footer>
    </main>
  );
}
