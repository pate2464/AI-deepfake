"use client";

import { AlertTriangle, Clock3, Scale, ShieldAlert, Sigma, TimerReset } from "lucide-react";
import type { LayerResult } from "@/lib/api";
import { cn, layerIcon, layerLabel, riskColor, scoreToPercent } from "@/lib/utils";

interface LayerDetailPanelProps {
  result: LayerResult | null;
  elaHeatmap?: string;
  truforHeatmap?: string;
  geminiReasoning?: string;
}

function formatPercent(value?: number) {
  return value === undefined ? "-" : `${(value * 100).toFixed(1)}%`;
}

function formatDetailValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  if (typeof value === "number") {
    return Number.isInteger(value) ? `${value}` : value.toFixed(Math.abs(value) >= 1 ? 2 : 4);
  }

  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }

  if (Array.isArray(value)) {
    const serialized = value.map((item) => formatDetailValue(item)).join(", ");
    return serialized.length > 120 ? `${serialized.slice(0, 117)}...` : serialized;
  }

  if (typeof value === "object") {
    const serialized = JSON.stringify(value);
    return serialized.length > 120 ? `${serialized.slice(0, 117)}...` : serialized;
  }

  return `${value}`;
}

const ROLE_LABELS: Record<string, string> = {
  "core-score": "Primary factor",
  "supporting-score": "Supporting check",
  "other-layer": "Additional check",
};

const ROLE_BADGES: Record<string, string> = {
  "core-score": "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  "supporting-score": "border-sky-500/30 bg-sky-500/10 text-sky-300",
  "other-layer": "border-zinc-500/30 bg-zinc-500/10 text-zinc-300",
};

