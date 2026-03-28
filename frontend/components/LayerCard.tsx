"use client";

import { useState } from "react";
import type { LayerResult } from "@/lib/api";
import { layerIcon, layerLabel, riskColor, scoreToPercent } from "@/lib/utils";

interface LayerCardProps {
  result: LayerResult;
  elaHeatmap?: string;
  truforHeatmap?: string;
  geminiReasoning?: string;
}

export default function LayerCard({
  result,
  elaHeatmap,
  truforHeatmap,
  geminiReasoning,
}: LayerCardProps) {
  const [expanded, setExpanded] = useState(false);
  const formatPercent = (value?: number) =>
    value === undefined ? "-" : `${(value * 100).toFixed(1)}%`;
  const roleLabel = {
    "core-score": "Core",
    "supporting-score": "Supporting",
    "other-layer": "Other",
  }[result.score_role ?? "supporting-score"];
  const roleBadgeClass = {
    "core-score": "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
    "supporting-score": "border-sky-500/30 bg-sky-500/10 text-sky-300",
    "other-layer": "border-zinc-500/30 bg-zinc-500/10 text-zinc-300",
  }[result.score_role ?? "supporting-score"];

  const percent = scoreToPercent(result.score);
  const tier =
    result.score >= 0.6 ? "high" : result.score >= 0.3 ? "medium" : "low";

  return (
    <div
      className={`
        border rounded-xl overflow-hidden transition-all duration-300
        ${result.error ? "border-red-900/50 bg-red-950/20" : "border-[#2a2a2a] bg-[#1a1a1a]"}
        hover:border-[#444]
      `}
    >
      {/* Header — always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-4 text-left"
      >
        <div className="flex items-center gap-3">
          <span className="text-2xl">{layerIcon(result.layer)}</span>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-sm">{layerLabel(result.layer)}</h3>
              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${roleBadgeClass}`}>
                {roleLabel}
              </span>
              {result.suppressed && (
                <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-300">
                  Guardrailed
                </span>
              )}
            </div>
            {result.suppression_reason ? (
              <p className="text-xs text-amber-300/90 mt-0.5 line-clamp-2">
                {result.suppression_reason}
              </p>
            ) : result.flags.length > 0 && (
              <p className="text-xs text-[#a0a0a0] mt-0.5 line-clamp-1">
                {result.flags[0]}
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Score bar */}
          <div className="w-24 h-2 bg-[#2a2a2a] rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-1000 ${
                tier === "high"
                  ? "bg-red-500"
                  : tier === "medium"
                    ? "bg-amber-500"
                    : "bg-green-500"
              }`}
              style={{ width: `${percent}%` }}
            />
          </div>
          <span className={`text-sm font-mono font-bold w-10 text-right ${riskColor(tier)}`}>
            {percent}
          </span>
          <span className="text-[#a0a0a0] text-sm">{expanded ? "▲" : "▼"}</span>
        </div>
      </button>

      {/* Expanded details */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-[#2a2a2a]">
          <div className="mt-3 grid grid-cols-2 md:grid-cols-6 gap-2">
            <div className="rounded-lg border border-[#2a2a2a] bg-[#111] p-2">
              <div className="text-[11px] uppercase tracking-wider text-[#777]">Family</div>
              <div className="mt-1 text-sm capitalize">{result.evidence_family ?? "unknown"}</div>
            </div>
            <div className="rounded-lg border border-[#2a2a2a] bg-[#111] p-2">
              <div className="text-[11px] uppercase tracking-wider text-[#777]">Role</div>
              <div className="mt-1 text-sm">{roleLabel}</div>
            </div>
            <div className="rounded-lg border border-[#2a2a2a] bg-[#111] p-2">
              <div className="text-[11px] uppercase tracking-wider text-[#777]">Kind</div>
              <div className="mt-1 text-sm capitalize">{result.implementation_kind ?? "unknown"}</div>
            </div>
            <div className="rounded-lg border border-[#2a2a2a] bg-[#111] p-2">
              <div className="text-[11px] uppercase tracking-wider text-[#777]">Weight</div>
              <div className="mt-1 text-sm">{formatPercent(result.configured_weight)}</div>
            </div>
            <div className="rounded-lg border border-[#2a2a2a] bg-[#111] p-2">
              <div className="text-[11px] uppercase tracking-wider text-[#777]">Contribution</div>
              <div className="mt-1 text-sm">{formatPercent(result.weighted_contribution)}</div>
            </div>
            <div className="rounded-lg border border-[#2a2a2a] bg-[#111] p-2">
              <div className="text-[11px] uppercase tracking-wider text-[#777]">Runtime</div>
              <div className="mt-1 text-sm">{result.duration_ms !== undefined ? `${result.duration_ms}ms` : "-"}</div>
            </div>
          </div>

          {result.suppression_reason && (
            <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
              {result.suppression_reason}
            </div>
          )}

          {/* Flags */}
          {result.flags.length > 0 && (
            <div className="mt-3">
              <h4 className="text-xs font-semibold text-[#a0a0a0] uppercase tracking-wider mb-2">
                Findings
              </h4>
              <ul className="space-y-1">
                {result.flags.map((flag, i) => (
                  <li key={i} className="text-sm flex items-start gap-2">
                    <span className={tier === "high" ? "text-red-400" : tier === "medium" ? "text-amber-400" : "text-green-400"}>
                      •
                    </span>
                    {flag}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* ELA Heatmap */}
          {result.layer === "ela" && elaHeatmap && (
            <div className="mt-4">
              <h4 className="text-xs font-semibold text-[#a0a0a0] uppercase tracking-wider mb-2">
                ELA Heatmap
              </h4>
              <img
                src={`data:image/png;base64,${elaHeatmap}`}
                alt="ELA Heatmap"
                className="rounded-lg max-w-full border border-[#2a2a2a]"
              />
              <p className="text-xs text-[#a0a0a0] mt-1">
                Bright areas = high compression error. Uniform brightness across the image suggests AI generation.
              </p>
            </div>
          )}

          {/* TruFor Manipulation Heatmap */}
          {result.layer === "trufor" && truforHeatmap && (
            <div className="mt-4">
              <h4 className="text-xs font-semibold text-[#a0a0a0] uppercase tracking-wider mb-2">
                Manipulation Localisation Map
              </h4>
              <img
                src={`data:image/png;base64,${truforHeatmap}`}
                alt="TruFor Manipulation Heatmap"
                className="rounded-lg max-w-full border border-[#2a2a2a]"
              />
              <p className="text-xs text-[#a0a0a0] mt-1">
                Red/warm areas = high probability of pixel-level manipulation. Blue = likely authentic.
              </p>
            </div>
          )}

          {/* Gemini Reasoning */}
          {result.layer === "gemini" && (geminiReasoning || result.details?.template_like_output) && (
            <div className="mt-4">
              <h4 className="text-xs font-semibold text-[#a0a0a0] uppercase tracking-wider mb-2">
                Gemini AI Reasoning
              </h4>
              <div className="bg-[#111] rounded-lg p-3 text-sm leading-relaxed border border-[#2a2a2a]">
                {geminiReasoning || "Local VLM did not return usable free-text reasoning for this image. The output looked like a copied template, so it was suppressed."}
              </div>
            </div>
          )}

          {/* Confidence */}
          <div className="mt-3 flex items-center gap-2 text-xs text-[#a0a0a0]">
            <span>Confidence:</span>
            <div className="w-16 h-1.5 bg-[#2a2a2a] rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 rounded-full"
                style={{ width: `${scoreToPercent(result.confidence)}%` }}
              />
            </div>
            <span>{scoreToPercent(result.confidence)}%</span>
          </div>

          {/* Error */}
          {result.error && (
            <div className="mt-3 text-xs text-red-400 bg-red-950/30 rounded p-2">
              Error: {result.error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
