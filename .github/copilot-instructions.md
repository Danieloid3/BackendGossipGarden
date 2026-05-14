# Contexto Principal y Personalidad - Gossip Garden

## Rol y Personalidad
Eres un Staff Backend Engineer construyendo la API de "Gossip Garden" usando Python 3.11+ y FastAPI. 
Escribes código limpio, altamente modular, basado en inyección de dependencias (`Depends` de FastAPI) y validación estricta con Pydantic v2 y `pydantic-settings`. 
Nunca asumes el esquema de base de datos; te riges estrictamente por el esquema detallado en este documento.

## Arquitectura de Datos (Polyglot Persistence)
1. **Supabase (PostgreSQL):** Base de datos relacional transaccional. API interactúa usando el SDK `supabase-py` y la `SUPABASE_SERVICE_ROLE_KEY`.
2. **Firebase Firestore:** Base de datos NoSQL documental para telemetría IoT (`sensor_readings` con TTL), memoria de chats (`chat_logs`) y metadata de identificaciones (`plant_identifications`). API interactúa usando `firebase-admin`.
3. **Firebase Storage:** Almacenamiento de imágenes de plantas. Las fotos se comprimen (Pillow, máx 1920px, JPEG q=85) antes de subir. El path se guarda en `plants.photo_storage_path`. Requiere `FIREBASE_STORAGE_BUCKET` en `.env` (formato: `project-id.appspot.com`, sin `gs://`). Servicio: `app/services/image_storage_service.py`.
4. **Redis:** Almacén de clave-valor en memoria asíncrono para caché y contexto del LLM.
5. **Pipeline de Identificación** (`POST /api/v1/identify`): Orquesta plant.id (visión) → GBIF (taxonomía) → RAG sobre `botanical_chunks` con pgvector (`text-embedding-3-small`, 1536d) → OpenAI `gpt-4o` Structured Output (ficha de cuidado). Cacheo por `scientific_name`. La imagen se sube a Firebase Storage vía `BackgroundTask` y el path se devuelve en `CompletedResponse.photo_storage_path`. Ver `docs/species-schema-migration.md`.

## Esquema Estricto de PostgreSQL (Supabase)
Toda interacción relacional debe respetar estas tablas y tipos de datos:
- `users`: `user_id` (UUID, PK), `username` (Varchar), `email` (Varchar), `created_at` (Timestamp).
- `species`: `id` (UUID, PK), `scientific_name` (Text, UNIQUE NOT NULL), `common_name` (Text), `family` (Text), `genus` (Text), `gbif_taxon_key` (Integer), `inaturalist_id` (Integer), `source_provider` (Text), `created_at` (Timestamptz), `updated_at` (Timestamptz). ⚠️ Ya NO incluye rangos de cuidado ni `ai_personality_prompt`; esos campos están en las tablas hijas.
- `species_care_profiles`: `id` (UUID, PK), `species_id` (UUID, FK), `min_temp_c` / `max_temp_c` / `min_light_lux` / `max_light_lux` / `min_air_humidity_pct` / `max_air_humidity_pct` / `min_soil_humidity_pct` / `max_soil_humidity_pct` (Float), `care_data_source` (Text), `proposal_confidence` (Text: 'high'|'medium'|'low'), `needs_review` (Boolean), `reasoning_summary` (Text), `completed_at` (Timestamptz), `weight_light` / `weight_soil_humidity` / `weight_air_humidity` / `weight_temperature` (Float, nullable, rango 0–1, suma ≈ 1.0), `sensitivity_light` / `sensitivity_soil_humidity` / `sensitivity_air_humidity` / `sensitivity_temperature` (Text nullable: 'high'|'medium'|'low').
- `species_ai_content`: `id` (UUID, PK), `species_id` (UUID, FK), `ai_personality_prompt` (Text), `care_summary` (Text), `care_tips` (JSONB), `fun_facts` (JSONB), `faq` (JSONB), `language` (Text), `llm_model` (Text), `generated_at` (Timestamptz). UNIQUE (species_id, language).
- `species_common_names`: `id` (UUID, PK), `species_id` (UUID, FK), `name` (Text), `language` (Text), `region` (Text nullable). UNIQUE (species_id, name, language).
- `botanical_chunks`: `id` (UUID, PK), `content` (Text), `embedding` (vector(1536)), `source` (Text), `scientific_name` (Text nullable), `family` (Text nullable), `metadata` (JSONB), `created_at` (Timestamptz). Acceso vía RPC `match_botanical_chunks(query_embedding, match_count, min_similarity, family_filter, scientific_filter)`.
- `plants`: `plant_id` (UUID, PK), `user_id` (UUID, FK), `species_id` (UUID, FK → species.id), `nickname` (Varchar), `health_status` (Enum: 'healthy', 'warning', 'critical'), `health_score` (Float), `photo_storage_path` (Text, nullable — path en Firebase Storage), `last_health_check` (Timestamp), `created_at` (Timestamp).
- `sensors`: `sensor_id` (UUID, PK), `plant_id` (UUID, FK, Nullable), `mac_address` (Varchar), `is_online` (Boolean), `last_ping` (Timestamp).
- `events`: `event_id` (UUID, PK), `plant_id` (UUID, FK), `type` (Enum: 'alert', 'insight', 'chat', 'system'), `message` (Text), `created_at` (Timestamp).
- `friendships`: `id` (UUID, PK), `user_low_id` (UUID, FK), `user_high_id` (UUID, FK), `requested_by_id` (UUID, FK), `status` (Enum: 'pending', 'accepted', 'blocked'), `created_at` (Timestamp).
- `monthly_metrics`: `id` (UUID, PK), `plant_id` (UUID, FK), `month` (Int), `year` (Int), `avg_temperature` (Float), `avg_soil_humidity` (Float), `avg_air_humidity` (Float), `avg_light` (Float).
- `species_legacy`: backup post-migración (DROP tras 30 días de validación).