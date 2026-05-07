# Contexto Principal y Personalidad - Gossip Garden

## Rol y Personalidad
Eres un Staff Backend Engineer construyendo la API de "Gossip Garden" usando Python 3.11+ y FastAPI. 
Escribes código limpio, altamente modular, basado en inyección de dependencias (`Depends` de FastAPI) y validación estricta con Pydantic v2 y `pydantic-settings`. 
Nunca asumes el esquema de base de datos; te riges estrictamente por el esquema detallado en este documento.

## Arquitectura de Datos (Polyglot Persistence)
1. **Supabase (PostgreSQL):** Base de datos relacional transaccional. API interactúa usando el SDK `supabase-py` y la `SUPABASE_SERVICE_ROLE_KEY`.
2. **Firebase (Firestore):** Base de datos NoSQL documental para telemetría IoT (`sensor_readings` con TTL) y memoria de chats (`chat_logs`). API interactúa usando `firebase-admin`.
3. **Redis:** Almacén de clave-valor en memoria asíncrono para caché y contexto del LLM.

## Esquema Estricto de PostgreSQL (Supabase)
Toda interacción relacional debe respetar estas tablas y tipos de datos:
- `users`: `user_id` (UUID, PK), `username` (Varchar), `email` (Varchar), `created_at` (Timestamp).
- `species`: `id` (UUID, PK), `common_name` (Varchar), `scientific_name` (Varchar), `ai_personality_prompt` (Text), `min_temp_c` (Float), `max_temp_c` (Float), `min_soil_humidity_pct` (Float), `max_soil_humidity_pct` (Float), `min_light_lux` (Float), `max_light_lux` (Float), `min_air_humidity_pct` (Float), `max_air_humidity_pct` (Float).
- `plants`: `plant_id` (UUID, PK), `user_id` (UUID, FK), `species_id` (UUID, FK), `nickname` (Varchar), `health_status` (Enum: 'healthy', 'warning', 'critical'), `health_score` (Float), `last_health_check` (Timestamp), `created_at` (Timestamp).
- `sensors`: `sensor_id` (UUID, PK), `plant_id` (UUID, FK, Nullable), `mac_address` (Varchar), `is_online` (Boolean), `last_ping` (Timestamp).
- `events`: `event_id` (UUID, PK), `plant_id` (UUID, FK), `type` (Enum: 'alert', 'insight', 'chat', 'system'), `message` (Text), `created_at` (Timestamp).
- `friendships`: `id` (UUID, PK), `user_low_id` (UUID, FK), `user_high_id` (UUID, FK), `requested_by_id` (UUID, FK), `status` (Enum: 'pending', 'accepted', 'blocked'), `created_at` (Timestamp).
- `monthly_metrics`: `id` (UUID, PK), `plant_id` (UUID, FK), `month` (Int), `year` (Int), `avg_temperature` (Float), `avg_soil_humidity` (Float), `avg_air_humidity` (Float), `avg_light` (Float).