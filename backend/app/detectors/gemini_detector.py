"""Layer 7 — Vision-Language Model Semantic Analysis.

Uses a local GPU-accelerated vision-language model (Moondream2, 1.86B params)
for semantic forensic analysis.  Falls back to Gemini API if the local model
is unavailable.

This layer provides semantic-level reasoning that no pixel-level detector can
match — identifying physically impossible objects, AI-typical style artifacts,
uncanny-valley textures, garbled text, and contextual inconsistencies.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import torch
from PIL import Image

from app.core.config import settings
from app.core.models import LayerName, LayerResult

logger = logging.getLogger(__name__)

# ── Singleton model holder ──────────────────────────────
_model = None
_tokenizer = None
_load_attempted = False

VLM_MODEL_ID = "vikhyatk/moondream2"
VLM_MAX_DIM = 768  # Resize for speed; moondream native is 378 anyway

_REASONING_PLACEHOLDERS = {
    "one concise paragraph citing only concrete evidence",
    "one paragraph summary",
    "reasoning",
    "analysis",
    "n/a",
    "na",
    "none",
    "null",
    "...",
}

_GENERIC_ARTIFACTS = {
    "impossible anatomy",
    "broken text",
    "inconsistent reflections",
    "duplicate structures",
    "duplicated structures",
    "melted boundaries",
    "globally synthetic rendering",
    "specific issue 1",
    "specific issue 2",
}


FORENSIC_PROMPT = (
    "You are a cautious forensic image analyst deciding whether an image shows clear, high-confidence evidence of AI generation. "
    "Do not treat ordinary smartphone processing, HDR, HEIC or JPEG compression, portrait smoothing, food styling, shallow depth of field, or clean studio lighting as AI evidence by themselves. "
    "Only call the image AI-generated when you can point to concrete artifacts such as impossible anatomy, broken text, inconsistent reflections, duplicated structures, melted boundaries, or globally synthetic rendering. "
    "If the evidence is weak, mixed, or plausibly explained by a real camera pipeline, return false and use low confidence.\n\n"
    "Respond with ONLY valid JSON, no other text. Use actual values, not placeholder strings or copied instructions.\n"
    'Format: {"is_ai": <boolean>, "confidence": <0.0-1.0>, "artifacts": [<concrete evidence strings>], "reasoning": <short concrete summary string>}'
)


# ── Model loading ───────────────────────────────────────

def _load_vlm():
    """Load the Moondream2 VLM (called once, eagerly at import time).

    Uses init_empty_weights + direct-to-GPU safetensors loading to
    bypass Windows pagefile mmap limitations.  Must run before any
    concurrent model loads (CLIP, TruFor, etc.) to avoid global-state
    leaks from accelerate's init_empty_weights context manager.
    """
    global _model, _tokenizer, _load_attempted
    if _load_attempted:
        return _model, _tokenizer
    _load_attempted = True

    try:
        import gc
        import glob
        import os

        import transformers
        from safetensors.torch import load_file

        device = "cuda" if torch.cuda.is_available() else "cpu"

        logger.info("Loading local VLM: %s (device=%s)", VLM_MODEL_ID, device)

        # ── Load tokenizer ──────────────────────────────────────────
        _tokenizer = transformers.AutoTokenizer.from_pretrained(
            VLM_MODEL_ID, trust_remote_code=True,
        )

        # ── Create empty model skeleton (zero memory via meta device).
        #    SAFE here because _load_vlm() runs eagerly at import time
        #    before any concurrent threads. ──────────────────────────────
        from accelerate import init_empty_weights

        config = transformers.AutoConfig.from_pretrained(
            VLM_MODEL_ID, trust_remote_code=True,
        )
        with init_empty_weights():
            _model = transformers.AutoModelForCausalLM.from_config(
                config, trust_remote_code=True,
            )

        # Patch ONLY the HfMoondream class (not global PreTrainedModel)
        # so other models (CLIP, TruFor, etc.) are not affected.
        if not hasattr(type(_model), "all_tied_weights_keys"):
            type(_model).all_tied_weights_keys = property(lambda self: {})

        # ── Load safetensors directly to GPU (bypass pagefile) ─────
        cache_dir = os.path.expanduser(
            "~/.cache/huggingface/hub/models--vikhyatk--moondream2"
        )
        sf_files = glob.glob(
            os.path.join(cache_dir, "snapshots/*/model.safetensors")
        )
        if not sf_files:
            # Trigger a download by attempting the standard from_pretrained
            # (may fail on Windows due to pagefile, but it downloads the file)
            logger.info("Downloading %s weights...", VLM_MODEL_ID)
            from huggingface_hub import hf_hub_download

            hf_hub_download(VLM_MODEL_ID, "model.safetensors")
            sf_files = glob.glob(
                os.path.join(cache_dir, "snapshots/*/model.safetensors")
            )
            if not sf_files:
                raise FileNotFoundError("Moondream2 weights download failed")

        state_dict = load_file(sf_files[0], device=device)
        _model.load_state_dict(state_dict, strict=False, assign=True)
        _model = _model.to(device=device, dtype=torch.bfloat16)
        _model.eval()

        del state_dict
        gc.collect()
        if device == "cuda":
            torch.cuda.empty_cache()

        logger.info(
            "Local VLM loaded successfully (%s, %.1f GB VRAM)",
            VLM_MODEL_ID,
            torch.cuda.memory_allocated() / (1024**3) if device == "cuda" else 0,
        )

    except Exception as exc:
        logger.warning("Failed to load local VLM: %s", exc)
        _model = None
        _tokenizer = None

    return _model, _tokenizer


# ── Local inference ─────────────────────────────────────

def _run_local_inference(image_path: str) -> str:
    """Run Moondream2 inference — returns raw text answer."""
    model, tokenizer = _load_vlm()
    if model is None:
        raise RuntimeError("Local VLM not loaded")

    image = Image.open(image_path).convert("RGB")

    # Resize for speed (moondream resizes internally but this saves decode time)
    if max(image.size) > VLM_MAX_DIM:
        ratio = VLM_MAX_DIM / max(image.size)
        image = image.resize(
            (int(image.size[0] * ratio), int(image.size[1] * ratio)),
            Image.LANCZOS,
        )

    enc_image = model.encode_image(image)
    answer = model.answer_question(enc_image, FORENSIC_PROMPT, tokenizer)
    return answer


# ── Response parsing ────────────────────────────────────

def _normalize_reasoning(reasoning: Any) -> str | None:
    """Drop empty/template reasoning so the UI does not show fake explanation."""
    value = " ".join(str(reasoning or "").strip().split())
    if not value:
        return None
    if value.lower() in _REASONING_PLACEHOLDERS:
        return None
    if len(value) < 24:
        return None
    return value


def _normalize_artifacts(artifacts: Any) -> list[str]:
    """Keep only usable, non-template artifact strings."""
    if not isinstance(artifacts, list):
        return []

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in artifacts:
        value = " ".join(str(item).strip().split())
        if not value:
            continue
        lowered = value.lower()
        if lowered in _GENERIC_ARTIFACTS or lowered.startswith("specific issue"):
            continue
        if lowered in seen:
            continue
        cleaned.append(value)
        seen.add(lowered)
    return cleaned


def _fallback_reasoning(assessment: str, artifacts: list[str]) -> str | None:
    """Return a safe explanation only when the model produced concrete artifacts."""
    if not artifacts:
        return None
    lead = (
        "Local VLM flagged concrete artifacts"
        if assessment == "likely_ai_generated"
        else "Local VLM found limited suspicious evidence"
    )
    return f"{lead}: {'; '.join(artifacts[:3])}."

def _parse_vlm_response(text: str) -> dict[str, Any]:
    """Parse VLM JSON response with robust fallback for malformed output."""
    # 1. Try to extract JSON object
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            candidate = match.group()
            # Fix common small-model JSON issues
            candidate = candidate.replace("'", '"')
            candidate = re.sub(r",\s*}", "}", candidate)  # trailing comma
            candidate = re.sub(r",\s*]", "]", candidate)  # trailing comma in array
            parsed = json.loads(candidate)
            # Normalise the is_ai field
            is_ai = parsed.get("is_ai", parsed.get("is_ai_generated", False))
            if isinstance(is_ai, str):
                is_ai = is_ai.lower() in ("true", "yes", "1")
            artifacts = _normalize_artifacts(parsed.get("artifacts", []))
            reasoning = _normalize_reasoning(parsed.get("reasoning", text[:500]))
            return {
                "is_ai": bool(is_ai),
                "confidence": max(0.0, min(1.0, float(parsed.get("confidence", 0.0)))),
                "artifacts": artifacts,
                "reasoning": reasoning,
                "template_like_output": reasoning is None and not artifacts,
            }
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # 2. Keyword-based fallback for plain-text responses
    lower = text.lower()
    ai_kws = [
        "ai-generated", "ai generated", "artificially generated", "synthetic",
        "not a real", "not real", "fake", "deepfake", "computer-generated",
        "digitally created", "generated image", "ai image", "looks artificial",
        "ai art", "generated by", "diffusion", "midjourney", "dall-e", "stable diffusion",
    ]
    real_kws = [
        "real photo", "real photograph", "authentic", "genuine photograph",
        "taken by a camera", "natural photo", "camera photo", "looks real",
        "not ai", "real image",
    ]
    ai_hits = sum(1 for kw in ai_kws if kw in lower)
    real_hits = sum(1 for kw in real_kws if kw in lower)
    is_ai = ai_hits > real_hits
    confidence = min(0.7, 0.2 + 0.08 * abs(ai_hits - real_hits))

    return {
        "is_ai": is_ai,
        "confidence": confidence,
        "artifacts": [f"Text analysis: {ai_hits} AI indicators, {real_hits} real indicators"],
        "reasoning": _normalize_reasoning(text[:500]),
        "template_like_output": False,
    }


# ── Gemini API fallback ────────────────────────────────

GEMINI_PROMPT = """You are an expert forensic image analyst. Analyze this image for signs of AI generation.

