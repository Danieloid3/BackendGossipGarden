"""Tests del orquestador identification_pipeline."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.schemas.identification import (
    CompletedResponse,
    NeedsMorePhotosResponse,
    NeedsUserSelectionResponse,
    PlantIdCandidate,
)
from app.services.identification_pipeline import (
    identify_from_image,
    validate_care_ranges,
    validate_care_weights,
)


def _make_candidate(probability: float, name="Sansevieria trifasciata") -> PlantIdCandidate:
    return PlantIdCandidate(
        scientific_name=name,
        common_names=["Lengua de suegra"],
        probability=probability,
        gbif_id=2764204,
        taxonomy={"family": "Asparagaceae"},
    )


def _make_llm_output(openai_profile: dict):
    from app.services.openai_service import _build_output
    return _build_output(openai_profile)


async def test_low_confidence_returns_needs_more_photos():
    with patch("app.services.identification_pipeline.plant_id_service.identify") as mock_identify:
        mock_identify.return_value = [_make_candidate(0.12)]

        result = await identify_from_image(b"img", latitude=None, longitude=None, output_language="es")

    assert isinstance(result, NeedsMorePhotosResponse)
    assert result.top_probability == pytest.approx(0.12)


async def test_medium_confidence_returns_user_selection():
    with patch("app.services.identification_pipeline.plant_id_service.identify") as mock_identify:
        mock_identify.return_value = [
            _make_candidate(0.55, "Monstera deliciosa"),
            _make_candidate(0.30, "Monstera adansonii"),
            _make_candidate(0.10, "Epipremnum aureum"),
        ]

        result = await identify_from_image(b"img", latitude=None, longitude=None, output_language="es")

    assert isinstance(result, NeedsUserSelectionResponse)
    assert len(result.candidates) == 3
    assert result.candidates[0].scientific_name == "Monstera deliciosa"


async def test_high_confidence_runs_full_pipeline(openai_profile):
    fake_species_id = uuid4()

    with (
        patch("app.services.identification_pipeline.plant_id_service.identify") as mock_identify,
        patch("app.services.identification_pipeline.species_repository.find_by_scientific_name") as mock_find,
        patch("app.services.identification_pipeline.gbif_service.get_species_by_key") as mock_gbif,
        patch("app.services.identification_pipeline.rag_service.retrieve_context") as mock_rag,
        patch("app.services.identification_pipeline.generate_care_profile") as mock_openai,
        patch("app.services.identification_pipeline.species_repository.upsert_species") as mock_upsert,
        patch("app.services.identification_pipeline.species_repository.insert_care_profile") as mock_cp,
        patch("app.services.identification_pipeline.species_repository.insert_ai_content") as mock_ai,
        patch("app.services.identification_pipeline.species_repository.insert_common_names") as mock_cn,
    ):
        mock_identify.return_value = [_make_candidate(0.92)]
        mock_find.return_value = None  # No cacheado
        mock_gbif.return_value = MagicMock(family="Asparagaceae", genus="Dracaena", key=2764204, class_=None, order=None, phylum=None, kingdom=None, canonical_name=None, vernacular_names=[])
        mock_rag.return_value = []
        mock_openai.return_value = _make_llm_output(openai_profile)
        mock_upsert.return_value = MagicMock(id=fake_species_id, scientific_name="Sansevieria trifasciata", created_at=datetime.now(timezone.utc))
        mock_cp.return_value = None
        mock_ai.return_value = None
        mock_cn.return_value = None

        result = await identify_from_image(b"img", latitude=None, longitude=None, output_language="es")

    assert isinstance(result, CompletedResponse)
    assert result.profile.scientific_name == "Sansevieria trifasciata"
    assert result.profile.cached is False
    mock_openai.assert_called_once()

    # Verificar que insert_care_profile recibió los pesos
    call_kwargs = mock_cp.call_args
    passed_profile = call_kwargs.args[1] if call_kwargs.args else call_kwargs.kwargs.get("profile")
    assert passed_profile.care_weights.light == pytest.approx(0.40)
    assert passed_profile.sensitivity_assessment.light == "high"

    # Verificar que la respuesta expone los pesos
    assert result.profile.care_weights is not None
    assert result.profile.sensitivity_assessment is not None
    total = sum([
        result.profile.care_weights.light,
        result.profile.care_weights.soil_humidity,
        result.profile.care_weights.air_humidity,
        result.profile.care_weights.temperature,
    ])
    assert total == pytest.approx(1.0, abs=0.01)


async def test_cached_species_skips_external_calls(openai_profile):
    from app.schemas.species import (
        SpeciesAiContentRecord,
        SpeciesCareProfileRecord,
        SpeciesCommonNameRecord,
        SpeciesFullResponse,
        SpeciesRecord,
    )

    fake_id = uuid4()
    now = datetime.now(timezone.utc)

    fake_full = SpeciesFullResponse(
        species=SpeciesRecord(
            id=fake_id,
            scientific_name="Sansevieria trifasciata",
            common_name="Lengua de suegra",
            source_provider="plant.id",
            created_at=now,
            updated_at=now,
        ),
        care_profile=SpeciesCareProfileRecord(
            id=uuid4(), species_id=fake_id,
            min_temp_c=15, max_temp_c=27,
            min_light_lux=500, max_light_lux=10000,
            min_air_humidity_pct=30, max_air_humidity_pct=60,
            min_soil_humidity_pct=20, max_soil_humidity_pct=50,
            needs_review=False, completed_at=now,
        ),
        ai_content=SpeciesAiContentRecord(
            id=uuid4(), species_id=fake_id,
            ai_personality_prompt="Hola soy una Sansevieria",
            care_summary="Muy resistente",
            care_tips=["regar poco"], fun_facts=["dato curioso"],
            faq=[{"question": "¿q?", "answer": "a"}],
            language="es", generated_at=now,
        ),
        common_names=[],
    )

    with (
        patch("app.services.identification_pipeline.species_repository.find_by_scientific_name") as mock_find,
        patch("app.services.identification_pipeline.gbif_service.get_species_by_key") as mock_gbif,
        patch("app.services.identification_pipeline.generate_care_profile") as mock_openai,
    ):
        mock_find.return_value = fake_full

        from app.services.identification_pipeline import enrich_and_persist
        result = await enrich_and_persist(_make_candidate(0.92), output_language="es")

    assert result.profile.cached is True
    mock_gbif.assert_not_called()
    mock_openai.assert_not_called()


async def test_validation_failure_marks_needs_review(openai_profile):
    bad_profile = dict(openai_profile)
    bad_profile["care_ranges"] = {
        "min_temp_c": 30.0, "max_temp_c": 15.0,  # min > max: inválido
        "min_light_lux": 500.0, "max_light_lux": 10000.0,
        "min_air_humidity_pct": 30.0, "max_air_humidity_pct": 60.0,
        "min_soil_humidity_pct": 20.0, "max_soil_humidity_pct": 50.0,
    }

    from app.services.openai_service import _build_output
    profile = _build_output(bad_profile)
    errors = validate_care_ranges(profile)

    assert len(errors) > 0
    assert any("min_temp_c" in e for e in errors)


async def test_validate_care_weights_valid(openai_profile):
    from app.services.openai_service import _build_output
    profile = _build_output(openai_profile)
    errors = validate_care_weights(profile)
    assert errors == []


async def test_validate_care_weights_sum_not_one(openai_profile):
    from app.services.openai_service import _build_output
    bad = dict(openai_profile)
    bad["care_weights"] = {"light": 0.30, "soil_humidity": 0.30, "air_humidity": 0.10, "temperature": 0.10}  # suma 0.80
    # Pydantic CareWeights tiene tolerancia de 0.05; 0.80 queda fuera
    with pytest.raises(Exception):
        _build_output(bad)


async def test_validate_care_weights_no_dominant_dimension(openai_profile):
    from app.services.openai_service import _build_output
    bad = dict(openai_profile)
    bad["care_weights"] = {"light": 0.25, "soil_humidity": 0.25, "air_humidity": 0.25, "temperature": 0.25}
    profile = _build_output(bad)
    errors = validate_care_weights(profile)
    assert any("dominante" in e for e in errors)


async def test_validate_care_weights_out_of_bounds():
    from app.schemas.identification import CareWeights
    with pytest.raises(Exception):
        CareWeights(light=1.5, soil_humidity=0.0, air_humidity=0.0, temperature=0.0)


async def test_invalid_weights_mark_needs_review(openai_profile):
    """Pesos sin dimensión dominante → needs_review=True en el perfil final."""
    fake_species_id = uuid4()
    bad_profile = dict(openai_profile)
    bad_profile["care_weights"] = {"light": 0.25, "soil_humidity": 0.25, "air_humidity": 0.25, "temperature": 0.25}

    with (
        patch("app.services.identification_pipeline.plant_id_service.identify") as mock_identify,
        patch("app.services.identification_pipeline.species_repository.find_by_scientific_name") as mock_find,
        patch("app.services.identification_pipeline.gbif_service.get_species_by_key") as mock_gbif,
        patch("app.services.identification_pipeline.rag_service.retrieve_context") as mock_rag,
        patch("app.services.identification_pipeline.generate_care_profile") as mock_openai,
        patch("app.services.identification_pipeline.species_repository.upsert_species") as mock_upsert,
        patch("app.services.identification_pipeline.species_repository.insert_care_profile") as mock_cp,
        patch("app.services.identification_pipeline.species_repository.insert_ai_content"),
        patch("app.services.identification_pipeline.species_repository.insert_common_names"),
    ):
        mock_identify.return_value = [_make_candidate(0.92)]
        mock_find.return_value = None
        mock_gbif.return_value = MagicMock(family="Asparagaceae", genus="Dracaena", key=2764204, class_=None, order=None, phylum=None, kingdom=None, canonical_name=None, vernacular_names=[])
        mock_rag.return_value = []
        mock_openai.return_value = _make_llm_output(bad_profile)
        mock_upsert.return_value = MagicMock(id=fake_species_id, scientific_name="Sansevieria trifasciata", created_at=datetime.now(timezone.utc))
        mock_cp.return_value = None

        result = await identify_from_image(b"img", latitude=None, longitude=None, output_language="es")

    assert result.profile.needs_review is True
