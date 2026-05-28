"""Tests del notification_service (fan-out a WS + FCM)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services import notification_service


@pytest.mark.asyncio
async def test_notify_chat_message_does_not_send_fcm():
    """Para chat normal solo se debe llamar a WebSocket, no a FCM."""
    with patch.object(notification_service.manager, "send_to_user", new=AsyncMock(return_value=1)) as ws_send, \
         patch.object(notification_service.fcm_service, "send_push", new=AsyncMock(return_value=0)) as fcm_send:

        await notification_service.notify(
            user_id="user-1",
            plant_id="plant-1",
            plant_nickname="Monstera",
            message="hola",
            notification_type="chat_message",
            send_fcm=False,
        )

        ws_send.assert_awaited_once()
        fcm_send.assert_not_called()


@pytest.mark.asyncio
async def test_notify_proactive_alert_sends_both_channels():
    """Para alertas proactivas se debe disparar WS + FCM en paralelo."""
    with patch.object(notification_service.manager, "send_to_user", new=AsyncMock(return_value=1)) as ws_send, \
         patch.object(notification_service.fcm_service, "send_push", new=AsyncMock(return_value=2)) as fcm_send:

        await notification_service.notify(
            user_id="user-1",
            plant_id="plant-1",
            plant_nickname="Cactus",
            message="¡tengo sed!",
            notification_type="proactive_alert",
            send_fcm=True,
        )

        ws_send.assert_awaited_once()
        fcm_send.assert_awaited_once()
        # El FCM debe llevar plant_id + type en data
        kwargs = fcm_send.await_args.kwargs
        assert kwargs["user_id"] == "user-1"
        assert kwargs["title"] == "Cactus"
        assert kwargs["data"]["plant_id"] == "plant-1"
        assert kwargs["data"]["type"] == "proactive_alert"


@pytest.mark.asyncio
async def test_notify_ws_payload_contains_required_fields():
    """El payload empujado por WS debe tener todos los campos del contrato."""
    captured: dict = {}

    async def fake_send(user_id, payload):
        captured.update(payload)
        return 1

    with patch.object(notification_service.manager, "send_to_user", new=fake_send), \
         patch.object(notification_service.fcm_service, "send_push", new=AsyncMock(return_value=0)):

        await notification_service.notify(
            user_id="user-1",
            plant_id="plant-1",
            plant_nickname="Orquídea",
            message="¡brillan mis hojas!",
            notification_type="chat_message",
            audio_url="path/audio.mp3",
            send_fcm=False,
        )

    assert captured["type"] == "chat_message"
    assert captured["plant_id"] == "plant-1"
    assert captured["plant_nickname"] == "Orquídea"
    assert captured["message"] == "¡brillan mis hojas!"
    assert captured["audio_url"] == "path/audio.mp3"
    assert "timestamp" in captured


@pytest.mark.asyncio
async def test_notify_swallows_errors_to_not_break_chat():
    """Errores en WS/FCM no deben propagarse — el chat no se puede romper."""
    with patch.object(notification_service.manager, "send_to_user", new=AsyncMock(side_effect=RuntimeError("ws boom"))), \
         patch.object(notification_service.fcm_service, "send_push", new=AsyncMock(side_effect=RuntimeError("fcm boom"))):

        # No debe lanzar
        await notification_service.notify(
            user_id="user-1",
            plant_id="plant-1",
            plant_nickname="Monstera",
            message="x",
            notification_type="proactive_alert",
            send_fcm=True,
        )


@pytest.mark.asyncio
async def test_fcm_body_truncates_long_messages():
    """El body de FCM se trunca a ~140 chars para no romper el push notification."""
    captured: dict = {}

    async def fake_fcm(user_id, title, body, data):
        captured["body"] = body
        return 1

    with patch.object(notification_service.manager, "send_to_user", new=AsyncMock(return_value=0)), \
         patch.object(notification_service.fcm_service, "send_push", new=fake_fcm):

        long_msg = "a" * 300
        await notification_service.notify(
            user_id="u",
            plant_id="p",
            plant_nickname="N",
            message=long_msg,
            notification_type="proactive_alert",
            send_fcm=True,
        )

    assert len(captured["body"]) <= 150
    assert captured["body"].endswith("…")
