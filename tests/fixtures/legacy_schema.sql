-- ============================================================
-- legacy_schema.sql — Esquema pre-migración (seed para CI)
-- Simula el esquema original que tenía GossipGarden antes de la
-- migración 001 (species con rangos de cuidado, sin tablas hijas).
-- Usado por el job db-schema del CI para probar migrations.sql.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS vector;

-- Usuarios (sin cambios entre legacy y nuevo)
CREATE TABLE users (
  user_id     UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  username    VARCHAR   NOT NULL,
  email       VARCHAR   NOT NULL UNIQUE,
  created_at  TIMESTAMP DEFAULT NOW()
);

-- Species legacy: incluye rangos de cuidado y ai_personality_prompt
-- que migrations.sql backfill desde species_legacy tras renombrar.
CREATE TABLE species (
  id                    UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  scientific_name       TEXT    NOT NULL UNIQUE,
  common_name           TEXT,
  min_temp_c            FLOAT,
  max_temp_c            FLOAT,
  min_light_lux         FLOAT,
  max_light_lux         FLOAT,
  min_air_humidity_pct  FLOAT,
  max_air_humidity_pct  FLOAT,
  min_soil_humidity_pct FLOAT,
  max_soil_humidity_pct FLOAT,
  ai_personality_prompt TEXT,
  created_at            TIMESTAMP DEFAULT NOW()
);

-- Plants con FK a species (con nombre de constraint explícito,
-- que migrations.sql espera eliminar y restaurar).
CREATE TABLE plants (
  plant_id    UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID    NOT NULL REFERENCES users(user_id),
  species_id  UUID    NOT NULL,
  nickname    VARCHAR NOT NULL,
  health_status TEXT  NOT NULL DEFAULT 'healthy'
                      CHECK (health_status IN ('healthy', 'warning', 'critical')),
  health_score FLOAT,
  last_health_check TIMESTAMP,
  created_at  TIMESTAMP DEFAULT NOW(),
  CONSTRAINT plants_species_id_fkey FOREIGN KEY (species_id) REFERENCES species(id)
);

-- Sensors
CREATE TABLE sensors (
  sensor_id   UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  plant_id    UUID    REFERENCES plants(plant_id),
  mac_address VARCHAR NOT NULL,
  is_online   BOOLEAN DEFAULT FALSE,
  last_ping   TIMESTAMP
);

-- Events
CREATE TABLE events (
  event_id   UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  plant_id   UUID      NOT NULL REFERENCES plants(plant_id),
  type       TEXT      NOT NULL CHECK (type IN ('alert', 'insight', 'chat', 'system')),
  message    TEXT      NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Friendships
CREATE TABLE friendships (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_low_id      UUID NOT NULL REFERENCES users(user_id),
  user_high_id     UUID NOT NULL REFERENCES users(user_id),
  requested_by_id  UUID NOT NULL REFERENCES users(user_id),
  status           TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'accepted', 'blocked')),
  created_at       TIMESTAMP DEFAULT NOW()
);

-- Monthly metrics (sin avg_health_score / health_status_majority que añade migration 004)
CREATE TABLE monthly_metrics (
  id                UUID  PRIMARY KEY DEFAULT gen_random_uuid(),
  plant_id          UUID  NOT NULL REFERENCES plants(plant_id),
  month             INT   NOT NULL CHECK (month BETWEEN 1 AND 12),
  year              INT   NOT NULL,
  avg_temperature   FLOAT,
  avg_soil_humidity FLOAT,
  avg_air_humidity  FLOAT,
  avg_light         FLOAT
);
