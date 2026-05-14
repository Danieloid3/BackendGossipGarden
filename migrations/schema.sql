-- ============================================================
-- schema.sql — Gossip Garden
-- Script completo para crear la base de datos desde cero en Supabase.
-- Unifica migrations 001, 002 y 003.
-- ============================================================

-- ============================================================
-- EXTENSIONES
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- TABLAS CORE
-- ============================================================

CREATE TABLE users (
  user_id     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  username    VARCHAR     NOT NULL,
  email       VARCHAR     NOT NULL UNIQUE,
  created_at  TIMESTAMP   DEFAULT NOW()
);

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

CREATE INDEX idx_species_family           ON species(family);
CREATE INDEX idx_species_gbif_taxon_key   ON species(gbif_taxon_key);

-- ============================================================
-- TABLAS HIJAS DE SPECIES
-- ============================================================

CREATE TABLE species_care_profiles (
  id                        UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  species_id                UUID    NOT NULL REFERENCES species(id) ON DELETE CASCADE,
  -- Rangos de cuidado
  min_temp_c                FLOAT,
  max_temp_c                FLOAT,
  min_light_lux             FLOAT,
  max_light_lux             FLOAT,
  min_air_humidity_pct      FLOAT,
  max_air_humidity_pct      FLOAT,
  min_soil_humidity_pct     FLOAT,
  max_soil_humidity_pct     FLOAT,
  -- Metadatos de la inferencia
  care_data_source          TEXT    DEFAULT 'llm_inference',
  proposal_confidence       TEXT    CHECK (proposal_confidence IN ('high', 'medium', 'low')),
  needs_review              BOOLEAN DEFAULT TRUE,
  reasoning_summary         TEXT,
  completed_at              TIMESTAMPTZ DEFAULT NOW(),
  -- Pesos de cuidado (suma ≈ 1.0, nullable)
  weight_light              FLOAT   CHECK (weight_light IS NULL OR weight_light BETWEEN 0 AND 1),
  weight_soil_humidity      FLOAT   CHECK (weight_soil_humidity IS NULL OR weight_soil_humidity BETWEEN 0 AND 1),
  weight_air_humidity       FLOAT   CHECK (weight_air_humidity IS NULL OR weight_air_humidity BETWEEN 0 AND 1),
  weight_temperature        FLOAT   CHECK (weight_temperature IS NULL OR weight_temperature BETWEEN 0 AND 1),
  -- Sensibilidad por parámetro (nullable)
  sensitivity_light         TEXT    CHECK (sensitivity_light IS NULL OR sensitivity_light IN ('high', 'medium', 'low')),
  sensitivity_soil_humidity TEXT    CHECK (sensitivity_soil_humidity IS NULL OR sensitivity_soil_humidity IN ('high', 'medium', 'low')),
  sensitivity_air_humidity  TEXT    CHECK (sensitivity_air_humidity IS NULL OR sensitivity_air_humidity IN ('high', 'medium', 'low')),
  sensitivity_temperature   TEXT    CHECK (sensitivity_temperature IS NULL OR sensitivity_temperature IN ('high', 'medium', 'low'))
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
  id          UUID  PRIMARY KEY DEFAULT gen_random_uuid(),
  species_id  UUID  NOT NULL REFERENCES species(id) ON DELETE CASCADE,
  name        TEXT  NOT NULL,
  language    TEXT  NOT NULL,
  region      TEXT,
  UNIQUE (species_id, name, language)
);

CREATE INDEX idx_common_names_species_id ON species_common_names(species_id);

-- ============================================================
-- RAG — CHUNKS BOTÁNICOS CON PGVECTOR
-- ============================================================

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

-- ============================================================
-- PLANTAS, SENSORES Y EVENTOS
-- ============================================================

CREATE TABLE plants (
  plant_id           UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            UUID      NOT NULL REFERENCES users(user_id),
  species_id         UUID      NOT NULL REFERENCES species(id),
  nickname           VARCHAR   NOT NULL,
  health_status      TEXT      NOT NULL DEFAULT 'healthy'
                               CHECK (health_status IN ('healthy', 'warning', 'critical')),
  health_score       FLOAT,
  photo_storage_path TEXT,
  last_health_check  TIMESTAMP,
  created_at         TIMESTAMP DEFAULT NOW()
);

CREATE TABLE sensors (
  sensor_id    UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  plant_id     UUID      REFERENCES plants(plant_id),
  mac_address  VARCHAR   NOT NULL,
  is_online    BOOLEAN   DEFAULT FALSE,
  last_ping    TIMESTAMP
);

CREATE TABLE events (
  event_id    UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  plant_id    UUID      NOT NULL REFERENCES plants(plant_id),
  type        TEXT      NOT NULL CHECK (type IN ('alert', 'insight', 'chat', 'system')),
  message     TEXT      NOT NULL,
  created_at  TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- SOCIAL
-- ============================================================

CREATE TABLE friendships (
  id               UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  user_low_id      UUID      NOT NULL REFERENCES users(user_id),
  user_high_id     UUID      NOT NULL REFERENCES users(user_id),
  requested_by_id  UUID      NOT NULL REFERENCES users(user_id),
  status           TEXT      NOT NULL DEFAULT 'pending'
                             CHECK (status IN ('pending', 'accepted', 'blocked')),
  created_at       TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- MÉTRICAS MENSUALES
-- ============================================================

CREATE TABLE monthly_metrics (
  id                UUID  PRIMARY KEY DEFAULT gen_random_uuid(),
  plant_id          UUID  NOT NULL REFERENCES plants(plant_id),
  month             INT   NOT NULL CHECK (month BETWEEN 1 AND 12),
  year              INT   NOT NULL,
  avg_temperature   FLOAT,
  avg_soil_humidity FLOAT,
  avg_air_humidity  FLOAT,
  avg_light         FLOAT,
  avg_health_score  FLOAT,
  health_status_majority VARCHAR
);
