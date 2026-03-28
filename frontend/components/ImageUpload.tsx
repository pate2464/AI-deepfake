"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";

interface ImageUploadProps {
  onFileSelect: (file: File) => void;
  isAnalyzing: boolean;
}

export default function ImageUpload({
  onFileSelect,
  isAnalyzing,
}: ImageUploadProps) {
  const [preview, setPreview] = useState<string | null>(null);

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      const file = acceptedFiles[0];
      if (!file) return;
      setPreview(URL.createObjectURL(file));
      onFileSelect(file);
    },
    [onFileSelect]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "image/*": [".jpeg", ".jpg", ".png", ".webp", ".heic", ".heif", ".tiff", ".tif", ".bmp", ".avif"] },
    maxFiles: 1,
    disabled: isAnalyzing,
  });

  return (
    <div className="w-full">
      <div
        {...getRootProps()}
        className={`
          relative border-2 border-dashed rounded-2xl p-8
          flex flex-col items-center justify-center min-h-[300px]
          cursor-pointer transition-all duration-300
          ${isDragActive ? "border-blue-500 bg-blue-500/5" : "border-[#2a2a2a] hover:border-[#444]"}
          ${isAnalyzing ? "opacity-50 cursor-not-allowed" : ""}
        `}
      >
        <input {...getInputProps()} />

        {preview ? (
          <div className="relative">
            <img
              src={preview}
              alt="Preview"
              className="max-h-[250px] rounded-lg object-contain"
            />
            {isAnalyzing && (
              <div className="absolute inset-0 bg-black/60 rounded-lg flex items-center justify-center">
                <div className="flex flex-col items-center gap-3">
                  <div className="relative w-20 h-20">
                    <div className="absolute inset-0 rounded-full border-4 border-blue-500/30" />
                    <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-blue-500 animate-spin" />
                  </div>
                  <span className="text-sm text-blue-400 font-medium">
                    Analyzing 8 layers...
                  </span>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-4 text-[#a0a0a0]">
            <div className="text-5xl">🔍</div>
            <div className="text-center">
              <p className="text-lg font-medium text-[#ededed]">
                {isDragActive ? "Drop image here" : "Drop an image to analyze"}
              </p>
              <p className="text-sm mt-1">
                or click to browse — JPEG, PNG, WebP, HEIC, TIFF up to 20MB
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
