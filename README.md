# AI Fraud Detector

Multi-signal analysis pipeline for detecting AI-generated or suspicious images in claim-review workflows.

> This repository started as an 8-layer hackathon prototype. The live system now runs a 21-layer ensemble. If there is ever a mismatch between docs and behavior, treat `backend/app/engine/pipeline.py` and `backend/app/engine/scoring.py` as the source of truth.

Built for HackyIndy 2026.

## What This Project Does

This system is designed for teams reviewing customer-submitted images in fraud-sensitive flows such as refund claims, delivery disputes, and identity or evidence checks.

Instead of trusting a single classifier, it combines multiple evidence families:

- Provenance checks such as EXIF metadata and C2PA content credentials
- Duplicate-image checks using perceptual hashes and historical claim matching
- Learned image detectors such as CLIP and TruFor
- Vision-language reasoning using Gemini with local fallback support
- Statistical and compression forensics such as ELA, NPR, MLEP, and spectral heuristics
- Behavioral fraud context such as account age, device reuse, and claim frequency

The system returns a risk score, a risk tier, plain-language reasons, per-layer evidence, and optional heatmaps for analyst review.

## End-to-End Flow

```
User uploads image + optional context
            |
            v
Frontend (Next.js) sends multipart request to /api/v1/analyze
            |
            v
FastAPI validates file, saves upload, builds analysis context
            |
            v
Pipeline pre-processes image once (decode, convert, resize)
            |
            v
21 detection layers run in parallel
            |
            v
Scoring engine blends weighted signals, applies guardrails, consensus, overrides
            |
            v
Claim + hashes + scoring details are stored in SQLite
            |
            v
Frontend renders reviewer summary + technical analysis panel
```

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                           Frontend (Next.js)                        │
│  Image upload -> summary verdict -> reasons -> layer drill-down     │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ POST /api/v1/analyze
┌───────────────────────────────▼──────────────────────────────────────┐
│                          Backend (FastAPI)                          │
│                                                                      │
│  1. Validate file type and size                                      │
│  2. Save upload locally, optionally mirror to object storage         │
│  3. Pre-process image once to avoid repeated heavy decodes           │
│  4. Run 21 detectors in parallel                                     │
│  5. Compute ensemble risk score with confidence-aware weighting      │
│  6. Persist claim, hashes, layer results, and scoring summary        │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                ┌───────────────┼────────────────┐
                │               │                │
                v               v                v
          SQLite history   Optional object   Model cache /
          and hash store   storage mirror    detector weights
```

## Detection Layers

The pipeline currently runs 21 checks. Each layer returns a suspicion score in `[0, 1]`, a confidence value, flags, and detailed evidence.

### Score-driving layers

These have the biggest influence on the automated verdict.

| Layer | Role | What it looks for |
| --- | --- | --- |
| EXIF | Core | Whether metadata looks like a real camera capture or a synthetic export |
| CLIP Detect | Core | Learned fake-image classification using a CLIP-based probe |
| TruFor | Core | Learned forgery detection plus localization heatmap |
| NPR | Core | Neighboring-pixel regularities common in generated imagery |
| MLEP | Core | Unnatural multi-scale entropy uniformity left by generators |
| ELA | Supporting | Compression error patterns that differ between real and generated images |
| Hash | Supporting | Exact or near-duplicate matches against previous claims |
| AI Model | Supporting | Frequency-domain and spectral cues associated with generation pipelines |
| Gemini | Supporting | Semantic reasoning about impossible details, broken text, reflections, or synthetic structure |
| Attention Pattern | Supporting | Repetitive spatial structure consistent with text-to-image attention artifacts |

### Context and corroboration layers

These are still valuable, but several are deliberately excluded from directly driving the final score so brittle heuristics do not dominate the verdict.

| Layer | Why it exists |
| --- | --- |
| C2PA | High-trust provenance evidence and authenticated origin checks |
| Behavioral | Account-level fraud context like account age, claim spikes, and device reuse |
| Noise | Camera sensor noise / PRNU-style evidence |
| CNN Detect | Legacy learned detector kept as corroboration |
| Watermark | Checks for invisible generation watermarks |
| DIRE | Diffusion-reconstruction style proxy signal |
| Gradient | Gradient-distribution statistics |
| LSB | Least-significant-bit regularity checks |
| DCT Histogram | Compression-block coefficient patterns |
| GAN Fingerprint | Periodic upsampling artifacts in frequency space |
| Texture | Texture breakdown or over-regularity |

### Evidence-family view

Thinking in families is more useful than memorizing 21 names:

- Provenance: EXIF, C2PA
- Duplicate fraud: Hash
- Fraud context: Behavioral
- Learned image models: CLIP Detect, CNN Detect, TruFor
- Semantic reasoning: Gemini
- Compression and spectral heuristics: ELA, AI Model, DCT Histogram, GAN Fingerprint
- Statistical image forensics: NPR, MLEP, Attention Pattern, Gradient, Texture, LSB, Noise, DIRE

## How Scoring Works

The scoring engine lives in `backend/app/engine/scoring.py`.

### 1. Every layer emits score plus confidence

Each detector returns:

- `score`: how suspicious the detector believes the image is
- `confidence`: how reliable that detector thinks its own signal is
- `details`, `flags`, and optional `error`

### 2. Configured weights determine influence

Weights are defined in `backend/app/core/config.py`.

The strongest configured score drivers right now are:

- CLIP Detect: `0.15`
- TruFor: `0.14`
- NPR: `0.12`
- EXIF: `0.10`
- Hash: `0.10`
- Gemini: `0.10`
- MLEP: `0.10`

Several layers are intentionally excluded from direct score-driving because they are better as corroboration than automation.

### 3. Effective confidence guardrails reduce brittle calls

The system does not blindly trust every model output.

Examples:

- If the local fallback VLM makes a weak AI call, its impact is capped.
- If semantic reasoning says AI but provenance and image-space evidence strongly suggest a real camera capture, the semantic layer is down-weighted.

This keeps one noisy detector from overpowering stronger evidence.

### 4. Multi-family agreement can raise the score

If strong evidence families agree with each other, the engine can apply a consensus floor.

Examples:

- Provenance + learned detectors + statistical detectors all point toward suspicion
- Semantic + learned + statistical families all align

This is how the system rewards corroboration across fundamentally different kinds of evidence.

### 5. High-trust overrides can replace the blended score

Two special cases matter a lot:

- Exact or near-exact perceptual hash match: score is overridden to a very high risk value
- High-confidence valid C2PA provenance: score is overridden to a very low risk value

These are treated as stronger than the normal ensemble average.

### 6. Final risk tiers

By default:

- Low: score below `0.3`
- Medium: score from `0.3` up to below `0.6`
- High: score `0.6` and above

## Why the Ensemble Approach Matters

This project is strongest when you explain it as a decision system, not just a model.

A single fake-image classifier can be wrong for many reasons: new generators, unusual compression, stylized photography, or poor calibration. This repository reduces that risk by combining independent signal families.

That gives you three advantages:

- Better robustness because multiple detector families must agree before the score becomes very strong
- Better explainability because every layer reports its own evidence and confidence
- Better operational usefulness because image evidence can be combined with duplicate-history and account-behavior signals

## Frontend Experience

The frontend is built in Next.js and acts as a reviewer-facing decision surface.

Main user flow:

1. Upload an image
2. Optionally attach account or device context
3. Receive a verdict card with risk tier and risk score
4. Read plain-language reasons summarizing the strongest signals
5. Expand into technical analysis for weights, per-layer results, conflicts, and heatmaps

The UI groups layers into:

- Core score layers
- Supporting score layers
- Other analyst layers

This mirrors the live score-role metadata from `backend/app/core/layer_catalog.py`.

## Persistence and History

The backend stores:

- Claims and filenames
- Final risk score and tier
- Per-layer scores and detailed layer results
- Scoring summary including overrides, conflicts, and consensus notes
- Perceptual hashes for future duplicate matching
- Hash-match records between claims

The default database is SQLite through async SQLAlchemy. Optional S3-compatible object storage can mirror uploaded images.

## API Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/analyze` | Run the full 21-layer analysis pipeline |
| GET | `/api/v1/history` | List previous analyses |
| GET | `/api/v1/analysis/{id}` | Retrieve a full stored analysis |
| GET | `/api/v1/stats` | Aggregate scan statistics |
| GET | `/api/v1/health` | Health check |

