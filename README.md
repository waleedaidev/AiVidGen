# AiVidGen

Lead-gen tool disguised as an AI video generator. Landing page takes a one-line prompt,
fires a LangGraph video-generation job in the background, and shows the visitor a guided
chat (real LLM via OpenRouter) that collects business/tone details plus email + WhatsApp
number while the video renders. Ends with a 10-15s teaser + a "pay for full video" CTA.

## Architecture

- **Orchestration**: LangGraph (`backend/app/graph/`) — parse intent -> script -> subject
  image + TTS -> video generation (retry up to `MAX_GENERATION_ATTEMPTS`, then falls back to
  a pre-fetched stock clip from Pexels with your generated voiceover overlaid).
- **Chat**: `backend/app/chat/chat_llm.py` — a guided slot-filling state machine that *feels*
  like free conversation (gpt-4o-mini via OpenRouter) but always captures: business_type,
  tone, email (gate), target_audience, use_case, preferred_style, phone (gate). Falls back to
  a scripted question flow if no OpenRouter key is set.
- **DB**: Postgres (`backend/app/models_db.py`) — leads, generation_jobs, chat_messages,
  stock_clips.
- **Providers**: `backend/app/providers/` — pluggable interfaces for image/audio/video
  generation, selected by `PROVIDER_MODE`:
  - `mock` — fully free/local (placeholder image, silent TTS, ffmpeg-rendered clip), zero
    external calls, for quick sanity checks.
  - `free` (default) — real, genuinely free providers: **Pollinations.ai** for images (no key,
    no limit), **Piper** for voiceover (local, no key), **Hugging Face** Inference API for
    video (free token, but expect occasional cold-start failures — that's fine, it feeds the
    same retry/fallback path). Any of the three silently falls back to its mock counterpart if
    not configured yet.
  - `live` — Highfield. `highfield.py` is a stub — fill in the three TODOs once you have
    Highfield's API docs.

## Prerequisites

- Python 3.11+
- Docker (for Postgres) — or point `DATABASE_URL` at any Postgres you already have
- `ffmpeg` on your PATH (used for mock video generation and stock-fallback audio overlay)
- For the `free` provider mode (default):
  - A free Hugging Face token from https://huggingface.co/settings/tokens (video)
  - `piper-tts` installed (`pip install -r requirements.txt` covers this) plus a downloaded
    voice model — see "Piper voice setup" below (voice). Without it, audio falls back to
    silent placeholder automatically, so this step can be skipped for a first smoke test.

## Setup

```bash
# 1. Start Postgres
docker compose up -d

# 2. Backend
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # edit if you have real keys, mock mode works with none

# 3. Run
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000 — that's the landing page. Submitting a prompt takes you to the
chat, which runs alongside the background LangGraph job, and ends with a rendered teaser.

## Piper voice setup

```bash
# Download a voice model (this one is a good default: natural, medium quality/speed)
# from https://huggingface.co/rhasspy/piper-voices — you need BOTH files:
#   en_US-lessac-medium.onnx
#   en_US-lessac-medium.onnx.json
# Put them anywhere, e.g. backend/voices/, then in .env:
PIPER_VOICE_MODEL_PATH=./voices/en_US-lessac-medium.onnx
```

## Going live with real models

1. Add `OPENROUTER_API_KEY` to `.env` — chat becomes adaptive immediately, no code changes.
2. `PROVIDER_MODE=free` (default) already wires real image/voice/video generation — see above.
3. Once you have Highfield's actual REST API spec (base URL, auth, request/response shape),
   fill in the three TODO methods in `backend/app/providers/highfield.py`. The graph nodes
   never need to change — they only depend on the provider interface.
4. Set `PROVIDER_MODE=live` and `HIGHFIELD_API_KEY` + `HIGHFIELD_BASE_URL` in `.env`.

## Seeding the stock fallback library

Only needed once you have a `PEXELS_API_KEY` (free tier is fine):

```bash
cd backend
python -m scripts.seed_stock_library
```

This pre-fetches a few clips per industry tag (restaurant, fitness, real_estate, fashion,
salon, retail, other) and stores them in Postgres + `backend/storage/stock_library/`. It's
never called live during a user's session — only read from at retry-exhaustion time.

## Cost notes

- Chat: gpt-4o-mini, ~7 short turns per lead — a few cents at most.
- Teaser video: exactly 1 subject image + 1 TTS call + 1 video-model call per attempt, capped
  at `MAX_GENERATION_ATTEMPTS` (default 2) before falling back to free stock footage.
- No Celery/Redis/Cloudinary yet — background jobs run as FastAPI `BackgroundTasks` and
  assembly is local ffmpeg. Fine for localhost testing and low volume; revisit before scaling.
