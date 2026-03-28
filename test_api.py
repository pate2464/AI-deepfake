import httpx
import sys

with open("test_image.jpg", "rb") as f:
    files = {"file": ("test_image.jpg", f, "image/jpeg")}
    r = httpx.post("http://localhost:8000/api/v1/analyze", files=files, timeout=60.0)

print("Status:", r.status_code)
if r.status_code == 200:
    data = r.json()
    print("Risk Score:", data["risk_score"])
    print("Risk Tier:", data["risk_tier"])
    print("Layers:", len(data["layer_results"]))
    for lr in data["layer_results"]:
        layer = lr["layer"]
        score = lr["score"]
        conf = lr["confidence"]
        flags = lr["flags"][:1]
        print(f"  {layer:12s} score={score:.4f}  conf={conf:.4f}  flags={flags}")
    print("Time:", data["processing_time_ms"], "ms")
else:
    print("Error:", r.text[:500])
