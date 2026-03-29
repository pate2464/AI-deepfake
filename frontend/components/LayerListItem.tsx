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
          ? "selection-glow border-[#a8b7ae]/70 bg-[#fff7f2]"
          : "border-[#a8b7ae]/45 bg-[#f7f1ea] hover:border-[#93939b]/60 hover:bg-[#fff7f2]"
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.04] text-lg">
              {layerIcon(result.layer)}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-start gap-2">
                <h4 className="min-w-0 flex-1 text-sm font-semibold leading-5 text-white">
                  {layerLabel(result.layer)}
                </h4>
                <span className="shrink-0 rounded-full border border-white/20 bg-[#2b2e35] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-[#ffeddc]">
                  {roleLabel}
                </span>
              </div>
              <p className="mt-2 line-clamp-2 text-xs leading-5 text-[#dfe2db]">
                {headline}
              </p>
            </div>
          </div>
        </div>
        <ChevronRight className={cn("mt-1 h-4 w-4 shrink-0 text-[#7f7f7f] transition", isActive && "translate-x-0.5 text-white")} />
      </div>

      <div className="mt-4 flex items-center gap-3">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
          <div
            className={cn(
              "h-full rounded-full",
              tier === "high"
                ? "bg-red-500"
                : tier === "medium"
                  ? "bg-amber-500"
                  : "bg-green-500"
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