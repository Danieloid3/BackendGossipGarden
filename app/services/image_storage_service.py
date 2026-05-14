"""Almacenamiento asíncrono de imágenes de identificación y de plantas.

Comprime con Pillow (máx 1920px, JPEG q=85) antes de subir a Firebase Storage.
El metadata de identificación se persiste en Firestore.
Diseñado para ejecutarse como BackgroundTask — nunca bloquea la respuesta al cliente.
"""

from __future__ import annotations

import asyncio
import io
import logging
import uuid
from datetime import datetime, timezone

from app.core.config import settings
from app.db.firebase import firebase_db
from app.schemas.identification import CompletedResponse, NeedsMorePhotosResponse, NeedsUserSelectionResponse

logger = logging.getLogger(__name__)

_MAX_PX = 1920
_JPEG_QUALITY = 85


def compute_storage_path(user_id: str, scientific_name: str | None, content_type: str) -> str:
    """Genera el path en Firebase Storage de forma determinista.

    Llamar antes de lanzar el BackgroundTask para incluir el path en la respuesta.
    """
    ext = content_type.split("/")[-1]  # jpeg, png, webp
    safe_name = (scientific_name or "unknown").replace(" ", "_")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    uid = str(uuid.uuid4())[:8]
    return f"plant_identifications/{user_id}/{ts}_{safe_name}_{uid}.{ext}"


def compress_image(image_bytes: bytes) -> bytes:
    """Redimensiona a máx 1920px y re-encoda como JPEG q=85.

    Siempre retorna JPEG independientemente del formato de entrada.
    """
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes))
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    ratio = min(_MAX_PX / img.width, _MAX_PX / img.height, 1.0)
    if ratio < 1.0:
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    return out.getvalue()


async def store_identification_result(
    image_bytes: bytes,
    user_id: str,
    result: CompletedResponse | NeedsMorePhotosResponse | NeedsUserSelectionResponse,
    *,
    storage_path: str | None,
    latitude: float | None,
    longitude: float | None,
    output_language: str,
) -> None:
    """Comprime la imagen, sube a Firebase Storage y escribe metadata en Firestore.

    Captura todas las excepciones internamente: un fallo aquí nunca debe
    afectar la respuesta que ya recibió el cliente.
    """
    try:
        identified_at = datetime.now(timezone.utc)
        status = result.status
        species_id: str | None = None
        scientific_name: str | None = None
        top_probability: float | None = None

        if isinstance(result, CompletedResponse):
            species_id = str(result.profile.species_id)
            scientific_name = result.profile.scientific_name
        elif isinstance(result, NeedsMorePhotosResponse):
            top_probability = result.top_probability
        elif isinstance(result, NeedsUserSelectionResponse) and result.candidates:
            scientific_name = result.candidates[0].scientific_name
            top_probability = result.candidates[0].probability

        actual_storage_path: str | None = None
        if storage_path and settings.FIREBASE_STORAGE_BUCKET:
            actual_storage_path = await _upload_compressed(image_bytes, storage_path)

        doc = {
            "user_id": user_id,
            "identified_at": identified_at,
            "status": status,
            "species_id": species_id,
            "scientific_name": scientific_name,
            "top_probability": top_probability,
            "output_language": output_language,
            "latitude": latitude,
            "longitude": longitude,
            "storage_path": actual_storage_path,
        }

        await asyncio.to_thread(firebase_db.collection("plant_identifications").add, doc)

        logger.info(
            "Identificación almacenada — user=%s status=%s species=%s",
            user_id, status, scientific_name,
        )

    except Exception as e:
        logger.error("Error en store_identification_result para user=%s: %s", user_id, e)


async def upload_plant_photo(
    image_bytes: bytes,
    user_id: str,
    plant_id: str,
) -> str:
    """Comprime y sube la foto de una planta a Firebase Storage.

    Retorna el storage_path. Lanza excepción si el bucket no está configurado
    o si la subida falla (el caller decide cómo manejarlo).
    """
    if not settings.FIREBASE_STORAGE_BUCKET:
        raise RuntimeError("FIREBASE_STORAGE_BUCKET no está configurado")

    storage_path = f"plant_photos/{user_id}/{plant_id}.jpg"
    result = await _upload_compressed(image_bytes, storage_path)
    if result is None:
        raise RuntimeError("Error subiendo la imagen a Firebase Storage")
    return result


async def _upload_compressed(image_bytes: bytes, storage_path: str) -> str | None:
    """Comprime y sube bytes al path dado. Retorna el path o None si falla."""
    try:
        from firebase_admin import storage as fb_storage

        compressed = await asyncio.to_thread(compress_image, image_bytes)
        bucket = fb_storage.bucket()
        blob = bucket.blob(storage_path)

        await asyncio.to_thread(
            blob.upload_from_file,
            io.BytesIO(compressed),
            content_type="image/jpeg",
        )
        logger.debug("Imagen subida a Storage: %s (%d KB)", storage_path, len(compressed) // 1024)
        return storage_path

    except Exception as e:
        logger.error("Error subiendo a Firebase Storage (%s): %s", storage_path, e)
        return None
