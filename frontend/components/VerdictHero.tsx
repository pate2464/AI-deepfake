"use client";

import type { AnalysisResponse } from "@/lib/api";
import { tierLabelPlain, tierVerdictHeadline, tierVerdictSubtext } from "@/lib/copy";
import { aggregateConfidenceBand } from "@/lib/verdict";
import { cn, riskBg } from "@/lib/utils";
import RiskGauge from "@/components/RiskGauge";
import RiskMeter from "@/components/RiskMeter";

interface VerdictHeroProps {
  result: AnalysisResponse;
  className?: string;
}

export default function VerdictHero({ result, className }: VerdictHeroProps) {
  const conf = aggregateConfidenceBand(result);

  return (
    <section
      className={cn(
        "rounded-[28px] border px-5 py-6 md:px-6 md:py-7",
        riskBg(result.risk_tier),
        "panel-hero",
        className
      )}
    >
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-[var(--text-secondary)]">Screening results</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-[var(--text-primary)] md:text-3xl">
            {tierVerdictHeadline(result.risk_tier)}
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--text-soft)]">
            {tierVerdictSubtext(result.risk_tier)}
          </p>

          <div className="mt-6 space-y-4">
            <RiskMeter score={result.risk_score} tier={result.risk_tier} />
            <div className="rounded-2xl border border-[var(--line-soft)] bg-[rgba(247,252,255,0.78)] px-4 py-3">
              <p className="text-xs font-medium text-[var(--text-muted-strong)]">
                How confident we are in this summary
              </p>
              <p className="mt-1 text-sm text-[var(--text-primary)]">
                <span className="font-semibold">{conf.label}</span>
                <span className="text-[var(--text-soft)]"> — {conf.detail}</span>
              </p>
            </div>
            <p className="text-xs leading-5 text-[var(--text-soft)]">
              Overall band: <span className="font-medium text-[var(--text-secondary)]">{tierLabelPlain(result.risk_tier)}</span>
              {" · "}
              This tool uses automated and AI-assisted checks. Results can be wrong—use alongside human judgment.
            </p>
          </div>
        </div>

        <div className="flex shrink-0 flex-col items-center gap-2 lg:pt-1">
          <RiskGauge score={result.risk_score} tier={result.risk_tier} size={112} />
        </div>
      </div>
    </section>
  );
}
