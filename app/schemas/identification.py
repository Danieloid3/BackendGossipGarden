from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class WateringScale(BaseModel):
    min: int | None = None
    max: int | None = None


class PlantIdCandidate(BaseModel):
    scientific_name: str
    common_names: list[str] = []
    probability: float
    gbif_id: int | None = None
    inaturalist_id: int | None = None
    taxonomy: dict = Field(default_factory=dict)
    watering: WateringScale | None = None
    description: str | None = None
    image_url: str | None = None
    reference_images: list[str] = []


class GbifTaxonomy(BaseModel):
    key: int
    scientific_name: str
    canonical_name: str | None = None
    family: str | None = None
    genus: str | None = None
    order: str | None = None
    class_: str | None = Field(default=None, alias="class")
    phylum: str | None = None
    kingdom: str | None = None
    vernacular_names: list[dict] = []

    model_config = {"populate_by_name": True}


class RagChunk(BaseModel):
    content: str
    source: str
    scientific_name: str | None = None
    family: str | None = None
    similarity: float


class CareRanges(BaseModel):
    min_temp_c: float
    max_temp_c: float
    min_light_lux: float
    max_light_lux: float
    min_air_humidity_pct: float
    max_air_humidity_pct: float
    min_soil_humidity_pct: float
    max_soil_humidity_pct: float


class FaqItem(BaseModel):
    question: str
    answer: str


class CareWeights(BaseModel):
    light: float = Field(ge=0, le=1)
    soil_humidity: float = Field(ge=0, le=1)
    air_humidity: float = Field(ge=0, le=1)
    temperature: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def check_sum(self) -> "CareWeights":
        total = self.light + self.soil_humidity + self.air_humidity + self.temperature
        if abs(total - 1.0) > 0.05:
            raise ValueError(f"Los pesos deben sumar 1.0 (suma actual: {total:.3f})")
        return self


class SensitivityAssessment(BaseModel):
    light: Literal["high", "medium", "low"]
    soil_humidity: Literal["high", "medium", "low"]
    air_humidity: Literal["high", "medium", "low"]
    temperature: Literal["high", "medium", "low"]


class EvalIntervals(BaseModel):
    temperature: int = Field(ge=30)
    light: int = Field(ge=30)
    air_humidity: int = Field(ge=30)
    soil_humidity: int = Field(ge=30)


class CareProfileLlmOutput(BaseModel):
    scientific_name: str
    common_name: str
    family: str
    care_ranges: CareRanges
    care_weights: CareWeights
    sensitivity_assessment: SensitivityAssessment
    eval_intervals: EvalIntervals
    care_summary: str
    ai_personality_prompt: str
    care_tips: list[str]
    fun_facts: list[str]
    faq: list[FaqItem]
    proposal_confidence: Literal["high", "medium", "low"]
    reasoning_summary: str
    elevenlabs_voice_id: str | None = None
    elevenlabs_voice_alternatives: list[str] = []


# ---- Respuesta discriminada del endpoint /identify ----------

class NeedsMorePhotosResponse(BaseModel):
    status: Literal["needs_more_photos"] = "needs_more_photos"
    reason: str = "Confianza demasiado baja para identificar la planta"
    top_probability: float


class NeedsUserSelectionResponse(BaseModel):
    status: Literal["needs_user_selection"] = "needs_user_selection"
    candidates: list[PlantIdCandidate]
    photo_storage_path: str | None = None


class CareProfileResponse(BaseModel):
    species_id: UUID
    scientific_name: str
    common_name: str
    family: str | None
    care_ranges: CareRanges
    care_weights: CareWeights | None = None
    sensitivity_assessment: SensitivityAssessment | None = None
    eval_intervals: EvalIntervals | None = None
    care_summary: str | None
    ai_personality_prompt: str | None
    care_tips: list[str]
    fun_facts: list[str]
    faq: list[FaqItem]
    proposal_confidence: Literal["high", "medium", "low"] | None
    needs_review: bool
    language: str
    cached: bool
    created_at: datetime


class CompletedResponse(BaseModel):
    status: Literal["completed"] = "completed"
    profile: CareProfileResponse
    photo_storage_path: str | None = None


IdentifyResponse = Annotated[
    Union[NeedsMorePhotosResponse, NeedsUserSelectionResponse, CompletedResponse],
    Field(discriminator="status"),
]


class FromCandidateRequest(BaseModel):
    candidate: PlantIdCandidate
    output_language: str = Field(default="es", pattern="^(es|en|fr|pt|de|it)$")
