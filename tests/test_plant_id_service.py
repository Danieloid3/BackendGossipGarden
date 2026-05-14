"""Tests del servicio plant_id_service."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from app.services.plant_id_service import (
    PlantIdAuthError,
    PlantIdRateLimitError,
    PlantIdUnavailableError,
    identify,
)


@pytest.fixture
def plant_id_high_bytes(plant_id_high):
    return json.dumps(plant_id_high).encode()


@respx.mock
async def test_identify_high_confidence_returns_candidates(plant_id_high):
    respx.post("https://plant.id/api/v3/identification").mock(
        return_value=httpx.Response(200, json=plant_id_high)
    )

    candidates = await identify(b"fake_image_bytes")

    assert len(candidates) == 1
    top = candidates[0]
    assert top.scientific_name == "Sansevieria trifasciata"
    assert top.probability == pytest.approx(0.92)
    assert top.gbif_id == 2764204
    assert "Lengua de suegra" in top.common_names
    assert top.taxonomy["family"] == "Asparagaceae"


@respx.mock
async def test_identify_401_raises_auth_error():
    respx.post("https://plant.id/api/v3/identification").mock(
        return_value=httpx.Response(401)
    )

    with pytest.raises(PlantIdAuthError):
        await identify(b"fake_image_bytes")


@respx.mock
async def test_identify_429_raises_rate_limit_after_retries():
    respx.post("https://plant.id/api/v3/identification").mock(
        return_value=httpx.Response(429)
    )

    with pytest.raises(PlantIdRateLimitError):
        await identify(b"fake_image_bytes")


@respx.mock
async def test_identify_500_raises_unavailable():
    respx.post("https://plant.id/api/v3/identification").mock(
        return_value=httpx.Response(503)
    )

    with pytest.raises(PlantIdUnavailableError):
        await identify(b"fake_image_bytes")


@respx.mock
async def test_identify_medium_confidence_returns_multiple_candidates(plant_id_medium):
    respx.post("https://plant.id/api/v3/identification").mock(
        return_value=httpx.Response(200, json=plant_id_medium)
    )

    candidates = await identify(b"fake_image_bytes")

    assert len(candidates) == 3
    assert candidates[0].probability > candidates[1].probability
    assert candidates[0].scientific_name == "Monstera deliciosa"
