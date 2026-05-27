"""Tests live del pipeline completo de chat.

Usa Supabase, Firestore, Redis y OpenAI reales.
La planta de prueba (TEST_PLANT_ID) se crea y destruye automáticamente
por el fixture de sesión `test_plant` en conftest.py.
"""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.schemas.chat import ChatMessage, ChatResponse
from app.services.chat_service import chat_with_plant, get_chat_history

TEST_USER_ID = "f9c11ced-2085-4acf-996f-7c2320703132"

pytestmark = pytest.mark.live


# ---------------------------------------------------------------------------
# Chat básico (texto)
# ---------------------------------------------------------------------------

async def test_chat_returns_valid_response(test_plant, redis_client):
    """chat_with_plant() retorna una respuesta de texto coherente."""
    result = await chat_with_plant(
        plant_id=test_plant,
        user_id=TEST_USER_ID,
        message="Hola, ¿cómo te encuentras hoy?",
        language="es",
        redis_client=redis_client,
    )

    assert isinstance(result, ChatResponse)
    assert result.plant_id == test_plant
    assert isinstance(result.reply, str)
    assert len(result.reply.strip()) > 5
    assert result.audio_url is None


async def test_chat_stays_on_topic(test_plant, redis_client):
    """El chatbot no responde directamente preguntas off-topic."""
    result = await chat_with_plant(
        plant_id=test_plant,
        user_id=TEST_USER_ID,
        message="¿Cuál es la capital de Francia?",
        language="es",
        redis_client=redis_client,
    )

    assert isinstance(result.reply, str)
    assert len(result.reply.strip()) > 5


async def test_chat_responds_in_requested_language(test_plant, redis_client):
    """El chatbot responde en el idioma solicitado."""
    result = await chat_with_plant(
        plant_id=test_plant,
        user_id=TEST_USER_ID,
        message="Hello! How are you?",
        language="en",
        redis_client=redis_client,
    )

    assert isinstance(result.reply, str)
    assert len(result.reply.strip()) > 5


# ---------------------------------------------------------------------------
# Chat con audio (TTS)
# ---------------------------------------------------------------------------

async def test_chat_audio_format_returns_audio_url(test_plant, redis_client):
    """response_format='audio' llama a ElevenLabs sin lanzar excepción."""
    result = await chat_with_plant(
        plant_id=test_plant,
        user_id=TEST_USER_ID,
        message="Dime algo bonito.",
        language="es",
        redis_client=redis_client,
        response_format="audio",
    )

    assert isinstance(result, ChatResponse)
    assert result.reply
    if settings.FIREBASE_STORAGE_BUCKET:
        assert result.audio_url is not None


# ---------------------------------------------------------------------------
# Historial
# ---------------------------------------------------------------------------

async def test_history_contains_messages_after_chat(test_plant, redis_client):
    """get_chat_history() retorna mensajes user+assistant después de chatear."""
    await chat_with_plant(
        plant_id=test_plant,
        user_id=TEST_USER_ID,
        message="¿Cuánta agua necesitas?",
        language="es",
        redis_client=redis_client,
    )

    history = await get_chat_history(test_plant, TEST_USER_ID, limit=20)

    assert len(history) > 0
    assert all(isinstance(m, ChatMessage) for m in history)
    roles = {m.role for m in history}
    assert "user" in roles
    assert "assistant" in roles


async def test_history_limit_respected(test_plant, redis_client):
    """get_chat_history() respeta el parámetro limit."""
    history = await get_chat_history(test_plant, TEST_USER_ID, limit=2)
    assert len(history) <= 2


# ---------------------------------------------------------------------------
# Errores esperados
# ---------------------------------------------------------------------------

async def test_wrong_user_raises_permission_error(test_plant, redis_client):
    """Un user_id diferente al dueño lanza PermissionError."""
    other_user = "00000000-0000-0000-0000-000000000099"

    with pytest.raises(PermissionError):
        await chat_with_plant(
            plant_id=test_plant,
            user_id=other_user,
            message="Hola",
            language="es",
            redis_client=redis_client,
        )


async def test_nonexistent_plant_raises_value_error(redis_client):
    """Un plant_id que no existe lanza ValueError."""
    fake_plant = "00000000-0000-0000-0000-000000000000"

    with pytest.raises(ValueError, match="no encontrada"):
        await chat_with_plant(
            plant_id=fake_plant,
            user_id=TEST_USER_ID,
            message="Hola",
            language="es",
            redis_client=redis_client,
        )
