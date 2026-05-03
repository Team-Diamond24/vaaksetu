# VaakSetu - 1092 Helpline Intelligence Layer

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Realtime-009688)
![React](https://img.shields.io/badge/React-Voice%20UI-61DAFB)
![WebSocket](https://img.shields.io/badge/WebSocket-Live%20Streaming-orange)
![SQLite](https://img.shields.io/badge/SQLite-Analytics-003B57)

**Verified Understanding + Cultural Intelligence for emergency response at scale.**  
VaakSetu is a real-time AI-assisted call workflow for the **1092 helpline**, built to understand citizens correctly across dialects, emotion, and noisy environments before action is taken.

---

## Project Vision

Emergency calls fail when systems misunderstand people under stress. Callers switch between Kannada, Hindi, and English, use regional slang, and speak in panic from noisy surroundings. A wrong interpretation can delay help.

VaakSetu addresses this with a mission-first pipeline:
- real-time speech-to-text from live call audio,
- dialect-aware contextual reasoning,
- acoustic distress intelligence,
- a verified confirmation loop before escalation,
- and instant human takeover when needed.

The goal is simple: **understand correctly, verify safely, respond faster.**

---

## Core Features (The Winning Edge)

### 1) Dialect-Aware RAG
- `backend/app/services/cultural_service.py` detects regional slang markers in the *current* transcript and injects only matched definitions.
- Cultural context is included in reasoning **only when detected**, reducing token waste and preserving precision.
- The design is compatible with Kannada linguistic enrichment pipelines (including Igo-style dictionary expansions) through the editable corpus in `backend/app/data/cultural_slang.json`.

### 2) Acoustic Intelligence
- `backend/app/services/acoustic_service.py` performs chunk-level DSP over live PCM:
  - RMS loudness,
  - Zero-Crossing Rate (pitch proxy),
  - rolling noise floor/environment classification,
  - distress-level scoring (1-5).
- Supervisors see distress and environment signals in real time for proactive intervention.

### 3) Verified Understanding Loop
- `backend/app/services/call_service.py` maintains call state machine:
  - `LISTENING -> VERIFYING -> CONFIRMED/ESCALATED`.
- In `VERIFYING`, the system performs binary confirmation analysis before progressing.
- This prevents silent failure from confident but incorrect interpretation.

### 4) Seamless Human-in-the-Loop
- Takeover is built in via `TOGGLE_TAKEOVER` over WebSocket.
- When muted (`is_muted=true`), AI TTS is suppressed while transcription/monitoring continues.
- `frontend/src/components/dashboard/SupervisorDashboard.tsx` gives a high-visibility command center with live transcript, distress context, and control state.

### 5) Global Resilience
- `backend/app/main.py` enforces API guardrails with timeout protection (`4s`) around STT/reasoning calls.
- On timeout/failure:
  - system emits fallback voice message,
  - automatically mutes AI,
  - and transitions to immediate human control.

---

## Tech Stack

| Layer | Technologies |
|---|---|
| Frontend | React 19, Vite, TypeScript, Shadcn UI, Lucide, Tailwind, Web Audio API, WebSocket streaming |
| Backend | FastAPI, Uvicorn, Groq Whisper (STT), Gemini Flash via OpenRouter (reasoning + analytics), Edge-TTS, SQLite, Pydantic |

---

## System Architecture

```mermaid
flowchart LR
    A[Citizen Voice] --> B[Frontend AudioWorklet]
    B --> C[WebSocket audio_chunk]
    C --> D[Groq STT + VAD]
    C --> E[Acoustic Intelligence]
    D --> F[Transcript Emission to UI]
    D --> G[Cultural Context Detection]
    G --> H[Gemini Reasoning]
    E --> I[Distress/Environment Updates]
    H --> J[Verification Loop]
    J --> K[Edge-TTS Streaming]
    K --> A
    J --> L[Human Takeover]
    D --> M[SQLite transcript_events]
    M --> N[Post-Call Analytics (Gemini)]
    N --> O[Supervisor Call Summary Modal]
```

Text flow: **Citizen -> Groq STT -> Cultural + Acoustic Analysis -> Gemini Reasoning -> Verification -> Edge-TTS -> Citizen**, with resilience short-circuits and human takeover at any point.

---

## Installation & Setup

## 1) Backend Setup (FastAPI)

```bash
cd backend
python -m venv .venv
```

Activate virtual environment:

- Windows (PowerShell):
```bash
.\.venv\Scripts\Activate.ps1
```

- Windows (cmd):
```bash
.\.venv\Scripts\activate.bat
```

- Linux/macOS:
```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create backend environment file:

```bash
copy .env.example .env
```

Run backend:

```bash
uvicorn app.main:app --reload
```

---

## 2) Frontend Setup (React)

```bash
cd frontend
npm install
```

Create frontend environment file:

```bash
copy .env.example .env
```

Run frontend:

```bash
npm run dev
```

Build:

```bash
npm run build
```

---

## Environment Variables

Backend (`backend/.env`):

| Variable | Required | Purpose |
|---|---|---|
| `APP_ENV` | No | Runtime mode (`development`, `production`) |
| `APP_DEBUG` | No | Debug behavior |
| `APP_HOST` | No | Backend host binding |
| `APP_PORT` | No | Backend port |
| `GROQ_API_KEY` | Yes | Groq Whisper transcription |
| `OPENROUTER_API_KEY` | Yes | Gemini Flash reasoning + analytics via OpenRouter |
| `OPENAI_API_KEY` | Optional | Reserved/compat use |
| `DEEPGRAM_API_KEY` | Optional | Reserved/compat use |
| `ELEVENLABS_API_KEY` | Optional | Reserved/compat use |
| `VAD_ENERGY_THRESHOLD` | No | Voice activity threshold tuning |
| `DATABASE_URL` | No | SQLite URL (default `sqlite:///./vaaksetu.db`) |
| `CORS_ORIGINS` | No | Allowed frontend origins |
| `WS_HEARTBEAT_INTERVAL` | No | WS keepalive interval |

Frontend (`frontend/.env`):

| Variable | Required | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | Yes | REST base URL |
| `VITE_WS_BASE_URL` | Yes | WebSocket base URL |

> Note: `GEMINI_API_KEY` may appear in legacy env examples; current runtime wiring uses `OPENROUTER_API_KEY`.

---

## Post-Call Analytics (The Coach)

- `backend/app/services/analytics_service.py` generates a final performance report at call end:
  - `understanding_score` (1-10),
  - `cultural_accuracy` (1-10),
  - `bottleneck_detected`,
  - `coaching_tip`.
- Reports are emitted to the supervisor UI and persisted into SQLite (`transcript_events.analytics_report`).
- `SupervisorDashboard` surfaces this in a **Call Summary** modal for operator coaching and QA.

---

## Impact

VaakSetu is architected as a reusable emergency intelligence layer, not a single-use prototype.  
With policy and integration adaptations, this model can scale across **112 / 108** and related public safety channels:

- better first-understanding under language diversity,
- faster escalation in high-distress conditions,
- safer automation through verified confirmation loops,
- and measurable post-call quality improvement.

**When emergency systems understand correctly on the first attempt, lives are saved.**
