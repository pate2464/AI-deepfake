import json
import os
import time
from pathlib import Path

import httpx


def _resolve_test_image() -> Path:
    candidates = []

    env_path = os.environ.get("REAL_TEST_IMAGE")
    if env_path:
        candidates.append(Path(env_path))

    script_dir = Path(__file__).resolve().parent
    candidates.append(script_dir / "IMG_8592.HEIC")
    candidates.append(Path.home() / "Downloads" / "IMG_8592.HEIC")

    for candidate in candidates:
        if candidate.exists():
            return candidate

    searched = "\n".join(f"  - {path}" for path in candidates)
    raise FileNotFoundError(f"Could not find real test image. Searched:\n{searched}")


image_path = _resolve_test_image()

start = time.time()
with image_path.open("rb") as f:
    files = {"file": (image_path.name, f, "image/heic")}
    r = httpx.post("http://localhost:8000/api/v1/analyze", files=files, timeout=300.0)
elapsed = time.time() - start

print("Status:", r.status_code, f"Time: {elapsed:.1f}s")
print("Image:", image_path)
if r.status_code == 200:
    data = r.json()
    print(f"Risk: {data['risk_score']}/100  Tier: {data['risk_tier']}")
    print(f"Processing: {data['processing_time_ms']}ms")
    print()
    for lr in data["layer_results"]:
        layer = lr["layer"]
        score = lr["score"]
        conf = lr["confidence"]
        err = lr.get("error")
        flags = ", ".join(lr.get("flags", []))[:70]
        err_str = f"  ERR: {str(err)[:60]}" if err else ""
        print(f"  {layer:12s}  score={score:.4f}  conf={conf:.2f}  {flags}{err_str}")
    if data.get("trufor_heatmap_b64"):
        print(f"\nTruFor heatmap: {len(data['trufor_heatmap_b64'])} chars")
    with open("test_result2.json", "w") as out:
        json.dump(data, out, indent=2, default=str)
    print("\nFull result saved to test_result2.json")
else:
    print("Error:", r.text[:1000])
