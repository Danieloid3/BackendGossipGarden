"""Tests unitarios de los modelos Pydantic — sin ninguna dependencia de BD."""

from __future__ import annotations

from uuid import uuid4, UUID

import pytest
from pydantic import ValidationError


# ─── CareWeights ──────────────────────────────────────────────────────────────

from app.schemas.identification import (
    CareWeights,
    SensitivityAssessment,
    NeedsMorePhotosResponse,
    NeedsUserSelectionResponse,
    CompletedResponse,
    CareProfileResponse,
    CareRanges,
    PlantIdCandidate,
    WateringScale,
    FromCandidateRequest,
)


def test_care_weights_valid_sum():
    w = CareWeights(light=0.4, soil_humidity=0.3, air_humidity=0.2, temperature=0.1)
    assert abs((w.light + w.soil_humidity + w.air_humidity + w.temperature) - 1.0) <= 0.05


def test_care_weights_exact_sum_one():
    CareWeights(light=0.25, soil_humidity=0.25, air_humidity=0.25, temperature=0.25)


def test_care_weights_sum_within_tolerance():
    # 0.99 está dentro del margen ±0.05
    CareWeights(light=0.33, soil_humidity=0.33, air_humidity=0.33, temperature=0.00)


def test_care_weights_sum_exceeds_tolerance():
    with pytest.raises(ValidationError, match="pesos deben sumar 1.0"):
        CareWeights(light=0.5, soil_humidity=0.5, air_humidity=0.5, temperature=0.5)


def test_care_weights_sum_below_tolerance():
    with pytest.raises(ValidationError, match="pesos deben sumar 1.0"):
        CareWeights(light=0.1, soil_humidity=0.1, air_humidity=0.1, temperature=0.1)


def test_care_weights_negative_value_rejected():
    with pytest.raises(ValidationError):
        CareWeights(light=-0.1, soil_humidity=0.4, air_humidity=0.4, temperature=0.3)


def test_care_weights_value_above_one_rejected():
    with pytest.raises(ValidationError):
        CareWeights(light=1.1, soil_humidity=0.0, air_humidity=0.0, temperature=0.0)


# ─── SensitivityAssessment ────────────────────────────────────────────────────

def test_sensitivity_valid_literals():
    s = SensitivityAssessment(
        light="high", soil_humidity="medium", air_humidity="low", temperature="high"
    )
    assert s.light == "high"


def test_sensitivity_invalid_literal():
    with pytest.raises(ValidationError):
        SensitivityAssessment(
            light="very_high", soil_humidity="medium", air_humidity="low", temperature="high"
        )


# ─── IdentifyResponse discriminated union ─────────────────────────────────────

def _make_care_profile() -> CareProfileResponse:
    return CareProfileResponse(
        species_id=uuid4(),
        scientific_name="Rosa canina",
        common_name="Escaramujo",
        family="Rosaceae",
        care_ranges=CareRanges(
            min_temp_c=5.0, max_temp_c=30.0,
            min_light_lux=5000.0, max_light_lux=80000.0,
            min_air_humidity_pct=40.0, max_air_humidity_pct=70.0,
            min_soil_humidity_pct=30.0, max_soil_humidity_pct=60.0,
        ),
        care_summary="Resistente y fácil.",
        ai_personality_prompt="Soy una rosa silvestre.",
        care_tips=["Regar moderadamente"],
        fun_facts=["Es la madre de las rosas modernas"],
        faq=[],
        proposal_confidence="high",
        needs_review=False,
        language="es",
        cached=False,
        created_at=__import__("datetime").datetime.now(),
    )


def test_needs_more_photos_status():
    r = NeedsMorePhotosResponse(top_probability=0.1)
    assert r.status == "needs_more_photos"
    assert r.top_probability == 0.1


def test_needs_user_selection_status():
    candidate = PlantIdCandidate(scientific_name="Rosa canina", probability=0.5)
    r = NeedsUserSelectionResponse(candidates=[candidate])
    assert r.status == "needs_user_selection"
    assert len(r.candidates) == 1


