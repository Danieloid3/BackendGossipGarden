# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

**Prerequisites:**
- Python 3.12+ (or use `uv`)
- Populate `.env` from `.env.example`
- Provide `firebase_credentials.json` OR set `FIREBASE_CREDENTIALS_JSON` env var with JSON string

**Run locally:**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Run with Docker (API + Redis, hot-reload):**
```bash
docker-compose up
```

---

## Testing

```bash
# All tests (unit + integration)
pytest

# Unit tests only (external services mocked)
pytest -m "not dbschema"

# Database schema validation (requires local Postgres + pgvector)
pytest -m dbschema

# With coverage
pytest --cov=app

# Single test file
pytest tests/test_auth.py

# Single test function
pytest tests/test_auth.py::test_register_user

# Verbose output
pytest -v
```

**Local DB schema testing**: Start a Postgres container with pgvector:
```bash
docker run --rm -d -p 5432:5432 -e POSTGRES_PASSWORD=ci pgvector/pgvector:pg16
PGPASSWORD=ci psql -h localhost -U postgres -d postgres -c "CREATE DATABASE gg_schema;"
PGPASSWORD=ci psql -h localhost -U postgres -d gg_schema -f migrations/schema.sql
pytest -m dbschema
```

---

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

Confidence thresholds: `< 0.25` → needs more photos; `0.25–0.75` → user selection (up to 3 candidates); `> 0.75` → auto-completed.

### Chatbot pipeline (`/api/v1/chat/{plant_id}/*`)

Load `ai_personality_prompt` from `species_ai_content` → load plant health state → load history from Redis (fallback: Firestore) → context compaction if > 3000 tokens (summarize old messages, keep last 6) → topic guardrails → OpenAI `gpt-4o` → store in Redis + Firestore → **push real-time via `notification_service.notify()`**.

### Real-time notifications (`/api/v1/notifications/*`, `/api/v1/devices/*`)

Two parallel channels fan out from a single point (`notification_service.notify()`):

- **WebSocket** (`WS /notifications/ws?token=<jwt>`): in-memory `ConnectionManager` (`app/services/websocket_manager.py`) keeps per-user connections. JWT goes in query string because WS clients can't reliably set headers. Stateful — if you scale beyond one Railway instance, add Redis pub/sub.
- **FCM** (`app/services/fcm_service.py`): wraps `firebase_admin.messaging`. Reads tokens from `device_tokens` table. Auto-cleans dead tokens on `UNREGISTERED`/`invalid-argument`.

Trigger points:
- Inside `chat_with_plant()` — pushes the bot's reply at the end. `send_fcm=False` for normal chat (user is already in-app), `send_fcm=True` for `is_proactive=True` (evaluator alerts).
- The evaluator (`evaluator_service.py`) needs no changes — it already calls `chat_with_plant(is_proactive=True)` in a background task; the notify happens automatically when that completes.

`notify()` swallows all errors so a push failure can't break the chat response.

Endpoints:
- `POST /devices` upserts an FCM token (`{ token, platform: ios|android|web }`)
- `DELETE /devices/{token}` (logout)
- `GET /notifications?limit=50` returns history from `events` table, filtered to plants owned by the user

---

## PostgreSQL schema (Supabase)

Canonical SQL: `migrations/schema.sql` (from scratch) and `migrations/migrations.sql` (incremental). **Never assume column names — read the schema files.**

Key constraints:
- `species` does **not** contain care ranges or personality — those live in `species_care_profiles` and `species_ai_content`.
- `species_care_profiles`: weight fields nullable floats 0–1, should sum ≈ 1.0.
- `species_ai_content`: UNIQUE on `(species_id, language)`.
- `botanical_chunks`: queried via Supabase RPC `match_botanical_chunks(...)` using pgvector (1536-dim).
- `plants.photo_storage_path`: path in Firebase Storage (not a full URL).
- `plants.photo_url`: **computed field**, not a DB column. Built by `_photo_url()` in `app/api/v1/endpoints/plants.py` from `photo_storage_path` + `FIREBASE_STORAGE_BUCKET`. Returned by `GET /plants/`, `POST /plants/`, and `PUT /plants/{plant_id}/photo`. Excluded from schema validation via `computed_fields` in `tests/test_db_schema_static.py`.
- `plants.common_name` / `plants.scientific_name`: **join-derived fields**, not DB columns on `plants`. Fetched via `select('*, species(common_name, scientific_name)')` and flattened by `_flatten_species(row)`. Also excluded via `computed_fields` in the schema test.
- `FIREBASE_STORAGE_BUCKET` must be `project-id.appspot.com` (no `gs://` prefix).
- `DELETE /plants/{plant_id}`: returns 204; validates ownership (403 if not owner, 404 if not found).
- `device_tokens`: stores FCM push tokens per user. `ON DELETE CASCADE` from `users`. Token `UNIQUE` — upsert on conflict to support re-login across users.
- `events`: log-only (no `read_at`/`user_id`). To query events for a user you must join through `plants.user_id`.

---

## Git workflow

Branch types: `feat/*`, `fix/*`, `bug/*`, `refactor/*`, `docs/*`, `test/*`, `chore/*`  
Flow: `feature branch → qa → main` — **never push directly to main**  
Commits: Conventional Commits — `<type>(<scope>): <description>`

---

## Key env vars

See `.env.example` for the full list. Notable ones:
- `OPENAI_PERSONALITY_MODEL` — defaults to `gpt-5.5` for personality generation
- `LLM_DEFAULT_OUTPUT_LANGUAGE` — defaults to `es`
- `RAG_ENABLED`, `RAG_TOP_K`, `RAG_MIN_SIMILARITY` — tune RAG behavior
- `MQTT_ENABLED` — opt-in; set `true` only when IoT broker is available
- `ELEVENLABS_API_KEY` — TTS (branch feature/chatbot-TTS)

---

## Debugging & Common Issues

**"App already exists" — Firebase initialization**
- Firebase client is a singleton initialized once per process. In tests with `mock.patch`, ensure `firebase_admin._apps` is cleared if re-running inits.

**"connection refused" — Redis/Postgres**
- Docker: run `docker-compose up` first, or check ports: `docker ps`
- Tests: unit tests mock these; only `pytest -m dbschema` needs real Postgres

**"Token invalid" — Supabase JWT**
- Verify `SUPABASE_JWKS_URL` and `SUPABASE_SERVICE_ROLE_KEY` are correct
- Check `Authorization: Bearer <token>` header is present in requests

**"Storage path wrong" — Firebase Storage uploads**
- `FIREBASE_STORAGE_BUCKET` must be `project-id.appspot.com` (no `gs://` prefix)
- `plants.photo_storage_path` is a path, not a full URL — e.g., `users/uuid/img.jpg`

**Linting/formatting**
- CI runs no linting checks (ruff/black/mypy). Code style is enforced via code review.

---

## Development Notes

- **Async code**: All database and HTTP calls are async; use `async def` and `await` throughout.
- **Dependency injection**: Use FastAPI `Depends()` for DB clients and auth — never import singletons directly in endpoint handlers.
- **Schema first**: Always read `migrations/schema.sql` before writing DB queries; column names and constraints define behavior.
- **No direct Firestore/Redis access in endpoints**: Use service layer (`app/services/`) to isolate DB logic.
- **Structured Output**: Identification and personality generation use OpenAI's `response_format` parameter — test with actual API calls, not mocks.
