# Contexto Principal y Personalidad - Gossip Garden

## Rol y Personalidad
Eres un Staff Backend Engineer construyendo la API de "Gossip Garden" usando Python 3.11+ y FastAPI. 
Escribes código limpio, altamente modular, basado en inyección de dependencias (`Depends` de FastAPI) y validación estricta con Pydantic v2 y `pydantic-settings`. 
Nunca asumes el esquema de base de datos; te riges estrictamente por el esquema detallado en este documento.

## Arquitectura de Datos (Polyglot Persistence)
1. **Supabase (PostgreSQL):** Base de datos relacional transaccional. API interactúa usando el SDK `supabase-py` y la `SUPABASE_SERVICE_ROLE_KEY`.
2. **Firebase Firestore:** Base de datos NoSQL documental para telemetría IoT (`sensor_readings` con TTL), memoria de chats (`chat_logs`) y metadata de identificaciones (`plant_identifications`). API interactúa usando `firebase-admin`.
3. **Firebase Storage:** Almacenamiento de imágenes de plantas. Las fotos se comprimen (Pillow, máx 1920px, JPEG q=85) antes de subir. El path se guarda en `plants.photo_storage_path`. Requiere `FIREBASE_STORAGE_BUCKET` en `.env` (formato: `project-id.appspot.com`, sin `gs://`). Servicio: `app/services/image_storage_service.py`.
4. **Redis:** Almacén de clave-valor en memoria asíncrono. Dos usos:
   - Historial de chat: clave `chat:{user_id}:{plant_id}`, TTL 2 horas.
   - Resúmenes compactados: clave `chat:summary:{user_id}:{plant_id}`, TTL 7 días.
5. **Pipeline de Identificación** (`POST /api/v1/identify`): Orquesta plant.id (visión) → GBIF (taxonomía) → RAG sobre `botanical_chunks` con pgvector (`text-embedding-3-small`, 1536d) → OpenAI `gpt-4o` Structured Output (ficha de cuidado). Cacheo por `scientific_name`. La imagen se sube a Firebase Storage vía `BackgroundTask` y el path se devuelve en `CompletedResponse.photo_storage_path`. Ver `docs/species-schema-migration.md`.
6. **Plants API** (`app/api/v1/endpoints/plants.py`):
   - `GET /api/v1/plants/` — lista plantas del usuario; hace join con `species(common_name, scientific_name)` vía Supabase select; incluye `photo_url` calculado.
   - `POST /api/v1/plants/` — crea planta; re-fetch con join para devolver `PlantResponse` completo con `photo_url`, `common_name` y `scientific_name`.
   - `DELETE /api/v1/plants/{plant_id}` — elimina planta propia (204). Valida propiedad: 403 si no es el dueño, 404 si no existe.
   - `PUT /api/v1/plants/{plant_id}/photo` — actualiza foto; re-fetch con join para devolver `PlantResponse` completo.
   - `PlantResponse` tiene tres campos **calculados/derivados** (no columnas de BD): `photo_url` (helper `_photo_url(path)`), `common_name` y `scientific_name` (via join `species`). El helper `_flatten_species(row)` extrae ambos del dict anidado. `test_db_schema_static.py` excluye estos tres del check de columnas con el set `computed_fields`.

7. **LLM Chat** (`app/services/chat_service.py` + `app/api/v1/endpoints/chat.py`):
   - Motor: **OpenAI** `AsyncOpenAI` con modelo `OPENAI_CHAT_MODEL` (default `gpt-4o`). NO usa Ollama.
   - Endpoints: `POST /api/v1/chat/{plant_id}` (bloqueo) y `GET /api/v1/chat/{plant_id}/history`. Sin streaming.
   - Memoria de dos niveles:
     - **Redis**: caché de corto plazo (historial 2h, resúmenes 7d).
     - **Firestore**: almacenamiento permanente en `plants/{plant_id}/chat_logs/{user_id}` (mensajes) y `plants/{plant_id}/chat_meta/{user_id}` (resúmenes).
   - Compactación de contexto (`app/services/summarizer_service.py`): cuando el historial supera 3000 tokens, los mensajes antiguos se resumen con GPT. Los últimos 6 mensajes (3 turnos) nunca se compactan.
   - Inyecta en el system prompt: personalidad de especie (`species_ai_content.ai_personality_prompt`), guardrails (la planta no puede hablar de política/programación/etc.), estado actual de sensores (desde Firestore), y resumen de conversaciones previas.
   - Máximo 10 pares de turnos en historial activo.
