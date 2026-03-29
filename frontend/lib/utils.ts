import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function riskColor(tier: "low" | "medium" | "high") {
  return {
    low: "text-[#8fb8ca]",
    medium: "text-[#91ac9a]",
    high: "text-[#6c8277]",
  }[tier];
}

export function riskBg(tier: "low" | "medium" | "high") {
  return {
    low: "bg-[#cedfdf]/76 border-[#b7d1d3]",
    medium: "bg-[#b7d1d3]/34 border-[#a6c3ce]",
    high: "bg-[#a9c3b6]/28 border-[#91ac9a]",
  }[tier];
}

export function layerLabel(layer: string): string {
  const labels: Record<string, string> = {
    exif: "File & camera metadata",
    ela: "Compression consistency",
    hash: "Visual fingerprint match",
    ai_model: "AI-model pattern cues",
    c2pa: "Content credentials (C2PA)",
    behavioral: "Behavior context",
    gemini: "Vision model (AI explanation)",
    noise: "Sensor noise pattern",
    clip_detect: "Semantic pattern check",
    cnn_detect: "Neural fingerprint",
    watermark: "Watermark detection",
    trufor: "Edit-region estimate",
    dire: "Reconstruction realism",
    gradient: "Edge & gradient distribution",
    lsb: "Hidden data pattern",
    dct_hist: "Frequency pattern",
    gan_fingerprint: "GAN-style spectrum",
    attention_pattern: "Attention pattern",
    texture: "Texture consistency",
    npr: "Pixel residual noise",
    mlep: "Entropy pattern",
  };
  return labels[layer] || layer.replace(/_/g, " ");
}

export function layerIcon(layer: string): string {
  const icons: Record<string, string> = {
    exif: "📷",
    ela: "🔥",
    hash: "🔗",
    ai_model: "🧠",
    c2pa: "🔐",
    behavioral: "👤",
    gemini: "🤖",
    noise: "📊",
    clip_detect: "👁️",
    cnn_detect: "🧬",
    watermark: "💧",
    trufor: "🗺️",
    dire: "🔄",
    gradient: "📈",
    lsb: "🔬",
    dct_hist: "📐",
    gan_fingerprint: "👾",
    attention_pattern: "🎯",
    texture: "🧵",
    npr: "🔍",
    mlep: "📊",
  };
  return icons[layer] || "🔍";
}

export function scoreToPercent(score: number): number {
  return Math.round(score * 100);
}
