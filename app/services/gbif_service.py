"""Wrapper async de GBIF Species API (pública, sin autenticación).

Resuelve taxonomía estructurada a partir de gbif_id o scientific_name.
Degrada graciosamente: si falla, el pipeline continúa con la taxonomía de plant.id.
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import settings
from app.schemas.identification import GbifTaxonomy

logger = logging.getLogger(__name__)


class GbifError(Exception):
    pass


class GbifNotFoundError(GbifError):
    pass


async def get_species_by_key(
    gbif_key: int,
    *,
    client: httpx.AsyncClient | None = None,
) -> GbifTaxonomy:
    """GET /species/{key} → normaliza taxonomía completa."""
    url = f"{settings.GBIF_BASE_URL}/species/{gbif_key}"
    data = await _get(url, client=client)
    return _parse_taxonomy(data)


async def search_species_by_name(
    scientific_name: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> GbifTaxonomy | None:
    """GET /species?name=... → primer match exacto o None si no hay resultado."""
    url = f"{settings.GBIF_BASE_URL}/species"
    try:
        own_client = client is None
        if own_client:
            client = httpx.AsyncClient(timeout=settings.GBIF_TIMEOUT_SECONDS)
        try:
            response = await client.get(url, params={"name": scientific_name})
        finally:
            if own_client:
                await client.aclose()
    except httpx.HTTPError as e:
        logger.warning("GBIF búsqueda por nombre falló: %s", e)
        return None

    if not response.is_success:
        return None

    results = response.json().get("results", [])
    if not results:
        return None
    return _parse_taxonomy(results[0])


async def _get(url: str, *, client: httpx.AsyncClient | None) -> dict:
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=settings.GBIF_TIMEOUT_SECONDS)
    try:
        response = await client.get(url)
    except httpx.TimeoutException as e:
        raise GbifError("Timeout con GBIF") from e
    except httpx.NetworkError as e:
        raise GbifError(f"Error de red con GBIF: {e}") from e
    finally:
        if own_client:
            await client.aclose()

    if response.status_code == 404:
        raise GbifNotFoundError(f"GBIF no encontró: {url}")
    if not response.is_success:
        raise GbifError(f"GBIF respondió {response.status_code}")

    return response.json()


def _parse_taxonomy(data: dict) -> GbifTaxonomy:
    vernacular: list[dict] = []
    raw_names = data.get("vernacularNames", [])
    for vn in raw_names[:20]:
        if isinstance(vn, dict) and vn.get("vernacularName") and vn.get("language"):
            vernacular.append({"name": vn["vernacularName"], "language": vn["language"]})

    return GbifTaxonomy(
        key=data.get("key", 0),
        scientific_name=data.get("scientificName", ""),
        canonical_name=data.get("canonicalName"),
        family=data.get("family"),
        genus=data.get("genus"),
        order=data.get("order"),
        **{"class": data.get("class")},
        phylum=data.get("phylum"),
        kingdom=data.get("kingdom"),
        vernacular_names=vernacular,
    )
