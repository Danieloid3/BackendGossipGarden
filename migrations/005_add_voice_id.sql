-- Add ElevenLabs voice ID per species/language to support per-plant TTS voices
ALTER TABLE species_ai_content
  ADD COLUMN IF NOT EXISTS elevenlabs_voice_id TEXT;
