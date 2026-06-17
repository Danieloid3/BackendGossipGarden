from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional, Any

class CareTips(BaseModel):
    watering: str
    light: str
    substrate: str
    humidity: str
    general_tip: str

class PlantCreate(BaseModel):
    species_id: UUID = Field(..., description="UUID de la especie en la tabla species")
    nickname: str = Field(..., description="Apodo de la planta")
    photo_storage_path: str | None = Field(
        default=None,
        description="Path en Firebase Storage devuelto por /identify (photo_storage_path)"
    )
    estimated_age_months: Optional[int] = Field(None, description="Edad estimada al momento de adopción")
    location: Optional[str] = Field(None, description="Ubicación en casa (ej. Sala, Balcón)")

class PersonalizedCareRequest(BaseModel):
    city: str = Field(..., description="Ciudad o región para adaptar el clima")
    language: Optional[str] = Field(None, description="Idioma deseado para los consejos (ej. 'es', 'en')")

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
    estimated_age_months: Optional[int] = None
    location: Optional[str] = None
    specific_care_tips: Optional[Any] = None
