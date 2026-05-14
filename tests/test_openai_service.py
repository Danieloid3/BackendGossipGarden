"""Tests del servicio openai_service."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.openai_service import OpenAISchemaViolationError, generate_care_profile


def _make_choice(content: str, refusal=None, finish_reason="stop"):
    choice = MagicMock()
    choice.finish_reason = finish_reason
    choice.message.content = content
    choice.message.refusal = refusal
    return choice


def _make_completion(content: str, **kwargs):
    completion = MagicMock()
    completion.choices = [_make_choice(content, **kwargs)]
    return completion


CANONICAL_PAYLOAD = {
    "identification": {
        "scientific_name": "Sansevieria trifasciata",
        "common_names": ["Lengua de suegra"],
        "confidence": 0.92,
        "provider": "plant.id",
        "gbif_id": 2764204,
        "inaturalist_id": 53522,
        "watering_scale": {"min": 1, "max": 2},
    },
    "taxonomy": {"family": "Asparagaceae", "genus": "Dracaena"},
    "rag_context": [],
    "sensor_reference": {},
}


async def test_generate_care_profile_returns_parsed_output(openai_profile):
    with patch("app.services.openai_service._get_client") as mock_client_factory:
        mock_client = AsyncMock()
        mock_client_factory.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_completion(json.dumps(openai_profile))
        )

        result = await generate_care_profile(CANONICAL_PAYLOAD)

        assert result.scientific_name == "Sansevieria trifasciata"
        assert result.proposal_confidence == "high"
        assert len(result.care_tips) >= 3
        assert result.care_ranges.min_temp_c < result.care_ranges.max_temp_c
        # Verificar pesos
        assert result.care_weights is not None
        total = (
            result.care_weights.light
            + result.care_weights.soil_humidity
            + result.care_weights.air_humidity
            + result.care_weights.temperature
        )
        assert total == pytest.approx(1.0, abs=0.05)
        # Verificar sensitivity
        assert result.sensitivity_assessment is not None
        assert result.sensitivity_assessment.light in ("high", "medium", "low")


async def test_generate_care_profile_refusal_retries_once_then_raises():
    with patch("app.services.openai_service._get_client") as mock_client_factory:
        mock_client = AsyncMock()
        mock_client_factory.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_completion("", refusal="I cannot generate this content")
        )

        with pytest.raises(OpenAISchemaViolationError):
            await generate_care_profile(CANONICAL_PAYLOAD)

        # Debe haber intentado 2 veces (intento 1 + retry con temp=0)
        assert mock_client.chat.completions.create.call_count == 2


async def test_embed_texts_returns_list_of_embeddings():
    fake_embedding = [0.1] * 1536

    with patch("app.services.openai_service._get_client") as mock_client_factory:
        mock_client = AsyncMock()
        mock_client_factory.return_value = mock_client
        mock_item = MagicMock()
        mock_item.embedding = fake_embedding
        mock_client.embeddings.create = AsyncMock(
            return_value=MagicMock(data=[mock_item, mock_item])
        )

        from app.services.openai_service import embed_texts
        result = await embed_texts(["texto 1", "texto 2"])

        assert len(result) == 2
        assert len(result[0]) == 1536
