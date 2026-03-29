"use client";

import { ListOrdered } from "lucide-react";
import { cn } from "@/lib/utils";

interface ReasonListProps {
  reasons: string[];
  onViewTechnical?: () => void;
  className?: string;
}

export default function ReasonList({ reasons, onViewTechnical, className }: ReasonListProps) {
  return (
    <section className={cn("rounded-[24px] panel-muted px-5 py-5", className)}>
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-white">
          <ListOrdered className="h-4 w-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="text-base font-semibold text-white">Why this result</h3>
          <p className="mt-1 text-sm leading-6 text-[#a3a3a3]">
            Plain-language takeaways. For scores, heatmaps, and raw fields, open technical details.
          </p>
          <ul className="mt-4 grid gap-2.5 text-sm leading-7 text-[#e4e4e4]">
            {reasons.map((reason, i) => (
              <li key={i} className="flex gap-2">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-white/35" aria-hidden />
                <span className="min-w-0 [overflow-wrap:anywhere]">{reason}</span>
              </li>
            ))}
          </ul>
          {onViewTechnical ? (
            <button
              type="button"
              onClick={onViewTechnical}
              className="mt-4 text-sm font-medium text-sky-300/95 underline-offset-4 hover:underline"
            >
              See technical evidence
            </button>
          ) : null}
        </div>
      </div>
    </section>
  );
}