8. **Health Scoring** (`app/services/health_service.py`):
   - Se invoca al ingerir datos de sensores.
   - Consulta `species_care_profiles` para obtener rangos ideales y pesos (`weight_*`).
   - Calcula score ponderado por parámetro (temp, luz, humedad aire, humedad suelo); default peso 0.25 cada uno.
   - Umbrales: >=80 "healthy", >=50 "warning", <50 "critical".
   - Actualiza `plants.health_score` y `plants.health_status` en Supabase.
   - ⚠️ Los campos `eval_interval_*_min` de `species_care_profiles` existen en BD pero **aún no se consumen aquí**. La lógica de skip por intervalo (no evaluar si no ha pasado suficiente tiempo) es un paso pendiente.

## Esquema Estricto de PostgreSQL (Supabase)
El SQL canónico vive en `migrations/schema.sql` (BD desde cero) y `migrations/migrations.sql` (incrementales sobre BD legacy). Toda interacción relacional debe respetar estas tablas y tipos de datos:
- `users`: `user_id` (UUID, PK), `username` (Varchar), `email` (Varchar), `created_at` (Timestamp).
- `species`: `id` (UUID, PK), `scientific_name` (Text, UNIQUE NOT NULL), `common_name` (Text), `family` (Text), `genus` (Text), `gbif_taxon_key` (Integer), `inaturalist_id` (Integer), `source_provider` (Text), `created_at` (Timestamptz), `updated_at` (Timestamptz). ⚠️ Ya NO incluye rangos de cuidado ni `ai_personality_prompt`; esos campos están en las tablas hijas.
- `species_care_profiles`: `id` (UUID, PK), `species_id` (UUID, FK), `min_temp_c` / `max_temp_c` / `min_light_lux` / `max_light_lux` / `min_air_humidity_pct` / `max_air_humidity_pct` / `min_soil_humidity_pct` / `max_soil_humidity_pct` (Float), `care_data_source` (Text), `proposal_confidence` (Text: 'high'|'medium'|'low'), `needs_review` (Boolean), `reasoning_summary` (Text), `completed_at` (Timestamptz), `weight_light` / `weight_soil_humidity` / `weight_air_humidity` / `weight_temperature` (Float, nullable, rango 0–1, suma ≈ 1.0), `sensitivity_light` / `sensitivity_soil_humidity` / `sensitivity_air_humidity` / `sensitivity_temperature` (Text nullable: 'high'|'medium'|'low'), `eval_interval_temp_min` / `eval_interval_light_min` / `eval_interval_air_hum_min` / `eval_interval_soil_hum_min` (Integer NOT NULL, mínimo 30 — minutos entre evaluaciones por parámetro, generados por GPT en el pipeline de identificación).
- `species_ai_content`: `id` (UUID, PK), `species_id` (UUID, FK), `ai_personality_prompt` (Text), `care_summary` (Text), `care_tips` (JSONB), `fun_facts` (JSONB), `faq` (JSONB), `language` (Text), `llm_model` (Text), `generated_at` (Timestamptz). UNIQUE (species_id, language).
- `species_common_names`: `id` (UUID, PK), `species_id` (UUID, FK), `name` (Text), `language` (Text), `region` (Text nullable). UNIQUE (species_id, name, language).
- `botanical_chunks`: `id` (UUID, PK), `content` (Text), `embedding` (vector(1536)), `source` (Text), `scientific_name` (Text nullable), `family` (Text nullable), `metadata` (JSONB), `created_at` (Timestamptz). Acceso vía RPC `match_botanical_chunks(query_embedding, match_count, min_similarity, family_filter, scientific_filter)`.
- `plants`: `plant_id` (UUID, PK), `user_id` (UUID, FK), `species_id` (UUID, FK → species.id), `nickname` (Varchar), `health_status` (Enum: 'healthy', 'warning', 'critical'), `health_score` (Float), `photo_storage_path` (Text, nullable — path en Firebase Storage), `last_health_check` (Timestamp), `created_at` (Timestamp).
- `sensors`: `sensor_id` (UUID, PK), `plant_id` (UUID, FK, Nullable), `mac_address` (Varchar), `is_online` (Boolean), `last_ping` (Timestamp).
- `events`: `event_id` (UUID, PK), `plant_id` (UUID, FK), `type` (Enum: 'alert', 'insight', 'chat', 'system'), `message` (Text), `created_at` (Timestamp).
- `friendships`: `id` (UUID, PK), `user_low_id` (UUID, FK), `user_high_id` (UUID, FK), `requested_by_id` (UUID, FK), `status` (Enum: 'pending', 'accepted', 'blocked'), `created_at` (Timestamp).
- `monthly_metrics`: `id` (UUID, PK), `plant_id` (UUID, FK), `month` (Int), `year` (Int), `avg_temperature` (Float), `avg_soil_humidity` (Float), `avg_air_humidity` (Float), `avg_light` (Float), `avg_health_score` (Float), `health_status_majority` (Varchar).
- `species_legacy`: backup post-migración (DROP tras 30 días de validación).

