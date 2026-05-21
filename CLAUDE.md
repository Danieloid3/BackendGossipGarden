# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run locally
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Run with Docker (API + Redis, hot-reload)
docker-compose up

# Tests
pytest                     # all tests
pytest tests/              # explicit dir
pytest -k <test_name>      # single test
```

Required before running: populate `.env` from `.env.example`, and provide `firebase_credentials.json` (or set `FIREBASE_CREDENTIALS_JSON` env var).

## Architecture

**FastAPI** backend with polyglot persistence and an AI-driven plant identification + chatbot pipeline.

### Data layer

| Store | Usage |
|---|---|
| **Supabase (PostgreSQL)** | Relational data, transactions, pgvector RAG |
| **Firebase Firestore** | IoT telemetry (`sensor_readings` w/ TTL), chat logs, identification metadata |
| **Firebase Storage** | Plant images (compressed to max 1920px JPEG q=85 before upload) |
| **Redis** | Async cache for LLM context (2h TTL), compacted summaries (7d TTL) |

### Request path

```
app/main.py          # lifespan: verifies all DB connections, starts MQTT if enabled
app/api/v1/api.py    # router registration
app/api/v1/endpoints/<domain>.py   # HTTP layer
app/services/<domain>_service.py   # business logic
app/schemas/<domain>.py            # Pydantic v2 request/response models
app/db/{supabase,firebase,redis}.py  # DB clients (imported as singletons)
app/core/config.py   # pydantic-settings (all env vars)
```

### Plant identification pipeline (`POST /api/v1/identify`)

Image → plant.id API → GBIF taxonomy → pgvector RAG on `botanical_chunks` → OpenAI `gpt-4o` Structured Output → cached in Redis by `scientific_name` → image uploaded to Firebase Storage via `BackgroundTask`.

Confidence thresholds: `< IDENT_CONFIDENCE_LOW (0.25)` → needs more photos; `0.25–0.75` → user selection (up to 3 candidates); `> 0.75` → auto-completed.

### Chatbot pipeline (`/api/v1/chat/{plant_id}/*`)

Load `ai_personality_prompt` from `species_ai_content` → load plant health state → load history from Redis (fallback: Firestore) → context compaction if > 3000 tokens (summarize old messages, keep last 6) → topic guardrails (block politics, religion, off-topic) → OpenAI `gpt-4o` → store in Redis + Firestore.

## PostgreSQL schema (Supabase)

Canonical SQL: `migrations/schema.sql` (from scratch) and `migrations/migrations.sql` (incremental). Never assume column names — read the schema files.

Key constraints:
- `species` does **not** contain care ranges or personality — those live in `species_care_profiles` and `species_ai_content`.
- `species_care_profiles`: weight fields (`weight_light`, etc.) are nullable floats 0–1, should sum ≈ 1.0. Sensitivity fields are nullable `'high'|'medium'|'low'`.
- `species_ai_content`: UNIQUE on `(species_id, language)`.
- `botanical_chunks`: queried via Supabase RPC `match_botanical_chunks(query_embedding, match_count, min_similarity, family_filter, scientific_filter)` using pgvector (1536-dim, `text-embedding-3-small`).
- `plants.photo_storage_path`: path in Firebase Storage (not a full URL).
- `FIREBASE_STORAGE_BUCKET` must be `project-id.appspot.com` format (no `gs://` prefix).

## Git workflow

Branch types: `feat/*`, `fix/*`, `bug/*`, `refactor/*`, `docs/*`, `test/*`, `chore/*`  
Flow: `feature branch → qa → main` (never push directly to main)  
Commits: Conventional Commits — `<type>(<scope>): <description>` e.g. `feat(chat): add TTS support`

## Key env vars

See `.env.example` for the full list. Notable ones beyond the obvious:
- `ELEVENLABS_API_KEY` — TTS (feature/chatbot-TTS branch)
- `OPENAI_PERSONALITY_MODEL` — defaults to `gpt-5.5` for personality generation
- `LLM_DEFAULT_OUTPUT_LANGUAGE` — defaults to `es`
- `RAG_ENABLED`, `RAG_TOP_K`, `RAG_MIN_SIMILARITY` — tune RAG behavior
- `MQTT_ENABLED` — MQTT is opt-in; set to `true` only when IoT broker is available