def test_completed_response_status():
    r = CompletedResponse(profile=_make_care_profile())
    assert r.status == "completed"
    assert r.photo_storage_path is None


def test_completed_response_with_photo_path():
    r = CompletedResponse(
        profile=_make_care_profile(),
        photo_storage_path="plant_identifications/user1/photo.jpg",
    )
    assert r.photo_storage_path == "plant_identifications/user1/photo.jpg"


# ─── PlantIdCandidate ─────────────────────────────────────────────────────────

def test_plant_id_candidate_minimal():
    c = PlantIdCandidate(scientific_name="Ficus lyrata", probability=0.9)
    assert c.common_names == []
    assert c.reference_images == []
    assert c.gbif_id is None


def test_plant_id_candidate_full():
    c = PlantIdCandidate(
        scientific_name="Monstera deliciosa",
        probability=0.95,
        common_names=["Costilla de Adán"],
        gbif_id=12345,
        reference_images=["https://example.com/img.jpg"],
    )
    assert c.gbif_id == 12345


# ─── FromCandidateRequest ─────────────────────────────────────────────────────

def test_from_candidate_request_default_language():
    req = FromCandidateRequest(
        candidate=PlantIdCandidate(scientific_name="Test", probability=0.8)
    )
    assert req.output_language == "es"


def test_from_candidate_request_valid_languages():
    for lang in ("es", "en", "fr", "pt", "de", "it"):
        req = FromCandidateRequest(
            candidate=PlantIdCandidate(scientific_name="Test", probability=0.8),
            output_language=lang,
        )
        assert req.output_language == lang


def test_from_candidate_request_invalid_language():
    with pytest.raises(ValidationError):
        FromCandidateRequest(
            candidate=PlantIdCandidate(scientific_name="Test", probability=0.8),
            output_language="zh",
        )


# ─── SpeciesAiContentRecord — parse_jsonb ─────────────────────────────────────

from app.schemas.species import SpeciesAiContentRecord


def _make_ai_content(**kwargs):
    base = {
        "id": uuid4(),
        "species_id": uuid4(),
        "language": "es",
        "generated_at": __import__("datetime").datetime.now(),
    }
    base.update(kwargs)
    return SpeciesAiContentRecord(**base)


def test_ai_content_parse_jsonb_from_list():
    r = _make_ai_content(care_tips=["tip1", "tip2"], fun_facts=["fact1"], faq=[])
    assert r.care_tips == ["tip1", "tip2"]


def test_ai_content_parse_jsonb_from_json_string():
    r = _make_ai_content(care_tips='["tip1","tip2"]', fun_facts="[]", faq="[]")
    assert r.care_tips == ["tip1", "tip2"]
    assert r.fun_facts == []


def test_ai_content_parse_jsonb_none_becomes_empty():
    r = _make_ai_content(care_tips=None, fun_facts=None, faq=None)
    assert r.care_tips == []
    assert r.fun_facts == []
    assert r.faq == []


# ─── PlantResponse / SensorDataCreate ────────────────────────────────────────

from app.schemas.plants import PlantCreate, PlantResponse
from app.schemas.sensors import SensorDataCreate


def test_plant_create_valid():
    p = PlantCreate(species_id=uuid4(), nickname="Mi Monstera")
    assert p.photo_storage_path is None


def test_plant_create_missing_nickname():
    with pytest.raises(ValidationError):
        PlantCreate(species_id=uuid4())


def test_sensor_data_create_valid():
    s = SensorDataCreate(
        plant_id=uuid4(),
        temperature_c=22.5,
        humidity_pct=60.0,
        soil_moisture_pct=45.0,
        light_lux=5000.0,
    )
    assert s.sensor_id is None


def test_sensor_data_create_missing_required():
    with pytest.raises(ValidationError):
        SensorDataCreate(plant_id=uuid4(), temperature_c=22.5)
