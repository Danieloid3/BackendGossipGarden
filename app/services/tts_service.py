"""Síntesis de voz con ElevenLabs y almacenamiento del audio en Firebase Storage.

Llama a la API de ElevenLabs para convertir texto a MP3, luego sube el archivo
a Firebase Storage siguiendo el mismo patrón que image_storage_service.py.
"""

from __future__ import annotations

import asyncio
import io
import logging
import uuid

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

# Voces curadas disponibles para las plantas. El LLM elige entre estas.
AVAILABLE_VOICES: list[dict] = [
    {"id": "N2lVS1w4EtoT3dr4eOWO", "name": "Callum",  "gender": "male",    "style": "husky trickster, misterioso",       "lang": "en"},
    {"id": "SOYHLrjzK2X1ezoPC6cr", "name": "Harry",   "gender": "male",    "style": "fierce warrior, áspero y fuerte",   "lang": "en"},
    {"id": "tomkxGQGz4b1kE0EM722", "name": "Mario",   "gender": "male",    "style": "animado, charlatán, energético",    "lang": "es"},
    {"id": "6fN2iFIr0E9Ldj3fYqdo", "name": "Ricky",   "gender": "male",    "style": "exagerado, dramático, expresivo",   "lang": "es"},
    {"id": "o2vbTbO3g4GrKUg7rehy", "name": "Cristian","gender": "male",    "style": "tranquilo, chill, colombiano",      "lang": "es"},
    {"id": "VmejBeYhbrcTPwDniox7", "name": "Lina",    "gender": "female",  "style": "despreocupada, fresca, joven",      "lang": "es"},
    {"id": "p5EUznrYaWnafKvUkNiR", "name": "Gaviota", "gender": "female",  "style": "natural, casual, latinoamericana",  "lang": "es"},
    {"id": "JddqVF50ZSIR7SRbJE6u", "name": "Valeria", "gender": "female",  "style": "amigable, sociable, conversacional","lang": "es"},
    {"id": "b2htR0pMe28pYwCY9gnP", "name": "Sofía",   "gender": "female",  "style": "cálida, confiable, colombiana",     "lang": "es"},
    {"id": "ZLtrNuxn2sKIoUphMxLE", "name": "Natalia", "gender": "female",  "style": "caribeña, casual, chispeante",      "lang": "es"},
    {"id": "cgSgspJ2msm6clMCkdW9", "name": "Jessica", "gender": "female",  "style": "juguetona, cálida, alegre",         "lang": "en"},
    {"id": "FGY2WhTYpPnrIDTdsKH5", "name": "Laura",   "gender": "female",  "style": "entusiasta, extravagante, irónica", "lang": "en"},
]

VOICE_IDS: list[str] = [v["id"] for v in AVAILABLE_VOICES]


class ElevenLabsError(Exception):
    pass


class ElevenLabsAuthError(ElevenLabsError):
    pass


class ElevenLabsRateLimitError(ElevenLabsError):
    pass


class ElevenLabsUnavailableError(ElevenLabsError):
    pass


@retry(
    retry=retry_if_exception_type((ElevenLabsRateLimitError, ElevenLabsUnavailableError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def synthesize(
    text: str,
    voice_id: str | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> bytes:
    """Convierte texto a audio MP3 usando ElevenLabs.

    Usa voice_id si se provee, o el voice ID default del config.
    Retorna los bytes del MP3.
    """
    effective_voice_id = voice_id or settings.ELEVENLABS_DEFAULT_VOICE_ID
    url = f"{settings.ELEVENLABS_BASE_URL}/text-to-speech/{effective_voice_id}"

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=settings.ELEVENLABS_TIMEOUT_SECONDS)

    try:
        response = await client.post(
            url,
            headers={
                "xi-api-key": settings.ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": settings.ELEVENLABS_MODEL_ID,
                "voice_settings": {
                    "stability": 0.35,
                    "similarity_boost": 0.85,
                    "style": 0.05,
                },
            },
        )
    except httpx.TimeoutException as e:
        raise ElevenLabsUnavailableError("ElevenLabs timeout") from e
    except httpx.NetworkError as e:
        raise ElevenLabsUnavailableError("ElevenLabs network error") from e
    finally:
        if own_client:
            await client.aclose()

    if response.status_code == 401:
        raise ElevenLabsAuthError("ElevenLabs API key inválida o sin permisos")
    if response.status_code == 429:
        raise ElevenLabsRateLimitError("ElevenLabs rate limit alcanzado")
    if response.status_code >= 500:
        raise ElevenLabsUnavailableError(f"ElevenLabs error {response.status_code}")
    if not response.is_success:
        raise ElevenLabsError(f"ElevenLabs error inesperado: {response.status_code} — {response.text[:200]}")

    return response.content


async def upload_audio(
    audio_bytes: bytes,
    user_id: str,
    plant_id: str,
    timestamp: str,
    extension: str = "mp3",
    content_type: str = "audio/mpeg",
) -> str | None:
    """Sube el audio a Firebase Storage y retorna el storage path.

    Retorna None si el bucket no está configurado o si la subida falla,
    sin lanzar excepción — igual que image_storage_service._upload_compressed.
    """
    if not settings.FIREBASE_STORAGE_BUCKET:
        logger.warning("FIREBASE_STORAGE_BUCKET no configurado — audio no se subirá")
        return None

    uid = str(uuid.uuid4())[:8]
    safe_ts = timestamp.replace(" ", "T").replace(":", "")
    storage_path = f"plant_audio/{user_id}/{plant_id}/{safe_ts}_{uid}.{extension}"

    try:
        from firebase_admin import storage as fb_storage

        bucket = fb_storage.bucket()
        blob = bucket.blob(storage_path)

        await asyncio.to_thread(
            blob.upload_from_file,
            io.BytesIO(audio_bytes),
            content_type=content_type,
        )
        
        # Hacemos el blob público para evitar error 403
        await asyncio.to_thread(blob.make_public)
        
        public_url = f"https://storage.googleapis.com/{bucket.name}/{storage_path}"
        logger.debug("Audio subido y hecho público a Storage: %s (%d KB)", public_url, len(audio_bytes) // 1024)
        return public_url

    except Exception as e:
        logger.error("Error subiendo audio a Firebase Storage (%s): %s", storage_path, e)
        return None
