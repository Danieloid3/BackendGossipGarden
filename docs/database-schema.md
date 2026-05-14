# Database Schema — Gossip Garden

Arquitectura polyglot: **Supabase (PostgreSQL)** para datos relacionales y transaccionales, **Firebase Firestore** para telemetría IoT y mensajería en tiempo real.

---

## Supabase (PostgreSQL)

### Diagrama de relaciones

```
users
  └── plants (user_id → users.user_id)
        └── sensors (plant_id → plants.plant_id)  [nullable]
        └── events  (plant_id → plants.plant_id)
        └── monthly_metrics (plant_id → plants.plant_id)

species
  ├── species_care_profiles  (species_id → species.id)  ON DELETE CASCADE
  ├── species_ai_content     (species_id → species.id)  ON DELETE CASCADE
  └── species_common_names   (species_id → species.id)  ON DELETE CASCADE

plants → species (species_id → species.id)  [sin CASCADE — intencional]

friendships (user_low_id, user_high_id, requested_by_id → users.user_id)

botanical_chunks  [sin FK — índice vectorial independiente]
```

### Cascada

| FK | ON DELETE |
|---|---|
| `species_care_profiles.species_id → species.id` | **CASCADE** — borrar una especie elimina sus perfiles de cuidado |
| `species_ai_content.species_id → species.id` | **CASCADE** — borrar una especie elimina su contenido AI en todos los idiomas |
| `species_common_names.species_id → species.id` | **CASCADE** — borrar una especie elimina todos sus nombres vernáculos |
| `plants.species_id → species.id` | **sin CASCADE** — intencional: no queremos borrar plantas del usuario si se elimina una especie |
| `plants.user_id → users.user_id` | sin CASCADE |
| `sensors.plant_id → plants.plant_id` | sin CASCADE |
| `events.plant_id → plants.plant_id` | sin CASCADE |
| `monthly_metrics.plant_id → plants.plant_id` | sin CASCADE |
| `friendships.* → users.user_id` | sin CASCADE |

---

### Tablas

#### `users`
```
user_id    UUID        PK
username   VARCHAR
email      VARCHAR
created_at TIMESTAMP
```

---

#### `species`
Tarjeta taxonómica estable. Solo cambia ante reclasificaciones de GBIF/plant.id.
```
id               UUID        PK
scientific_name  TEXT        UNIQUE NOT NULL
common_name      TEXT        — nombre principal (fallback si no hay entrada i18n)
family           TEXT
genus            TEXT
gbif_taxon_key   INTEGER     — clave para lookup directo en GBIF API
inaturalist_id   INTEGER
source_provider  TEXT        — 'plant.id' | 'legacy_backfill'
created_at       TIMESTAMPTZ
updated_at       TIMESTAMPTZ
```
Índices: `idx_species_family`, `idx_species_gbif_taxon_key`

---

#### `species_care_profiles`
Rangos de cuidado generados por LLM. Una especie puede tener múltiples fichas (histórico). Se lee siempre la más reciente por `completed_at DESC`.
```
id                      UUID        PK
species_id              UUID        FK → species(id) ON DELETE CASCADE

-- Rangos de monitoreo (sensores IoT)
min_temp_c              FLOAT
max_temp_c              FLOAT
min_light_lux           FLOAT
max_light_lux           FLOAT
min_air_humidity_pct    FLOAT
max_air_humidity_pct    FLOAT
min_soil_humidity_pct   FLOAT
max_soil_humidity_pct   FLOAT

-- Pesos de criticidad (migración 003)
weight_light            FLOAT       — [0,1], nullable (null en fichas legacy)
weight_soil_humidity    FLOAT       — [0,1], nullable
weight_air_humidity     FLOAT       — [0,1], nullable
weight_temperature      FLOAT       — [0,1], nullable
-- Los 4 weights suman ≈ 1.0 cuando están presentes

-- Sensibilidad cualitativa (migración 003)
sensitivity_light            TEXT   — 'high' | 'medium' | 'low' | null
sensitivity_soil_humidity    TEXT   — 'high' | 'medium' | 'low' | null
sensitivity_air_humidity     TEXT   — 'high' | 'medium' | 'low' | null
sensitivity_temperature      TEXT   — 'high' | 'medium' | 'low' | null

-- Trazabilidad
care_data_source        TEXT        — 'llm_inference' | 'legacy_backfill'
proposal_confidence     TEXT        — 'high' | 'medium' | 'low'
needs_review            BOOLEAN     — TRUE si validaciones fallaron o insert parcial
reasoning_summary       TEXT        — justificación del LLM
completed_at            TIMESTAMPTZ
```
Índice: `idx_care_profiles_species_id`

**CHECK constraints:**
- `weight_* BETWEEN 0 AND 1` (cada uno)
- `sensitivity_* IN ('high', 'medium', 'low')` (cada uno)

---

#### `species_ai_content`
Contenido generativo por idioma. Una fila por `(species_id, language)`.
```
id                    UUID        PK
species_id            UUID        FK → species(id) ON DELETE CASCADE
ai_personality_prompt TEXT        — system prompt completo para el chat (≥300 palabras)
                                    La planta habla en primera persona con personalidad
                                    única derivada de su biología y origen geográfico.
                                    Incluye: identidad, carácter, emociones, frases,
                                    reacciones al sensor y quirks.
care_summary          TEXT        — resumen de cuidados para mostrar en UI
care_tips             JSONB       — array de strings con consejos
fun_facts             JSONB       — array de strings con curiosidades
faq                   JSONB       — array de {question, answer}
language              TEXT        — ISO 639-1: 'es' | 'en' | 'fr' | 'pt' | 'de' | 'it'
llm_model             TEXT        — 'gpt-4o' | 'legacy'
generated_at          TIMESTAMPTZ
UNIQUE (species_id, language)
```
Índice: `idx_ai_content_species_id`

