"""Test script — sends the HEIC pizza image to the analysis endpoint and prints results."""
import httpx
import sys
import os
import json

image_path = sys.argv[1] if len(sys.argv) > 1 else "IMG_8592.HEIC"
if not os.path.exists(image_path):
    print(f"File not found: {image_path}")
    sys.exit(1)

ext = os.path.splitext(image_path)[1].lower()
mime_map = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp",
    ".heic": "image/heic", ".heif": "image/heif",
    ".tiff": "image/tiff", ".bmp": "image/bmp",
}
mime = mime_map.get(ext, "application/octet-stream")

print(f"Testing: {image_path} ({os.path.getsize(image_path):,} bytes, MIME: {mime})")
print("=" * 70)

with open(image_path, "rb") as f:
    files = {"file": (os.path.basename(image_path), f, mime)}
    r = httpx.post("http://localhost:8000/api/v1/analyze", files=files, timeout=120.0)

print(f"Status: {r.status_code}")
if r.status_code != 200:
    print(f"Error: {r.text[:500]}")
    sys.exit(1)

data = r.json()
print(f"\nRISK SCORE: {data['risk_score']:.4f}")
print(f"RISK TIER:  {data['risk_tier'].upper()}")
print(f"TIME:       {data['processing_time_ms']}ms")
print(f"LAYERS:     {len(data['layer_results'])}")

print("\n" + "-" * 70)
print(f"{'Layer':15s} {'Score':>8s} {'Conf':>8s}  First Flag")
print("-" * 70)
for lr in sorted(data["layer_results"], key=lambda x: x["score"], reverse=True):
    first_flag = lr["flags"][0][:60] if lr["flags"] else "(none)"
    err = " [ERR]" if lr.get("error") else ""
    print(f"{lr['layer']:15s} {lr['score']:8.4f} {lr['confidence']:8.4f}  {first_flag}{err}")

# Show Gemini reasoning if available
if data.get("gemini_reasoning"):
    print(f"\nGEMINI REASONING:")
    print(f"  {data['gemini_reasoning'][:500]}")

# Show hash matches
if data.get("hash_matches"):
    print(f"\nHASH MATCHES ({len(data['hash_matches'])}):")
    for m in data["hash_matches"]:
        print(f"  Claim #{m['matched_claim_id']} — {m['hash_type']} dist={m['hamming_distance']}")

# Detailed layer output
print("\n" + "=" * 70)
print("DETAILED LAYER OUTPUT")
print("=" * 70)
for lr in data["layer_results"]:
    print(f"\n--- {lr['layer'].upper()} ---")
    print(f"  Score: {lr['score']:.4f}  Confidence: {lr['confidence']:.4f}")
    if lr.get("error"):
        print(f"  ERROR: {lr['error']}")
    for flag in lr["flags"]:
        print(f"  FLAG: {flag}")
    if lr.get("details"):
        for k, v in lr["details"].items():
            v_str = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
            if len(v_str) > 200:
                v_str = v_str[:200] + "..."
            print(f"  {k}: {v_str}")
