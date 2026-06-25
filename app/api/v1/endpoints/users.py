"""Endpoints de perfil del usuario autenticado: GET /users/me y PATCH /users/me."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.db.supabase import supabase
from app.schemas.users import UserResponse, UserUpdate

logger = logging.getLogger(__name__)

router = APIRouter()


def _fetch_user(user_id: str) -> dict | None:
    """Obtiene el registro del usuario desde la tabla `users`. Síncrono (se envuelve con to_thread)."""
    res = (
        supabase.table("users")
        .select("user_id, username, email, preferred_language, created_at")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    return res.data if res else None


@router.get("/me", response_model=UserResponse)
async def get_me(user_id: str = Depends(get_current_user)):
    """Devuelve el perfil del usuario autenticado.

    Incluye: `user_id`, `username`, `email`, `preferred_language`, `created_at`.
    """
    try:
        row = await asyncio.to_thread(_fetch_user, user_id)
    except Exception as e:
        logger.error("Error consultando perfil de usuario %s: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Error consultando el perfil del usuario")

    if not row:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    return UserResponse(**row)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdate,
    user_id: str = Depends(get_current_user),
):
    """Actualiza los campos editables del perfil del usuario.

    Campos editables: `username`, `preferred_language`.
    Enviar solo los campos que se quieren cambiar.
    """
    # Solo actualizar los campos enviados y no nulos
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}

    if not updates:
        raise HTTPException(status_code=400, detail="No se enviaron campos para actualizar")

    def _update() -> dict | None:
        res = (
            supabase.table("users")
            .update(updates)
            .eq("user_id", user_id)
            .execute()
        )
        if not res.data:
            return None
        # Re-fetch para devolver el registro completo
        return _fetch_user(user_id)

    try:
        row = await asyncio.to_thread(_update)
    except Exception as e:
        logger.error("Error actualizando perfil de usuario %s: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Error actualizando el perfil del usuario")

    if not row:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    return UserResponse(**row)