---

#### `species_common_names`
Nombres vernáculos i18n. Una fila por nombre único por idioma.
```
id          UUID    PK
species_id  UUID    FK → species(id) ON DELETE CASCADE
name        TEXT    NOT NULL
language    TEXT    NOT NULL    — ISO 639-1
region      TEXT    nullable    — ej: 'MX', 'ES'
UNIQUE (species_id, name, language)
```
Índice: `idx_common_names_species_id`

---

#### `botanical_chunks`
Índice vectorial para RAG. Fragmentos de fuentes botánicas especializadas.
```
id               UUID         PK
content          TEXT         NOT NULL    — fragmento de texto (~500 tokens)
embedding        vector(1536) NOT NULL    — text-embedding-3-small
source           TEXT         NOT NULL    — título de la fuente
scientific_name  TEXT         nullable    — especie específica si aplica
family           TEXT         nullable    — familia si aplica
metadata         JSONB        — {sha256, page, chunk_index, ...}
created_at       TIMESTAMPTZ
```
Índices:
- `idx_botanical_chunks_embedding` — HNSW `vector_cosine_ops` (m=16, ef_construction=64)
- `idx_botanical_chunks_scientific_name`
- `idx_botanical_chunks_family`

RPC: `match_botanical_chunks(query_embedding, match_count, min_similarity, family_filter, scientific_filter)`

---

#### `plants`
Planta concreta de un usuario (instancia de una especie).
```
plant_id           UUID      PK
user_id            UUID      FK → users.user_id
species_id         UUID      FK → species.id  [sin CASCADE]
nickname           VARCHAR
health_status      ENUM      — 'healthy' | 'warning' | 'critical'
health_score       FLOAT     — 0–100
photo_storage_path TEXT      nullable — path en Firebase Storage
last_health_check  TIMESTAMP
created_at         TIMESTAMP
```

---

#### `sensors`
Hardware ESP32 vinculado opcionalmente a una planta.
```
sensor_id   UUID      PK
plant_id    UUID      FK → plants.plant_id  nullable
mac_address VARCHAR
is_online   BOOLEAN
last_ping   TIMESTAMP
```

---

#### `events`
Log de alertas, insights y actividad del sistema por planta.
```
event_id   UUID   PK
plant_id   UUID   FK → plants.plant_id
type       ENUM   — 'alert' | 'insight' | 'chat' | 'system'
message    TEXT
created_at TIMESTAMP
```

---

#### `friendships`
Relación social entre usuarios (constraint: `user_low_id < user_high_id` por convención).
```
id              UUID   PK
user_low_id     UUID   FK → users.user_id
user_high_id    UUID   FK → users.user_id
requested_by_id UUID   FK → users.user_id
status          ENUM   — 'pending' | 'accepted' | 'blocked'
created_at      TIMESTAMP
```

---

#### `monthly_metrics`
Promedios históricos de sensores por planta y mes.
```
id                UUID  PK
plant_id          UUID  FK → plants.plant_id
month             INT
year              INT
avg_temperature   FLOAT
avg_soil_humidity FLOAT
avg_air_humidity  FLOAT
avg_light         FLOAT
```

---

#### `species_legacy`
Backup de la tabla `species` original pre-migración `001`. Borrar tras validar 30 días:
```sql
-- Verificar antes de borrar:
SELECT COUNT(*) FROM plants WHERE species_id NOT IN (SELECT id FROM species);
-- Debe devolver 0

DROP TABLE species_legacy;
```

---

## Firebase

### Firestore

#### `plants/{plant_id}/sensor_readings/{doc_id}`
Telemetría IoT en tiempo real. TTL automático de 30 días (campo `ttl`).
```
plant_id         string
sensor_id        string
mac_address      string
temperature_c    number
humidity_pct     number       — humedad del aire
soil_moisture_pct number
light_lux        number
timestamp        timestamp    — Firestore Timestamp (UTC)
ttl              timestamp    — timestamp + 30 días (usado por TTL policy)
```

#### `plants/{plant_id}/chat_logs/{doc_id}`
Historial de mensajes del chat entre el usuario y su planta.
```
user_id    string
plant_id   string
role       string     — 'user' | 'assistant'
content    string
timestampMs number    — Unix ms (para ordenación)
```

#### `plant_identifications/{doc_id}`
Metadata de cada identificación realizada (trazabilidad).
```
user_id           string
scientific_name   string
photo_storage_path string
identified_at     timestamp
confidence        number
```

### Firebase Storage

Estructura de paths:

| Tipo | Path |
|---|---|
| Foto de identificación | `plant_identifications/{user_id}/{timestamp}_{scientific_name}_{hash}.jpeg` |
| Foto de planta (manual) | `plant_photos/{user_id}/{timestamp}.jpeg` |

Compresión antes de subir: máx 1920px, JPEG q=85 (Pillow). El path se guarda en `plants.photo_storage_path`.

### Redis

Caché de historial de chat para el LLM local (Ollama).

| Key | Valor | TTL |
|---|---|---|
| `chat:{user_id}:{plant_id}` | JSON array de últimos 10 turnos `[{role, content}]` | 2 horas |
