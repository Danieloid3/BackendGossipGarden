"""Punto único de fan-out de notificaciones.

Cuando el evaluator o el chat generan un mensaje que debe llegar al usuario,
llaman a `notify()` y este se encarga de empujarlo por WebSocket (app abierta)
y FCM (app cerrada) en paralelo.

Diseñado para no romper el flujo principal: cualquier error en push es loggeado
pero nunca propagado.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Literal

from app.services import fcm_service
from app.services.websocket_manager import manager

logger = logging.getLogger(__name__)

NotificationType = Literal["chat_message", "proactive_alert"]


async def notify(
    user_id: str,
    plant_id: str,
    plant_nickname: str,
    message: str,
    notification_type: NotificationType,
    audio_url: str | None = None,
    send_fcm: bool = True,
) -> None:
    """Empuja una notificación al usuario por WebSocket y FCM.

    - `send_fcm=False` para mensajes normales del chat: el usuario ya está
      en la app, no queremos spamear con notificaciones del sistema.
    - `send_fcm=True` para alertas proactivas: queremos que llegue aunque
      la app esté cerrada.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    ws_payload = {
        "type": notification_type,
        "plant_id": plant_id,
        "plant_nickname": plant_nickname,
        "message": message,
        "audio_url": audio_url,
        "timestamp": timestamp,
    }

    tasks = [_safe_ws(user_id, ws_payload)]
    if send_fcm:
        tasks.append(_safe_fcm(user_id, plant_id, plant_nickname, message, notification_type))

    await asyncio.gather(*tasks, return_exceptions=True)


async def _safe_ws(user_id: str, payload: dict) -> None:
    try:
        delivered = await manager.send_to_user(user_id, payload)
        if delivered:
            logger.info("WS push entregado a %d conexión(es) del user %s", delivered, user_id)
    except Exception as e:
        logger.error("Error enviando WS a user %s: %s", user_id, e)


async def _safe_fcm(
    user_id: str,
    plant_id: str,
    plant_nickname: str,
    message: str,
    notification_type: NotificationType,
) -> None:
    try:
        body = (message[:140] + "…") if len(message) > 140 else message
        count = await fcm_service.send_push(
            user_id=user_id,
            title=plant_nickname,
            body=body,
            data={"plant_id": plant_id, "type": notification_type},
        )
        if count:
            logger.info("FCM entregado a %d dispositivo(s) del user %s", count, user_id)
    except Exception as e:
        logger.error("Error enviando FCM a user %s: %s", user_id, e)
