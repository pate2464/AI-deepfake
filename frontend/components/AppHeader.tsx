"use client";

import { ImageIcon, Shield } from "lucide-react";
import { PRODUCT } from "@/lib/copy";
import { cn } from "@/lib/utils";

export default function AppHeader({ className }: { className?: string }) {
  return (
    <header
      className={cn(
        "section-enter glass-highlight accent-orbit ambient-glow mb-6 flex flex-col gap-6 rounded-[28px] border border-white/[0.12] bg-[radial-gradient(circle_at_top_left,rgba(169,195,182,0.24),transparent_52%),radial-gradient(circle_at_top_right,rgba(166,195,206,0.2),transparent_45%),radial-gradient(circle_at_72%_18%,rgba(206,223,223,0.24),transparent_42%),var(--surface-hero)] px-5 py-6 md:flex-row md:items-center md:justify-between md:px-7",
        className
      )}
    >
      <div className="max-w-2xl">
        <div className="inline-flex items-center gap-2 rounded-full border border-[var(--line-soft)] bg-[rgba(255,248,245,0.78)] px-3 py-1 text-xs font-medium text-[var(--text-secondary)]">
          <Shield className="h-3.5 w-3.5 text-brand-200" aria-hidden />
          {PRODUCT.eyebrow}
        </div>
        <h1 className="mt-4 text-3xl font-semibold tracking-[-0.04em] text-[var(--text-primary)] md:text-4xl">
          {PRODUCT.name}
        </h1>
        <p className="mt-3 text-sm leading-7 text-[var(--text-soft)] md:text-[15px]">
          {PRODUCT.tagline}. You get a clear summary first—heatmaps, metadata, and per-check breakdowns stay
          available for experts.
        </p>
      </div>
      <div className="flex shrink-0 items-start gap-3 rounded-2xl border border-[var(--line-soft)] bg-[rgba(255,248,245,0.76)] px-4 py-3 backdrop-blur-sm md:max-w-xs">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-[rgba(145,172,154,0.24)] bg-[radial-gradient(circle_at_top,rgba(169,195,182,0.32),rgba(255,255,255,0.14))] text-[var(--text-primary)]">
          <ImageIcon className="h-5 w-5 text-brand-100" aria-hidden />
        </span>
        <div className="text-sm leading-6 text-[var(--text-soft)]">
          <span className="font-medium text-[var(--text-primary)]">Guided screening</span>
          <br />
          Upload on the left, read the verdict in plain English, then expand technical detail only if you need it.
        </div>
      </div>
    </header>
  );
}
