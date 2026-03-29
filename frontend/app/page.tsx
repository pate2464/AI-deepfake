"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import AppHeader from "@/components/AppHeader";
import EvidenceSummaryAccordions from "@/components/EvidenceSummaryAccordions";
import ImageUpload, { type SelectedFileMeta } from "@/components/ImageUpload";
import LayerDetailPanel from "@/components/LayerDetailPanel";
import LayerListItem from "@/components/LayerListItem";
import NextSteps from "@/components/NextSteps";
import ReasonList from "@/components/ReasonList";
import RunMetaChips from "@/components/RunMetaChips";
import TechnicalAnalysisSection from "@/components/TechnicalAnalysisSection";
import TrustFooter from "@/components/TrustFooter";
import VerdictHero from "@/components/VerdictHero";
import { analyzeImage, type AnalysisResponse } from "@/lib/api";
import { GROUP_SECTION } from "@/lib/copy";
import { buildTopReasons } from "@/lib/verdict";
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
  const [technicalOpen, setTechnicalOpen] = useState(false);

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
      setTechnicalOpen(false);

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

  const scrollToUpload = useCallback(() => {
    document.getElementById("image-upload-anchor")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const openTechnical = useCallback(() => {
    setTechnicalOpen(true);
    requestAnimationFrame(() => {
      document.getElementById("technical-analysis-toggle")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }, []);

  const groupedLayers = useMemo(() => {
    if (!result) return EMPTY_LAYER_GROUPS;
    const sortFn = (a: AnalysisResponse["layer_results"][0], b: AnalysisResponse["layer_results"][0]) =>
      (b.weighted_contribution ?? b.score) - (a.weighted_contribution ?? a.score) || b.score - a.score;

    return {
      core: [...result.layer_results].filter((l) => l.score_role === "core-score").sort(sortFn),
      supporting: [...result.layer_results].filter((l) => l.score_role === "supporting-score").sort(sortFn),
      other: [...result.layer_results].filter((l) => l.score_role === "other-layer").sort(sortFn),
    };
  }, [result]);

  const layerSections = useMemo(
    () =>
      [
        { key: "core" as const, ...GROUP_SECTION.core, layers: groupedLayers.core },
        { key: "supporting" as const, ...GROUP_SECTION.supporting, layers: groupedLayers.supporting },
        { key: "other" as const, ...GROUP_SECTION.other, layers: groupedLayers.other },
      ] as const,
    [groupedLayers]
  );

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
  }, [result, layerSections]);

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
          title: "How the score was built",
          body: result.scoring_summary.override_applied
            ? result.scoring_summary.override_reason ?? ""
            : result.scoring_summary.consensus_floor_applied
              ? `Multiple signal families (${result.scoring_summary.consensus_signal_families
                  .map(formatFamily)
                  .join(" + ")}) raised the blended score from ${scoreToPercent(
                  result.scoring_summary.weighted_score
                )}% to ${scoreToPercent(result.scoring_summary.final_score)}%.`
              : `Blended score before tiering: about ${scoreToPercent(result.scoring_summary.weighted_score)}%.`,
          tone: "default" as const,
        },
        {
          title: "About this analysis",
          body: `${result.scoring_summary.method} · ${result.processing_time_ms} ms · ${result.layer_results.length} checks · ${result.scoring_summary.scoring_version}`,
          tone: "default" as const,
        },
        {
          title: "Notes from scoring",
          body:
            result.scoring_summary.scoring_notes.length > 0
              ? result.scoring_summary.scoring_notes.join(" ")
              : "No extra caveats were recorded for this run.",
          tone: result.scoring_summary.scoring_notes.length > 0 ? ("warning" as const) : ("default" as const),
        },
      ]
    : [];

  const topReasons = result ? buildTopReasons(result) : [];

  return (
    <main className="mx-auto relative flex min-h-screen w-full max-w-[1860px] flex-col px-4 pb-10 pt-6 md:px-8 2xl:px-10">
      <div className="pointer-events-none absolute inset-x-16 top-0 -z-10 h-64 rounded-full bg-[radial-gradient(circle,rgba(169,195,182,0.3),transparent_70%)] blur-3xl" />
      <div className="pointer-events-none absolute right-16 top-16 -z-10 h-52 w-52 rounded-full bg-[radial-gradient(circle,rgba(143,184,202,0.24),transparent_72%)] blur-3xl" />
      <AppHeader />

      {error && (
        <div className="section-enter mb-6 rounded-[22px] border border-[rgba(145,172,154,0.24)] bg-[rgba(169,195,182,0.24)] px-4 py-3 text-sm text-[var(--text-primary)]">
          {error}
        </div>
      )}

      <div className="grid flex-1 gap-7 xl:grid-cols-[minmax(360px,460px)_minmax(0,1fr)] xl:items-start">
        <aside className="section-enter flex flex-col gap-5 xl:sticky xl:top-6 xl:max-h-[calc(100vh-2rem)] xl:overflow-y-auto xl:pr-2">
          <div id="image-upload-anchor">
            <ImageUpload
              onFileSelect={handleFileSelect}
              isAnalyzing={isAnalyzing}
              previewUrl={previewUrl}
              selectedFile={selectedFile}
            />
          </div>

          <div
            className={cn(
              "glass-highlight rounded-[26px] border px-5 py-5",
              result ? riskBg(result.risk_tier) : "panel-surface border-[rgba(73,118,159,0.2)]"
            )}
          >
            {result ? (
              <div className="space-y-3">
                <h2 className="text-sm font-medium text-[var(--text-secondary)]">Current file</h2>
                <p className="break-words text-base font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
                  {result.filename}
                </p>
                <div className="flex flex-wrap gap-2">
                  <span
                    className={cn(
                      "rounded-full border px-3 py-1 text-xs font-semibold",
                      result.risk_tier === "high"
                        ? "border-[#91AC9A] bg-[#A9C3B6]/38 text-[var(--text-primary)]"
                        : result.risk_tier === "medium"
                          ? "border-[#A6C3CE] bg-[#B7D1D3]/32 text-[var(--text-primary)]"
                          : "border-[#8FB8CA] bg-[#CEDFDF]/68 text-[var(--text-primary)]"
                    )}
                  >
                    {result.risk_tier === "high"
                      ? "Elevated concern"
                      : result.risk_tier === "medium"
                        ? "Moderate concern"
                        : "Lower concern"}
                  </span>
                </div>
                <RunMetaChips result={result} />
              </div>
            ) : (
              <div>
                <h2 className="text-lg font-semibold text-[var(--text-primary)]">Your image stays visible</h2>
                <p className="mt-2 text-sm leading-6 text-[var(--text-soft)]">
                  Upload a file to see a plain-language summary first. Detailed checks, heatmaps, and metadata are
                  one click away when you need them.
                </p>
              </div>
            )}
          </div>

          <div className="glass-highlight rounded-[26px] panel-surface px-5 py-5">
            <button
              type="button"
              onClick={() => setShowContext((c) => !c)}
              className="flex w-full items-center justify-between gap-3 text-left"
            >
              <div>
                <p className="text-xs font-medium text-[var(--text-muted-strong)]">Optional context</p>
                <h3 className="mt-1 text-base font-semibold text-[var(--text-primary)]">Review context (claims / orders)</h3>
              </div>
              <span className="soft-chip rounded-full px-3 py-1 text-xs font-medium">
                {showContext ? "Hide" : "Show"}
              </span>
            </button>

            {showContext ? (
              <div className="mt-4 grid gap-3">
                <input
                  type="text"
                  placeholder="Account ID"
                  value={accountId}
                  onChange={(e) => setAccountId(e.target.value)}
                  className="field-input rounded-2xl px-4 py-3 text-sm outline-none transition"
                />
                <input
                  type="text"
                  placeholder="Device fingerprint"
                  value={deviceFp}
                  onChange={(e) => setDeviceFp(e.target.value)}
                  className="field-input rounded-2xl px-4 py-3 text-sm outline-none transition"
                />
                <input
                  type="number"
                  placeholder="Order value (USD)"
                  value={orderValue}
                  onChange={(e) => setOrderValue(e.target.value)}
                  className="field-input rounded-2xl px-4 py-3 text-sm outline-none transition"
                />
              </div>
            ) : (
              <p className="mt-3 text-sm leading-6 text-[var(--text-soft)]">
                Add account, device, or order hints when you want behavioral scoring to influence the run.
              </p>
            )}
          </div>
        </aside>

        <section className="section-enter glass-highlight ambient-glow min-h-[540px] rounded-[28px] panel-surface px-5 py-6 md:px-7 md:py-7">
          {result ? (
            <div className="flex flex-col gap-6">
              <VerdictHero result={result} />

              <ReasonList reasons={topReasons} onViewTechnical={openTechnical} />

              {result.scoring_summary.conflicting_signals.length > 0 && (
                <div className="rounded-[22px] border border-[rgba(145,172,154,0.22)] bg-[rgba(169,195,182,0.18)] px-4 py-4">
                  <p className="text-xs font-medium text-[var(--text-secondary)]">Mixed signals</p>
                  <ul className="mt-3 grid gap-2 text-sm leading-6 text-[var(--text-primary)] md:grid-cols-2">
                    {result.scoring_summary.conflicting_signals.map((signal, index) => (
                      <li
                        key={`${signal}-${index}`}
                        className="rounded-2xl border border-[rgba(145,172,154,0.18)] bg-[rgba(245,249,247,0.76)] px-3 py-2 break-words [overflow-wrap:anywhere]"
                      >
                        {signal}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {result.hash_matches.length > 0 && (
                <div className="rounded-[22px] border border-[rgba(166,195,206,0.24)] bg-[rgba(143,184,202,0.18)] px-4 py-4">
                  <p className="text-xs font-medium text-[var(--text-primary)]">Possible duplicate images</p>
                  <ul className="mt-3 grid gap-2 text-sm leading-6 text-[var(--text-primary)] md:grid-cols-2">
                    {result.hash_matches.map((match, index) => (
                      <li
                        key={`${match.matched_claim_id}-${match.hash_type}-${index}`}
                        className="rounded-2xl border border-[rgba(166,195,206,0.22)] bg-[rgba(245,249,247,0.78)] px-3 py-2 break-words [overflow-wrap:anywhere]"
                      >
                        Record #{match.matched_claim_id} · {match.hash_type} · distance {match.hamming_distance}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <EvidenceSummaryAccordions grouped={groupedLayers} />

              <NextSteps onUploadAnother={scrollToUpload} />

              <TechnicalAnalysisSection
                open={technicalOpen}
                onToggle={() => setTechnicalOpen((o) => !o)}
                overviewCards={overviewCards}
              >
                <div className="grid min-h-0 gap-5 2xl:grid-cols-[minmax(360px,460px)_minmax(0,1fr)]">
                  <div className="flex max-h-[min(78vh,900px)] min-h-[380px] flex-col rounded-[24px] border border-[rgba(145,172,154,0.24)] bg-[rgba(245,249,247,0.78)] p-4">
                    <div className="flex items-center justify-between gap-3 px-2 pb-3 pt-1">
                      <div>
                        <p className="text-xs font-medium text-[var(--text-muted-strong)]">All checks</p>
                        <h3 className="mt-0.5 text-base font-semibold text-[var(--text-primary)]">By group</h3>
                      </div>
                      <span className="soft-chip rounded-full px-2.5 py-0.5 text-xs">
                        {result.layer_results.length} total
                      </span>
                    </div>

                    <div className="flex flex-wrap gap-2 px-2 pb-3">
                      {layerSections.map((section) => {
                        const isActive = selectedGroup === section.key;
                        return (
                          <button
                            key={section.key}
                            type="button"
                            onClick={() => setSelectedGroup(section.key)}
                            disabled={section.layers.length === 0}
                            className={cn(
                              "rounded-full border px-3 py-2 text-left text-sm transition",
                              isActive
                                ? "border-[rgba(145,172,154,0.34)] bg-[rgba(169,195,182,0.34)] text-[var(--text-primary)]"
                                : "border-[rgba(145,172,154,0.2)] bg-[rgba(237,244,241,0.82)] text-[var(--text-soft)] hover:border-[rgba(145,172,154,0.32)] hover:bg-[rgba(206,223,223,0.5)] hover:text-[var(--text-primary)]",
                              section.layers.length === 0 && "cursor-not-allowed opacity-40"
                            )}
                          >
                            <div className="text-xs font-medium text-[var(--text-muted-strong)]">{section.title}</div>
                            <div className="mt-0.5 text-xs text-[var(--text-muted-strong)]">{section.layers.length} checks</div>
                          </button>
                        );
                      })}
                    </div>

                    <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-1 pb-2 pr-1">
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
                        <div className="rounded-[20px] border border-[rgba(145,172,154,0.24)] bg-[rgba(237,244,241,0.8)] px-4 py-4 text-sm text-[var(--text-soft)]">
                          No checks in this group for this run.
                        </div>
                      )}
                    </div>
                  </div>

                  <LayerDetailPanel
                    result={selectedLayerResult}
                    elaHeatmap={
                      selectedLayerResult?.layer === "ela" ? result.ela_heatmap_b64 ?? undefined : undefined
                    }
                    truforHeatmap={
                      selectedLayerResult?.layer === "trufor" ? result.trufor_heatmap_b64 ?? undefined : undefined
                    }
                    geminiReasoning={
                      selectedLayerResult?.layer === "gemini" ? result.gemini_reasoning ?? undefined : undefined
                    }
                  />
                </div>
              </TechnicalAnalysisSection>
            </div>
          ) : (
            <div className="flex min-h-[420px] flex-col justify-center gap-6 py-6">
              <div className="mx-auto max-w-2xl text-center">
                <p className="text-sm font-medium text-[var(--text-muted-strong)]">Results will appear here</p>
                <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
                  Upload an image to see your screening summary
                </h2>
                <p className="mt-3 text-sm leading-7 text-[var(--text-soft)]">
                  You’ll get a plain-language verdict, a short “why,” and optional technical evidence—heatmaps,
                  metadata, and per-check scores—for teams that need depth.
                </p>
              </div>
              <div className="mx-auto grid max-w-2xl gap-3 sm:grid-cols-2">
                <div className="rounded-[22px] border border-[rgba(145,172,154,0.24)] bg-[rgba(237,244,241,0.82)] px-4 py-4 text-left text-sm leading-6 text-[var(--text-soft)]">
                  <span className="font-medium text-[var(--text-primary)]">Honest uncertainty</span>
                  <br />
                  We don’t force a fake-vs-real label. You’ll see risk, confidence, and reasons.
                </div>
                <div className="rounded-[22px] border border-[rgba(145,172,154,0.24)] bg-[rgba(237,244,241,0.82)] px-4 py-4 text-left text-sm leading-6 text-[var(--text-soft)]">
                  <span className="font-medium text-[var(--text-primary)]">HEIC-friendly</span>
                  <br />
                  If the browser can’t preview HEIC/HEIF, analysis still runs and we show file details instead.
                </div>
              </div>
            </div>
          )}
        </section>
      </div>

      <TrustFooter scoringVersion={result?.scoring_summary.scoring_version} />
    </main>
  );
}
