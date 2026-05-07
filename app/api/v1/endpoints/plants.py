from fastapi import APIRouter, Depends, HTTPException
from typing import List
from app.schemas.plants import PlantCreate, PlantResponse
from app.core.security import get_current_user
from app.db.supabase import supabase

router = APIRouter()

@router.post("/", response_model=PlantResponse)
async def create_plant(
    plant: PlantCreate,
    user_id: str = Depends(get_current_user)
):
    try:
        # Preparar los datos a insertar
        plant_data = {
            "user_id": user_id,
            "species_id": str(plant.species_id),
            "nickname": plant.nickname,
            "health_status": "healthy",  # Valor por defecto inicial
            "health_score": 100.0        # Valor por defecto inicial
        }

        # Insertar en Supabase
        response = supabase.table('plants').insert(plant_data).execute()

        if not response.data:
            raise HTTPException(status_code=400, detail="No se pudo crear la planta.")

        return response.data[0]

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creando la planta: {str(e)}"
        )

@router.get("/", response_model=List[PlantResponse])
async def get_plants(
    user_id: str = Depends(get_current_user)
):
    try:
        # Obtener las plantas del usuario
        response = supabase.table('plants').select('*').eq('user_id', user_id).execute()

        return response.data

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo las plantas: {str(e)}"
        )
