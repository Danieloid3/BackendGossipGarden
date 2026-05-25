"""Tests de los endpoints HTTP del chat (/api/v1/chat/*)."""
from __future__ import annotations

from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.security import get_current_user
from app.db.redis import get_redis_client
from app.main import app
from app.schemas.chat import ChatMessage, ChatResponse, VoiceOption, VoicesResponse

FAKE_PLANT_ID = "aaaaaaaa-0000-0000-0000-000000000001"
FAKE_USER_ID = "00000000-0000-0000-0000-000000000001"

VOICE_ID_A = "N2lVS1w4EtoT3dr4eOWO"
VOICE_ID_B = "SOYHLrjzK2X1ezoPC6cr"
VOICE_ID_C = "tomkxGQGz4b1kE0EM722"

_FAKE_CHAT_RESPONSE = ChatResponse(
    reply="¡Hola desde la planta!",
    plant_id=FAKE_PLANT_ID,
    timestamp="2026-01-01 00:00:00",
    audio_url=None,
)

_FAKE_VOICES_RESPONSE = VoicesResponse(
    plant_id=FAKE_PLANT_ID,
    current_voice_id=VOICE_ID_A,
    options=[
        VoiceOption(voice_id=VOICE_ID_A, name="Callum", gender="male", style="husky", lang="en", recommended=True),
        VoiceOption(voice_id=VOICE_ID_B, name="Harry",  gender="male", style="fierce", lang="en"),
        VoiceOption(voice_id=VOICE_ID_C, name="Mario",  gender="male", style="animado", lang="es"),
    ],
)

_FAKE_MESSAGES = [
    ChatMessage(role="user",      content="Hola",        timestamp="2026-01-01 00:00:00"),
    ChatMessage(role="assistant", content="¡Hola planta!", timestamp="2026-01-01 00:00:01"),
]


@pytest_asyncio.fixture
async def chat_client() -> AsyncGenerator[AsyncClient, None]:
    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value=None)
    fake_redis.set = AsyncMock(return_value=True)

    async def override_redis():
        yield fake_redis

    app.dependency_overrides[get_current_user] = lambda: FAKE_USER_ID
    app.dependency_overrides[get_redis_client] = override_redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /api/v1/chat/{plant_id}
# ---------------------------------------------------------------------------

