"""Tests del servicio gbif_service."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.services.gbif_service import GbifNotFoundError, get_species_by_key, search_species_by_name


@respx.mock
async def test_get_species_by_key_returns_taxonomy(gbif_response):
    respx.get("https://api.gbif.org/v1/species/2764204").mock(
        return_value=httpx.Response(200, json=gbif_response)
    )

    taxonomy = await get_species_by_key(2764204)

    assert taxonomy.family == "Asparagaceae"
    assert taxonomy.genus == "Dracaena"
    assert taxonomy.key == 2764204
    assert taxonomy.canonical_name == "Sansevieria trifasciata"
    assert any(v["name"] == "Snake plant" for v in taxonomy.vernacular_names)


@respx.mock
async def test_get_species_by_key_404_raises_not_found():
    respx.get("https://api.gbif.org/v1/species/99999999").mock(
        return_value=httpx.Response(404)
    )

    with pytest.raises(GbifNotFoundError):
        await get_species_by_key(99999999)


@respx.mock
async def test_search_by_name_no_match_returns_none():
    respx.get("https://api.gbif.org/v1/species").mock(
        return_value=httpx.Response(200, json={"results": []})
    )

    result = await search_species_by_name("Imaginary plantus nonexistentus")

    assert result is None


@respx.mock
async def test_search_by_name_returns_first_match(gbif_response):
    respx.get("https://api.gbif.org/v1/species").mock(
        return_value=httpx.Response(200, json={"results": [gbif_response]})
    )

    taxonomy = await search_species_by_name("Sansevieria trifasciata")

    assert taxonomy is not None
    assert taxonomy.family == "Asparagaceae"
