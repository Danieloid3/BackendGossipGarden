"""Wrapper de Firebase Cloud Messaging (FCM) para push notifications."""
from __future__ import annotations

import asyncio
import logging

from firebase_admin import messaging

from app.db.firebase import firebase_db  # noqa: F401  asegura initialize_app() antes de usar messaging
from app.db.supabase import supabase

logger = logging.getLogger(__name__)


def _send_multicast_sync(tokens: list[str], title: str, body: str, data: dict[str, str]) -> messaging.BatchResponse:
    message = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=body),
        data={k: str(v) for k, v in data.items()},
        tokens=tokens,
    )
    return messaging.send_each_for_multicast(message)


async def send_push(
    user_id: str,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> int:
    """Envía push notification a todos los device_tokens del usuario.

    Devuelve el número de mensajes entregados exitosamente.
    Limpia automáticamente tokens inválidos (UNREGISTERED).
    """
    result = (
        supabase.table("device_tokens")
        .select("token")
        .eq("user_id", user_id)
        .execute()
    )
    tokens = [row["token"] for row in (result.data or [])]
    if not tokens:
        return 0

    try:
        response = await asyncio.to_thread(
            _send_multicast_sync, tokens, title, body, data or {}
        )
    except Exception as e:
        logger.error("FCM send_multicast falló para user %s: %s", user_id, e)
        return 0

    # Limpiar tokens muertos
    dead_tokens: list[str] = []
    for i, resp in enumerate(response.responses):
        if not resp.success and resp.exception:
            code = getattr(resp.exception, "code", "")
            if code in ("messaging/registration-token-not-registered", "messaging/invalid-argument"):
                dead_tokens.append(tokens[i])

    if dead_tokens:
        try:
            supabase.table("device_tokens").delete().in_("token", dead_tokens).execute()
            logger.info("Eliminados %d tokens FCM muertos del user %s", len(dead_tokens), user_id)
        except Exception as e:
            logger.warning("No se pudieron eliminar tokens muertos: %s", e)

    return response.success_count
