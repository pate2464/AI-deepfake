"""Download pre-trained model weights for all ML detection layers.

Run once before first use:
    python download_models.py

Downloads to backend/models/ (gitignored).
"""

import os
import sys
import hashlib
import urllib.request
from pathlib import Path

MODEL_DIR = Path(__file__).parent / "backend" / "models"

# ── Model registry ─────────────────────────────────────
# Each entry: (subdir, filename, url, sha256_or_None)

MODELS = [
    # CLIP UniversalFakeDetect — linear probe weights
    # Source: https://github.com/WisconsinAIVision/UniversalFakeDetect
    (
        "clip_universalfakedetect",
        "fc_weights.pth",
        "https://github.com/WisconsinAIVision/UniversalFakeDetect/raw/main/pretrained_weights/fc_weights.pth",
        None,
    ),
    # CNNDetection — ResNet-50 blur+jpg augmented
    # Source: https://github.com/PeterWang512/CNNDetection
    (
        "cnndetection",
        "blur_jpg_prob0.5.pth",
        "https://www.dropbox.com/s/2g2jagq2jn1fd0i/blur_jpg_prob0.5.pth?dl=1",
        None,
    ),
]

# TruFor weights — downloaded from university server as ZIP
TRUFOR_ZIP_URL = "https://www.grip.unina.it/download/prog/TruFor/TruFor_weights.zip"
TRUFOR_ZIP_MD5 = "7bee48f3476c75616c3c5721ab256ff8"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(subdir: str, filename: str, url: str, expected_sha: str | None):
    dest = MODEL_DIR / subdir / filename
    if dest.is_file():
        print(f"  [OK] {subdir}/{filename} already exists ({dest.stat().st_size:,} bytes)")
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Downloading {subdir}/{filename} ...")
    print(f"    URL: {url}")

    try:
        opener = urllib.request.build_opener()
        opener.addheaders = [("User-Agent", "Mozilla/5.0")]
        urllib.request.install_opener(opener)
        urllib.request.urlretrieve(url, str(dest))
    except Exception as e:
        print(f"  [FAIL] {e}")
        print(f"  >> Manual download: save from {url} to {dest}")
        return

    size = dest.stat().st_size
    print(f"  [OK] Downloaded ({size:,} bytes)")

    if expected_sha:
        actual = sha256_file(dest)
        if actual != expected_sha:
            print(f"  [WARN] Checksum mismatch: expected {expected_sha}, got {actual}")
        else:
            print(f"  [OK] Checksum verified")


def main():
    print(f"Model directory: {MODEL_DIR}\n")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Downloading ML model weights")
    print("=" * 60)

    for subdir, filename, url, sha in MODELS:
        print(f"\n[{subdir}] {filename}")
        download(subdir, filename, url, sha)

    # CLIP backbone (downloaded by open_clip automatically)
    print("\n[CLIP ViT-L/14 backbone]")
    print("  This is downloaded automatically by open_clip on first use (~900 MB)")
    print("  Cached in: ~/.cache/huggingface/ or ~/.cache/open_clip/")

    # TruFor weights — auto-download from university server
    print("\n" + "=" * 60)
    print("TruFor Weights (Layer 12)")
    print("=" * 60)

    trufor_dir = MODEL_DIR / "trufor"
    trufor_dir.mkdir(parents=True, exist_ok=True)
    trufor_pth = trufor_dir / "trufor.pth.tar"
    if not trufor_pth.is_file():
        print("\n[TruFor] Downloading weights from university server (~250 MB)...")
        zip_path = trufor_dir / "TruFor_weights.zip"
        try:
            download("trufor", "TruFor_weights.zip", TRUFOR_ZIP_URL, None)
            # Verify MD5
            import hashlib as _hl
            md5 = _hl.md5()
            with open(zip_path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    md5.update(chunk)
            if md5.hexdigest() == TRUFOR_ZIP_MD5:
                print(f"  [OK] MD5 verified: {TRUFOR_ZIP_MD5}")
            else:
                print(f"  [WARN] MD5 mismatch: expected {TRUFOR_ZIP_MD5}, got {md5.hexdigest()}")

            # Extract
            import zipfile
            print("  Extracting ZIP...")
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(trufor_dir)

            # Move trufor.pth.tar if in subdirectory
            import shutil
            for root, dirs, files in os.walk(trufor_dir):
                for f in files:
                    if f == "trufor.pth.tar" and root != str(trufor_dir):
                        shutil.move(os.path.join(root, f), str(trufor_pth))
                        print(f"  [OK] Extracted trufor.pth.tar ({trufor_pth.stat().st_size:,} bytes)")

            # Clean up
            if zip_path.is_file():
                zip_path.unlink()
            weights_subdir = trufor_dir / "weights"
            if weights_subdir.is_dir():
                shutil.rmtree(weights_subdir, ignore_errors=True)
        except Exception as e:
            print(f"  [FAIL] {e}")
            print(f"  >> Manual: download from {TRUFOR_ZIP_URL}")
            print(f"  >> Extract trufor.pth.tar to {trufor_dir}")
    else:
        print(f"\n[TruFor] Already present ({trufor_pth.stat().st_size:,} bytes)")

    # DIRE — disabled by default, no auto-download available
    print("\n" + "=" * 60)
    print("DIRE (Layer 13) — Optional")
    print("=" * 60)

    dire_dir = MODEL_DIR / "dire"
    dire_dir.mkdir(parents=True, exist_ok=True)
    print("\n[DIRE] DIRE is enabled by default with heuristic mode (no weights needed)")
    print("  For trained weights, download from: https://github.com/ZhendongWang6/DIRE")
    print("  (Weights available on BaiduDrive only)")

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
