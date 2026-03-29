"use client";

import { cn, riskColor, scoreToPercent } from "@/lib/utils";

interface RiskMeterProps {
  score: number;
  tier: "low" | "medium" | "high";
  label?: string;
  className?: string;
}

export default function RiskMeter({
  score,
  tier,
  label = "Overall concern",
  className,
}: RiskMeterProps) {
  const pct = scoreToPercent(score);
  const barColor =
    tier === "high" ? "bg-[#d4949d]" : tier === "medium" ? "bg-[#8b7fac]" : "bg-[#5c63a4]";

  return (
    <div className={cn("w-full", className)}>
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="text-[var(--text-secondary)]">{label}</span>
        <span className={cn("font-semibold tabular-nums", riskColor(tier))}>{pct} / 100</span>
      </div>
      <div
        className="mt-2 h-2.5 overflow-hidden rounded-full bg-[#acb0cc]/50"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-label={`${label}: ${pct} out of 100`}
      >
        <div
          className={cn("h-full rounded-full transition-all duration-500", barColor)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
