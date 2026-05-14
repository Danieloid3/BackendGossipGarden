"""Wrapper async de Plant.id (Kindwise) API v3.

Identifica plantas a partir de bytes de imagen. Reintenta ante 429/5xx/timeout
con backoff exponencial via tenacity. Normaliza la respuesta al schema interno.
"""

from __future__ import annotations

import base64
import logging

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.schemas.identification import PlantIdCandidate, WateringScale

logger = logging.getLogger(__name__)


class PlantIdError(Exception):
    pass


class PlantIdAuthError(PlantIdError):
    pass


class PlantIdRateLimitError(PlantIdError):
    pass


class PlantIdUnavailableError(PlantIdError):
    pass


def _should_retry(exc: BaseException) -> bool:
    if isinstance(exc, PlantIdRateLimitError | PlantIdUnavailableError):
        return True
    if isinstance(exc, httpx.TimeoutException | httpx.NetworkError):
        return True
    return False


@retry(
    retry=retry_if_exception_type((PlantIdRateLimitError, PlantIdUnavailableError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def identify(
    image_bytes: bytes,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[PlantIdCandidate]:
    """POST multipart a /identification. Devuelve candidatos ordenados por probability desc."""
    image_b64 = base64.b64encode(image_bytes).decode()

    payload: dict = {
        "images": [image_b64],
        "similar_images": True,
        "classification_level": "species",
    }
    if latitude is not None and longitude is not None:
        payload["latitude"] = latitude
        payload["longitude"] = longitude

    headers = {
        "Api-Key": settings.PLANT_ID_API_KEY,
        "Content-Type": "application/json",
    }

    params = {"details": settings.PLANT_ID_DETAILS}

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=settings.PLANT_ID_TIMEOUT_SECONDS)

    try:
        response = await client.post(
            f"{settings.PLANT_ID_BASE_URL}/identification",
            json=payload,
            headers=headers,
            params=params,
        )
    except httpx.TimeoutException as e:
        raise PlantIdUnavailableError("Timeout conectando a Plant.id") from e
    except httpx.NetworkError as e:
        raise PlantIdUnavailableError(f"Error de red con Plant.id: {e}") from e
    finally:
        if own_client:
            await client.aclose()

    if response.status_code == 401:
        raise PlantIdAuthError("Plant.id API key inválida (401)")
    if response.status_code == 429:
        raise PlantIdRateLimitError("Plant.id rate limit alcanzado (429)")
    if response.status_code >= 500:
        raise PlantIdUnavailableError(f"Plant.id respondió {response.status_code}")
    if not response.is_success:
        raise PlantIdError(f"Plant.id error inesperado {response.status_code}: {response.text[:200]}")

    data = response.json()
    return _parse_candidates(data)


def _parse_candidates(data: dict) -> list[PlantIdCandidate]:
    result = data.get("result", {})
    classification = result.get("classification", {})
    suggestions = classification.get("suggestions", [])

    candidates: list[PlantIdCandidate] = []
    for s in suggestions:
        details = s.get("details", {})
        taxonomy = details.get("taxonomy", {})
        watering_raw = details.get("watering", {})
        watering = (
            WateringScale(min=watering_raw.get("min"), max=watering_raw.get("max"))
            if watering_raw
            else None
        )

        images = s.get("similar_images", [])
        image_url = images[0].get("url") if images else None

        candidates.append(
            PlantIdCandidate(
                scientific_name=s.get("name", ""),
                common_names=details.get("common_names") or [],
                probability=s.get("probability", 0.0),
                gbif_id=details.get("gbif_id"),
                inaturalist_id=details.get("inaturalist_id"),
                taxonomy={
                    "family": taxonomy.get("family"),
                    "genus": taxonomy.get("genus"),
                    "order": taxonomy.get("order"),
                    "class": taxonomy.get("class"),
                    "kingdom": taxonomy.get("kingdom"),
                },
                watering=watering,
                description=details.get("description", {}).get("value") if isinstance(details.get("description"), dict) else details.get("description"),
                image_url=image_url,
            )
        )

    candidates.sort(key=lambda c: c.probability, reverse=True)
    return candidates
