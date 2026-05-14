# Migración del Esquema de Species — Pipeline de Identificación

> **Fecha:** 2026-05-13  
> **Migración SQL:** `migrations/001_species_pipeline.sql`

---

## 1. Motivación

El esquema original de `species` mezclaba en una sola tabla datos de naturaleza muy distinta:

| Problema | Consecuencia |
|---|---|
| Rangos de sensores y datos de personalidad AI en la misma fila | Imposible trazar qué datos vienen de qué fuente |
| Un solo campo `common_name` | No permite internacionalización (una planta tiene nombre en español, inglés, latín...) |
| `ai_personality_prompt` en la tabla de taxonomía | No se puede regenerar contenido AI sin tocar la ficha taxonómica |
| No hay `needs_review` por ficha | Un rango incorrecto bloquea o contamina toda la especie |

La migración introduce 4 tablas especializadas + una tabla de RAG, **preservando los `id` UUID existentes** para que `plants.species_id` siga siendo válido sin migrar datos del cliente.

---

## 2. Esquema anterior (`species` original)

```
species:
  id                   UUID PK
  common_name          Varchar
  scientific_name      Varchar
  ai_personality_prompt Text
  min_temp_c           Float
  max_temp_c           Float
  min_soil_humidity_pct Float
  max_soil_humidity_pct Float
  min_light_lux        Float
  max_light_lux        Float
  min_air_humidity_pct Float
  max_air_humidity_pct Float
```

---

## 3. Esquema nuevo — 4 tablas + `botanical_chunks`

### `species` (tarjeta taxonómica estable)
```
id                UUID PK
scientific_name   TEXT UNIQUE NOT NULL
common_name       TEXT           ← nombre principal en español
family            TEXT
genus             TEXT
gbif_taxon_key    INTEGER        ← clave GBIF para lookups directos
inaturalist_id    INTEGER
source_provider   TEXT           ← 'plant.id' | 'legacy_backfill'
created_at        TIMESTAMPTZ
updated_at        TIMESTAMPTZ
```

### `species_care_profiles` (rangos de cuidado por ficha AI)
```
id                    UUID PK
species_id            UUID FK → species(id)
min_temp_c            FLOAT
max_temp_c            FLOAT
min_light_lux         FLOAT
max_light_lux         FLOAT
min_air_humidity_pct  FLOAT
max_air_humidity_pct  FLOAT
min_soil_humidity_pct FLOAT
max_soil_humidity_pct FLOAT
care_data_source      TEXT           ← 'llm_inference' | 'legacy_backfill'
proposal_confidence   TEXT           ← 'high' | 'medium' | 'low'
needs_review          BOOLEAN        ← TRUE mientras no haya validación humana
reasoning_summary     TEXT
completed_at          TIMESTAMPTZ
```

### `species_ai_content` (contenido generativo por idioma)
```
id                    UUID PK
species_id            UUID FK → species(id)
ai_personality_prompt TEXT
care_summary          TEXT
care_tips             JSONB
fun_facts             JSONB
faq                   JSONB
language              TEXT           ← ISO 639-1 ('es', 'en', 'fr'...)
llm_model             TEXT           ← 'gpt-4o' | 'legacy'
generated_at          TIMESTAMPTZ
UNIQUE (species_id, language)
```

### `species_common_names` (nombres vernáculos i18n)
```
id          UUID PK
species_id  UUID FK → species(id)
name        TEXT
language    TEXT
region      TEXT (nullable)
UNIQUE (species_id, name, language)
```

### `botanical_chunks` (RAG con pgvector)
```
id               UUID PK
content          TEXT
embedding        vector(1536)     ← text-embedding-3-small
source           TEXT             ← título del libro/guía
scientific_name  TEXT (nullable)
family           TEXT (nullable)
metadata         JSONB            ← incluye hash SHA-256 para dedup
created_at       TIMESTAMPTZ
```
Índice HNSW: `USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)`

---

## 4. Trazabilidad de campos (antiguo → nuevo)

