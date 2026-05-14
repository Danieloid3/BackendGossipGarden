-- 002_add_plant_photo.sql
-- Añade columna photo_storage_path a plants para asociar cada planta con su foto en Firebase Storage.

ALTER TABLE plants
  ADD COLUMN IF NOT EXISTS photo_storage_path TEXT;
