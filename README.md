# 🛡️ AI Fraud Detector

**Multi-layer deep analysis pipeline for detecting AI-generated fraudulent images**

> Note: this project started as an 8-layer hackathon prototype. The current backend runs a larger ensemble; trust the live API/UI output and `backend/app/engine/pipeline.py` for the active layer set.

Built for HackyIndy 2026 — 48-hour hackathon

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Next.js 14)                     │
│   Upload → Scanning Animation → Risk Gauge → Layer Cards    │
└──────────────────────────┬──────────────────────────────────┘
                           │ /api/v1/analyze
┌──────────────────────────▼──────────────────────────────────┐
│                  Backend (FastAPI + Python)                   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │             Multi-Layer Detection Pipeline             │   │
│  │                                                        │   │
│  │  L1  EXIF Metadata Forensics        (0.10 weight)     │   │
│  │  L2  Error Level Analysis (ELA)     (0.15 weight)     │   │
│  │  L3  Perceptual Hashing             (0.20 weight)     │   │
│  │  L4  FFT Frequency Analysis         (0.15 weight)     │   │
│  │  L5  C2PA Cryptographic Provenance  (0.05 weight)     │   │
│  │  L6  Behavioral Account Scoring     (0.20 weight)     │   │
│  │  L7  Gemini Vision Semantic AI      (0.10 weight)     │   │
│  │  L8  Noise / PRNU Analysis          (0.05 weight)     │   │
│  └──────────────────────────────────────────────────────┘   │
│                           │                                   │
│              Weighted Ensemble Scoring                        │
│          LOW (<0.3) │ MEDIUM │ HIGH (>0.6)                   │
│                                                              │
│  SQLite DB │ Account history │ Hash database │ Claim log     │
└──────────────────────────────────────────────────────────────┘
```

## Core Detection Layers

| # | Layer | What it detects | Key technique |
|---|-------|----------------|---------------|
| 1 | **EXIF Metadata** | Missing camera fields, AI tool software tags | Field presence ratio, software name matching |
| 2 | **Error Level Analysis** | Uniform compression → AI generation | JPEG re-save diff, uniformity metrics |
| 3 | **Perceptual Hashing** | Reused/duplicate images across claims | pHash, dHash, aHash, wHash @ 256-bit |
| 4 | **FFT Frequency** | GAN/diffusion spectral artifacts | 2D FFT radial power spectrum, DCT block analysis |
| 5 | **C2PA Provenance** | Cryptographic content credentials | c2pa-python manifest validation |
| 6 | **Behavioral** | Account fraud patterns | Claim frequency, device reuse, account age |
| 7 | **Gemini Vision** | Semantic AI artifact detection | Multimodal LLM forensic analysis |
| 8 | **Noise/PRNU** | Missing camera sensor fingerprint | Noise residual statistics, spatial autocorrelation |

## Quick Start

### Prerequisites
- Python 3.12+
- Node.js 18+

### Fastest Local Run on Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\start-dev.ps1
```

This opens backend and frontend in separate PowerShell windows with the correct working directories.

### Manual Run

### 1. Backend

```powershell
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r backend/requirements.txt

# Configure environment
cp backend/.env.example backend/.env
# Edit backend/.env and add your GEMINI_API_KEY (Gemini is the primary semantic VLM; local Moondream2 is the fallback)

# Start server
Set-Location .\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Frontend

```powershell
Set-Location .\frontend
npm install
npm run dev
```

### 3. Open

Navigate to **http://localhost:3000** — drop an image to analyze.

If you see `Could not import module "app.main"`, the backend was started from the wrong directory. Use `start-dev.ps1` or the exact backend command above.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/analyze` | Upload image for full-ensemble analysis |
| `GET` | `/api/v1/history` | List previous analyses |
| `GET` | `/api/v1/analysis/{id}` | Get detailed analysis by ID |
| `GET` | `/api/v1/stats` | Aggregate statistics |
| `GET` | `/api/v1/health` | Health check |

### Example: Analyze an image

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -F "file=@photo.jpg" \
  -F "account_id=user123" \
  -F "order_value=89.99"
```

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0 (async), aiosqlite
- **Frontend**: Next.js 14, React 18, Tailwind CSS, TypeScript
- **Detection**: Pillow, NumPy, SciPy, OpenCV, imagehash, c2pa-python
- **AI**: Google Gemini 2.5 Flash (primary multimodal vision), local Moondream2 fallback
- **Database**: SQLite (zero-config, single-file)

## Project Structure

```
AI-deepfake/
├── backend/
│   ├── app/
│   │   ├── api/routes.py          # FastAPI endpoints
│   │   ├── core/
│   │   │   ├── config.py          # Settings & env vars
│   │   │   └── models.py          # Pydantic schemas
│   │   ├── db/database.py         # SQLAlchemy ORM models
│   │   ├── detectors/
│   │   │   ├── exif_detector.py   # L1: EXIF metadata
│   │   │   ├── ela_detector.py    # L2: Error level analysis
│   │   │   ├── hash_detector.py   # L3: Perceptual hashing
│   │   │   ├── ai_model_detector.py # L4: FFT frequency
│   │   │   ├── c2pa_detector.py   # L5: C2PA provenance
│   │   │   ├── behavioral_detector.py # L6: Account behavior
│   │   │   ├── gemini_detector.py # L7: Gemini-first vision AI
│   │   │   └── noise_detector.py  # L8: Noise/PRNU
│   │   ├── engine/
│   │   │   ├── pipeline.py        # Orchestrator (parallel execution)
│   │   │   └── scoring.py         # Weighted ensemble scoring
│   │   └── main.py                # FastAPI app entry point
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx               # Main upload → results UI
│   │   └── globals.css
│   ├── components/
│   │   ├── ImageUpload.tsx        # Drag-and-drop upload
│   │   ├── RiskGauge.tsx          # Animated circular gauge
│   │   └── LayerCard.tsx          # Expandable layer result card
│   ├── lib/
│   │   ├── api.ts                 # API client
│   │   └── utils.ts               # Helpers
│   └── package.json
└── README.md
```

## Team

Built by Team [Your Team Name] at HackyIndy 2026
