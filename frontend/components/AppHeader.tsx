"use client";

import { ImageIcon, Shield } from "lucide-react";
import { PRODUCT } from "@/lib/copy";
import { cn } from "@/lib/utils";

export default function AppHeader({ className }: { className?: string }) {
  return (
    <header
      className={cn(
        "section-enter mb-6 flex flex-col gap-6 rounded-[28px] border border-white/[0.08] bg-[var(--surface-hero)] px-5 py-6 md:flex-row md:items-center md:justify-between md:px-7",
        className
      )}
    >
      <div className="max-w-2xl">
        <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.05] px-3 py-1 text-xs font-medium text-[#c4c4c4]">
          <Shield className="h-3.5 w-3.5 text-[#a8a8a8]" aria-hidden />
          {PRODUCT.eyebrow}
        </div>
        <h1 className="mt-4 text-3xl font-semibold tracking-[-0.04em] text-white md:text-4xl">
          {PRODUCT.name}
        </h1>
        <p className="mt-3 text-sm leading-7 text-[#a8a8a8] md:text-[15px]">
          {PRODUCT.tagline}. You get a clear summary first—heatmaps, metadata, and per-check breakdowns stay
          available for experts.
        </p>
      </div>
      <div className="flex shrink-0 items-start gap-3 rounded-2xl border border-white/[0.07] bg-black/25 px-4 py-3 md:max-w-xs">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-white">
          <ImageIcon className="h-5 w-5" aria-hidden />
        </span>
        <div className="text-sm leading-6 text-[#b6b6b6]">
          <span className="font-medium text-white">Guided screening</span>
          <br />
          Upload on the left, read the verdict in plain English, then expand technical detail only if you need it.
        </div>
      </div>
    </header>
  );
}
