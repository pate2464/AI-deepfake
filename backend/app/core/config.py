"""Application configuration with environment variable support."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AI Fraud Detector"
    DEBUG: bool = True
    API_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./fraud_detector.db"

    # Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Upload
    UPLOAD_DIR: str = str(Path(__file__).resolve().parent.parent.parent / "uploads")
    MAX_FILE_SIZE_MB: int = 20

    # Detection thresholds
    HASH_MATCH_THRESHOLD: int = 10  # hamming distance for 256-bit hash
    HASH_IDENTICAL_THRESHOLD: int = 5
    ELA_QUALITY: int = 90
    ELA_SCALE_FACTOR: int = 15

    # Risk tiers
    RISK_LOW_THRESHOLD: float = 0.3
    RISK_HIGH_THRESHOLD: float = 0.6

    # Ensemble weights (19 layers)
    # VLM + TruFor + CLIP are strongest for modern diffusion-model detection.
    # GAN-specific detectors (noise, gradient, GAN fingerprint) are de-weighted
    # because diffusion outputs bypass their heuristics.
    WEIGHT_EXIF: float = 0.10
    WEIGHT_ELA: float = 0.06
    WEIGHT_HASH: float = 0.10
    WEIGHT_AI_MODEL: float = 0.06
    WEIGHT_C2PA: float = 0.03
    WEIGHT_BEHAVIORAL: float = 0.05
    WEIGHT_GEMINI: float = 0.10
    WEIGHT_NOISE: float = 0.03
    WEIGHT_CLIP_DETECT: float = 0.15
    WEIGHT_CNN_DETECT: float = 0.04
    WEIGHT_WATERMARK: float = 0.03
    WEIGHT_TRUFOR: float = 0.14
    WEIGHT_DIRE: float = 0.03
    WEIGHT_GRADIENT: float = 0.03
    WEIGHT_LSB: float = 0.03
    WEIGHT_DCT_HIST: float = 0.03
    WEIGHT_GAN_FINGERPRINT: float = 0.03
    WEIGHT_ATTENTION_PATTERN: float = 0.06
    WEIGHT_TEXTURE: float = 0.04
    WEIGHT_NPR: float = 0.12
    WEIGHT_MLEP: float = 0.10

    # ML model settings
    ENABLE_DIRE: bool = True
    MODEL_CACHE_DIR: str = str(Path(__file__).resolve().parent.parent.parent / "models")

    # Behavioral thresholds
    BEHAVIORAL_MAX_CLAIMS_30D: int = 3
    BEHAVIORAL_MIN_ACCOUNT_AGE_DAYS: int = 7
    BEHAVIORAL_GPS_MISMATCH_KM: float = 5.0

    model_config = {
        "env_file": [
            ".env",  # current directory
            str(Path(__file__).resolve().parent.parent.parent / ".env"),  # backend/.env
        ],
        "extra": "ignore",
    }


settings = Settings()

# Ensure upload dir exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
