"use client";

import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface OverviewCard {
  title: string;
  body: string;
  tone?: "default" | "warning";
}

interface TechnicalAnalysisSectionProps {
  open: boolean;
  onToggle: () => void;
  overviewCards: OverviewCard[];
  children: ReactNode;
  className?: string;
}

export default function TechnicalAnalysisSection({
  open,
  onToggle,
  overviewCards,
  children,
  className,
}: TechnicalAnalysisSectionProps) {
  return (
    <section className={cn("rounded-[28px] panel-muted p-1", className)}>
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-3 rounded-[24px] px-4 py-4 text-left transition hover:bg-white/[0.04]"
        aria-expanded={open}
        id="technical-analysis-toggle"
      >
        <div>
          <p className="text-xs font-medium text-[var(--text-muted-strong)]">For reviewers & analysts</p>
          <h3 className="mt-1 text-lg font-semibold text-white">Technical analysis</h3>
          <p className="mt-1 text-sm text-[#9a9a9a]">
            Per-check scores, weights, heatmaps, metadata fields, and run diagnostics.
          </p>
        </div>
        <ChevronDown
          className={cn("h-6 w-6 shrink-0 text-[#888] transition", open && "rotate-180")}
          aria-hidden
        />
      </button>

      {open ? (
        <div
          className="border-t border-white/[0.06] p-4 md:p-5"
          role="region"
          aria-labelledby="technical-analysis-toggle"
        >
          <div className="grid gap-4 lg:grid-cols-3">
            {overviewCards.map((card) => (
              <div
                key={card.title}
                className={cn(
                  "rounded-[22px] px-4 py-4",
                  card.tone === "warning"
                    ? "border border-amber-500/20 bg-amber-500/[0.07]"
                    : "border border-white/[0.06] bg-black/20"
                )}
              >
                <div className="text-xs font-medium text-[var(--text-muted-strong)]">{card.title}</div>
                <p className="mt-3 break-words text-sm leading-6 text-[#d4d4d4] [overflow-wrap:anywhere]">
                  {card.body}
                </p>
              </div>
            ))}
          </div>

          <div className="mt-6">{children}</div>
        </div>
      ) : null}
    </section>
  );
}
