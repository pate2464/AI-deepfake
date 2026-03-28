import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function riskColor(tier: "low" | "medium" | "high") {
  return {
    low: "text-green-500",
    medium: "text-amber-500",
    high: "text-red-500",
  }[tier];
}

export function riskBg(tier: "low" | "medium" | "high") {
  return {
    low: "bg-green-500/10 border-green-500/30",
    medium: "bg-amber-500/10 border-amber-500/30",
    high: "bg-red-500/10 border-red-500/30",
  }[tier];
}

export function layerLabel(layer: string): string {
  const labels: Record<string, string> = {
    exif: "EXIF Metadata",
    ela: "Error Level Analysis",
    hash: "Perceptual Hashing",
    ai_model: "AI Model Detection",
    c2pa: "C2PA Provenance",
    behavioral: "Behavioral Scoring",
    gemini: "Gemini Vision AI",
    noise: "Noise / PRNU",
  };
  return labels[layer] || layer;
}

export function layerIcon(layer: string): string {
  const icons: Record<string, string> = {
    exif: "📷",
    ela: "🔥",
    hash: "🔗",
    ai_model: "🧠",
    c2pa: "🔐",
    behavioral: "👤",
    gemini: "✨",
    noise: "📊",
  };
  return icons[layer] || "🔍";
}

export function scoreToPercent(score: number): number {
  return Math.round(score * 100);
}
