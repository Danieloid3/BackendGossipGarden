"""Lógica de negocio del chatbot: carga personalidad, historial y llama a GPT."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from google.cloud.firestore import ArrayUnion, Query
from openai import AsyncOpenAI

from app.core.config import settings
from app.db.firebase import firebase_db
from app.db.supabase import supabase
from app.schemas.chat import ChatMessage, ChatHistoryResponse, ChatResponse
from app.services import tts_service
from app.services.summarizer_service import (
    build_system_with_summary,
    compact_if_needed,
)

logger = logging.getLogger(__name__)

_HISTORY_MAX_TURNS = 10  # últimos N pares (usuario + asistente)
_REDIS_TTL = 7200         # 2 horas
_REDIS_SUMMARY_TTL = 604800  # 7 días


def _redis_key(user_id: str, plant_id: str) -> str:
    return f"chat:{user_id}:{plant_id}"


def _summary_redis_key(user_id: str, plant_id: str) -> str:
    return f"chat:summary:{user_id}:{plant_id}"


# ---------------------------------------------------------------------------
# Helpers síncronos (se ejecutan en asyncio.to_thread)
# ---------------------------------------------------------------------------

def _verify_and_get_plant(plant_id: str, user_id: str) -> dict:
    result = (
        supabase.table("plants")
        .select("plant_id, user_id, species_id, nickname, health_score, health_status")
        .eq("plant_id", plant_id)
        .execute()
    )
    if not result.data:
        raise ValueError("Planta no encontrada")
    plant = result.data[0]
    if plant["user_id"] != user_id:
        raise PermissionError("No tienes acceso a esta planta")
    return plant


def _load_latest_sensor_sync(plant_id: str) -> dict | None:
    """Carga la última lectura de sensores desde Firestore."""
    try:
        from google.cloud.firestore import Query as FSQuery
        docs = (
            firebase_db.collection("plants")
            .document(plant_id)
            .collection("sensor_readings")
            .order_by("timestamp", direction=FSQuery.DESCENDING)
            .limit(1)
            .stream()
        )
        for doc in docs:
            return doc.to_dict()
    except Exception as e:
        logger.warning("Sensor data no disponible: %s", e)
    return None


def _format_plant_status(plant: dict, sensor: dict | None) -> str:
    """Construye el bloque de estado actual que se inyecta en el system prompt."""
    health_score = plant.get("health_score", "?")
    health_status = plant.get("health_status", "?")
    nickname = plant.get("nickname", "sin nombre")

    lines = [
        "--- Tu estado actual ---",
        f"Nombre: {nickname}",
        f"Salud general: {health_status} ({health_score}/100)",
    ]

    if sensor:
        lines += [
            f"Temperatura: {sensor.get('temperature_c', '?')}°C",
            f"Humedad del aire: {sensor.get('humidity_pct', '?')}%",
            f"Humedad del suelo: {sensor.get('soil_moisture_pct', '?')}%",
            f"Luz: {sensor.get('light_lux', '?')} lux",
        ]
    else:
        lines.append("(Sin datos de sensores disponibles)")

    return "\n".join(lines)


def _get_personality(species_id: str, language: str) -> tuple[str, str | None]:
    """Retorna (personality_prompt, elevenlabs_voice_id)."""
    result = (
        supabase.table("species_ai_content")
        .select("ai_personality_prompt, elevenlabs_voice_id")
        .eq("species_id", species_id)
        .eq("language", language)
        .limit(1)
        .execute()
    )
    if result.data:
        row = result.data[0]
        return row["ai_personality_prompt"], row.get("elevenlabs_voice_id")

    fallback = (
        supabase.table("species_ai_content")
        .select("ai_personality_prompt, elevenlabs_voice_id")
        .eq("species_id", species_id)
        .eq("language", "es")
        .limit(1)
        .execute()
    )
    if fallback.data:
        row = fallback.data[0]
        return row["ai_personality_prompt"], row.get("elevenlabs_voice_id")

    return "Eres una planta amigable y cariñosa. Habla en primera persona como si fueras la planta.", None


def _load_history_sync(plant_id: str, user_id: str) -> list[dict]:
    """Carga los últimos mensajes desde el documento de conversación en Firestore."""
    try:
        doc = (
            firebase_db.collection("plants")
            .document(plant_id)
            .collection("chat_logs")
            .document(user_id)
            .get()
        )
        if not doc.exists:
            return []
        messages = doc.to_dict().get("messages", [])
        recent = messages[-(_HISTORY_MAX_TURNS * 2):]
        return [{"role": m["role"], "content": m["content"]} for m in recent]
    except Exception as e:
        logger.warning("Firestore historial no disponible: %s", e)
        return []


def _load_summary_from_firestore_sync(plant_id: str, user_id: str) -> str:
    """Carga el resumen compactado desde Firestore."""
    try:
        doc = (
            firebase_db.collection("plants")
            .document(plant_id)
            .collection("chat_meta")
            .document(user_id)
            .get()
        )
        if doc.exists:
            return doc.to_dict().get("summary", "")
    except Exception as e:
        logger.warning("Firestore summary load falló: %s", e)
    return ""


def _save_summary_to_firestore_sync(plant_id: str, user_id: str, summary: str) -> None:
    try:
        firebase_db.collection("plants").document(plant_id).collection("chat_meta").document(
            user_id
        ).set({"summary": summary, "updated_at": int(time.time() * 1000)})
    except Exception as e:
        logger.warning("Firestore summary save falló: %s", e)


def _fetch_history_sync(plant_id: str, user_id: str, limit: int) -> list[dict]:
    """Carga el historial completo desde el documento de conversación en Firestore."""
    try:
        doc = (
            firebase_db.collection("plants")
            .document(plant_id)
            .collection("chat_logs")
            .document(user_id)
            .get()
        )
        if not doc.exists:
            return []
        messages = doc.to_dict().get("messages", [])[-limit:]
        return [
            {
                "role": m["role"],
                "content": m["content"],
                "timestamp": m.get("timestamp", ""),
            }
            for m in messages
        ]
    except Exception as e:
        logger.warning("Firestore fetch historial falló: %s", e)
        return []


def _save_exchange_sync(
    plant_id: str,
    user_id: str,
    user_message: str,
    reply: str,
    now_ms: int,
    audio_url: str | None = None,
) -> None:
    doc_ref = (
        firebase_db.collection("plants")
        .document(plant_id)
        .collection("chat_logs")
        .document(user_id)
    )
    now_str = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    assistant_msg: dict = {"role": "assistant", "content": reply, "timestamp": now_str}
    if audio_url:
        assistant_msg["audio_url"] = audio_url
    doc_ref.set(
        {
            "user_id": user_id,
            "plant_id": plant_id,
            "updated_at": now_str,
            "messages": ArrayUnion([
                {"role": "user", "content": user_message, "timestamp": now_str},
                assistant_msg,
            ]),
        },
        merge=True,
    )


# ---------------------------------------------------------------------------
# Helpers async para carga de caché
# ---------------------------------------------------------------------------

async def _load_cache(redis_client, user_id: str, plant_id: str) -> tuple[list[dict], str]:
    """Carga historial y resumen desde Redis. Devuelve (history, summary)."""
    history: list[dict] = []
    summary: str = ""
    try:
        hist_raw, summ_raw = await asyncio.gather(
            redis_client.get(_redis_key(user_id, plant_id)),
            redis_client.get(_summary_redis_key(user_id, plant_id)),
        )
        if hist_raw:
            history = json.loads(hist_raw)
        if summ_raw:
            summary = summ_raw
    except Exception as e:
        logger.warning("Redis load fallido: %s", e)
    return history, summary


async def _save_cache(
    redis_client,
    user_id: str,
    plant_id: str,
    history: list[dict],
    summary: str,
    save_summary: bool,
) -> None:
    try:
        ops = [
            redis_client.set(_redis_key(user_id, plant_id), json.dumps(history), ex=_REDIS_TTL)
        ]
        if save_summary:
            ops.append(
                redis_client.set(
                    _summary_redis_key(user_id, plant_id), summary, ex=_REDIS_SUMMARY_TTL
                )
            )
        await asyncio.gather(*ops)
    except Exception as e:
        logger.warning("Redis save fallido: %s", e)


# ---------------------------------------------------------------------------
# Funciones públicas del servicio
# ---------------------------------------------------------------------------

async def chat_with_plant(
    plant_id: str,
    user_id: str,
    message: str,
    language: str,
    redis_client,
    response_format: str = "text",
) -> ChatResponse:
    # 1. Verificar ownership + cargar caché en paralelo
    plant_task = asyncio.to_thread(_verify_and_get_plant, plant_id, user_id)
    cache_task = _load_cache(redis_client, user_id, plant_id)

    plant_row, (history, summary) = await asyncio.gather(plant_task, cache_task)
    species_id = plant_row["species_id"]

    # 2. Cargar en paralelo: personalidad, sensor y (si hace falta) historial desde Firestore
    personality_task = asyncio.to_thread(_get_personality, species_id, language)
    sensor_task = asyncio.to_thread(_load_latest_sensor_sync, plant_id)

    if not history:
        history_task = asyncio.to_thread(_load_history_sync, plant_id, user_id)
        (personality, voice_id), sensor, history = await asyncio.gather(
            personality_task, sensor_task, history_task
        )
    else:
        (personality, voice_id), sensor = await asyncio.gather(personality_task, sensor_task)

    # 3. Si no había resumen en Redis, intentar cargarlo desde Firestore
    if not summary:
        summary = await asyncio.to_thread(_load_summary_from_firestore_sync, plant_id, user_id)

    # 4. Compactar historial si supera el límite de tokens
    history, summary, was_compacted = await compact_if_needed(history, summary)

    # 5. Construir mensajes para el LLM
    plant_status = _format_plant_status(plant_row, sensor)
    system_content = build_system_with_summary(personality, summary, plant_status)
    llm_messages = [{"role": "system", "content": system_content}]
    llm_messages.extend(history)
    llm_messages.append({"role": "user", "content": message})

    # 6. Llamar a GPT
    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
        max_retries=0,
    )
    response = await client.chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        messages=llm_messages,
        temperature=0.8,
        max_tokens=500,
    )
    reply = response.choices[0].message.content or "..."

    # 7. Persistir el intercambio
    now_ms = int(time.time() * 1000)
    now_str = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    updated_history = (history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": reply},
    ])[-(_HISTORY_MAX_TURNS * 2):]

    # 8. Generar audio si el cliente lo solicitó
    audio_url: str | None = None
    if response_format == "audio":
        try:
            audio_bytes = await tts_service.synthesize(reply, voice_id)
            audio_url = await tts_service.upload_audio(audio_bytes, user_id, plant_id, now_str)
        except tts_service.ElevenLabsError as e:
            logger.error("TTS falló, se devuelve solo texto: %s", e)

    try:
        await asyncio.to_thread(
            _save_exchange_sync, plant_id, user_id, message, reply, now_ms, audio_url
        )
    except Exception as e:
        logger.error("Error guardando en Firestore: %s", e)

    # Guardar resumen en Firestore si hubo compactación
    if was_compacted:
        try:
            await asyncio.to_thread(
                _save_summary_to_firestore_sync, plant_id, user_id, summary
            )
        except Exception as e:
            logger.warning("Error guardando resumen en Firestore: %s", e)

    await _save_cache(redis_client, user_id, plant_id, updated_history, summary, was_compacted)

    return ChatResponse(reply=reply, plant_id=plant_id, timestamp=now_str, audio_url=audio_url)


async def get_chat_history(
    plant_id: str,
    user_id: str,
    limit: int,
) -> list[ChatMessage]:
    raw = await asyncio.to_thread(_fetch_history_sync, plant_id, user_id, limit)
    return [ChatMessage(**m) for m in raw]
