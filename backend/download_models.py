#!/usr/bin/env python3
"""Prefetch model weights/caches for production deployments.

This script is intended for servers (e.g., Vultr) where you want to download
all optional model assets once (during build/deploy) instead of on first request.

What it can warm:
- TruFor weights (download + extract to backend/models/trufor/trufor.pth.tar)
- Optional probe/weights files stored in backend/models/* (URLs provided via env)
- HuggingFace caches used by some detectors (CLIP backbone, Moondream2 fallback VLM)

Notes:
- Gemini itself is an API call; there are no weights to download locally.
- Some models (CLIP backbone, Moondream2) download into the HuggingFace cache
  under the runtime user's home directory.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
import zipfile
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("download_models")


def _download_trufor() -> Path:
    from app.core.model_manager import download_weights, model_path

    url = "https://www.grip.unina.it/download/prog/TruFor/TruFor_weights.zip"
    zip_path = download_weights(url, "trufor", "TruFor_weights.zip")

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(td_path)

        candidates = list(td_path.rglob("*.pth.tar"))
        if not candidates:
            raise RuntimeError(f"No .pth.tar found inside {zip_path}")

        # Prefer exact expected filename if present.
        picked = None
        for c in candidates:
            if c.name == "trufor.pth.tar":
                picked = c
                break
        if picked is None:
            picked = candidates[0]

        dest = model_path("trufor", "trufor.pth.tar")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(picked.read_bytes())
        logger.info("TruFor weights ready: %s", dest)
        return dest


def _download_optional_file(env_var: str, subdir: str, filename: str, sha_env: str | None = None) -> Path | None:
    """Download a single weights file to backend/models from URL in env."""
    url = os.getenv(env_var, "").strip()
    if not url:
        logger.warning("%s not set; skipping %s/%s", env_var, subdir, filename)
        return None

    sha = os.getenv(sha_env, "").strip() if sha_env else None
    if sha == "":
        sha = None

    from app.core.model_manager import download_weights

    path = download_weights(url, subdir, filename, sha256=sha)
    logger.info("Downloaded %s → %s", filename, path)
    return path


def _warm_clip_backbone() -> None:
    """Trigger HuggingFace cache download for CLIP ViT-L/14 backbone."""
    import open_clip
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("Warming CLIP backbone (device=%s)...", device)
    model, _, _ = open_clip.create_model_and_transforms("ViT-L-14", pretrained="openai")
    model.to(device).eval()
    logger.info("CLIP backbone warm OK")


def _warm_moondream2() -> None:
    """Trigger HuggingFace cache download for Moondream2 safetensors."""
    from huggingface_hub import hf_hub_download

    repo_id = "vikhyatk/moondream2"
    logger.info("Warming Moondream2 safetensors...")
    hf_hub_download(repo_id, "model.safetensors")
    logger.info("Moondream2 warm OK")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download/warm all backend model assets.")
    parser.add_argument("--trufor", action="store_true", help="Download TruFor weights into backend/models.")
    parser.add_argument("--clip", action="store_true", help="Warm CLIP backbone HF cache (large).")
    parser.add_argument("--moondream2", action="store_true", help="Warm Moondream2 HF cache.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run everything: TruFor + optional weights + CLIP + Moondream2.",
    )
    args = parser.parse_args()

    run_all = args.all
    did_any = False

    try:
        if run_all or args.trufor:
            did_any = True
            _download_trufor()

        # Optional probe/weights stored under backend/models/*
        # Provide URLs in the environment for your deployment:
        # - CLIP_PROBE_URL for backend/models/clip_universalfakedetect/fc_weights.pth
        # - CNNDETECTION_WEIGHTS_URL for backend/models/cnndetection/blur_jpg_prob0.5.pth
        _download_optional_file(
            "CLIP_PROBE_URL",
            "clip_universalfakedetect",
            "fc_weights.pth",
            sha_env="CLIP_PROBE_SHA256",
        )
        _download_optional_file(
            "CNNDETECTION_WEIGHTS_URL",
            "cnndetection",
            "blur_jpg_prob0.5.pth",
            sha_env="CNNDETECTION_WEIGHTS_SHA256",
        )

        if run_all or args.clip:
            did_any = True
            _warm_clip_backbone()

        if run_all or args.moondream2:
            did_any = True
            _warm_moondream2()

    except Exception as exc:
        logger.error("Download/warm failed: %s", exc, exc_info=True)
        return 1

    if not did_any and not (os.getenv("CLIP_PROBE_URL") or os.getenv("CNNDETECTION_WEIGHTS_URL")):
        logger.warning("Nothing selected. Try: python download_models.py --all")
        return 2

    logger.info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

