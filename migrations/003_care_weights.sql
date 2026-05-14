-- ============================================================
-- 003_care_weights.sql
-- Añade pesos de cuidado (care_weights) y evaluación de sensibilidad
-- (sensitivity_assessment) como columnas planas en species_care_profiles.
-- Columnas nullable: fichas pre-migración siguen siendo válidas.
-- ============================================================

BEGIN;

ALTER TABLE species_care_profiles
  ADD COLUMN IF NOT EXISTS weight_light            FLOAT,
  ADD COLUMN IF NOT EXISTS weight_soil_humidity    FLOAT,
  ADD COLUMN IF NOT EXISTS weight_air_humidity     FLOAT,
  ADD COLUMN IF NOT EXISTS weight_temperature      FLOAT,
  ADD COLUMN IF NOT EXISTS sensitivity_light            TEXT,
  ADD COLUMN IF NOT EXISTS sensitivity_soil_humidity    TEXT,
  ADD COLUMN IF NOT EXISTS sensitivity_air_humidity     TEXT,
  ADD COLUMN IF NOT EXISTS sensitivity_temperature      TEXT;

ALTER TABLE species_care_profiles
  ADD CONSTRAINT care_weights_light_range
    CHECK (weight_light IS NULL OR (weight_light BETWEEN 0 AND 1)),
  ADD CONSTRAINT care_weights_soil_range
    CHECK (weight_soil_humidity IS NULL OR (weight_soil_humidity BETWEEN 0 AND 1)),
  ADD CONSTRAINT care_weights_air_range
    CHECK (weight_air_humidity IS NULL OR (weight_air_humidity BETWEEN 0 AND 1)),
  ADD CONSTRAINT care_weights_temp_range
    CHECK (weight_temperature IS NULL OR (weight_temperature BETWEEN 0 AND 1)),
  ADD CONSTRAINT sensitivity_light_enum
    CHECK (sensitivity_light IS NULL OR sensitivity_light IN ('high', 'medium', 'low')),
  ADD CONSTRAINT sensitivity_soil_enum
    CHECK (sensitivity_soil_humidity IS NULL OR sensitivity_soil_humidity IN ('high', 'medium', 'low')),
  ADD CONSTRAINT sensitivity_air_enum
    CHECK (sensitivity_air_humidity IS NULL OR sensitivity_air_humidity IN ('high', 'medium', 'low')),
  ADD CONSTRAINT sensitivity_temp_enum
    CHECK (sensitivity_temperature IS NULL OR sensitivity_temperature IN ('high', 'medium', 'low'));

COMMIT;

-- ============================================================
-- Para verificar después de aplicar:
--   SELECT column_name, data_type
--   FROM information_schema.columns
--   WHERE table_name = 'species_care_profiles'
--   ORDER BY ordinal_position;
-- ============================================================
