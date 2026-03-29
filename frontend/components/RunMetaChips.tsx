"use client";

import { Clock3, Fingerprint, Layers3 } from "lucide-react";
import type { AnalysisResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

interface RunMetaChipsProps {
  result: AnalysisResponse;
  className?: string;
}

export default function RunMetaChips({ result, className }: RunMetaChipsProps) {
  return (
    <div
      className={cn(
        "flex flex-wrap gap-2 text-xs text-[var(--text-soft)]",
        className
      )}
    >
      <span className="soft-chip inline-flex items-center gap-1.5 rounded-full px-3 py-1">
        <Clock3 className="h-3.5 w-3.5 shrink-0" aria-hidden />
        Analysis time {result.processing_time_ms} ms
      </span>
      <span className="soft-chip inline-flex items-center gap-1.5 rounded-full px-3 py-1">
        <Layers3 className="h-3.5 w-3.5 shrink-0" aria-hidden />
        {result.layer_results.length} checks run
      </span>
      <span className="soft-chip inline-flex items-center gap-1.5 rounded-full px-3 py-1">
        <Fingerprint className="h-3.5 w-3.5 shrink-0" aria-hidden />
        {result.hash_matches.length} possible duplicate
        {result.hash_matches.length === 1 ? "" : "s"}
      </span>
    </div>
  );
}
