from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, field_validator


class SpeciesRecord(BaseModel):
    id: UUID
    scientific_name: str
    common_name: str | None = None
    family: str | None = None
    genus: str | None = None
    gbif_taxon_key: int | None = None
    inaturalist_id: int | None = None
    source_provider: str = "plant.id"
    created_at: datetime
    updated_at: datetime


class SpeciesCareProfileRecord(BaseModel):
    id: UUID
    species_id: UUID
    min_temp_c: float | None = None
    max_temp_c: float | None = None
    min_light_lux: float | None = None
    max_light_lux: float | None = None
    min_air_humidity_pct: float | None = None
    max_air_humidity_pct: float | None = None
    min_soil_humidity_pct: float | None = None
    max_soil_humidity_pct: float | None = None
    care_data_source: str = "llm_inference"
    proposal_confidence: str | None = None
    needs_review: bool = True
    reasoning_summary: str | None = None
    completed_at: datetime
    weight_light: float | None = None
    weight_soil_humidity: float | None = None
    weight_air_humidity: float | None = None
    weight_temperature: float | None = None
    sensitivity_light: str | None = None
    sensitivity_soil_humidity: str | None = None
    sensitivity_air_humidity: str | None = None
    sensitivity_temperature: str | None = None
    eval_interval_temp_min: int | None = None
    eval_interval_light_min: int | None = None
    eval_interval_air_hum_min: int | None = None
    eval_interval_soil_hum_min: int | None = None


class SpeciesAiContentRecord(BaseModel):
    id: UUID
    species_id: UUID
    ai_personality_prompt: str | None = None
    care_summary: str | None = None
    care_tips: list[Any] = []
    fun_facts: list[Any] = []
    faq: list[Any] = []
    language: str = "es"
    llm_model: str | None = None
    generated_at: datetime

    @field_validator("care_tips", "fun_facts", "faq", mode="before")
    @classmethod
    def parse_jsonb(cls, v: Any) -> list:
        if isinstance(v, str):
            return json.loads(v)
        return v if v is not None else []


class SpeciesCommonNameRecord(BaseModel):
    id: UUID
    species_id: UUID
    name: str
    language: str
    region: str | None = None


class SpeciesFullResponse(BaseModel):
    species: SpeciesRecord
    care_profile: SpeciesCareProfileRecord | None = None
    ai_content: SpeciesAiContentRecord | None = None
    common_names: list[SpeciesCommonNameRecord] = []
