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
            <h3 className="font-semibold text-sm">{layerLabel(result.layer)}</h3>
            {result.flags.length > 0 && (
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
          {result.layer === "gemini" && geminiReasoning && (
            <div className="mt-4">
              <h4 className="text-xs font-semibold text-[#a0a0a0] uppercase tracking-wider mb-2">
                Gemini AI Reasoning
              </h4>
              <div className="bg-[#111] rounded-lg p-3 text-sm leading-relaxed border border-[#2a2a2a]">
                {geminiReasoning}
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
