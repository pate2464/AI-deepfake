"use client";

import { riskColor, scoreToPercent } from "@/lib/utils";

interface RiskGaugeProps {
  score: number;
  tier: "low" | "medium" | "high";
}

export default function RiskGauge({ score, tier }: RiskGaugeProps) {
  const percent = scoreToPercent(score);
  const circumference = 2 * Math.PI * 45; // radius=45
  const offset = circumference - (score * circumference);

  const strokeColor = {
    low: "#22c55e",
    medium: "#f59e0b",
    high: "#ef4444",
  }[tier];

  const tierLabel = {
    low: "LOW RISK",
    medium: "MEDIUM RISK",
    high: "HIGH RISK",
  }[tier];

  const tierAction = {
    low: "Auto-approve",
    medium: "Human review",
    high: "Auto-reject",
  }[tier];

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative w-40 h-40">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
          {/* Background circle */}
          <circle
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke="#2a2a2a"
            strokeWidth="8"
          />
          {/* Score circle */}
          <circle
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke={strokeColor}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className="gauge-circle"
            style={{ transition: "stroke-dashoffset 1.5s ease-out" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span
            className={`text-3xl font-bold ${riskColor(tier)}`}
          >
            {percent}
          </span>
          <span className="text-xs text-[#a0a0a0]">/ 100</span>
        </div>
      </div>
      <div className="text-center">
        <div className={`text-sm font-bold tracking-wider ${riskColor(tier)}`}>
          {tierLabel}
        </div>
        <div className="text-xs text-[#a0a0a0] mt-1">
          Recommended: {tierAction}
        </div>
      </div>
    </div>
  );
}
