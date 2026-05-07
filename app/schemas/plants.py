from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional

class PlantCreate(BaseModel):
    species_id: UUID = Field(..., description="UUID de la especie en la tabla species")
    nickname: str = Field(..., description="Apodo de la planta")

class PlantResponse(BaseModel):
    plant_id: UUID
    user_id: UUID
    species_id: UUID
    nickname: str
    health_status: str
    health_score: float
    created_at: datetime
    last_health_check: Optional[datetime] = None