### Example request

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -F "file=@photo.jpg" \
  -F "account_id=user123" \
  -F "order_value=89.99"
```

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+

### Fastest local run on Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\start-dev.ps1
```

### Manual backend setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt

# Copy env example and add GEMINI_API_KEY if you want Gemini enabled.
Set-Location .\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Manual frontend setup

```powershell
Set-Location .\frontend
npm install
npm run dev
```

Open `http://localhost:3000` to use the app.

## Tech Stack

- Backend: Python 3.12, FastAPI, SQLAlchemy 2.0 async, aiosqlite
- Frontend: Next.js 14, React 18, TypeScript, Tailwind CSS
- Image and forensic libraries: Pillow, NumPy, SciPy, OpenCV, imagehash, c2pa-python
- AI: Gemini as primary semantic VLM, local Moondream2 fallback, CLIP probe, TruFor, CNN model
- Storage: SQLite by default, optional S3-compatible object storage

## Key Files

| Path | Purpose |
| --- | --- |
| `backend/app/main.py` | FastAPI app setup and startup lifecycle |
| `backend/app/api/routes.py` | API entry points |
| `backend/app/engine/pipeline.py` | 21-layer orchestration and persistence |
| `backend/app/engine/scoring.py` | Weighted ensemble scoring and overrides |
| `backend/app/core/config.py` | Thresholds, weights, storage, and model settings |
| `backend/app/core/layer_catalog.py` | Layer families and score roles |
| `backend/app/core/models.py` | Shared API and scoring schemas |
| `backend/app/db/database.py` | ORM models and DB initialization |
| `frontend/app/page.tsx` | Main upload and result page |
| `frontend/lib/api.ts` | Frontend API client and response types |
| `frontend/lib/verdict.ts` | Plain-language reason generation |

## Limitations and Operational Notes

- Some detectors require heavyweight model downloads or research weights.
- Gemini needs `GEMINI_API_KEY` for the primary semantic path.
- The local VLM fallback can be slower and is deliberately guarded against overconfident calls.
- Behavioral scoring is only useful when account or device context is provided.
- SQLite is convenient for local and demo use, but a higher-concurrency deployment should move to PostgreSQL.
- Not every detector directly drives the score; several are intentionally contextual.

## Pitch Summary

If you need a one-paragraph explanation:

This project is a fraud-review engine for suspicious images. A user uploads an image, the backend runs 21 parallel checks across provenance, learned models, semantic reasoning, duplicate history, and statistical forensics, then a scoring engine weights the reliable signals, suppresses brittle ones, applies strong overrides when high-trust evidence exists, and returns both a reviewer-friendly verdict and a technical forensic breakdown.

For a longer presentation script, see `PITCH_SCRIPT.md`.
