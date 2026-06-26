from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional, Any


class PlantCreate(BaseModel):
    species_id: UUID = Field(..., description="UUID de la especie en la tabla species")
    nickname: str = Field(..., description="Apodo de la planta")
    photo_storage_path: str | None = Field(
        default=None,
        description="Path en Firebase Storage devuelto por /identify (photo_storage_path)"
    )
    estimated_age_months: Optional[int] = Field(None, description="Edad estimada al momento de adopción")
    location: Optional[str] = Field(None, description="Ubicación en casa (ej. Sala, Balcón)")

class PlantUpdate(BaseModel):
    nickname: Optional[str] = Field(None, description="Apodo de la planta")
    location: Optional[str] = Field(None, description="Ubicación en casa (ej. Sala, Balcón)")
    mac_address: Optional[str] = Field(None, description="MAC Address del hardware ESP32")

class PersonalizedCareRequest(BaseModel):
    city: str = Field(..., description="Ciudad o región para adaptar el clima")
    language: Optional[str] = Field(None, description="Idioma deseado para los consejos (ej. 'es', 'en')")

class PlantActionRequest(BaseModel):
    action_type: str = Field(..., description="Tipo de acción: water, fertilize, prune, etc.")

class PlantResponse(BaseModel):
    plant_id: UUID
    user_id: UUID
    species_id: UUID
    nickname: str
    health_status: str
    health_score: float
    photo_storage_path: Optional[str] = None
    photo_url: Optional[str] = None
    common_name: Optional[str] = None
    scientific_name: Optional[str] = None
    created_at: datetime
    last_health_check: Optional[datetime] = None
    mac_address: Optional[str] = None
    last_watered: Optional[datetime] = None
    estimated_age_months: Optional[int] = None
    location: Optional[str] = None
    specific_care_tips: Optional[Any] = None

class CareRangesDTO(BaseModel):  # Fix #2: float para respetar los FLOAT de la BD
    min_temp_c: float
    max_temp_c: float
    min_light_lux: float
    max_light_lux: float
    min_air_humidity_pct: float
    max_air_humidity_pct: float
    min_soil_humidity_pct: float
    max_soil_humidity_pct: float

class SpeciesInfoDTO(BaseModel):
    care_summary: Optional[str] = None
    ai_personality_prompt: Optional[str] = None
    personality_traits: list[str] = []
    personality_description: Optional[str] = None
    care_tips: list[str] = []
    fun_facts: list[str] = []
    care_ranges: Optional[CareRangesDTO] = None

class PlantProfileResponse(PlantResponse):
    species_info: SpeciesInfoDTO
