"""Endpoints de identificación de plantas via Plant.id → GBIF → RAG → OpenAI."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from app.core.config import settings
from app.core.security import get_current_user
from app.schemas.identification import (
    CompletedResponse,
    FromCandidateRequest,
    IdentifyResponse,
)
from app.services import identification_pipeline as pipeline
from app.services.image_storage_service import compute_storage_path, store_identification_result

router = APIRouter()

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB


@router.post("/identify", response_model=IdentifyResponse)
async def identify(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(..., description="Foto de la planta (JPEG/PNG/WebP, máx 8 MB)"),
    latitude: float | None = Form(default=None),
    longitude: float | None = Form(default=None),
    output_language: str = Form(default="es"),
    user_id: str = Depends(get_current_user),
) -> IdentifyResponse:
    """Identifica la planta en la imagen y responde según umbral de confianza.

    - `< 0.25` → `needs_more_photos`: pedir otra foto.
    - `0.25 – 0.75` → `needs_user_selection`: top 3 candidatos para que el usuario elija.
    - `> 0.75` → `completed`: ejecuta pipeline completo y devuelve la ficha.

    La imagen se persiste en Firebase Storage de forma asíncrona (sin latencia extra).
    """
    if image.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Formato no soportado: {image.content_type}. Usa JPEG, PNG o WebP.",
        )

    content_type = image.content_type or "image/jpeg"
    image_bytes = await image.read()
    if len(image_bytes) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Imagen demasiado grande (máx 8 MB)")

    # Quitamos la validación estricta de idiomas aquí, o la aplicamos solo al input inicial.
    # Pero el usuario dice que el backend ya lo debería traer. Así que si no viene, usamos "es".
    
    from app.db.supabase import supabase
    
    final_language = output_language
    try:
        user_row = supabase.table("users").select("preferred_language").eq("user_id", user_id).execute()
        if user_row.data and user_row.data[0].get("preferred_language"):
            final_language = user_row.data[0]["preferred_language"]
    except Exception as e:
        import logging
        logging.warning(f"Failed to fetch preferred_language (column might not exist): {e}")

    result = await pipeline.identify_from_image(
        image_bytes,
        latitude=latitude,
        longitude=longitude,
        output_language=final_language,
    )

    # Generar el path antes del background task para incluirlo en la respuesta.
    # El app puede usarlo inmediatamente al crear la planta.
    photo_storage_path: str | None = None
    if settings.FIREBASE_STORAGE_BUCKET:
        if isinstance(result, CompletedResponse):
            photo_storage_path = compute_storage_path(
                user_id, result.profile.scientific_name, content_type
            )
            result = result.model_copy(update={"photo_storage_path": photo_storage_path})
        elif isinstance(result, NeedsUserSelectionResponse) and result.candidates:
            photo_storage_path = compute_storage_path(
                user_id, result.candidates[0].scientific_name, content_type
            )
            result = result.model_copy(update={"photo_storage_path": photo_storage_path})

    background_tasks.add_task(
        store_identification_result,
        image_bytes,
        user_id,
        result,
        storage_path=photo_storage_path,
        latitude=latitude,
        longitude=longitude,
        output_language=final_language,
    )

    return result


@router.post("/species/from-candidate", response_model=CompletedResponse)
async def from_candidate(
    body: FromCandidateRequest,
    user_id: str = Depends(get_current_user),
) -> CompletedResponse:
    """Recibe el candidato elegido por el usuario tras un `needs_user_selection`
    y ejecuta el pipeline completo (GBIF → RAG → OpenAI → persistencia).

    Es idempotente: si la especie ya existe con contenido en el idioma solicitado,
    devuelve la ficha cacheada sin llamar a APIs externas.
    """
    from app.db.supabase import supabase
    final_language = body.output_language
    try:
        user_row = supabase.table("users").select("preferred_language").eq("user_id", user_id).execute()
        if user_row.data and user_row.data[0].get("preferred_language"):
            final_language = user_row.data[0]["preferred_language"]
    except Exception as e:
        import logging
        logging.warning(f"Failed to fetch preferred_language (column might not exist): {e}")

    return await pipeline.enrich_and_persist(
        body.candidate,
        output_language=final_language,
    )
