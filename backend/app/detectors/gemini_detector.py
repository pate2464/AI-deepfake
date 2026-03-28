"""Layer 7 — Gemini Vision Semantic Analysis.

Sends the image to Google's Gemini multimodal model with a structured forensic
prompt.  This layer provides semantic-level reasoning that no pixel-level
detector can match.
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.core.config import settings
from app.core.models import LayerName, LayerResult

FORENSIC_PROMPT = """You are an expert forensic image analyst. Analyze this image that was submitted as evidence of a food quality complaint or refund claim.

Evaluate the following criteria and return ONLY valid JSON (no markdown, no explanation outside JSON):

{
  "physical_plausibility": {
    "score": 0.0-1.0,
    "notes": "Does the food/damage look physically realistic? Are textures, lighting, shadows consistent?"
  },
  "ai_artifacts": {
    "score": 0.0-1.0,
    "notes": "Signs of AI generation: unnatural smoothness, warped text, impossible geometry, wrong finger count, weird reflections, uncanny valley textures"
  },
  "contextual_consistency": {
    "score": 0.0-1.0,
    "notes": "Does the setting (plate, table, background) look realistic and consistent?"
  },
  "lighting_analysis": {
    "score": 0.0-1.0,
    "notes": "Is the lighting natural and consistent across the image? Multiple light sources that don't make sense?"
  },
  "text_rendering": {
    "score": 0.0-1.0,
    "notes": "If any text is visible (brand names, labels, receipts), is it rendered correctly or garbled?"
  },
  "overall_assessment": "likely_real | likely_ai_generated | uncertain",
  "confidence": 0.0-1.0,
  "reasoning": "One paragraph summary of your analysis"
}

Score meaning: 0.0 = no issues (looks authentic), 1.0 = highly suspicious (likely AI-generated).
Be conservative — only flag as AI-generated if you see clear evidence."""


async def analyze(image_path: str) -> tuple[LayerResult, str | None]:
    """Run Gemini Vision analysis.

    Returns (LayerResult, gemini_reasoning_text_or_None).
    """
    flags: list[str] = []
    details: dict[str, Any] = {}

    api_key = settings.GEMINI_API_KEY
    if not api_key:
        return LayerResult(
            layer=LayerName.GEMINI,
            score=0.0,
            confidence=0.0,
            flags=["Gemini API key not configured — layer skipped"],
            details={"note": "Set GEMINI_API_KEY in .env to enable this layer"},
        ), None

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(settings.GEMINI_MODEL)

        # Upload image
        with open(image_path, "rb") as f:
            image_data = f.read()

        # Determine mime type
        ext = image_path.rsplit(".", 1)[-1].lower()
        mime_map = {
            "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png", "webp": "image/webp",
            "heic": "image/heic", "heif": "image/heif",
            "tiff": "image/tiff", "tif": "image/tiff",
            "bmp": "image/bmp", "avif": "image/avif",
        }
        mime_type = mime_map.get(ext, "image/jpeg")

        # For HEIC/HEIF, Gemini may not accept it — convert to JPEG in-memory
        if ext in ("heic", "heif"):
            from PIL import Image as PILImage
            import io
            pil_img = PILImage.open(image_path).convert("RGB")
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=95)
            image_data = buf.getvalue()
            mime_type = "image/jpeg"

        response = model.generate_content([
            FORENSIC_PROMPT,
            {"mime_type": mime_type, "data": image_data},
        ])

        response_text = response.text.strip()

        # Strip markdown code fences if present
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            response_text = "\n".join(lines)

        parsed = json.loads(response_text)
        details["gemini_raw"] = parsed

        # Extract scores
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
        reasoning = parsed.get("reasoning", "")

        details["assessment"] = assessment
        details["gemini_confidence"] = gemini_confidence

        # Compute overall score
        if assessment == "likely_ai_generated":
            base_score = 0.8
        elif assessment == "likely_real":
            base_score = 0.15
        else:
            base_score = 0.45

        # Modulate with sub-scores
        if sub_scores:
            avg_sub = sum(sub_scores) / len(sub_scores)
            score = base_score * 0.6 + avg_sub * 0.4
        else:
            score = base_score

        score = min(1.0, max(0.0, score))
        flags.append(f"Gemini assessment: {assessment} (confidence={gemini_confidence:.2f})")

        return LayerResult(
            layer=LayerName.GEMINI,
            score=round(score, 4),
            confidence=round(gemini_confidence, 4),
            flags=flags,
            details=details,
        ), reasoning

    except json.JSONDecodeError:
        return LayerResult(
            layer=LayerName.GEMINI,
            score=0.5,
            confidence=0.2,
            flags=["Gemini returned unparseable response"],
            details={"raw_response": response_text[:500] if "response_text" in dir() else "N/A"},
        ), None

    except Exception as e:
        return LayerResult(
            layer=LayerName.GEMINI,
            score=0.0,
            confidence=0.0,
            flags=[f"Gemini analysis failed: {type(e).__name__}"],
            error=str(e),
        ), None