Return ONLY valid JSON:
{
  "physical_plausibility": {"score": 0.0-1.0, "notes": "..."},
  "ai_artifacts": {"score": 0.0-1.0, "notes": "..."},
  "contextual_consistency": {"score": 0.0-1.0, "notes": "..."},
  "lighting_analysis": {"score": 0.0-1.0, "notes": "..."},
  "text_rendering": {"score": 0.0-1.0, "notes": "..."},
  "overall_assessment": "likely_real | likely_ai_generated | uncertain",
  "confidence": 0.0-1.0,
  "reasoning": "One paragraph summary"
}
Score: 0.0 = authentic, 1.0 = highly suspicious."""


async def _gemini_fallback(image_path: str) -> tuple[LayerResult, str | None]:
    """Original Gemini API path — used only if local VLM is unavailable."""
    flags: list[str] = []
    details: dict[str, Any] = {}

    api_key = settings.GEMINI_API_KEY
    if not api_key:
        return LayerResult(
            layer=LayerName.GEMINI, score=0.0, confidence=0.0,
            flags=["No API key and local VLM unavailable — layer skipped"],
        ), None

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(settings.GEMINI_MODEL)

        with open(image_path, "rb") as f:
            image_data = f.read()

        ext = image_path.rsplit(".", 1)[-1].lower()
        mime_map = {
            "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png", "webp": "image/webp",
            "heic": "image/heic", "heif": "image/heif",
            "tiff": "image/tiff", "tif": "image/tiff",
            "bmp": "image/bmp", "avif": "image/avif",
        }
        mime_type = mime_map.get(ext, "image/jpeg")

        if ext in ("heic", "heif"):
            import io
            pil_img = Image.open(image_path).convert("RGB")
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=95)
            image_data = buf.getvalue()
            mime_type = "image/jpeg"

        response = model.generate_content([
            GEMINI_PROMPT,
            {"mime_type": mime_type, "data": image_data},
        ])
        response_text = response.text.strip()
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            response_text = "\n".join(lines)

        parsed = json.loads(response_text)
        details["gemini_raw"] = parsed

        sub_scores = []
        for key in ("physical_plausibility", "ai_artifacts", "contextual_consistency",
                     "lighting_analysis", "text_rendering"):
            if key in parsed and isinstance(parsed[key], dict):
                sub_score = float(parsed[key].get("score", 0.0))
                sub_scores.append(sub_score)
                notes = parsed[key].get("notes", "")
                if sub_score >= 0.6:
                    flags.append(f"Gemini [{key}]: {notes}")

        assessment = parsed.get("overall_assessment", "uncertain")
        gemini_confidence = float(parsed.get("confidence", 0.5))
        reasoning = _normalize_reasoning(parsed.get("reasoning", ""))
        details["assessment"] = assessment
        details["source"] = "gemini_api"

        if assessment == "likely_ai_generated":
            base_score = 0.8
        elif assessment == "likely_real":
            base_score = 0.15
        else:
            base_score = 0.45

        if sub_scores:
            avg_sub = sum(sub_scores) / len(sub_scores)
            score = base_score * 0.6 + avg_sub * 0.4
        else:
            score = base_score

        score = min(1.0, max(0.0, score))
        flags.append(f"Gemini assessment: {assessment} (confidence={gemini_confidence:.2f})")

        return LayerResult(
            layer=LayerName.GEMINI, score=round(score, 4),
            confidence=round(gemini_confidence, 4), flags=flags, details=details,
        ), reasoning

    except Exception as e:
        return LayerResult(
            layer=LayerName.GEMINI, score=0.0, confidence=0.0,
            flags=[f"Gemini fallback also failed: {type(e).__name__}"],
            error=str(e),
        ), None


# ── Public entry point ──────────────────────────────────

async def analyze(image_path: str) -> tuple[LayerResult, str | None]:
    """Run semantic forensic analysis.

    Strategy:
      1. Try local VLM (Moondream2 on GPU) — fast, free, no API limits.
      2. Fall back to Gemini API if the local model cannot load.

    Returns ``(LayerResult, reasoning_text_or_None)``.
    """
    # ── Attempt local VLM ───────────────────────────────
    try:
        raw_text = await asyncio.to_thread(_run_local_inference, image_path)
        parsed = _parse_vlm_response(raw_text)

        is_ai: bool = parsed["is_ai"]
        artifacts: list = parsed.get("artifacts", [])
        reasoning = parsed.get("reasoning")
        template_like_output = bool(parsed.get("template_like_output", False))
        parsed_confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.0))))

        # Small local VLMs tend to over-describe ordinary camera artifacts.
        # Keep the confidence close to the model's self-reported certainty and
        # allow only a small corroboration bonus from multiple concrete findings.
        n_artifacts = len(artifacts)
        corroboration_bonus = min(0.10, n_artifacts * 0.02)
        if is_ai:
            vlm_confidence = min(0.85, max(0.18, parsed_confidence + corroboration_bonus))
        else:
            vlm_confidence = min(0.8, max(0.15, parsed_confidence))

        if template_like_output:
            vlm_confidence = min(vlm_confidence, 0.12)

        # Score mapping  ─  AI → high score,  Real → low score
        if is_ai:
            score = 0.45 + 0.45 * vlm_confidence
        else:
            score = 0.18 - 0.12 * vlm_confidence

        score = max(0.0, min(1.0, score))

        assessment = "likely_ai_generated" if is_ai else "likely_real"
        flags: list[str] = [
            f"Local VLM assessment: {assessment} (confidence={vlm_confidence:.2f})"
        ]
        for art in artifacts[:5]:
            flags.append(str(art)[:120])

        if template_like_output:
            flags.append("Local VLM returned template-like output; explanation was suppressed.")
        elif reasoning is None:
            reasoning = _fallback_reasoning(assessment, artifacts)

        return LayerResult(
            layer=LayerName.GEMINI,
            score=round(score, 4),
            confidence=round(vlm_confidence, 4),
            flags=flags,
            details={
                "model": VLM_MODEL_ID,
                "source": "local_vlm",
                "assessment": assessment,
                "artifacts": artifacts,
                "parsed_confidence": round(parsed_confidence, 4),
                "artifact_count": n_artifacts,
                "template_like_output": template_like_output,
                "raw_response": raw_text[:2000],
            },
        ), reasoning

    except Exception as exc:
        logger.warning("Local VLM failed (%s) — falling back to Gemini API", exc)

    # ── Gemini API fallback ─────────────────────────────
    return await _gemini_fallback(image_path)


# ── Eager-load the VLM at import time (before any request threads) ──
_load_vlm()
