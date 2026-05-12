from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from app.schemas.plants import PlantCreate, PlantResponse
from app.schemas.sensors import SensorDataResponse
from app.core.security import get_current_user
from app.db.supabase import supabase
from app.db.firebase import firebase_db
from google.cloud.firestore import Query

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
    target_user_id: Optional[str] = None,
    current_user_id: str = Depends(get_current_user)
):
    try:
        user_to_query = target_user_id if target_user_id else current_user_id

        # Validar amistad si se está consultando a otro usuario
        if target_user_id and target_user_id != current_user_id:
            user_low = min(current_user_id, target_user_id)
            user_high = max(current_user_id, target_user_id)
            friendship = supabase.table('friendships').select('status').eq('user_low_id', user_low).eq('user_high_id', user_high).eq('status', 'accepted').execute()
            if not friendship.data:
                raise HTTPException(status_code=403, detail="No tienes acceso a las plantas de este usuario.")

        # Obtener las plantas
        response = supabase.table('plants').select('*').eq('user_id', user_to_query).execute()

        return response.data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo las plantas: {str(e)}"
        )

@router.get("/{plant_id}/sensor-data/latest", response_model=SensorDataResponse)
async def get_latest_sensor_data(
    plant_id: str,
    user_id: str = Depends(get_current_user)
):
    try:
        # Verificar acceso a la planta
        plant_check = supabase.table('plants').select('user_id').eq('plant_id', plant_id).execute()
        if not plant_check.data:
            raise HTTPException(status_code=404, detail="Planta no encontrada.")

        plant_owner_id = plant_check.data[0]['user_id']

        if plant_owner_id != user_id:
            user_low = min(user_id, plant_owner_id)
            user_high = max(user_id, plant_owner_id)
            friendship = supabase.table('friendships').select('status').eq('user_low_id', user_low).eq('user_high_id', user_high).eq('status', 'accepted').execute()
            if not friendship.data:
                raise HTTPException(status_code=403, detail="No tienes acceso a los datos de esta planta.")

        # Obtener el último dato de sensor de Firebase
        docs = firebase_db.collection("plants").document(plant_id).collection("sensor_readings")\
            .order_by("timestamp", direction=Query.DESCENDING).limit(1).stream()

        latest_doc = None
        for doc in docs:
            latest_doc = doc
            break

        if not latest_doc:
            raise HTTPException(status_code=404, detail="No hay datos de sensores para esta planta.")

        doc_dict = latest_doc.to_dict()
        doc_dict["id"] = latest_doc.id
        return doc_dict

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo los datos actuales: {str(e)}"
        )

@router.get("/{plant_id}/sensor-data/history", response_model=List[SensorDataResponse])
async def get_sensor_data_history(
    plant_id: str,
    days: int = 30,
    user_id: str = Depends(get_current_user)
):
    try:
        from datetime import datetime, timezone, timedelta

        # Verificar acceso a la planta
        plant_check = supabase.table('plants').select('user_id').eq('plant_id', plant_id).execute()
        if not plant_check.data:
            raise HTTPException(status_code=404, detail="Planta no encontrada.")

        plant_owner_id = plant_check.data[0]['user_id']

        if plant_owner_id != user_id:
            user_low = min(user_id, plant_owner_id)
            user_high = max(user_id, plant_owner_id)
            friendship = supabase.table('friendships').select('status').eq('user_low_id', user_low).eq('user_high_id', user_high).eq('status', 'accepted').execute()
            if not friendship.data:
                raise HTTPException(status_code=403, detail="No tienes acceso a los datos de esta planta.")

        past_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Obtener el historial de Firebase
        docs = firebase_db.collection("plants").document(plant_id).collection("sensor_readings")\
            .where("timestamp", ">=", past_date)\
            .order_by("timestamp", direction=Query.DESCENDING).stream()

        history = []
        for doc in docs:
            doc_dict = doc.to_dict()
            doc_dict["id"] = doc.id
            history.append(doc_dict)

        return history

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo el historial de los datos: {str(e)}"
        )
