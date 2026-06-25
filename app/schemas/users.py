from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# Idiomas soportados — consistente con los demás endpoints del sistema
SUPPORTED_LANGUAGES = Literal["es", "en", "fr", "pt", "de", "it"]


class UserResponse(BaseModel):
    """Perfil público del usuario autenticado."""
    user_id: UUID
    username: str
    email: Optional[str] = None          # Viene de Supabase Auth (metadata), puede ser null
    preferred_language: str = "es"
    created_at: datetime


class UserUpdate(BaseModel):
    """Campos editables del perfil de usuario. Enviar solo los que cambian."""
    username: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="Nombre de usuario visible en la app"
    )
    preferred_language: Optional[SUPPORTED_LANGUAGES] = Field(
        default=None,
        description="Idioma preferido para respuestas de IA y alertas: es|en|fr|pt|de|it"
    )