| Campo antiguo | Campo nuevo | Tabla nueva |
|---|---|---|
| `species.common_name` | `species.common_name` (principal) | `species` |
| `species.common_name` | `species_common_names.name` | `species_common_names` (i18n) |
| `species.scientific_name` | `species.scientific_name` | `species` |
| `species.ai_personality_prompt` | `species_ai_content.ai_personality_prompt` | `species_ai_content` |
| `species.min_temp_c, max_temp_c` | `species_care_profiles.min_temp_c, max_temp_c` | `species_care_profiles` |
| `species.min_light_lux, max_light_lux` | `species_care_profiles.min_light_lux, max_light_lux` | `species_care_profiles` |
| `species.min_air_humidity_pct, max_air_humidity_pct` | `species_care_profiles.min_air_humidity_pct, max_air_humidity_pct` | `species_care_profiles` |
| `species.min_soil_humidity_pct, max_soil_humidity_pct` | `species_care_profiles.min_soil_humidity_pct, max_soil_humidity_pct` | `species_care_profiles` |
| — | `species.family, genus, gbif_taxon_key, inaturalist_id` | `species` (nuevo) |
| — | `species_care_profiles.needs_review, proposal_confidence, reasoning_summary` | `species_care_profiles` (nuevo) |
| — | `species_ai_content.care_summary, care_tips, fun_facts, faq, language, llm_model` | `species_ai_content` (nuevo) |

---

## 5. Por qué 4 tablas y no una sola

**Separación por responsabilidad y ciclo de vida:**

- **`species`** es estable: viene de GBIF/plant.id, cambia cuando hay un reclasificación taxonómica global. No debería tocarla cada vez que se regenera contenido AI.
- **`species_care_profiles`** es una propuesta del LLM y puede estar equivocada. `needs_review=TRUE` por defecto la marca para validación humana sin bloquear el lanzamiento.
- **`species_ai_content`** por idioma permite que el mismo pipeline genere contenido en español para un usuario y en inglés para otro, sin duplicar la taxonomía.
- **`species_common_names`** i18n real: una Sansevieria se llama "snake plant" en inglés, "lengua de suegra" en español, "Bogenhanf" en alemán. Un solo campo `common_name` no puede representar eso.
- **`botanical_chunks`** es el índice vectorial del RAG: independiente de cualquier especie concreta, crece con nuevas fuentes sin tocar las tablas transaccionales.

---

## 6. Estrategia de migración no destructiva

El script `migrations/001_species_pipeline.sql` realiza estas operaciones en una transacción:

1. **`ALTER TABLE species RENAME TO species_legacy`** — los datos históricos quedan intactos.
2. **`CREATE TABLE species (...)`** — nueva tabla con los `id` correctos.
3. **`INSERT INTO species ... SELECT id, ... FROM species_legacy`** — copia los `id` UUID, preservando las FK de `plants.species_id`.
4. **Backfill** de `species_care_profiles`, `species_ai_content`, `species_common_names` desde `species_legacy`.
5. **Restaura FK** `plants.species_id → species(id)`.

`species_legacy` se **mantiene 30 días** como backup. Antes de borrarla, verificar:
```sql
SELECT COUNT(*) FROM plants WHERE species_id NOT IN (SELECT id FROM species);
-- Debe devolver 0
```
Cuando esté confirmado:
```sql
DROP TABLE species_legacy;
```

---

## 7. Compatibilidad con el frontend

- `plants.species_id` (UUID FK) **no cambia**. El endpoint `GET /api/v1/plants` sigue funcionando igual.
- Los nuevos endpoints `/api/v1/identify` y `/api/v1/species/from-candidate` son **aditivos**.
- El campo `ai_personality_prompt` que el chat endpoint necesita ahora se lee de `species_ai_content` en vez de `species` directamente — el endpoint de chat habrá de actualizarse cuando se implemente.

---

## 8. Fuentes RAG

`botanical_sources/` se commitea vacía (`.gitkeep`). Para activar el RAG con valor real:

```bash
# Agregar PDFs/TXTs de fuentes botánicas:
cp /path/to/rhs_encyclopedia.pdf botanical_sources/Asparagaceae__Sansevieria_trifasciata__RHS_Encyclopedia.pdf

# Ingestar:
python scripts/ingest_botanical_sources.py --dry-run   # preview
python scripts/ingest_botanical_sources.py             # insertar
```

Fuentes recomendadas: RHS Encyclopedia of Plants and Flowers, The Complete Houseplant Survival Manual (Pleasant), fichas USDA/FAO.

El pipeline funciona sin RAG (devuelve `reasoning_summary` basado solo en plant.id + GBIF + conocimiento base del LLM, con `proposal_confidence` tendiendo a `medium`/`low` para especies raras).
