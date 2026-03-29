"use client";

import { useId } from "react";
import { ChevronDown } from "lucide-react";
import type { LayerResult } from "@/lib/api";
import { GROUP_SECTION } from "@/lib/copy";
import { cn, layerLabel, scoreToPercent } from "@/lib/utils";

type GroupKey = "core" | "supporting" | "other";

interface EvidenceSummaryAccordionsProps {
  grouped: Record<GroupKey, LayerResult[]>;
  className?: string;
}

function summarizeGroup(layers: LayerResult[]): string {
  if (layers.length === 0) return "No checks in this group for this run.";
  const top = [...layers].sort(
    (a, b) => (b.weighted_contribution ?? b.score) - (a.weighted_contribution ?? a.score)
  )[0];
  const hint = top.suppression_reason || top.flags[0];
  if (hint) return `Strongest signal: ${layerLabel(top.layer)} — ${hint}`;
  return `Highest attention: ${layerLabel(top.layer)} (about ${scoreToPercent(top.score)} on this check).`;
}

export default function EvidenceSummaryAccordions({
  grouped,
  className,
}: EvidenceSummaryAccordionsProps) {
  const baseId = useId();
  const sections: { key: GroupKey; layers: LayerResult[] }[] = [
    { key: "core", layers: grouped.core },
    { key: "supporting", layers: grouped.supporting },
    { key: "other", layers: grouped.other },
  ];

  return (
    <section className={cn("space-y-3", className)}>
      <div>
        <h3 className="text-lg font-semibold text-[var(--text-primary)]">What we checked</h3>
        <p className="mt-1 text-sm text-[var(--text-soft)]">
          Groups are for readability—open any section for a quick peek. Full detail lives in technical view.
        </p>
      </div>

      <div className="grid gap-2">
        {sections.map(({ key, layers }) => {
          const meta = GROUP_SECTION[key];
          const panelId = `${baseId}-${key}-panel`;
          const headingId = `${baseId}-${key}-heading`;

          return (
            <details
              key={key}
              className="group rounded-[22px] border border-[rgba(73,118,159,0.18)] bg-[rgba(230,243,250,0.72)] open:border-[rgba(73,118,159,0.28)] open:bg-[rgba(123,189,232,0.28)]"
            >
              <summary
                className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-4 text-left [&::-webkit-details-marker]:hidden"
                aria-labelledby={headingId}
              >
                <div className="min-w-0">
                  <div id={headingId} className="text-base font-semibold text-[var(--text-primary)]">
                    {meta.title}
                  </div>
                  <div className="mt-0.5 text-xs text-[var(--text-muted-strong)]">{meta.subtitle}</div>
                  <p className="mt-2 text-sm leading-6 text-[var(--text-soft)]">{summarizeGroup(layers)}</p>
                </div>
                <ChevronDown className="h-5 w-5 shrink-0 text-[var(--text-muted-strong)] transition group-open:rotate-180" aria-hidden />
              </summary>
              <div id={panelId} className="border-t border-[rgba(73,118,159,0.12)] px-4 pb-4 pt-0">
                {layers.length === 0 ? (
                  <p className="pt-3 text-sm text-[var(--text-soft)]">Nothing in this group.</p>
                ) : (
                  <ul className="mt-3 grid gap-2">
                    {layers.map((layer) => (
                      <li
                        key={layer.layer}
                        className="deep-panel flex flex-wrap items-baseline justify-between gap-2 rounded-xl px-3 py-2 text-sm"
                      >
                        <span className="font-medium text-[var(--text-primary)] [overflow-wrap:anywhere]">
                          {layerLabel(layer.layer)}
                        </span>
                        <span className="tabular-nums text-[var(--text-secondary)]">
                          signal {scoreToPercent(layer.score)} · confidence {scoreToPercent(layer.confidence)}%
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </details>
          );
        })}
      </div>
    </section>
  );
}
