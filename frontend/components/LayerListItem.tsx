"use client";

import { ChevronRight } from "lucide-react";
import type { LayerResult } from "@/lib/api";
import { ROLE_LABELS_SHORT } from "@/lib/copy";
import { cn, layerIcon, layerLabel, riskColor, scoreToPercent } from "@/lib/utils";

interface LayerListItemProps {
  result: LayerResult;
  isActive: boolean;
  onSelect: () => void;
}

export default function LayerListItem({
  result,
  isActive,
  onSelect,
}: LayerListItemProps) {
  const tier =
    result.score >= 0.6 ? "high" : result.score >= 0.3 ? "medium" : "low";
  const roleLabel = ROLE_LABELS_SHORT[result.score_role ?? "supporting-score"] ?? "Check";
  const headline = result.suppression_reason || result.flags[0] || "No notable flags emitted.";

  return (
    <button
      onClick={onSelect}
      className={cn(
        "w-full rounded-[24px] border px-4 py-4 text-left transition",
        isActive
          ? "selection-glow border-[rgba(73,118,159,0.34)] bg-[rgba(123,189,232,0.34)]"
          : "border-[rgba(73,118,159,0.22)] bg-[rgba(235,246,252,0.84)] hover:border-[rgba(73,118,159,0.34)] hover:bg-[rgba(189,216,233,0.56)]"
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-2xl border border-[rgba(73,118,159,0.14)] bg-white/[0.36] text-lg">
              {layerIcon(result.layer)}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-start gap-2">
                <h4 className="min-w-0 flex-1 text-sm font-semibold leading-5 text-[var(--text-primary)]">
                  {layerLabel(result.layer)}
                </h4>
                <span className="shrink-0 rounded-full border border-[rgba(73,118,159,0.18)] bg-[rgba(123,189,232,0.16)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-secondary)]">
                  {roleLabel}
                </span>
              </div>
              <p className="mt-2 line-clamp-2 text-xs leading-5 text-[var(--text-soft)]">
                {headline}
              </p>
            </div>
          </div>
        </div>
        <ChevronRight className={cn("mt-1 h-4 w-4 shrink-0 text-[var(--text-muted-strong)] transition", isActive && "translate-x-0.5 text-[var(--text-primary)]")} />
      </div>

      <div className="mt-4 flex items-center gap-3">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-[rgba(73,118,159,0.14)]">
          <div
            className={cn(
              "h-full rounded-full",
              tier === "high"
                ? "bg-[#6EA2B3]"
                : tier === "medium"
                  ? "bg-[#49769F]"
                  : "bg-[#4E8EA2]"
            )}
            style={{ width: `${scoreToPercent(result.score)}%` }}
          />
        </div>
        <span className={cn("w-14 text-right text-sm font-semibold tabular-nums", riskColor(tier))}>
          {scoreToPercent(result.score)}
        </span>
      </div>
    </button>
  );
}
