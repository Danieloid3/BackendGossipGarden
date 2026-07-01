"""Tests unitarios del servicio de chat (chat_service)."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.chat import ChatMessage, ChatResponse, VoicesResponse
from app.services.chat_service import (
    _build_voices_response,
    _format_plant_status,
    _redis_key,
    _summary_redis_key,
    chat_with_plant,
    get_chat_history,
    set_plant_voice,
)
from app.services.tts_service import VOICE_IDS

FAKE_PLANT_ID = "aaaaaaaa-0000-0000-0000-000000000001"
FAKE_USER_ID = "00000000-0000-0000-0000-000000000001"
FAKE_SPECIES_ID = "cccccccc-0000-0000-0000-000000000001"

FAKE_PLANT_ROW = {
    "plant_id": FAKE_PLANT_ID,
    "user_id": FAKE_USER_ID,
    "species_id": FAKE_SPECIES_ID,
    "nickname": "Pepe",
    "health_score": 85.0,
    "health_status": "healthy",
    "elevenlabs_voice_id": None,
}

FAKE_SENSOR = {
    "temperature_c": 22.5,
    "humidity_pct": 65.0,
    "soil_moisture_pct": 40.0,
    "light_lux": 3000,
}

VOICE_ID_A = "N2lVS1w4EtoT3dr4eOWO"  # Callum
VOICE_ID_B = "SOYHLrjzK2X1ezoPC6cr"  # Harry
VOICE_ID_C = "tomkxGQGz4b1kE0EM722"  # Mario


def _make_openai_response(content: str):
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    completion = MagicMock()
    completion.choices = [choice]
    return completion


@pytest.fixture
def fake_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    return redis


# ---------------------------------------------------------------------------
# Helpers puros — sin I/O
# ---------------------------------------------------------------------------

def test_redis_key_format():
    assert _redis_key("uid1", "pid1") == "chat:uid1:pid1"


def test_summary_redis_key_format():
    assert _summary_redis_key("uid1", "pid1") == "chat:summary:uid1:pid1"


def test_format_plant_status_with_sensor():
    status = _format_plant_status(FAKE_PLANT_ROW, FAKE_SENSOR, "dueño/a")
    assert "Pepe" in status
    assert "22.5°C" in status
    assert "65.0%" in status
    assert "40.0%" in status
    assert "3000 lux" in status


def test_format_plant_status_without_sensor():
    status = _format_plant_status(FAKE_PLANT_ROW, None, "dueño/a")
    assert "Sin datos de sensores disponibles" in status
    assert "Pepe" in status
    assert "healthy" in status


def test_build_voices_response_three_options():
    voice_data = {
        "plant_voice_id": None,
        "recommended_voice_id": VOICE_ID_A,
        "alternatives": [VOICE_ID_B, VOICE_ID_C],
    }
    result = _build_voices_response(FAKE_PLANT_ID, voice_data)
    assert isinstance(result, VoicesResponse)
    assert len(result.options) == 3


def test_build_voices_response_pads_from_catalog_when_no_alternatives():
    voice_data = {
        "plant_voice_id": None,
        "recommended_voice_id": VOICE_ID_A,
        "alternatives": [],
    }
    result = _build_voices_response(FAKE_PLANT_ID, voice_data)
    assert len(result.options) == 3


def test_build_voices_response_recommended_flag_on_correct_voice():
    voice_data = {
        "plant_voice_id": None,
        "recommended_voice_id": VOICE_ID_A,
        "alternatives": [VOICE_ID_B, VOICE_ID_C],
    }
    result = _build_voices_response(FAKE_PLANT_ID, voice_data)
    recommended = [o for o in result.options if o.recommended]
    assert len(recommended) == 1
    assert recommended[0].voice_id == VOICE_ID_A


def test_build_voices_response_current_voice_from_plant_when_set():
    voice_data = {
        "plant_voice_id": VOICE_ID_B,
        "recommended_voice_id": VOICE_ID_A,
        "alternatives": [VOICE_ID_B, VOICE_ID_C],
    }
    result = _build_voices_response(FAKE_PLANT_ID, voice_data)
    assert result.current_voice_id == VOICE_ID_B


def test_build_voices_response_current_voice_falls_back_to_recommended():
    voice_data = {
        "plant_voice_id": None,
        "recommended_voice_id": VOICE_ID_A,
        "alternatives": [VOICE_ID_B, VOICE_ID_C],
    }
    result = _build_voices_response(FAKE_PLANT_ID, voice_data)
    assert result.current_voice_id == VOICE_ID_A


# ---------------------------------------------------------------------------
# chat_with_plant — camino feliz y errores
# ---------------------------------------------------------------------------

async def test_chat_with_plant_returns_response(fake_redis):
    with (
        patch("app.services.chat_service._verify_and_get_plant", return_value=FAKE_PLANT_ROW),
        patch("app.services.chat_service._get_personality", return_value=("Soy una planta.", None)),
        patch("app.services.chat_service._load_latest_sensor_sync", return_value=None),
        patch("app.services.chat_service._load_history_sync", return_value=[]),
        patch("app.services.chat_service._fetch_username_sync", return_value="dueño/a"),
        patch("app.services.chat_service._load_summary_from_firestore_sync", return_value=""),
        patch("app.services.chat_service._save_exchange_sync"),
        patch(
            "app.services.chat_service.compact_if_needed",
            new_callable=AsyncMock,
            return_value=([], "", False),
        ),
        patch("app.services.chat_service.AsyncOpenAI") as mock_openai_cls,
    ):
        mock_openai = AsyncMock()
        mock_openai_cls.return_value = mock_openai
        mock_openai.chat.completions.create = AsyncMock(
            return_value=_make_openai_response("¡Hola desde la planta!")
        )

        result = await chat_with_plant(
            plant_id=FAKE_PLANT_ID,
            user_id=FAKE_USER_ID,
            message="¿Cómo estás?",
            language="es",
            redis_client=fake_redis,
        )

    assert isinstance(result, ChatResponse)
    assert result.reply == "¡Hola desde la planta!"
    assert result.plant_id == FAKE_PLANT_ID
    assert result.audio_url is None


async def test_chat_with_plant_plant_not_found_raises(fake_redis):
    with patch(
        "app.services.chat_service._verify_and_get_plant",
        side_effect=ValueError("Planta no encontrada"),
    ):
        with pytest.raises(ValueError, match="Planta no encontrada"):
            await chat_with_plant(
                plant_id=FAKE_PLANT_ID,
                user_id=FAKE_USER_ID,
                message="Test",
                language="es",
                redis_client=fake_redis,
            )


async def test_chat_with_plant_wrong_owner_raises(fake_redis):
    with patch(
        "app.services.chat_service._verify_and_get_plant",
        side_effect=PermissionError("No tienes acceso a esta planta"),
    ):
        with pytest.raises(PermissionError, match="No tienes acceso"):
            await chat_with_plant(
                plant_id=FAKE_PLANT_ID,
                user_id=FAKE_USER_ID,
                message="Test",
                language="es",
                redis_client=fake_redis,
            )


async def test_chat_with_plant_redis_cache_hit_skips_firestore():
    cached = json.dumps([
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": "Hola planta"},
    ])

    fake_redis = AsyncMock()

    async def redis_get(key: str):
        return cached if "summary" not in key else None

    fake_redis.get = AsyncMock(side_effect=redis_get)
    fake_redis.set = AsyncMock(return_value=True)

    with (
        patch("app.services.chat_service._verify_and_get_plant", return_value=FAKE_PLANT_ROW),
        patch("app.services.chat_service._get_personality", return_value=("Soy una planta.", None)),
        patch("app.services.chat_service._load_latest_sensor_sync", return_value=None),
        patch("app.services.chat_service._fetch_username_sync", return_value="dueño/a"),
        patch("app.services.chat_service._load_history_sync") as mock_fs_history,
        patch("app.services.chat_service._load_summary_from_firestore_sync", return_value=""),
        patch("app.services.chat_service._save_exchange_sync"),
        patch(
            "app.services.chat_service.compact_if_needed",
            new_callable=AsyncMock,
            return_value=([], "", False),
        ),
        patch("app.services.chat_service.AsyncOpenAI") as mock_openai_cls,
    ):
        mock_openai = AsyncMock()
        mock_openai_cls.return_value = mock_openai
        mock_openai.chat.completions.create = AsyncMock(
            return_value=_make_openai_response("Respuesta")
        )

        await chat_with_plant(
            plant_id=FAKE_PLANT_ID,
            user_id=FAKE_USER_ID,
            message="Test",
            language="es",
            redis_client=fake_redis,
        )

    mock_fs_history.assert_not_called()


async def test_chat_with_plant_audio_format_calls_tts(fake_redis):
    plant_with_voice = {**FAKE_PLANT_ROW, "elevenlabs_voice_id": VOICE_ID_A}

    with (
        patch("app.services.chat_service._verify_and_get_plant", return_value=plant_with_voice),
        patch("app.services.chat_service._get_personality", return_value=("Soy una planta.", VOICE_ID_A)),
        patch("app.services.chat_service._load_latest_sensor_sync", return_value=None),
        patch("app.services.chat_service._fetch_username_sync", return_value="dueño/a"),
        patch("app.services.chat_service._load_history_sync", return_value=[]),
        patch("app.services.chat_service._load_summary_from_firestore_sync", return_value=""),
        patch("app.services.chat_service._save_exchange_sync"),
        patch(
            "app.services.chat_service.compact_if_needed",
            new_callable=AsyncMock,
            return_value=([], "", False),
        ),
        patch("app.services.chat_service.AsyncOpenAI") as mock_openai_cls,
        patch("app.services.chat_service.tts_service.synthesize", new_callable=AsyncMock, return_value=b"audio"),
        patch("app.services.chat_service.tts_service.upload_audio", new_callable=AsyncMock, return_value="https://audio.url/clip.mp3"),
    ):
        mock_openai = AsyncMock()
        mock_openai_cls.return_value = mock_openai
        mock_openai.chat.completions.create = AsyncMock(
            return_value=_make_openai_response("Hola")
        )

        result = await chat_with_plant(
            plant_id=FAKE_PLANT_ID,
            user_id=FAKE_USER_ID,
            message="Test",
            language="es",
            redis_client=fake_redis,
            response_format="audio",
        )

    assert result.audio_url == "https://audio.url/clip.mp3"


# ---------------------------------------------------------------------------
# set_plant_voice
# ---------------------------------------------------------------------------

async def test_set_plant_voice_invalid_id_raises():
    with pytest.raises(ValueError, match="no es válido"):
        await set_plant_voice(FAKE_PLANT_ID, FAKE_USER_ID, "fake-invalid-voice-id-xyz")


async def test_set_plant_voice_valid_id_saves_and_returns(mock_supabase):
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{
            "plant_id": FAKE_PLANT_ID,
            "user_id": FAKE_USER_ID,
            "species_id": FAKE_SPECIES_ID,
            "nickname": "Pepe",
            "health_score": 85.0,
            "health_status": "healthy",
            "elevenlabs_voice_id": VOICE_ID_A,
            "elevenlabs_voice_alternatives": [VOICE_ID_B, VOICE_ID_C],
        }]
    )

    with patch("app.services.chat_service.supabase", mock_supabase):
        result = await set_plant_voice(FAKE_PLANT_ID, FAKE_USER_ID, VOICE_ID_A)

    assert isinstance(result, VoicesResponse)
    assert result.current_voice_id == VOICE_ID_A


# ---------------------------------------------------------------------------
# get_chat_history
# ---------------------------------------------------------------------------

async def test_get_chat_history_returns_messages():
    raw = [
        {"role": "user", "content": "Hola", "timestamp": "2026-01-01 00:00:00"},
        {"role": "assistant", "content": "¡Hola planta!", "timestamp": "2026-01-01 00:00:01"},
    ]
    with patch("app.services.chat_service._fetch_history_sync", return_value=raw):
        result = await get_chat_history(FAKE_PLANT_ID, FAKE_USER_ID, limit=50)

    assert len(result) == 2
    assert all(isinstance(m, ChatMessage) for m in result)
    assert result[0].role == "user"
    assert result[1].role == "assistant"


async def test_get_chat_history_empty():
    with patch("app.services.chat_service._fetch_history_sync", return_value=[]):
        result = await get_chat_history(FAKE_PLANT_ID, FAKE_USER_ID, limit=50)

    assert result == []
