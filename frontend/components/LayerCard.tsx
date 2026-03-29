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
    "core-score": "border-[rgba(10,65,116,0.22)] bg-[rgba(123,189,232,0.18)] text-[var(--text-primary)]",
    "supporting-score": "border-[rgba(73,118,159,0.22)] bg-[rgba(110,162,179,0.16)] text-[var(--text-primary)]",
    "other-layer": "border-[rgba(73,118,159,0.18)] bg-[rgba(189,216,233,0.22)] text-[var(--text-secondary)]",
  }[result.score_role ?? "supporting-score"];

  const percent = scoreToPercent(result.score);
  const tier =
    result.score >= 0.6 ? "high" : result.score >= 0.3 ? "medium" : "low";

  return (
    <div
      className={`
        rounded-xl overflow-hidden transition-all duration-300 text-[var(--text-primary)]
        ${result.error ? "border border-[rgba(10,65,116,0.24)] bg-[rgba(123,189,232,0.2)]" : "border panel-muted"}
        hover:border-[rgba(73,118,159,0.32)]
      `}
    >
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
                <span className="rounded-full border border-[rgba(10,65,116,0.2)] bg-[rgba(123,189,232,0.2)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-primary)]">
                  Guardrailed
                </span>
              )}
            </div>
            {result.suppression_reason ? (
              <p className="text-xs text-[var(--text-soft)] mt-0.5 line-clamp-2">
                {result.suppression_reason}
              </p>
            ) : result.flags.length > 0 && (
              <p className="text-xs text-[var(--text-soft)] mt-0.5 line-clamp-1">
                {result.flags[0]}
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="w-24 h-2 bg-[rgba(73,118,159,0.16)] rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-1000 ${
                tier === "high"
                  ? "bg-[#6EA2B3]"
                  : tier === "medium"
                    ? "bg-[#49769F]"
                    : "bg-[#4E8EA2]"
              }`}
              style={{ width: `${percent}%` }}
            />
          </div>
          <span className={`text-sm font-mono font-bold w-10 text-right ${riskColor(tier)}`}>
            {percent}
          </span>
          <span className="text-[var(--text-soft)] text-sm">{expanded ? "▲" : "▼"}</span>
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-[rgba(73,118,159,0.18)]">
          <div className="mt-3 grid grid-cols-2 md:grid-cols-6 gap-2">
            <div className="rounded-lg border border-[rgba(73,118,159,0.18)] bg-white/[0.34] p-2">
              <div className="text-[11px] uppercase tracking-wider text-[var(--text-muted-strong)]">Family</div>
              <div className="mt-1 text-sm capitalize text-[var(--text-primary)]">{result.evidence_family ?? "unknown"}</div>
            </div>
            <div className="rounded-lg border border-[rgba(73,118,159,0.18)] bg-white/[0.34] p-2">
              <div className="text-[11px] uppercase tracking-wider text-[var(--text-muted-strong)]">Role</div>
              <div className="mt-1 text-sm text-[var(--text-primary)]">{roleLabel}</div>
            </div>
            <div className="rounded-lg border border-[rgba(73,118,159,0.18)] bg-white/[0.34] p-2">
              <div className="text-[11px] uppercase tracking-wider text-[var(--text-muted-strong)]">Kind</div>
              <div className="mt-1 text-sm capitalize text-[var(--text-primary)]">{result.implementation_kind ?? "unknown"}</div>
            </div>
            <div className="rounded-lg border border-[rgba(73,118,159,0.18)] bg-white/[0.34] p-2">
              <div className="text-[11px] uppercase tracking-wider text-[var(--text-muted-strong)]">Weight</div>
              <div className="mt-1 text-sm text-[var(--text-primary)]">{formatPercent(result.configured_weight)}</div>
            </div>
            <div className="rounded-lg border border-[rgba(73,118,159,0.18)] bg-white/[0.34] p-2">
              <div className="text-[11px] uppercase tracking-wider text-[var(--text-muted-strong)]">Contribution</div>
              <div className="mt-1 text-sm text-[var(--text-primary)]">{formatPercent(result.weighted_contribution)}</div>
            </div>
            <div className="rounded-lg border border-[rgba(73,118,159,0.18)] bg-white/[0.34] p-2">
              <div className="text-[11px] uppercase tracking-wider text-[var(--text-muted-strong)]">Runtime</div>
              <div className="mt-1 text-sm text-[var(--text-primary)]">{result.duration_ms !== undefined ? `${result.duration_ms}ms` : "-"}</div>
            </div>
          </div>

          {result.suppression_reason && (
            <div className="mt-3 rounded-lg border border-[rgba(10,65,116,0.22)] bg-[rgba(123,189,232,0.18)] p-3 text-sm text-[var(--text-primary)]">
              {result.suppression_reason}
            </div>
          )}

          {result.flags.length > 0 && (
            <div className="mt-3">
              <h4 className="text-xs font-semibold text-[var(--text-muted-strong)] uppercase tracking-wider mb-2">
                Findings
              </h4>
              <ul className="space-y-1">
                {result.flags.map((flag, i) => (
                  <li key={i} className="text-sm flex items-start gap-2 text-[var(--text-primary)]">
                    <span className={tier === "high" ? "text-[#49769F]" : tier === "medium" ? "text-[#49769F]" : "text-[#4E8EA2]"}>
                      •
                    </span>
                    {flag}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {result.layer === "ela" && elaHeatmap && (
            <div className="mt-4">
              <h4 className="text-xs font-semibold text-[var(--text-muted-strong)] uppercase tracking-wider mb-2">
                ELA Heatmap
              </h4>
              <img
                src={`data:image/png;base64,${elaHeatmap}`}
                alt="ELA Heatmap"
                className="rounded-lg max-w-full border border-[rgba(73,118,159,0.18)]"
              />
              <p className="text-xs text-[var(--text-soft)] mt-1">
                Bright areas = high compression error. Uniform brightness across the image suggests AI generation.
              </p>
            </div>
          )}

          {result.layer === "trufor" && truforHeatmap && (
            <div className="mt-4">
              <h4 className="text-xs font-semibold text-[var(--text-muted-strong)] uppercase tracking-wider mb-2">
                Manipulation Localisation Map
              </h4>
              <img
                src={`data:image/png;base64,${truforHeatmap}`}
                alt="TruFor Manipulation Heatmap"
                className="rounded-lg max-w-full border border-[rgba(73,118,159,0.18)]"
              />
              <p className="text-xs text-[var(--text-soft)] mt-1">
                Red/warm areas = high probability of pixel-level manipulation. Blue = likely authentic.
              </p>
            </div>
          )}

          {result.layer === "gemini" && (geminiReasoning || result.details?.template_like_output) && (
            <div className="mt-4">
              <h4 className="text-xs font-semibold text-[var(--text-muted-strong)] uppercase tracking-wider mb-2">
                Gemini AI Reasoning
              </h4>
              <div className="deep-panel rounded-lg p-3 text-sm leading-relaxed">
                {geminiReasoning || "Local VLM did not return usable free-text reasoning for this image. The output looked like a copied template, so it was suppressed."}
              </div>
            </div>
          )}

          <div className="mt-3 flex items-center gap-2 text-xs text-[var(--text-soft)]">
            <span>Confidence:</span>
            <div className="w-16 h-1.5 bg-[rgba(73,118,159,0.16)] rounded-full overflow-hidden">
              <div
                className="h-full bg-[#6EA2B3] rounded-full"
                style={{ width: `${scoreToPercent(result.confidence)}%` }}
              />
            </div>
            <span>{scoreToPercent(result.confidence)}%</span>
          </div>

          {result.error && (
            <div className="mt-3 text-xs text-[var(--text-primary)] bg-[rgba(123,189,232,0.24)] rounded p-2">
              Error: {result.error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