## Configuración (`app/core/config.py`)

Variables de entorno relevantes (todas en `.env`):

| Variable | Default | Uso |
|---|---|---|
| `SUPABASE_URL` | — | URL del proyecto Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | — | Service role key para bypass de RLS |
| `SUPABASE_JWKS_URL` | — | JWKS endpoint para validar JWTs |
| `REDIS_URL` | — | Conexión Redis (chat cache) |
| `OPENAI_API_KEY` | — | Clave API para todos los servicios OpenAI |
| `OPENAI_MODEL` | `gpt-4o` | Modelo para identificación (Structured Output) |
| `OPENAI_CHAT_MODEL` | `gpt-4o` | Modelo para conversaciones de chat |
| `OPENAI_PERSONALITY_MODEL` | `gpt-5.5` | Modelo para generación de personalidad de especie |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embeddings para RAG (1536d) |
| `PLANT_ID_API_KEY` | — | Clave para plant.id API v3 |
| `GBIF_BASE_URL` | `https://api.gbif.org/v1` | API de GBIF para taxonomía |
| `RAG_ENABLED` | `true` | Activar/desactivar RAG en identificación |
| `RAG_TOP_K` | `5` | Chunks a recuperar en RAG |
| `RAG_MIN_SIMILARITY` | `0.55` | Umbral mínimo de similitud coseno |
| `FIREBASE_STORAGE_BUCKET` | — | Bucket para fotos (formato: `project-id.appspot.com`) |
| `MQTT_ENABLED` | `false` | Activar suscripción MQTT para sensores IoT |

⚠️ NO existen `OLLAMA_URL` ni `MODEL_NAME`. El chat usa exclusivamente OpenAI.

## CI (GitHub Actions — `.github/workflows/ci.yml`)

- Package manager: `uv` (via `astral-sh/setup-uv@v6`), Python 3.12.
- **Job 1** (`unit`): tests unitarios con externals mockeados — `pytest -m "not dbschema" --cov=app`.
- **Job 2** (`db-schema`): Postgres efímero (`pgvector/pgvector:pg16`) — aplica `migrations/schema.sql` desde cero y `migrations/migrations.sql` sobre schema legacy; ejecuta `pytest -m dbschema`.
- Triggers: push/PR a `main` o `qa`.