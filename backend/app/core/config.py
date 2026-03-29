"""Application configuration with environment variable support."""

import os
import re
from pathlib import Path
from pydantic_settings import BaseSettings


BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[/\\]")


def _resolve_database_url(url: str) -> str:
    """Resolve relative SQLite URLs against the backend directory."""
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if not url.startswith(prefix):
            continue

        raw_path = url[len(prefix):]
        if raw_path == ":memory:":
            return url

        if Path(raw_path).is_absolute() or WINDOWS_ABSOLUTE_PATH.match(raw_path):
            return url

        resolved_path = (BACKEND_ROOT / raw_path).resolve().as_posix()
        return f"{prefix}{resolved_path}"

    return url


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
    UPLOAD_DIR: str = str(BACKEND_ROOT / "uploads")
    MAX_FILE_SIZE_MB: int = 20

    # Object storage (S3-compatible, e.g. Vultr Object Storage)
    OBJECT_STORAGE_ENABLED: bool = False
    OBJECT_STORAGE_ENDPOINT_URL: str = ""  # e.g. https://ewr1.vultrobjects.com
    OBJECT_STORAGE_REGION: str = "us-east-1"  # Vultr uses "us-east-1" for SigV4; keep unless you know otherwise
    OBJECT_STORAGE_BUCKET: str = ""
    OBJECT_STORAGE_ACCESS_KEY_ID: str = ""
    OBJECT_STORAGE_SECRET_ACCESS_KEY: str = ""
    OBJECT_STORAGE_PREFIX: str = "uploads"  # key prefix inside the bucket

    # Detection thresholds
    HASH_MATCH_THRESHOLD: int = 10  # hamming distance for 256-bit hash
    HASH_IDENTICAL_THRESHOLD: int = 5
    ELA_QUALITY: int = 90
    ELA_SCALE_FACTOR: int = 15

    # Risk tiers
    RISK_LOW_THRESHOLD: float = 0.3
    RISK_HIGH_THRESHOLD: float = 0.6

    # Ensemble weights (21 layers)
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
    MODEL_CACHE_DIR: str = str(BACKEND_ROOT / "models")

    # Behavioral thresholds
    BEHAVIORAL_MAX_CLAIMS_30D: int = 3
    BEHAVIORAL_MIN_ACCOUNT_AGE_DAYS: int = 7
    BEHAVIORAL_GPS_MISMATCH_KM: float = 5.0

    model_config = {
        "env_file": [
            ".env",  # current directory
            str(BACKEND_ROOT / ".env"),  # backend/.env
        ],
        "extra": "ignore",
    }


settings = Settings()
settings.DATABASE_URL = _resolve_database_url(settings.DATABASE_URL)

# Ensure upload dir exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