async def test_send_message_returns_200(chat_client):
    with patch(
        "app.services.chat_service.chat_with_plant",
        new_callable=AsyncMock,
        return_value=_FAKE_CHAT_RESPONSE,
    ):
        response = await chat_client.post(
            f"/api/v1/chat/{FAKE_PLANT_ID}",
            json={"message": "¿Cómo estás?", "language": "es"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["reply"] == "¡Hola desde la planta!"
    assert data["plant_id"] == FAKE_PLANT_ID
    assert data["audio_url"] is None


async def test_send_message_empty_string_returns_422(chat_client):
    response = await chat_client.post(
        f"/api/v1/chat/{FAKE_PLANT_ID}",
        json={"message": "", "language": "es"},
    )
    assert response.status_code == 422


async def test_send_message_too_long_returns_422(chat_client):
    response = await chat_client.post(
        f"/api/v1/chat/{FAKE_PLANT_ID}",
        json={"message": "x" * 2001, "language": "es"},
    )
    assert response.status_code == 422


async def test_send_message_invalid_language_returns_422(chat_client):
    response = await chat_client.post(
        f"/api/v1/chat/{FAKE_PLANT_ID}",
        json={"message": "Hola", "language": "zh"},
    )
    assert response.status_code == 422


async def test_send_message_invalid_response_format_returns_422(chat_client):
    response = await chat_client.post(
        f"/api/v1/chat/{FAKE_PLANT_ID}",
        json={"message": "Hola", "language": "es", "response_format": "video"},
    )
    assert response.status_code == 422


async def test_send_message_missing_body_returns_422(chat_client):
    response = await chat_client.post(f"/api/v1/chat/{FAKE_PLANT_ID}")
    assert response.status_code == 422


async def test_send_message_plant_not_found_returns_404(chat_client):
    with patch(
        "app.services.chat_service.chat_with_plant",
        new_callable=AsyncMock,
        side_effect=ValueError("Planta no encontrada"),
    ):
        response = await chat_client.post(
            f"/api/v1/chat/{FAKE_PLANT_ID}",
            json={"message": "Hola", "language": "es"},
        )

    assert response.status_code == 404
    assert "Planta no encontrada" in response.json()["detail"]


async def test_send_message_wrong_owner_returns_403(chat_client):
    with patch(
        "app.services.chat_service.chat_with_plant",
        new_callable=AsyncMock,
        side_effect=PermissionError("No tienes acceso a esta planta"),
    ):
        response = await chat_client.post(
            f"/api/v1/chat/{FAKE_PLANT_ID}",
            json={"message": "Hola", "language": "es"},
        )

    assert response.status_code == 403


async def test_send_message_openai_failure_returns_500(chat_client):
    with patch(
        "app.services.chat_service.chat_with_plant",
        new_callable=AsyncMock,
        side_effect=RuntimeError("OpenAI timeout"),
    ):
        response = await chat_client.post(
            f"/api/v1/chat/{FAKE_PLANT_ID}",
            json={"message": "Hola", "language": "es"},
        )

    assert response.status_code == 500


# ---------------------------------------------------------------------------
# GET /api/v1/chat/{plant_id}/history
# ---------------------------------------------------------------------------

async def test_get_history_returns_200_with_messages(chat_client):
    with (
        patch("app.api.v1.endpoints.chat._verify_plant_access"),
        patch(
            "app.services.chat_service.get_chat_history",
            new_callable=AsyncMock,
            return_value=_FAKE_MESSAGES,
        ),
    ):
        response = await chat_client.get(f"/api/v1/chat/{FAKE_PLANT_ID}/history")

    assert response.status_code == 200
    data = response.json()
    assert data["plant_id"] == FAKE_PLANT_ID
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"


async def test_get_history_returns_empty_list(chat_client):
    with (
        patch("app.api.v1.endpoints.chat._verify_plant_access"),
        patch(
            "app.services.chat_service.get_chat_history",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        response = await chat_client.get(f"/api/v1/chat/{FAKE_PLANT_ID}/history")

    assert response.status_code == 200
    assert response.json()["messages"] == []


async def test_get_history_plant_not_found_returns_404(chat_client):
    with patch(
        "app.api.v1.endpoints.chat._verify_plant_access",
        side_effect=ValueError("Planta no encontrada"),
    ):
        response = await chat_client.get(f"/api/v1/chat/{FAKE_PLANT_ID}/history")

    assert response.status_code == 404


async def test_get_history_wrong_owner_returns_403(chat_client):
    with patch(
        "app.api.v1.endpoints.chat._verify_plant_access",
        side_effect=PermissionError("No tienes acceso a esta planta"),
    ):
        response = await chat_client.get(f"/api/v1/chat/{FAKE_PLANT_ID}/history")

    assert response.status_code == 403


async def test_get_history_limit_param_is_passed(chat_client):
    with (
        patch("app.api.v1.endpoints.chat._verify_plant_access"),
        patch(
            "app.services.chat_service.get_chat_history",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_history,
    ):
        await chat_client.get(f"/api/v1/chat/{FAKE_PLANT_ID}/history?limit=10")

    mock_history.assert_called_once_with(FAKE_PLANT_ID, FAKE_USER_ID, 10)


# ---------------------------------------------------------------------------
# GET /api/v1/chat/{plant_id}/voices
# ---------------------------------------------------------------------------

async def test_get_voices_returns_200_with_three_options(chat_client):
    with patch(
        "app.services.chat_service.get_voice_options",
        new_callable=AsyncMock,
        return_value=_FAKE_VOICES_RESPONSE,
    ):
        response = await chat_client.get(f"/api/v1/chat/{FAKE_PLANT_ID}/voices")

    assert response.status_code == 200
    data = response.json()
    assert len(data["options"]) == 3
    assert data["current_voice_id"] == VOICE_ID_A


async def test_get_voices_plant_not_found_returns_404(chat_client):
    with patch(
        "app.services.chat_service.get_voice_options",
        new_callable=AsyncMock,
        side_effect=ValueError("Planta no encontrada"),
    ):
        response = await chat_client.get(f"/api/v1/chat/{FAKE_PLANT_ID}/voices")

    assert response.status_code == 404


async def test_get_voices_wrong_owner_returns_403(chat_client):
    with patch(
        "app.services.chat_service.get_voice_options",
        new_callable=AsyncMock,
        side_effect=PermissionError("No tienes acceso"),
    ):
        response = await chat_client.get(f"/api/v1/chat/{FAKE_PLANT_ID}/voices")

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /api/v1/chat/{plant_id}/voice
# ---------------------------------------------------------------------------

async def test_set_voice_returns_200_with_valid_id(chat_client):
    with patch(
        "app.services.chat_service.set_plant_voice",
        new_callable=AsyncMock,
        return_value=_FAKE_VOICES_RESPONSE,
    ):
        response = await chat_client.patch(
            f"/api/v1/chat/{FAKE_PLANT_ID}/voice",
            json={"voice_id": VOICE_ID_A},
        )

    assert response.status_code == 200
    assert response.json()["current_voice_id"] == VOICE_ID_A


async def test_set_voice_empty_id_returns_422(chat_client):
    response = await chat_client.patch(
        f"/api/v1/chat/{FAKE_PLANT_ID}/voice",
        json={"voice_id": ""},
    )
    assert response.status_code == 422


async def test_set_voice_missing_body_returns_422(chat_client):
    response = await chat_client.patch(f"/api/v1/chat/{FAKE_PLANT_ID}/voice")
    assert response.status_code == 422


async def test_set_voice_invalid_id_returns_404(chat_client):
    # set_plant_voice lanza ValueError para voice_id no en catálogo → endpoint devuelve 404
    with patch(
        "app.services.chat_service.set_plant_voice",
        new_callable=AsyncMock,
        side_effect=ValueError("voice_id 'nonexistent' no es válido"),
    ):
        response = await chat_client.patch(
            f"/api/v1/chat/{FAKE_PLANT_ID}/voice",
            json={"voice_id": "nonexistent-id"},
        )

    assert response.status_code == 404