export default function LayerDetailPanel({
  result,
  elaHeatmap,
  truforHeatmap,
  geminiReasoning,
}: LayerDetailPanelProps) {
  if (!result) {
    return (
      <div className="flex min-h-[320px] items-center justify-center rounded-[28px] panel-muted px-6 py-8 text-center xl:min-h-0">
        <div className="max-w-sm">
          <div className="text-xs font-medium text-[var(--text-muted-strong)]">Check details</div>
          <h3 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-white">
            Pick a check on the left
          </h3>
          <p className="mt-3 text-sm leading-6 text-[#9d9d9d]">
            We show one check at a time so scores, notes, and visuals stay easy to read.
          </p>
        </div>
      </div>
    );
  }

  const tier =
    result.score >= 0.6 ? "high" : result.score >= 0.3 ? "medium" : "low";
  const detailEntries = Object.entries(result.details ?? {}).filter(([, value]) =>
    value !== null && value !== undefined && value !== ""
  );
  const roleLabel = ROLE_LABELS[result.score_role ?? "supporting-score"] ?? "Layer";
  const roleBadgeClass =
    ROLE_BADGES[result.score_role ?? "supporting-score"] ?? ROLE_BADGES["supporting-score"];

  return (
    <div className="flex min-h-[320px] flex-col rounded-[28px] panel-muted xl:min-h-0 xl:overflow-hidden">
      <div className="border-b border-white/8 px-5 py-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-3">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.05] text-xl">
                {layerIcon(result.layer)}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="min-w-0 flex-1 break-words text-xl font-semibold tracking-[-0.03em] text-white [overflow-wrap:anywhere]">
                    {layerLabel(result.layer)}
                  </h3>
                  <span className={cn("shrink-0 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em]", roleBadgeClass)}>
                    {roleLabel}
                  </span>
                  {result.suppressed ? (
                    <span className="shrink-0 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-amber-300">
                      Guardrailed
                    </span>
                  ) : null}
                </div>
                <p className="mt-2 break-words text-sm leading-6 text-[#a7a7a7] [overflow-wrap:anywhere]">
                  {result.suppression_reason || result.flags[0] || "No noteworthy flags were emitted for this layer."}
                </p>
              </div>
            </div>
          </div>

          <div className="shrink-0 rounded-[24px] border border-white/10 bg-black/10 px-4 py-3 text-right">
            <div className="text-xs font-medium text-[var(--text-muted-strong)]">Signal strength</div>
            <div className={cn("mt-2 text-3xl font-semibold", riskColor(tier))}>
              {scoreToPercent(result.score)}
            </div>
          </div>
        </div>
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto px-5 pb-8 pt-5">
        <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(112px,1fr))] lg:[grid-template-columns:repeat(auto-fit,minmax(126px,1fr))]">
          <div className="min-w-0 rounded-[22px] panel-inset px-4 py-4">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
              <ShieldAlert className="h-3.5 w-3.5" />
              Signal family
            </div>
            <div className="mt-2 break-words text-sm text-white [overflow-wrap:anywhere]">
              {result.evidence_family ?? "Unknown"}
            </div>
          </div>
          <div className="min-w-0 rounded-[22px] panel-inset px-4 py-4">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
              <Sigma className="h-3.5 w-3.5" />
              How sure (this check)
            </div>
            <div className="mt-2 break-words text-sm text-white [overflow-wrap:anywhere]">
              {scoreToPercent(result.confidence)}%
            </div>
          </div>
          <div className="min-w-0 rounded-[22px] panel-inset px-4 py-4">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
              <Scale className="h-3.5 w-3.5" />
              Configured weight
            </div>
            <div className="mt-2 break-words text-sm text-white [overflow-wrap:anywhere]">
              {formatPercent(result.configured_weight)}
            </div>
          </div>
          <div className="min-w-0 rounded-[22px] panel-inset px-4 py-4">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
              <Sigma className="h-3.5 w-3.5" />
              Impact on score
            </div>
            <div className="mt-2 break-words text-sm text-white [overflow-wrap:anywhere]">
              {formatPercent(result.weighted_contribution)}
            </div>
          </div>
          <div className="min-w-0 rounded-[22px] panel-inset px-4 py-4">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
              <Clock3 className="h-3.5 w-3.5" />
              Check duration
            </div>
            <div className="mt-2 break-words text-sm text-white [overflow-wrap:anywhere]">
              {result.duration_ms !== undefined ? `${result.duration_ms}ms` : "-"}
            </div>
          </div>
          <div className="min-w-0 rounded-[22px] panel-inset px-4 py-4">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
              <TimerReset className="h-3.5 w-3.5" />
              Kind
            </div>
            <div className="mt-2 break-words text-sm text-white [overflow-wrap:anywhere]">
              {result.implementation_kind ?? "Unknown"}
            </div>
          </div>
        </div>

        {result.suppression_reason ? (
          <div className="rounded-[24px] border border-amber-500/25 bg-amber-500/[0.08] px-4 py-4 text-sm leading-6 text-amber-50">
            {result.suppression_reason}
          </div>
        ) : null}

        {result.flags.length > 0 ? (
          <section className="rounded-[24px] panel-inset px-4 py-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
              What we noticed
            </div>
            <ul className="mt-3 grid gap-2 md:grid-cols-2">
              {result.flags.map((flag, index) => (
                <li key={`${flag}-${index}`} className="rounded-2xl border border-white/8 bg-black/10 px-3 py-3 text-sm leading-6 text-[#dedede] break-words [overflow-wrap:anywhere]">
                  {flag}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {detailEntries.length > 0 ? (
          <section className="rounded-[24px] panel-inset px-4 py-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
              Raw fields
            </div>
            <div className="mt-3 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(168px,1fr))]">
              {detailEntries.map(([key, value]) => (
                <div key={key} className="min-w-0 rounded-2xl border border-white/8 bg-black/10 px-3 py-3">
                  <div className="break-words text-[11px] font-semibold uppercase tracking-[0.16em] text-[#7f7f7f] [overflow-wrap:anywhere]">
                    {key.replace(/_/g, " ")}
                  </div>
                  <div className="mt-2 break-words text-sm leading-6 text-[#e0e0e0] [overflow-wrap:anywhere]">
                    {formatDetailValue(value)}
                  </div>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {result.layer === "ela" && elaHeatmap ? (
          <section className="rounded-[24px] panel-inset px-4 py-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
              Compression difference map
            </div>
            <img
              src={`data:image/png;base64,${elaHeatmap}`}
              alt="ELA heatmap"
              className="mt-3 w-full rounded-[22px] border border-white/8"
            />
            <p className="mt-3 text-sm leading-6 text-[#a2a2a2]">
              Bright areas indicate stronger compression error. Uniform brightness across large regions can align with synthetic generation.
            </p>
          </section>
        ) : null}

        {result.layer === "trufor" && truforHeatmap ? (
          <section className="rounded-[24px] panel-inset px-4 py-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
              Possible edit regions
            </div>
            <img
              src={`data:image/png;base64,${truforHeatmap}`}
              alt="TruFor manipulation heatmap"
              className="mt-3 w-full rounded-[22px] border border-white/8"
            />
            <p className="mt-3 text-sm leading-6 text-[#a2a2a2]">
              Warm regions indicate a higher probability of pixel-level manipulation, while cool regions are more likely authentic.
            </p>
          </section>
        ) : null}

        {result.layer === "gemini" && (geminiReasoning || result.details?.template_like_output) ? (
          <section className="rounded-[24px] panel-inset px-4 py-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
              AI-generated interpretation
            </div>
            <div className="mt-3 rounded-[22px] border border-white/8 bg-black/10 px-4 py-4 text-sm leading-7 text-[#dedede] break-words [overflow-wrap:anywhere]">
              {geminiReasoning || "Local VLM output resembled a copied template, so free-text reasoning was suppressed for this run."}
            </div>
          </section>
        ) : null}

        <div className="rounded-[24px] panel-inset px-4 py-4">
          <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
            <span className="break-words [overflow-wrap:anywhere]">Confidence bar</span>
            <span className="shrink-0">{scoreToPercent(result.confidence)}%</span>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/[0.06]">
            <div
              className="h-full rounded-full bg-white/70"
              style={{ width: `${scoreToPercent(result.confidence)}%` }}
            />
          </div>
        </div>

        {result.error ? (
          <div className="rounded-[24px] border border-red-900/50 bg-red-950/20 px-4 py-4 text-sm leading-6 text-red-100">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-red-200/70">
              <AlertTriangle className="h-3.5 w-3.5" />
              Check error
            </div>
            <div className="mt-2 break-words [overflow-wrap:anywhere]">{result.error}</div>
          </div>
        ) : null}
      </div>
    </div>
  );
}