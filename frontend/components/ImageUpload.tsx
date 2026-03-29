"use client";

import { useCallback, useEffect, useState } from "react";
import { FileImage, ImagePlus, LoaderCircle, RefreshCcw } from "lucide-react";
import { useDropzone } from "react-dropzone";
import { cn } from "@/lib/utils";

export interface SelectedFileMeta {
  name: string;
  type: string;
  size: number;
}

interface ImageUploadProps {
  onFileSelect: (file: File) => void;
  isAnalyzing: boolean;
  previewUrl: string | null;
  selectedFile: SelectedFileMeta | null;
}

function formatFileSize(size: number) {
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }

  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileExtension(fileName: string) {
  const parts = fileName.split(".");
  return parts.length > 1 ? parts[parts.length - 1].toUpperCase() : "FILE";
}

export default function ImageUpload({
  onFileSelect,
  isAnalyzing,
  previewUrl,
  selectedFile,
}: ImageUploadProps) {
  const [canRenderPreview, setCanRenderPreview] = useState(Boolean(previewUrl));

  useEffect(() => {
    setCanRenderPreview(Boolean(previewUrl));
  }, [previewUrl]);

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      const file = acceptedFiles[0];
      if (!file) {
        return;
      }

      onFileSelect(file);
    },
    [onFileSelect]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "image/*": [
        ".jpeg",
        ".jpg",
        ".png",
        ".webp",
        ".heic",
        ".heif",
        ".tiff",
        ".tif",
        ".bmp",
        ".avif",
      ],
    },
    maxFiles: 1,
    disabled: isAnalyzing,
  });

  const footerNote = selectedFile
    ? `${getFileExtension(selectedFile.name)} · ${formatFileSize(selectedFile.size)}`
    : "JPEG, PNG, WebP, HEIC, TIFF, AVIF, BMP up to 20MB";

  return (
    <div className="accent-orbit ambient-glow rounded-[30px] panel-surface p-4 md:p-5 xl:shrink-0">
      <div
        {...getRootProps()}
        className={cn(
          "group flex h-full min-h-[320px] cursor-pointer flex-col rounded-[26px] border border-dashed border-white/20 bg-white/[0.03] p-4 transition duration-300 md:min-h-[360px]",
          isDragActive && "border-brand-300/80 bg-brand-400/[0.10] shadow-[0_0_0_1px_rgba(241,181,181,0.4),0_0_28px_rgba(241,181,181,0.24)]",
          !isAnalyzing && "hover:border-brand-300/45 hover:bg-white/[0.05]",
          isAnalyzing && "cursor-progress"
        )}
      >
        <input {...getInputProps()} />

        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-xs font-medium text-[var(--text-muted-strong)]">Your image</div>
            <h2 className="mt-1 text-lg font-semibold tracking-[-0.03em] text-white">
              {selectedFile ? "Preview for review" : "Drop or choose a file"}
            </h2>
          </div>
          <div className="rounded-full border border-brand-400/25 bg-brand-400/10 px-3 py-1 text-xs font-medium text-[#d6f3ff]">
            {selectedFile ? "Replace" : "Upload"}
          </div>
        </div>

        <div className="relative mt-4 flex min-h-[240px] flex-1 items-center justify-center overflow-hidden rounded-[24px] border border-white/20 bg-[radial-gradient(circle_at_top_left,_rgba(241,181,181,0.24),_transparent_55%),radial-gradient(circle_at_top_right,_rgba(168,183,174,0.24),_transparent_50%),radial-gradient(circle_at_72%_26%,_rgba(255,237,220,0.24),_transparent_46%),radial-gradient(circle_at_top,_rgba(255,255,255,0.12),_transparent_55%),linear-gradient(180deg,rgba(255,255,255,0.06),rgba(0,0,0,0.15))] p-4 md:min-h-[300px]">
          {previewUrl && selectedFile ? (
            canRenderPreview ? (
              <img
                src={previewUrl}
                alt={selectedFile.name}
                className="h-full max-h-[360px] w-full rounded-[20px] object-contain md:max-h-[420px]"
                onError={() => setCanRenderPreview(false)}
              />
            ) : (
              <div className="flex h-full w-full max-w-md flex-col items-center justify-center rounded-[22px] border border-white/10 bg-black/20 px-6 py-8 text-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-white/[0.05] text-white">
                  <FileImage className="h-8 w-8" />
                </div>
                <div className="mt-5 text-sm font-semibold uppercase tracking-[0.2em] text-[#d0d0d0]">
                  {getFileExtension(selectedFile.name)} preview unavailable
                </div>
                <p className="mt-3 text-sm leading-6 text-[#a5a5a5]">
                  This browser accepted the file but could not render a local preview. Analysis still works for HEIC and HEIF uploads.
                </p>
                <div className="mt-5 rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs text-[#d8d8d8]">
                  {selectedFile.name}
                </div>
              </div>
            )
          ) : (
            <div className="flex max-w-sm flex-col items-center text-center">
              <div className="flex h-20 w-20 items-center justify-center rounded-[26px] border border-white/10 bg-white/[0.04] text-white transition duration-300 group-hover:scale-[1.02] group-hover:bg-white/[0.06]">
                <ImagePlus className="h-9 w-9" />
              </div>
              <p className="mt-6 text-lg font-semibold tracking-[-0.03em] text-white">
                {isDragActive ? "Release to start" : "Drop an image to screen it"}
              </p>
              <p className="mt-3 text-sm leading-6 text-[#a0a0a0]">
                We’ll run consistency and risk checks. HEIC/HEIF are supported even when your browser can’t preview them.
              </p>
            </div>
          )}

          {isAnalyzing && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/60 backdrop-blur-sm">
              <div className="flex max-w-xs flex-col items-center gap-4 rounded-[24px] border border-white/10 bg-black/40 px-6 py-6 text-center">
                <LoaderCircle className="h-8 w-8 animate-spin text-white" aria-hidden />
                <div>
                  <div className="text-sm font-semibold text-white">Analyzing your image…</div>
                  <p className="mt-2 text-xs leading-5 text-[#c0c0c0]">
                    Running pattern, file, and model-assisted checks. This usually finishes quickly.
                  </p>
                </div>
                <div
                  className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.08]"
                  role="progressbar"
                  aria-label="Analysis in progress"
                >
                  <div className="h-full w-3/5 animate-pulse rounded-full bg-white/40" />
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-xs text-[#9a9a9a]">
          <span className="min-w-0 flex-1 break-words">{footerNote}</span>
          {selectedFile ? (
            <span className="inline-flex shrink-0 items-center gap-2 rounded-full border border-white/10 bg-black/10 px-3 py-1 text-[#d8d8d8]">
              <RefreshCcw className="h-3.5 w-3.5" />
              Click or drop to replace
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
}
