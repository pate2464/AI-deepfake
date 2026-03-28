"""Model management utility for lazy-loading PyTorch models.

Downloads, caches, and serves ML model weights.  Models are loaded on first
use and kept in memory for subsequent requests.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import torch

logger = logging.getLogger(__name__)

# Default model cache directory
MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"

# Singleton cache: name → loaded model/object
_model_cache: dict[str, Any] = {}

# Determined once
_device: torch.device | None = None


def get_device() -> torch.device:
    """Return the best available torch device (cached)."""
    global _device
    if _device is None:
        if torch.cuda.is_available():
            _device = torch.device("cuda")
            logger.info("Using GPU: %s", torch.cuda.get_device_name(0))
        else:
            _device = torch.device("cpu")
            logger.info("CUDA not available — falling back to CPU")
    return _device


def ensure_model_dir() -> Path:
    """Create and return the model cache directory."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    return MODEL_DIR


def model_path(subdir: str, filename: str) -> Path:
    """Return the full path to a model weight file."""
    return ensure_model_dir() / subdir / filename


def is_downloaded(subdir: str, filename: str) -> bool:
    """Check if a model weight file exists locally."""
    return model_path(subdir, filename).is_file()


def download_weights(url: str, subdir: str, filename: str, sha256: str | None = None) -> Path:
    """Download model weights from *url* to the cache directory.

    If *sha256* is given, verifies the file checksum after download.
    Returns the local path.
    """
    dest = model_path(subdir, filename)
    if dest.is_file():
        if sha256 and _sha256(dest) != sha256:
            logger.warning("Checksum mismatch for %s — re-downloading", dest)
        else:
            return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading %s → %s", url, dest)

    import urllib.request
    urllib.request.urlretrieve(url, str(dest))

    if sha256:
        actual = _sha256(dest)
        if actual != sha256:
            dest.unlink()
            raise RuntimeError(
                f"Checksum mismatch for {filename}: expected {sha256}, got {actual}"
            )

    logger.info("Downloaded %s (%d bytes)", filename, dest.stat().st_size)
    return dest


def get_cached(name: str) -> Any | None:
    """Return a previously cached model or ``None``."""
    return _model_cache.get(name)


def set_cached(name: str, model: Any) -> None:
    """Store a model in the in-memory cache."""
    _model_cache[name] = model


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
