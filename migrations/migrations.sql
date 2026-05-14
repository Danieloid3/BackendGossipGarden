-- ============================================================
-- migrations.sql — Gossip Garden
-- Migraciones incrementales unificadas (001 + 002 + 003 + 004).
-- Aplicar sobre una BD existente con el esquema legacy.
-- ============================================================


-- ============================================================
-- 001 — Pipeline plant.id → GBIF → RAG → OpenAI
-- Migración no destructiva: preserva plants.species_id y datos
-- existentes renombrando la tabla species como backup.
-- ============================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS vector;

-- Desconectar FK de plants temporalmente
ALTER TABLE plants DROP CONSTRAINT IF EXISTS plants_species_id_fkey;

-- Renombrar species existente como backup
ALTER TABLE species RENAME TO species_legacy;

-- Nueva tabla species (sin rangos, sin prompt)
CREATE TABLE species (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  scientific_name  TEXT        NOT NULL UNIQUE,
  common_name      TEXT,
  family           TEXT,
  genus            TEXT,
  gbif_taxon_key   INTEGER,
  inaturalist_id   INTEGER,
  source_provider  TEXT        DEFAULT 'legacy_backfill',
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_species_family         ON species(family);
CREATE INDEX idx_species_gbif_taxon_key ON species(gbif_taxon_key);

-- Backfill preservando IDs (FK de plants sigue válida)
INSERT INTO species (id, scientific_name, common_name, source_provider, created_at, updated_at)
SELECT
  id,
  COALESCE(NULLIF(TRIM(scientific_name), ''), 'unknown_' || id::text),
  common_name,
  'legacy_backfill',
  NOW(),
  NOW()
FROM species_legacy
ON CONFLICT (scientific_name) DO NOTHING;

-- Tablas hijas de species
CREATE TABLE species_care_profiles (
  id                    UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  species_id            UUID    NOT NULL REFERENCES species(id) ON DELETE CASCADE,
  min_temp_c            FLOAT,
  max_temp_c            FLOAT,
  min_light_lux         FLOAT,
  max_light_lux         FLOAT,
  min_air_humidity_pct  FLOAT,
  max_air_humidity_pct  FLOAT,
  min_soil_humidity_pct FLOAT,
  max_soil_humidity_pct FLOAT,
  care_data_source      TEXT    DEFAULT 'llm_inference',
  proposal_confidence   TEXT    CHECK (proposal_confidence IN ('high', 'medium', 'low')),
  needs_review          BOOLEAN DEFAULT TRUE,
  reasoning_summary     TEXT,
  completed_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_care_profiles_species_id ON species_care_profiles(species_id);

CREATE TABLE species_ai_content (
  id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  species_id            UUID        NOT NULL REFERENCES species(id) ON DELETE CASCADE,
  ai_personality_prompt TEXT,
  care_summary          TEXT,
  care_tips             JSONB,
  fun_facts             JSONB,
  faq                   JSONB,
  language              TEXT        NOT NULL DEFAULT 'es',
  llm_model             TEXT,
  generated_at          TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (species_id, language)
);

CREATE INDEX idx_ai_content_species_id ON species_ai_content(species_id);

CREATE TABLE species_common_names (
  id         UUID  PRIMARY KEY DEFAULT gen_random_uuid(),
  species_id UUID  NOT NULL REFERENCES species(id) ON DELETE CASCADE,
  name       TEXT  NOT NULL,
  language   TEXT  NOT NULL,
  region     TEXT,
  UNIQUE (species_id, name, language)
);

CREATE INDEX idx_common_names_species_id ON species_common_names(species_id);

-- Tabla RAG con pgvector
CREATE TABLE botanical_chunks (
  id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  content          TEXT         NOT NULL,
  embedding        vector(1536) NOT NULL,
  source           TEXT         NOT NULL,
  scientific_name  TEXT,
  family           TEXT,
  metadata         JSONB        DEFAULT '{}'::jsonb,
  created_at       TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX idx_botanical_chunks_embedding
  ON botanical_chunks
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_botanical_chunks_scientific_name ON botanical_chunks(scientific_name);
CREATE INDEX idx_botanical_chunks_family          ON botanical_chunks(family);

-- Backfill desde species_legacy
INSERT INTO species_care_profiles (
  species_id, min_temp_c, max_temp_c,
  min_light_lux, max_light_lux,
  min_air_humidity_pct, max_air_humidity_pct,
  min_soil_humidity_pct, max_soil_humidity_pct,
  care_data_source, proposal_confidence, needs_review
)
SELECT
  id, min_temp_c, max_temp_c,
  min_light_lux, max_light_lux,
  min_air_humidity_pct, max_air_humidity_pct,
  min_soil_humidity_pct, max_soil_humidity_pct,
  'legacy_backfill', 'medium', TRUE
FROM species_legacy
WHERE (min_temp_c IS NOT NULL OR min_light_lux IS NOT NULL)
  AND id IN (SELECT id FROM species);

INSERT INTO species_ai_content (species_id, ai_personality_prompt, language, llm_model)
SELECT id, ai_personality_prompt, 'es', 'legacy'
FROM species_legacy
WHERE ai_personality_prompt IS NOT NULL
  AND TRIM(ai_personality_prompt) <> ''
  AND id IN (SELECT id FROM species)
ON CONFLICT (species_id, language) DO NOTHING;

INSERT INTO species_common_names (species_id, name, language)
SELECT id, common_name, 'es'
FROM species_legacy
WHERE common_name IS NOT NULL
  AND TRIM(common_name) <> ''
  AND id IN (SELECT id FROM species)
ON CONFLICT (species_id, name, language) DO NOTHING;

-- Restaurar FK de plants
ALTER TABLE plants
  ADD CONSTRAINT plants_species_id_fkey
  FOREIGN KEY (species_id) REFERENCES species(id);

-- RPC para búsqueda semántica
CREATE OR REPLACE FUNCTION match_botanical_chunks(
  query_embedding   vector(1536),
  match_count       int   DEFAULT 5,
  min_similarity    float DEFAULT 0.55,
  family_filter     text  DEFAULT NULL,
  scientific_filter text  DEFAULT NULL
)
RETURNS TABLE (
  id              uuid,
  content         text,
  source          text,
  scientific_name text,
  family          text,
  similarity      float
)
LANGUAGE sql STABLE AS $$
  SELECT
    id, content, source, scientific_name, family,
    1 - (embedding <=> query_embedding) AS similarity
  FROM botanical_chunks
  WHERE
    (family_filter IS NULL OR family = family_filter)
    AND (scientific_filter IS NULL
         OR scientific_name = scientific_filter
         OR scientific_name IS NULL)
    AND (1 - (embedding <=> query_embedding)) >= min_similarity
  ORDER BY embedding <=> query_embedding
  LIMIT match_count;
$$;

COMMIT;

-- Verificar huérfanos antes de hacer DROP:
--   SELECT COUNT(*) FROM plants WHERE species_id NOT IN (SELECT id FROM species);
-- Cuando esté confirmado, ejecutar:
--   DROP TABLE species_legacy;


-- ============================================================
-- 002 — Foto de planta en Firebase Storage
-- ============================================================

ALTER TABLE plants
  ADD COLUMN IF NOT EXISTS photo_storage_path TEXT;


-- ============================================================
-- 003 — Pesos de cuidado y evaluación de sensibilidad
-- ============================================================

BEGIN;

ALTER TABLE species_care_profiles
  ADD COLUMN IF NOT EXISTS weight_light            FLOAT,
  ADD COLUMN IF NOT EXISTS weight_soil_humidity    FLOAT,
  ADD COLUMN IF NOT EXISTS weight_air_humidity     FLOAT,
  ADD COLUMN IF NOT EXISTS weight_temperature      FLOAT,
  ADD COLUMN IF NOT EXISTS sensitivity_light            TEXT CHECK (sensitivity_light IS NULL OR sensitivity_light IN ('high', 'medium', 'low')),
  ADD COLUMN IF NOT EXISTS sensitivity_soil_humidity    TEXT CHECK (sensitivity_soil_humidity IS NULL OR sensitivity_soil_humidity IN ('high', 'medium', 'low')),
  ADD COLUMN IF NOT EXISTS sensitivity_air_humidity     TEXT CHECK (sensitivity_air_humidity IS NULL OR sensitivity_air_humidity IN ('high', 'medium', 'low')),
  ADD COLUMN IF NOT EXISTS sensitivity_temperature      TEXT CHECK (sensitivity_temperature IS NULL OR sensitivity_temperature IN ('high', 'medium', 'low'));

COMMIT;

-- ============================================================
-- 004 — Monthly Metrics Health
-- ============================================================

ALTER TABLE monthly_metrics
ADD COLUMN IF NOT EXISTS avg_health_score FLOAT,
ADD COLUMN IF NOT EXISTS health_status_majority VARCHAR;

COMMIT;
