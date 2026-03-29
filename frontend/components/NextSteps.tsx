"use client";

import { ImagePlus } from "lucide-react";
import { cn } from "@/lib/utils";

interface NextStepsProps {
  onUploadAnother: () => void;
  className?: string;
}

export default function NextSteps({ onUploadAnother, className }: NextStepsProps) {
  return (
    <section className={cn("rounded-[24px] border border-[rgba(73,118,159,0.18)] bg-white/[0.28] px-5 py-5", className)}>
      <h3 className="text-base font-semibold text-[var(--text-primary)]">What to do next</h3>
      <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-7 text-[var(--text-soft)] marker:text-[var(--text-muted-strong)]">
        <li>If this matters for a decision, ask for the original file or more context.</li>
        <li>Treat this as triage—have a human review before high-stakes actions.</li>
        <li>Do not use this output alone as legal proof.</li>
      </ul>
      <p className="mt-4 text-sm text-[var(--text-soft)]">
        Need charts, heatmaps, or raw fields? Expand <span className="font-medium text-[var(--text-primary)]">Technical analysis</span>{" "}
        below.
      </p>
      <div className="mt-5 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={onUploadAnother}
          className="inline-flex items-center gap-2 rounded-full bg-[#49769F] px-4 py-2.5 text-sm font-semibold text-[var(--text-on-dark)] transition hover:bg-[#6EA2B3] hover:text-[var(--text-primary)]"
        >
          <ImagePlus className="h-4 w-4" aria-hidden />
          Upload another image
        </button>
      </div>
    </section>
  );
}
