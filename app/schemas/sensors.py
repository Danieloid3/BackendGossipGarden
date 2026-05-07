from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional

class SensorDataCreate(BaseModel):
    sensor_id: Optional[str] = Field(default=None, description="ID del sensor o su MAC Address")
    mac_address: Optional[str] = Field(default=None, description="MAC Address del hardware ESP32")
    plant_id: UUID = Field(..., description="UUID de la planta en Supabase")
    temperature_c: float = Field(..., description="Temperatura en grados Celsius")
    humidity_pct: float = Field(..., description="Humedad relativa del aire en porcentaje")
    soil_moisture_pct: float = Field(..., description="Humedad del suelo en porcentaje")
    light_lux: float = Field(..., description="Intensidad de la luz en Lux")
