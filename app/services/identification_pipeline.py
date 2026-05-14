"""Orquestador del pipeline de identificación de plantas.

Implementa la lógica de umbrales de confianza y coordina los servicios externos:
plant.id → GBIF → caché → RAG → OpenAI → validación → persistencia.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from app.core.config import settings
from app.schemas.identification import (
    CareProfileLlmOutput,
    CareProfileResponse,
    CareWeights,
    CompletedResponse,
    FaqItem,
    IdentifyResponse,
    NeedsMorePhotosResponse,
    NeedsUserSelectionResponse,
    PlantIdCandidate,
    SensitivityAssessment,
)
from app.services import gbif_service, plant_id_service, rag_service, species_repository
from app.services.openai_service import (
    SENSOR_REFERENCE,
    OpenAISchemaViolationError,
    generate_care_profile,
)
from app.services.plant_id_service import PlantIdAuthError, PlantIdRateLimitError, PlantIdUnavailableError

logger = logging.getLogger(__name__)


async def identify_from_image(
    image_bytes: bytes,
    *,
    latitude: float | None,
    longitude: float | None,
    output_language: str,
) -> IdentifyResponse:
    """Identifica la planta en la imagen y decide qué devolver según umbral de confianza."""
    try:
        candidates = await plant_id_service.identify(
            image_bytes,
            latitude=latitude,
            longitude=longitude,
        )
    except PlantIdAuthError as e:
        logger.critical("PLANTA ID AUTH ERROR — revisar PLANT_ID_API_KEY: %s", e)
        raise HTTPException(status_code=500, detail="Error de configuración del servicio de identificación")
    except PlantIdRateLimitError as e:
        logger.warning("Plant.id rate limit: %s", e)
        raise HTTPException(status_code=503, detail="Servicio de identificación temporalmente saturado, reintenta en unos segundos")
    except PlantIdUnavailableError as e:
        logger.warning("Plant.id no disponible: %s", e)
        raise HTTPException(status_code=502, detail="Servicio de identificación no disponible temporalmente")

    if not candidates:
        return NeedsMorePhotosResponse(top_probability=0.0)

    top = candidates[0]

    if top.probability < settings.IDENT_CONFIDENCE_LOW:
        return NeedsMorePhotosResponse(top_probability=top.probability)

    if top.probability < settings.IDENT_CONFIDENCE_HIGH:
        return NeedsUserSelectionResponse(candidates=candidates[:3])

    return await enrich_and_persist(top, output_language=output_language)


async def enrich_and_persist(
    candidate: PlantIdCandidate,
    *,
    output_language: str,
) -> CompletedResponse:
    """Ejecuta GBIF → caché → RAG → OpenAI → validación → persistencia.

    Si la especie + contenido AI en el idioma ya existen, devuelve ficha cacheada.
    """
    # Verificar caché completo
    cached = await species_repository.find_by_scientific_name(
        candidate.scientific_name, language=output_language
    )
    if cached and cached.care_profile and cached.ai_content:
        return CompletedResponse(profile=_build_response(cached, cached_hit=True, output_language=output_language))

    # GBIF
    taxonomy = None
    if candidate.gbif_id:
        try:
            taxonomy = await gbif_service.get_species_by_key(candidate.gbif_id)
        except gbif_service.GbifError as e:
            logger.warning("GBIF lookup falló para %s: %s", candidate.scientific_name, e)
    else:
        taxonomy = await gbif_service.search_species_by_name(candidate.scientific_name)

    family = (taxonomy.family if taxonomy else None) or candidate.taxonomy.get("family")

    # RAG
    rag_chunks = await rag_service.retrieve_context(candidate.scientific_name, family)

    # Construir payload canónico
    canonical = _build_canonical_payload(candidate, taxonomy, rag_chunks)

    # OpenAI
    try:
        llm_output = await generate_care_profile(canonical, output_language=output_language)
    except OpenAISchemaViolationError as e:
        logger.error("OpenAI violó el schema: %s — payload: %s", e, str(canonical)[:500])
        raise HTTPException(status_code=502, detail="No se pudo generar la ficha de cuidado, reintenta más tarde")

    # Validación de rangos y pesos
    errors = validate_care_ranges(llm_output) + validate_care_weights(llm_output)
    needs_review = bool(errors)
    if errors:
        logger.warning(
            "Ficha de %s tiene rangos inválidos (needs_review=True): %s",
            candidate.scientific_name,
            errors,
        )

    # Persistencia
    species_record = await species_repository.upsert_species(candidate, taxonomy)

    try:
        await species_repository.insert_care_profile(species_record.id, llm_output, needs_review=needs_review)
    except Exception as e:
        logger.error("Error insertando care_profile para %s: %s", species_record.id, e)
        needs_review = True

    try:
        await species_repository.insert_ai_content(species_record.id, llm_output, output_language, settings.OPENAI_MODEL)
    except Exception as e:
        logger.error("Error insertando ai_content para %s: %s", species_record.id, e)

    try:
        await species_repository.insert_common_names(species_record.id, candidate, taxonomy)
    except Exception as e:
        logger.warning("Error insertando common_names para %s: %s", species_record.id, e)

    try:
        await species_repository.insert_localized_common_name(
            species_record.id, llm_output.common_name, output_language
        )
    except Exception as e:
        logger.warning("Error insertando common_name localizado para %s: %s", species_record.id, e)

    profile = CareProfileResponse(
        species_id=species_record.id,
        scientific_name=llm_output.scientific_name,
        common_name=llm_output.common_name,
        family=llm_output.family,
        care_ranges=llm_output.care_ranges,
        care_weights=llm_output.care_weights,
        sensitivity_assessment=llm_output.sensitivity_assessment,
        care_summary=llm_output.care_summary,
        ai_personality_prompt=llm_output.ai_personality_prompt,
        care_tips=llm_output.care_tips,
        fun_facts=llm_output.fun_facts,
        faq=llm_output.faq,
        proposal_confidence=llm_output.proposal_confidence,
        needs_review=needs_review,
        language=output_language,
        cached=False,
        created_at=datetime.now(timezone.utc),
    )
    return CompletedResponse(profile=profile)


def validate_care_weights(profile: CareProfileLlmOutput) -> list[str]:
    """Valida que los pesos de cuidado sean coherentes y sumen 1.0."""
    w = profile.care_weights
    errors: list[str] = []

    values = {
        "light": w.light,
        "soil_humidity": w.soil_humidity,
        "air_humidity": w.air_humidity,
        "temperature": w.temperature,
    }
    for name, v in values.items():
        if not (0 <= v <= 1):
            errors.append(f"weight_{name} fuera de [0,1]: {v}")

    total = sum(values.values())
    if abs(total - 1.0) > 0.01:
        errors.append(f"Los pesos deben sumar 1.0 (suma actual: {total:.3f})")

    if max(values.values()) < 0.30:
        errors.append("No hay dimensión dominante en care_weights (todos los pesos < 0.30)")

    return errors


def validate_care_ranges(profile: CareProfileLlmOutput) -> list[str]:
    """Valida coherencia física de los rangos propuestos por el LLM."""
    r = profile.care_ranges
    errors: list[str] = []

    if r.min_temp_c >= r.max_temp_c:
        errors.append("min_temp_c debe ser menor que max_temp_c")
    if r.min_light_lux >= r.max_light_lux:
        errors.append("min_light_lux debe ser menor que max_light_lux")
    if r.min_air_humidity_pct >= r.max_air_humidity_pct:
        errors.append("min_air_humidity_pct debe ser menor que max_air_humidity_pct")
    if r.min_soil_humidity_pct >= r.max_soil_humidity_pct:
        errors.append("min_soil_humidity_pct debe ser menor que max_soil_humidity_pct")

    def check_range(field: str, value: float, lo: float, hi: float) -> None:
        if not (lo <= value <= hi):
            errors.append(f"{field} fuera de rango físico ({lo}–{hi}): {value}")

    check_range("min_temp_c", r.min_temp_c, -10, 60)
    check_range("max_temp_c", r.max_temp_c, -10, 60)
    check_range("min_light_lux", r.min_light_lux, 0, 100_000)
    check_range("max_light_lux", r.max_light_lux, 0, 100_000)
    check_range("min_air_humidity_pct", r.min_air_humidity_pct, 0, 100)
    check_range("max_air_humidity_pct", r.max_air_humidity_pct, 0, 100)
    check_range("min_soil_humidity_pct", r.min_soil_humidity_pct, 0, 100)
    check_range("max_soil_humidity_pct", r.max_soil_humidity_pct, 0, 100)

    return errors


def _build_canonical_payload(
    candidate: PlantIdCandidate,
    taxonomy,
    rag_chunks: list,
) -> dict:
    family = (taxonomy.family if taxonomy else None) or candidate.taxonomy.get("family")
    genus = (taxonomy.genus if taxonomy else None) or candidate.taxonomy.get("genus")

    return {
        "identification": {
            "scientific_name": candidate.scientific_name,
            "common_names": candidate.common_names,
            "confidence": candidate.probability,
            "provider": "plant.id",
            "gbif_id": candidate.gbif_id,
            "inaturalist_id": candidate.inaturalist_id,
            "watering_scale": candidate.watering.model_dump() if candidate.watering else None,
        },
        "taxonomy": {
            "family": family,
            "genus": genus,
            "order": (taxonomy.order if taxonomy else None) or candidate.taxonomy.get("order"),
            "class": (taxonomy.class_ if taxonomy else None) or candidate.taxonomy.get("class"),
            "kingdom": (taxonomy.kingdom if taxonomy else None) or candidate.taxonomy.get("kingdom"),
        },
        "rag_context": [chunk.content for chunk in rag_chunks],
        "sensor_reference": SENSOR_REFERENCE,
    }


def _build_response(full: "SpeciesFullResponse", *, cached_hit: bool, output_language: str) -> CareProfileResponse:
    from app.schemas.identification import CareRanges

    s = full.species
    cp = full.care_profile
    ai = full.ai_content

    care_ranges = CareRanges(
        min_temp_c=cp.min_temp_c or 0.0,
        max_temp_c=cp.max_temp_c or 30.0,
        min_light_lux=cp.min_light_lux or 0.0,
        max_light_lux=cp.max_light_lux or 10000.0,
        min_air_humidity_pct=cp.min_air_humidity_pct or 0.0,
        max_air_humidity_pct=cp.max_air_humidity_pct or 100.0,
        min_soil_humidity_pct=cp.min_soil_humidity_pct or 0.0,
        max_soil_humidity_pct=cp.max_soil_humidity_pct or 100.0,
    ) if cp else CareRanges(
        min_temp_c=0, max_temp_c=30, min_light_lux=0, max_light_lux=10000,
        min_air_humidity_pct=0, max_air_humidity_pct=100,
        min_soil_humidity_pct=0, max_soil_humidity_pct=100,
    )

    # Reconstruir pesos desde el record si están todos presentes (fichas legacy tendrán None)
    care_weights = None
    if cp and all(
        v is not None for v in [cp.weight_light, cp.weight_soil_humidity, cp.weight_air_humidity, cp.weight_temperature]
    ):
        try:
            care_weights = CareWeights(
                light=cp.weight_light,
                soil_humidity=cp.weight_soil_humidity,
                air_humidity=cp.weight_air_humidity,
                temperature=cp.weight_temperature,
            )
        except Exception:
            care_weights = None

    sensitivity_assessment = None
    if cp and all(
        v is not None for v in [cp.sensitivity_light, cp.sensitivity_soil_humidity, cp.sensitivity_air_humidity, cp.sensitivity_temperature]
    ):
        try:
            sensitivity_assessment = SensitivityAssessment(
                light=cp.sensitivity_light,
                soil_humidity=cp.sensitivity_soil_humidity,
                air_humidity=cp.sensitivity_air_humidity,
                temperature=cp.sensitivity_temperature,
            )
        except Exception:
            sensitivity_assessment = None

    faq_items: list[FaqItem] = []
    if ai and ai.faq:
        raw_faq = ai.faq if isinstance(ai.faq, list) else []
        for item in raw_faq:
            if isinstance(item, dict):
                faq_items.append(FaqItem(**item))

    localized_name = next(
        (cn.name for cn in full.common_names if cn.language == output_language),
        s.common_name or "",
    )

    return CareProfileResponse(
        species_id=s.id,
        scientific_name=s.scientific_name,
        common_name=localized_name,
        family=s.family,
        care_ranges=care_ranges,
        care_weights=care_weights,
        sensitivity_assessment=sensitivity_assessment,
        care_summary=ai.care_summary if ai else None,
        ai_personality_prompt=ai.ai_personality_prompt if ai else None,
        care_tips=ai.care_tips if ai and isinstance(ai.care_tips, list) else [],
        fun_facts=ai.fun_facts if ai and isinstance(ai.fun_facts, list) else [],
        faq=faq_items,
        proposal_confidence=cp.proposal_confidence if cp else None,
        needs_review=cp.needs_review if cp else True,
        language=output_language,
        cached=cached_hit,
        created_at=s.created_at,
    )
