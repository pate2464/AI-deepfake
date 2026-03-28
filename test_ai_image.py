"""Test the 19-layer pipeline with an AI-generated image."""
import httpx, json, time, sys

image_path = r"C:\Users\g18g1\Downloads\Gemini_Generated_Image_6qre9r6qre9r6qre (1).png"

start = time.time()
with open(image_path, "rb") as f:
    files = {"file": ("Gemini_Generated_Image.png", f, "image/png")}
    r = httpx.post("http://localhost:8000/api/v1/analyze", files=files, timeout=600.0)
elapsed = time.time() - start

print(f"Status: {r.status_code}  Time: {elapsed:.1f}s")
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
        flags_str = ", ".join(lr.get("flags", []))[:90]
        err_str = f"  ERR: {str(err)[:60]}" if err else ""
        print(f"  {layer:20s}  score={score:.4f}  conf={conf:.2f}  {flags_str}{err_str}")
    print()
    if data.get("gemini_reasoning"):
        print("VLM Reasoning:", data["gemini_reasoning"][:500])
    with open("test_result_ai.json", "w") as out:
        json.dump(data, out, indent=2, default=str)
    print("\nResult saved to test_result_ai.json")
else:
    print("Error:", r.text[:1000])
