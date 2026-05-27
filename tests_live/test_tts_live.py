"""Tests live de ElevenLabs TTS.

Verifica que la API key es válida y que synthesize() devuelve audio MP3 real.
"""
from __future__ import annotations

import pytest

from app.services.tts_service import (
    AVAILABLE_VOICES,
    ElevenLabsAuthError,
    synthesize,
)

pytestmark = pytest.mark.live


async def test_synthesize_returns_mp3_bytes():
    """synthesize() con voz por defecto retorna bytes MP3 no vacíos."""
    audio = await synthesize("Hola, soy tu planta. ¿Cómo estás hoy?")

    assert isinstance(audio, bytes)
    assert len(audio) > 1000  # un MP3 real tiene al menos 1 KB
    # Header MP3: ID3 tag (0x49 0x44 0x33) o frame sync (0xFF 0xFB / 0xFF 0xFA)
    assert audio[:3] == b"ID3" or audio[0] == 0xFF, (
        f"Bytes iniciales inesperados: {audio[:4].hex()}"
    )


async def test_synthesize_with_explicit_voice():
    """synthesize() acepta un voice_id explícito del catálogo."""
    voice_id = AVAILABLE_VOICES[0]["id"]  # Callum
    audio = await synthesize("Me llamo Callum y soy una planta.", voice_id=voice_id)

    assert isinstance(audio, bytes)
    assert len(audio) > 1000


async def test_synthesize_spanish_voice():
    """Voz en español (Mario) funciona correctamente."""
    mario = next(v for v in AVAILABLE_VOICES if v["name"] == "Mario")
    audio = await synthesize("¡Bienvenidos al jardín! Soy Mario.", voice_id=mario["id"])

    assert isinstance(audio, bytes)
    assert len(audio) > 1000


async def test_synthesize_invalid_key_raises_auth_error(monkeypatch):
    """Una API key inválida lanza ElevenLabsAuthError (no un error genérico)."""
    from app.core import config as cfg_module

    original_key = cfg_module.settings.ELEVENLABS_API_KEY
    monkeypatch.setattr(cfg_module.settings, "ELEVENLABS_API_KEY", "invalid-key-xyz")

    with pytest.raises(ElevenLabsAuthError):
        await synthesize("Prueba de error.")

    monkeypatch.setattr(cfg_module.settings, "ELEVENLABS_API_KEY", original_key)
