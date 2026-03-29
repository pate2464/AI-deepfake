"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Clock3,
  Fingerprint,
  Layers3,
  ShieldAlert,
  Sparkles,
  Workflow,
} from "lucide-react";
import ImageUpload, { type SelectedFileMeta } from "@/components/ImageUpload";
import LayerDetailPanel from "@/components/LayerDetailPanel";
import LayerListItem from "@/components/LayerListItem";
import RiskGauge from "@/components/RiskGauge";
import { analyzeImage, type AnalysisResponse } from "@/lib/api";
import { cn, riskBg, scoreToPercent } from "@/lib/utils";

type LayerGroupKey = "core" | "supporting" | "other";

const EMPTY_LAYER_GROUPS: Record<LayerGroupKey, AnalysisResponse["layer_results"]> = {
  core: [],
  supporting: [],
  other: [],
};

export default function Home() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<SelectedFileMeta | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<LayerGroupKey>("core");
  const [selectedLayer, setSelectedLayer] = useState<string | null>(null);

  const [showContext, setShowContext] = useState(false);
  const [accountId, setAccountId] = useState("");
  const [deviceFp, setDeviceFp] = useState("");
  const [orderValue, setOrderValue] = useState("");

  const formatFamily = (family: string) =>
    family
      .replace(/_/g, " ")
      .replace(/^./, (value) => value.toUpperCase());

  useEffect(() => {
    if (!previewUrl) {
      return undefined;
    }

    return () => {
      URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const handleFileSelect = useCallback(
    async (file: File) => {
      setPreviewUrl(URL.createObjectURL(file));
      setSelectedFile({
        name: file.name,
        type: file.type,
        size: file.size,
      });
      setIsAnalyzing(true);
      setError(null);
      setResult(null);
      setSelectedLayer(null);

      try {
        const response = await analyzeImage(file, {
          account_id: accountId || undefined,
          device_fingerprint: deviceFp || undefined,
          order_value: orderValue ? parseFloat(orderValue) : undefined,
        });
        setResult(response);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message || "Analysis failed" : "Analysis failed");
      } finally {
        setIsAnalyzing(false);
      }
    },
    [accountId, deviceFp, orderValue]
  );

  const groupedLayers = result
    ? {
        core: [...result.layer_results]
          .filter((layer) => layer.score_role === "core-score")
          .sort(
            (a, b) =>
              (b.weighted_contribution ?? b.score) -
                (a.weighted_contribution ?? a.score) ||
              b.score - a.score
          ),
        supporting: [...result.layer_results]
          .filter((layer) => layer.score_role === "supporting-score")
          .sort(
            (a, b) =>
              (b.weighted_contribution ?? b.score) -
                (a.weighted_contribution ?? a.score) ||
              b.score - a.score
          ),
        other: [...result.layer_results]
          .filter((layer) => layer.score_role === "other-layer")
          .sort(
            (a, b) =>
              (b.weighted_contribution ?? b.score) -
                (a.weighted_contribution ?? a.score) ||
              b.score - a.score
          ),
      }
    : EMPTY_LAYER_GROUPS;

  const layerSections = [
    {
      key: "core" as const,
      title: "Core",
      subtitle: "Backbone scoring",
      layers: groupedLayers.core,
    },
    {
      key: "supporting" as const,
      title: "Supporting",
      subtitle: "Context and corroboration",
      layers: groupedLayers.supporting,
    },
    {
      key: "other" as const,
      title: "Other",
      subtitle: "Forensic side channels",
      layers: groupedLayers.other,
    },
  ];

  useEffect(() => {
    if (!result) {
      setSelectedGroup("core");
      setSelectedLayer(null);
      return;
    }

    const firstAvailable = layerSections.find((section) => section.layers.length > 0);
    if (!firstAvailable) {
      setSelectedGroup("core");
      setSelectedLayer(null);
      return;
    }

    setSelectedGroup((currentGroup) => {
      const currentStillHasLayers = layerSections.some(
        (section) => section.key === currentGroup && section.layers.length > 0
      );
      return currentStillHasLayers ? currentGroup : firstAvailable.key;
    });
  }, [result]);

  const activeLayers = groupedLayers[selectedGroup] ?? [];

  useEffect(() => {
    if (activeLayers.length === 0) {
      setSelectedLayer(null);
      return;
    }

    if (!activeLayers.some((layer) => layer.layer === selectedLayer)) {
      setSelectedLayer(activeLayers[0].layer);
    }
  }, [activeLayers, selectedLayer]);

  const selectedLayerResult = selectedLayer
    ? result?.layer_results.find((layer) => layer.layer === selectedLayer) ?? activeLayers[0] ?? null
    : activeLayers[0] ?? null;

  const overviewCards = result
    ? [
        {
          title: "Score path",
          body: result.scoring_summary.override_applied
            ? result.scoring_summary.override_reason
            : result.scoring_summary.consensus_floor_applied
              ? `Cross-family consensus (${result.scoring_summary.consensus_signal_families
                  .map(formatFamily)
                  .join(" + ")}) raised the backbone score from ${scoreToPercent(
                  result.scoring_summary.weighted_score
                )}% to ${scoreToPercent(result.scoring_summary.final_score)}%.`
              : `Backbone ensemble score settled at ${scoreToPercent(
                  result.scoring_summary.weighted_score
                )}% before final tiering.`,
          tone: "default" as const,
        },
        {
          title: "Run metadata",
          body: `${result.scoring_summary.method} · ${result.processing_time_ms}ms · ${result.layer_results.length} layers · ${result.scoring_summary.scoring_version}`,
          tone: "default" as const,
        },
        {
          title: "Scoring notes",
          body:
            result.scoring_summary.scoring_notes.length > 0
              ? result.scoring_summary.scoring_notes.join(" ")
              : "No extra scoring caveats were emitted for this run.",
          tone: result.scoring_summary.scoring_notes.length > 0 ? ("warning" as const) : ("default" as const),
        },
      ]
    : [];

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-[1600px] flex-col px-4 pb-8 pt-6 md:px-6 xl:px-8">
      <header className="section-enter mb-6 flex flex-col gap-5 rounded-[30px] panel-surface px-5 py-5 md:px-6 xl:flex-row xl:items-end xl:justify-between">
        <div className="max-w-3xl">
          <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-[#cfcfcf]">
            <ShieldAlert className="h-3.5 w-3.5" />
            Forensic Review Workspace
          </div>
          <h1 className="mt-4 text-3xl font-semibold tracking-[-0.04em] text-white md:text-5xl">
            AI Fraud Detector
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-[#a0a0a0] md:text-base">
            Review the source image on the left, inspect the grouped 21-layer evidence stack on the right, and keep the details without the long-scroll report feel.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-3 xl:min-w-[420px] xl:max-w-[520px] xl:flex-1">
          <div className="rounded-[24px] panel-muted px-4 py-3">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
              <Layers3 className="h-3.5 w-3.5" />
              Evidence layout
            </div>
            <p className="mt-2 text-sm leading-6 text-[#d8d8d8]">
              Split-screen source preview with grouped layer review.
            </p>
          </div>
          <div className="rounded-[24px] panel-muted px-4 py-3">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
              <Workflow className="h-3.5 w-3.5" />
              Same analysis
            </div>
            <p className="mt-2 text-sm leading-6 text-[#d8d8d8]">
              Existing scoring, conflicts, heatmaps, and notes stay intact.
            </p>
          </div>
          <div className="rounded-[24px] panel-muted px-4 py-3">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
              <Sparkles className="h-3.5 w-3.5" />
              Preview fallback
            </div>
            <p className="mt-2 text-sm leading-6 text-[#d8d8d8]">
              HEIC and HEIF still analyze even if the browser cannot render a preview.
            </p>
          </div>
        </div>
      </header>

      {error && (
        <div className="section-enter mb-6 rounded-[24px] border border-red-900/50 bg-red-950/30 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <section className="grid flex-1 gap-6 xl:grid-cols-[400px_minmax(0,1fr)] xl:items-start 2xl:grid-cols-[420px_minmax(0,1fr)]">
        <aside className="section-enter flex flex-col gap-4 xl:sticky xl:top-6 xl:max-h-[calc(100vh-3rem)] xl:overflow-y-auto xl:pr-1">
          <ImageUpload
            onFileSelect={handleFileSelect}
            isAnalyzing={isAnalyzing}
            previewUrl={previewUrl}
            selectedFile={selectedFile}
          />

          <div className="grid shrink-0 gap-4 xl:grid-rows-[auto_auto_1fr]">
            <div
              className={cn(
                "rounded-[28px] panel-surface px-5 py-5",
                result ? riskBg(result.risk_tier) : "border-white/10"
              )}
            >
              {result ? (
                <div className="grid gap-5 sm:grid-cols-[minmax(0,1fr)_132px] sm:items-center xl:grid-cols-1">
                  <div className="min-w-0">
                    <div className="grid gap-3">
                      <h2 className="max-w-full break-words text-xl font-semibold tracking-[-0.03em] text-white [overflow-wrap:anywhere]">
                        {result.filename}
                      </h2>
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={cn(
                            "rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em]",
                            result.risk_tier === "high"
                              ? "border-red-500/30 bg-red-500/10 text-red-300"
                              : result.risk_tier === "medium"
                                ? "border-amber-500/30 bg-amber-500/10 text-amber-300"
                                : "border-green-500/30 bg-green-500/10 text-green-300"
                          )}
                        >
                          {result.risk_tier} risk
                        </span>
                      </div>
                    </div>
                    <p className="mt-3 break-words text-sm leading-6 text-[#a9a9a9] [overflow-wrap:anywhere]">
                      Keep the source frame locked in view while you audit the strongest signals, conflicts, and layer-specific evidence.
                    </p>
                    <div className="mt-4 grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
                      <div className="rounded-[20px] panel-inset px-4 py-3">
                        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
                          <Clock3 className="h-3.5 w-3.5" />
                          Processing
                        </div>
                        <div className="mt-2 text-lg font-semibold text-white">
                          {result.processing_time_ms}ms
                        </div>
                      </div>
                      <div className="rounded-[20px] panel-inset px-4 py-3">
                        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
                          <Layers3 className="h-3.5 w-3.5" />
                          Layers
                        </div>
                        <div className="mt-2 text-lg font-semibold text-white">
                          {result.layer_results.length}
                        </div>
                      </div>
                      <div className="rounded-[20px] panel-inset px-4 py-3">
                        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
                          <Fingerprint className="h-3.5 w-3.5" />
                          Hash matches
                        </div>
                        <div className="mt-2 text-lg font-semibold text-white">
                          {result.hash_matches.length}
                        </div>
                      </div>
                    </div>
                  </div>
                  <RiskGauge score={result.risk_score} tier={result.risk_tier} size={124} />
                </div>
              ) : (
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
                    Verdict panel
                  </div>
                  <h2 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-white">
                    Upload a source image to start
                  </h2>
                  <p className="mt-3 text-sm leading-6 text-[#a9a9a9]">
                    Once a file is analyzed, the left rail will hold the source preview and verdict while the right pane becomes a dense evidence workspace.
                  </p>
                </div>
              )}
            </div>

            <div className="rounded-[28px] panel-surface px-5 py-5">
              <button
                onClick={() => setShowContext((current) => !current)}
                className="flex w-full items-center justify-between gap-3 text-left"
              >
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
                    Claim context
                  </div>
                  <h3 className="mt-1 text-base font-semibold text-white">
                    Optional fraud signals
                  </h3>
                </div>
                <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs font-medium text-[#c8c8c8]">
                  {showContext ? "Hide" : "Show"}
                </span>
              </button>

              {showContext ? (
                <div className="mt-4 grid gap-3">
                  <input
                    type="text"
                    placeholder="Account ID"
                    value={accountId}
                    onChange={(event) => setAccountId(event.target.value)}
                    className="rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white outline-none transition focus:border-white/20 focus:bg-black/30"
                  />
                  <input
                    type="text"
                    placeholder="Device Fingerprint"
                    value={deviceFp}
                    onChange={(event) => setDeviceFp(event.target.value)}
                    className="rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white outline-none transition focus:border-white/20 focus:bg-black/30"
                  />
                  <input
                    type="number"
                    placeholder="Order Value ($)"
                    value={orderValue}
                    onChange={(event) => setOrderValue(event.target.value)}
                    className="rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white outline-none transition focus:border-white/20 focus:bg-black/30"
                  />
                </div>
              ) : (
                <p className="mt-3 text-sm leading-6 text-[#9b9b9b]">
                  Add claim, device, or order context when you want behavioral signals to influence the final run.
                </p>
              )}
            </div>

            {!result && (
              <div className="rounded-[28px] panel-surface px-5 py-5">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
                  What changes here
                </div>
                <div className="mt-4 grid gap-3">
                  <div className="rounded-[22px] panel-inset px-4 py-4">
                    <div className="text-sm font-semibold text-white">Image-first review</div>
                    <p className="mt-2 text-sm leading-6 text-[#a3a3a3]">
                      The source image stays pinned on the left instead of disappearing after upload.
                    </p>
                  </div>
                  <div className="rounded-[22px] panel-inset px-4 py-4">
                    <div className="text-sm font-semibold text-white">Layer master-detail</div>
                    <p className="mt-2 text-sm leading-6 text-[#a3a3a3]">
                      Browse grouped layers quickly, then inspect one evidence stream at a time without opening a long stack of cards.
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </aside>

        <section className="section-enter rounded-[30px] panel-surface px-4 py-4 md:px-5 md:py-5 xl:h-[calc(100vh-10rem)] xl:min-h-[680px] xl:overflow-hidden">
          {result ? (
            <div className="flex h-full flex-col gap-4">
              <div className="grid gap-4 lg:grid-cols-3">
                {overviewCards.map((card) => (
                  <div
                    key={card.title}
                    className={cn(
                      "rounded-[24px] px-4 py-4",
                      card.tone === "warning"
                        ? "border border-amber-500/20 bg-amber-500/[0.07]"
                        : "panel-muted"
                    )}
                  >
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
                      {card.title}
                    </div>
                    <p className="mt-3 break-words text-sm leading-6 text-[#d7d7d7] [overflow-wrap:anywhere]">
                      {card.body}
                    </p>
                  </div>
                ))}
              </div>

              {result.scoring_summary.conflicting_signals.length > 0 && (
                <div className="rounded-[24px] border border-amber-500/20 bg-amber-500/[0.07] px-4 py-4">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-200/70">
                    Conflicting signals
                  </div>
                  <ul className="mt-3 grid gap-2 text-sm leading-6 text-amber-50/90 md:grid-cols-2">
                    {result.scoring_summary.conflicting_signals.map((signal, index) => (
                      <li key={`${signal}-${index}`} className="rounded-2xl border border-amber-500/10 bg-black/10 px-3 py-2 break-words [overflow-wrap:anywhere]">
                        {signal}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {result.hash_matches.length > 0 && (
                <div className="rounded-[24px] border border-red-900/40 bg-red-950/20 px-4 py-4">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-red-200/70">
                    Duplicate image matches
                  </div>
                  <ul className="mt-3 grid gap-2 text-sm leading-6 text-red-100 md:grid-cols-2">
                    {result.hash_matches.map((match, index) => (
                      <li
                        key={`${match.matched_claim_id}-${match.hash_type}-${index}`}
                        className="rounded-2xl border border-red-500/10 bg-black/10 px-3 py-2 break-words [overflow-wrap:anywhere]"
                      >
                        Claim #{match.matched_claim_id} · {match.hash_type} distance {match.hamming_distance}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[300px_minmax(0,1fr)] 2xl:grid-cols-[320px_minmax(0,1fr)]">
                <div className="flex min-h-[320px] flex-col rounded-[28px] panel-muted p-3 xl:min-h-0">
                  <div className="flex items-center justify-between gap-3 px-2 pb-3 pt-1">
                    <div>
                      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
                        Layer explorer
                      </div>
                      <h3 className="mt-1 text-base font-semibold text-white">
                        Evidence groups
                      </h3>
                    </div>
                    <span className="rounded-full border border-white/10 bg-black/10 px-3 py-1 text-xs text-[#bcbcbc]">
                      {result.layer_results.length} total
                    </span>
                  </div>

                  <div className="flex flex-wrap gap-2 px-2 pb-3">
                    {layerSections.map((section) => {
                      const isActive = selectedGroup === section.key;

                      return (
                        <button
                          key={section.key}
                          onClick={() => setSelectedGroup(section.key)}
                          disabled={section.layers.length === 0}
                          className={cn(
                            "rounded-full border px-3 py-2 text-left transition",
                            isActive
                              ? "border-white/20 bg-white/[0.08] text-white"
                              : "border-white/10 bg-black/10 text-[#9a9a9a] hover:border-white/20 hover:text-white",
                            section.layers.length === 0 && "cursor-not-allowed opacity-40"
                          )}
                        >
                          <div className="text-[11px] font-semibold uppercase tracking-[0.18em]">
                            {section.title}
                          </div>
                          <div className="mt-1 text-xs text-[#b6b6b6]">
                            {section.layers.length} · {section.subtitle}
                          </div>
                        </button>
                      );
                    })}
                  </div>

                  <div className="min-h-0 space-y-3 overflow-y-auto px-2 pb-2 pr-1">
                    {activeLayers.length > 0 ? (
                      activeLayers.map((layer) => (
                        <LayerListItem
                          key={layer.layer}
                          result={layer}
                          isActive={layer.layer === selectedLayerResult?.layer}
                          onSelect={() => setSelectedLayer(layer.layer)}
                        />
                      ))
                    ) : (
                      <div className="rounded-[24px] border border-white/10 bg-black/10 px-4 py-4 text-sm leading-6 text-[#989898]">
                        No layers are available in this group for the current run.
                      </div>
                    )}
                  </div>
                </div>

                <LayerDetailPanel
                  result={selectedLayerResult}
                  elaHeatmap={
                    selectedLayerResult?.layer === "ela"
                      ? result.ela_heatmap_b64 ?? undefined
                      : undefined
                  }
                  truforHeatmap={
                    selectedLayerResult?.layer === "trufor"
                      ? result.trufor_heatmap_b64 ?? undefined
                      : undefined
                  }
                  geminiReasoning={
                    selectedLayerResult?.layer === "gemini"
                      ? result.gemini_reasoning ?? undefined
                      : undefined
                  }
                />
              </div>
            </div>
          ) : (
            <div className="grid h-full gap-4 xl:grid-rows-[auto_minmax(0,1fr)]">
              <div className="grid gap-4 md:grid-cols-3">
                <div className="rounded-[24px] panel-muted px-4 py-4">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
                    Source panel
                  </div>
                  <p className="mt-3 text-sm leading-6 text-[#d7d7d7]">
                    The uploaded image remains visible throughout the review so you can compare it directly against downstream evidence.
                  </p>
                </div>
                <div className="rounded-[24px] panel-muted px-4 py-4">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
                    Overview cards
                  </div>
                  <p className="mt-3 text-sm leading-6 text-[#d7d7d7]">
                    Score path, metadata, notes, and conflicts move into short dense surfaces instead of a long narrative strip.
                  </p>
                </div>
                <div className="rounded-[24px] panel-muted px-4 py-4">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
                    Layer details
                  </div>
                  <p className="mt-3 text-sm leading-6 text-[#d7d7d7]">
                    Browse grouped layers on the left and inspect one detailed evidence stream at a time on the right.
                  </p>
                </div>
              </div>

              <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
                <div className="rounded-[28px] panel-muted p-4">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
                    Evidence groups
                  </div>
                  <div className="mt-4 space-y-3">
                    {[
                      { title: "Core", description: "Primary scoring backbone layers" },
                      { title: "Supporting", description: "Context and corroborating signals" },
                      { title: "Other", description: "Additional forensic traces and checks" },
                    ].map((item) => (
                      <div key={item.title} className="rounded-[22px] panel-inset px-4 py-4">
                        <div className="text-sm font-semibold text-white">{item.title}</div>
                        <p className="mt-2 text-sm leading-6 text-[#9d9d9d]">
                          {item.description}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-[28px] panel-muted px-5 py-5">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7f7f7f]">
                    Ready for review
                  </div>
                  <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-white">
                    Upload an image to populate the analyst workspace.
                  </h2>
                  <div className="mt-5 grid gap-4 md:grid-cols-2">
                    <div className="rounded-[24px] panel-inset px-4 py-4">
                      <div className="text-sm font-semibold text-white">Same color system</div>
                      <p className="mt-2 text-sm leading-6 text-[#9d9d9d]">
                        Dark neutral surfaces stay in place; risk colors remain reserved for low, medium, and high severity.
                      </p>
                    </div>
                    <div className="rounded-[24px] panel-inset px-4 py-4">
                      <div className="text-sm font-semibold text-white">HEIC fallback</div>
                      <p className="mt-2 text-sm leading-6 text-[#9d9d9d]">
                        If the browser cannot render a HEIC preview, the file still analyzes and the UI falls back to file metadata.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>
      </section>

      <footer className="mt-6 text-center text-xs leading-6 text-[#6d6d6d]">
        HackyIndy 2026 · Grouped evidence model across the core scoring backbone, supporting score layers, and other forensic checks.
      </footer>
    </main>
  );
}
