"""Endpoints de notificaciones: WebSocket (push tiempo real) + histórico REST."""
from __future__ import annotations

import asyncio
import logging

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.security import get_current_user, jwk_client
from app.db.supabase import supabase
from app.schemas.notifications import NotificationEvent, NotificationsResponse
from app.services.websocket_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()


def _verify_token(token: str) -> str:
    """Valida un JWT Supabase y devuelve el user_id. Lanza ValueError si es inválido."""
    try:
        signing_key = jwk_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
        )
    except Exception as e:
        raise ValueError(f"Token inválido: {e}")

    user_id = payload.get("sub")
    if not user_id:
        raise ValueError("Token sin sub")
    return user_id


@router.websocket("/ws")
async def notifications_ws(websocket: WebSocket, token: str = Query(...)):
    """Conexión WebSocket persistente para recibir notificaciones en tiempo real.

    Autenticación: JWT pasado como query param (`?token=<jwt>`).
    """
    try:
        user_id = _verify_token(token)
    except ValueError as e:
        await websocket.close(code=4401, reason=str(e))
        return

    await manager.connect(user_id, websocket)
    try:
        while True:
            # No esperamos mensajes del cliente, solo mantenemos viva la conexión.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WS terminó con error para user %s: %s", user_id, e)
    finally:
        await manager.disconnect(user_id, websocket)


@router.get("", response_model=NotificationsResponse)
async def get_notifications(
    limit: int = Query(50, ge=1, le=200),
    user_id: str = Depends(get_current_user),
):
    """Histórico de eventos del usuario (paginado por timestamp descendente).

    Solo devuelve eventos de plantas que pertenecen al usuario autenticado.
    """
    def _fetch():
        # Plantas del usuario
        plants_res = supabase.table("plants").select("plant_id").eq("user_id", user_id).execute()
        plant_ids = [p["plant_id"] for p in (plants_res.data or [])]
        if not plant_ids:
            return []

        events_res = (
            supabase.table("events")
            .select("*")
            .in_("plant_id", plant_ids)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return events_res.data or []

    try:
        rows = await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.error("Error consultando notificaciones: %s", e)
        raise HTTPException(status_code=500, detail="Error consultando notificaciones")

    events = [NotificationEvent(**row) for row in rows]
    return NotificationsResponse(events=events)
