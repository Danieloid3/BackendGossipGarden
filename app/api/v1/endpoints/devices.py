"""Endpoints para registrar y desregistrar device tokens de FCM."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.db.supabase import supabase
from app.schemas.devices import DeviceTokenCreate, DeviceTokenResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=DeviceTokenResponse, status_code=201)
async def register_device(
    body: DeviceTokenCreate,
    user_id: str = Depends(get_current_user),
):
    """Registra un FCM token para enviar push notifications al dispositivo.

    Si el token ya existe se actualiza el `user_id` (caso de re-login).
    """
    def _upsert():
        return (
            supabase.table("device_tokens")
            .upsert(
                {
                    "user_id": user_id,
                    "token": body.token,
                    "platform": body.platform,
                    "last_used_at": "now()",
                },
                on_conflict="token",
            )
            .execute()
        )

    try:
        result = await asyncio.to_thread(_upsert)
    except Exception as e:
        logger.error("Error registrando device token: %s", e)
        raise HTTPException(status_code=500, detail="No se pudo registrar el dispositivo")

    if not result.data:
        raise HTTPException(status_code=500, detail="Sin respuesta de Supabase al registrar el token")

    return result.data[0]


@router.delete("/{token}", status_code=204)
async def unregister_device(
    token: str,
    user_id: str = Depends(get_current_user),
):
    """Elimina un FCM token (logout o desinstalación)."""
    def _delete():
        return (
            supabase.table("device_tokens")
            .delete()
            .eq("user_id", user_id)
            .eq("token", token)
            .execute()
        )

    try:
        await asyncio.to_thread(_delete)
    except Exception as e:
        logger.error("Error eliminando device token: %s", e)
        raise HTTPException(status_code=500, detail="No se pudo eliminar el dispositivo")
