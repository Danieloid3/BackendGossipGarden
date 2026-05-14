"""Tests HTTP del endpoint /identify y /species/from-candidate."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.schemas.identification import (
    CareProfileResponse,
    CareRanges,
    CompletedResponse,
    FaqItem,
    NeedsMorePhotosResponse,
    NeedsUserSelectionResponse,
    PlantIdCandidate,
)

FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # minimal JPEG-like header

FAKE_PROFILE = CareProfileResponse(
    species_id=uuid4(),
    scientific_name="Sansevieria trifasciata",
    common_name="Lengua de suegra",
    family="Asparagaceae",
    care_ranges=CareRanges(
        min_temp_c=15, max_temp_c=27,
        min_light_lux=500, max_light_lux=10000,
        min_air_humidity_pct=30, max_air_humidity_pct=60,
        min_soil_humidity_pct=20, max_soil_humidity_pct=50,
    ),
    care_summary="Planta muy resistente.",
    ai_personality_prompt="Hola soy una Sansevieria",
    care_tips=["regar poco"], fun_facts=["dato"], faq=[FaqItem(question="q", answer="a")],
    proposal_confidence="high", needs_review=False,
    language="es", cached=False, created_at=datetime.now(timezone.utc),
)

FAKE_COMPLETED = CompletedResponse(profile=FAKE_PROFILE)
FAKE_NEEDS_MORE = NeedsMorePhotosResponse(top_probability=0.12)
FAKE_NEEDS_SELECTION = NeedsUserSelectionResponse(
    candidates=[PlantIdCandidate(scientific_name="Monstera deliciosa", probability=0.55)]
)


async def test_post_identify_requires_auth(client):
    from app.core.security import get_current_user
    from app.main import app

    app.dependency_overrides.pop(get_current_user, None)
    try:
        response = await client.post(
            "/api/v1/identify",
            files={"image": ("test.jpg", FAKE_JPEG, "image/jpeg")},
        )
        assert response.status_code == 401
    finally:
        from app.core.security import get_current_user as gcu
        from tests.conftest import FAKE_USER_ID
        app.dependency_overrides[gcu] = lambda: FAKE_USER_ID


async def test_post_identify_high_confidence_returns_completed(client):
    with patch("app.api.v1.endpoints.identification.pipeline.identify_from_image") as mock_pipeline:
        mock_pipeline.return_value = FAKE_COMPLETED

        response = await client.post(
            "/api/v1/identify",
            files={"image": ("plant.jpg", FAKE_JPEG, "image/jpeg")},
            data={"output_language": "es"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["profile"]["scientific_name"] == "Sansevieria trifasciata"


async def test_post_identify_low_confidence_returns_needs_more(client):
    with patch("app.api.v1.endpoints.identification.pipeline.identify_from_image") as mock_pipeline:
        mock_pipeline.return_value = FAKE_NEEDS_MORE

        response = await client.post(
            "/api/v1/identify",
            files={"image": ("blurry.jpg", FAKE_JPEG, "image/jpeg")},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "needs_more_photos"


async def test_post_identify_medium_confidence_returns_selection(client):
    with patch("app.api.v1.endpoints.identification.pipeline.identify_from_image") as mock_pipeline:
        mock_pipeline.return_value = FAKE_NEEDS_SELECTION

        response = await client.post(
            "/api/v1/identify",
            files={"image": ("plant.jpg", FAKE_JPEG, "image/jpeg")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "needs_user_selection"
    assert len(data["candidates"]) == 1


async def test_post_identify_rejects_oversize_image(client):
    big_image = b"\xff\xd8\xff\xe0" + b"\x00" * (9 * 1024 * 1024)

    response = await client.post(
        "/api/v1/identify",
        files={"image": ("big.jpg", big_image, "image/jpeg")},
    )

    assert response.status_code == 413


async def test_post_identify_rejects_bad_content_type(client):
    response = await client.post(
        "/api/v1/identify",
        files={"image": ("doc.pdf", b"%PDF", "application/pdf")},
    )

    assert response.status_code == 415


async def test_post_identify_rejects_unsupported_language(client):
    response = await client.post(
        "/api/v1/identify",
        files={"image": ("plant.jpg", FAKE_JPEG, "image/jpeg")},
        data={"output_language": "zh"},
    )

    assert response.status_code == 422


async def test_post_from_candidate_returns_completed(client):
    candidate_data = {
        "candidate": {
            "scientific_name": "Sansevieria trifasciata",
            "common_names": ["Lengua de suegra"],
            "probability": 0.92,
            "gbif_id": 2764204,
        },
        "output_language": "es",
    }

    with patch("app.api.v1.endpoints.identification.pipeline.enrich_and_persist") as mock_pipeline:
        mock_pipeline.return_value = FAKE_COMPLETED

        response = await client.post("/api/v1/species/from-candidate", json=candidate_data)

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
