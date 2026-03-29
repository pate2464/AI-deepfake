"use client";

import { cn } from "@/lib/utils";

interface TrustFooterProps {
  scoringVersion?: string;
  className?: string;
}

export default function TrustFooter({ scoringVersion, className }: TrustFooterProps) {
  return (
    <footer
      className={cn(
        "mt-8 border-t border-[rgba(92,99,164,0.14)] pt-6 text-center text-xs leading-6 text-[var(--text-soft)]",
        className
      )}
    >
      <p>
        HackyIndy 2026 · Image screening uses many automated checks and AI-assisted interpretation.{" "}
        <span className="text-[var(--text-secondary)]">
          It prioritizes review, not certainty{scoringVersion ? ` · scoring ${scoringVersion}` : ""}.
        </span>
      </p>
    </footer>
  );
}
