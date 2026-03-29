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
        "mt-8 border-t border-white/[0.06] pt-6 text-center text-xs leading-6 text-[#7a7a7a]",
        className
      )}
    >
      <p>
        HackyIndy 2026 · Image screening uses many automated checks and AI-assisted interpretation.{" "}
        <span className="text-[#9a9a9a]">
          It prioritizes review, not certainty{scoringVersion ? ` · scoring ${scoringVersion}` : ""}.
        </span>
      </p>
    </footer>
  );
}
