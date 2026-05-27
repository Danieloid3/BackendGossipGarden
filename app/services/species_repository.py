"""Persistencia transaccional-lógica de especies y contenido AI en Supabase.

supabase-py es síncrono; todas las operaciones se envuelven con asyncio.to_thread.
La idempotencia se garantiza con ON CONFLICT + UNIQUE constraints en la BD.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from app.db.supabase import supabase
from app.schemas.identification import (
    CareProfileLlmOutput,
    GbifTaxonomy,
    PlantIdCandidate,
)
from app.schemas.species import (
    SpeciesAiContentRecord,
    SpeciesCareProfileRecord,
    SpeciesCommonNameRecord,
    SpeciesFullResponse,
    SpeciesRecord,
)

logger = logging.getLogger(__name__)


async def find_by_scientific_name(
    scientific_name: str,
    *,
    language: str = "es",
) -> SpeciesFullResponse | None:
    """Lookup completo: species + care_profile + ai_content (por idioma) + common_names."""

    def _fetch_species() -> dict | None:
        res = supabase.table("species").select("*").eq("scientific_name", scientific_name).execute()
        return res.data[0] if res.data else None

    species_row = await asyncio.to_thread(_fetch_species)
    if not species_row:
        return None

    species_id = species_row["id"]

    def _fetch_care_profile() -> dict | None:
        res = (
            supabase.table("species_care_profiles")
            .select("*")
            .eq("species_id", species_id)
            .order("completed_at", desc=True)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    def _fetch_ai_content() -> dict | None:
        res = (
            supabase.table("species_ai_content")
            .select("*")
            .eq("species_id", species_id)
            .eq("language", language)
            .execute()
        )
        return res.data[0] if res.data else None

    def _fetch_common_names() -> list[dict]:
        res = (
            supabase.table("species_common_names")
            .select("*")
            .eq("species_id", species_id)
            .execute()
        )
        return res.data or []

    care_row, ai_row, names_rows = await asyncio.gather(
        asyncio.to_thread(_fetch_care_profile),
        asyncio.to_thread(_fetch_ai_content),
        asyncio.to_thread(_fetch_common_names),
    )

    return SpeciesFullResponse(
        species=SpeciesRecord(**species_row),
        care_profile=SpeciesCareProfileRecord(**care_row) if care_row else None,
        ai_content=SpeciesAiContentRecord(**ai_row) if ai_row else None,
        common_names=[SpeciesCommonNameRecord(**r) for r in names_rows],
    )


async def upsert_species(
    candidate: PlantIdCandidate,
    taxonomy: GbifTaxonomy | None,
) -> SpeciesRecord:
    """INSERT ON CONFLICT (scientific_name) DO NOTHING + SELECT de fallback.

    Preserva el id existente si la especie ya está en BD.
    """
    family = taxonomy.family if taxonomy else candidate.taxonomy.get("family")
    genus = taxonomy.genus if taxonomy else candidate.taxonomy.get("genus")

    data = {
        "scientific_name": candidate.scientific_name,
        "common_name": candidate.common_names[0] if candidate.common_names else None,
        "family": family,
        "genus": genus,
        "gbif_taxon_key": taxonomy.key if taxonomy else None,
        "inaturalist_id": candidate.inaturalist_id,
        "source_provider": "plant.id",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    def _upsert() -> dict:
        res = (
            supabase.table("species")
            .upsert(data, on_conflict="scientific_name", returning="representation")
            .execute()
        )
        if res.data:
            return res.data[0]
        # ON CONFLICT DO UPDATE returns the row; fallback to SELECT
        select_res = (
            supabase.table("species")
            .select("*")
            .eq("scientific_name", candidate.scientific_name)
            .execute()
        )
        return select_res.data[0]

    row = await asyncio.to_thread(_upsert)
    return SpeciesRecord(**row)


async def insert_care_profile(
    species_id: UUID | str,
    profile: CareProfileLlmOutput,
    *,
    needs_review: bool,
) -> None:
    data = {
        "species_id": str(species_id),
        "min_temp_c": profile.care_ranges.min_temp_c,
        "max_temp_c": profile.care_ranges.max_temp_c,
        "min_light_lux": profile.care_ranges.min_light_lux,
        "max_light_lux": profile.care_ranges.max_light_lux,
        "min_air_humidity_pct": profile.care_ranges.min_air_humidity_pct,
        "max_air_humidity_pct": profile.care_ranges.max_air_humidity_pct,
        "min_soil_humidity_pct": profile.care_ranges.min_soil_humidity_pct,
        "max_soil_humidity_pct": profile.care_ranges.max_soil_humidity_pct,
        "care_data_source": "llm_inference",
        "proposal_confidence": profile.proposal_confidence,
        "needs_review": needs_review,
        "reasoning_summary": profile.reasoning_summary,
        "weight_light": profile.care_weights.light,
        "weight_soil_humidity": profile.care_weights.soil_humidity,
        "weight_air_humidity": profile.care_weights.air_humidity,
        "weight_temperature": profile.care_weights.temperature,
        "sensitivity_light": profile.sensitivity_assessment.light,
        "sensitivity_soil_humidity": profile.sensitivity_assessment.soil_humidity,
        "sensitivity_air_humidity": profile.sensitivity_assessment.air_humidity,
        "sensitivity_temperature": profile.sensitivity_assessment.temperature,
        "eval_interval_temp_min": profile.eval_intervals.temperature,
        "eval_interval_light_min": profile.eval_intervals.light,
        "eval_interval_air_hum_min": profile.eval_intervals.air_humidity,
        "eval_interval_soil_hum_min": profile.eval_intervals.soil_humidity,
    }
    await asyncio.to_thread(lambda: supabase.table("species_care_profiles").insert(data).execute())


async def insert_ai_content(
    species_id: UUID | str,
    profile: CareProfileLlmOutput,
    language: str,
    model: str,
) -> None:
    import json

    data = {
        "species_id": str(species_id),
        "ai_personality_prompt": profile.ai_personality_prompt,
        "care_summary": profile.care_summary,
        "care_tips": json.dumps(profile.care_tips, ensure_ascii=False),
        "fun_facts": json.dumps(profile.fun_facts, ensure_ascii=False),
        "faq": json.dumps([f.model_dump() for f in profile.faq], ensure_ascii=False),
        "language": language,
        "llm_model": model,
        "elevenlabs_voice_id": profile.elevenlabs_voice_id,
        "elevenlabs_voice_alternatives": json.dumps(profile.elevenlabs_voice_alternatives, ensure_ascii=False),
    }
    await asyncio.to_thread(
        lambda: supabase.table("species_ai_content")
        .upsert(data, on_conflict="species_id,language")
        .execute()
    )


async def insert_common_names(
    species_id: UUID | str,
    candidate: PlantIdCandidate,
    taxonomy: GbifTaxonomy | None,
) -> None:
    rows: list[dict] = []

    seen: set[tuple[str, str]] = set()

    def _add(name: str, lang: str, region: str | None = None) -> None:
        key = (name.strip(), lang)
        if name.strip() and key not in seen:
            seen.add(key)
            rows.append({"species_id": str(species_id), "name": name.strip(), "language": lang, "region": region})

    for name in candidate.common_names:
        _add(name, "en")

    if taxonomy:
        for vn in taxonomy.vernacular_names:
            _add(vn.get("name", ""), vn.get("language", "und"))

    if not rows:
        return

    def _insert_batch() -> None:
        supabase.table("species_common_names").upsert(
            rows, on_conflict="species_id,name,language", ignore_duplicates=True
        ).execute()

    try:
        await asyncio.to_thread(_insert_batch)
    except Exception as e:
        logger.warning("insert_common_names falló parcialmente: %s", e)


async def insert_localized_common_name(
    species_id: UUID | str,
    name: str,
    language: str,
) -> None:
    if not name or not name.strip():
        return

    def _upsert() -> None:
        supabase.table("species_common_names").upsert(
            {"species_id": str(species_id), "name": name.strip(), "language": language},
            on_conflict="species_id,name,language",
            ignore_duplicates=True,
        ).execute()

    await asyncio.to_thread(_upsert)
