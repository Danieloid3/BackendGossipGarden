-- Guardar las 3 opciones de voz generadas por el LLM por especie
ALTER TABLE species_ai_content
  ADD COLUMN IF NOT EXISTS elevenlabs_voice_alternatives JSONB;

-- Guardar la voz elegida por el usuario por planta
ALTER TABLE plants
  ADD COLUMN IF NOT EXISTS elevenlabs_voice_id TEXT;
