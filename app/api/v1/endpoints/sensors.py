from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone, timedelta
from app.schemas.sensors import SensorDataCreate
from app.db.firebase import firebase_db

router = APIRouter()

@router.post("/")
async def ingest_sensor_data(
    data: SensorDataCreate
):
    try:
        # Generar timestamp en UTC y expireAt (30 días)
        now = datetime.now(timezone.utc)
        expire_at = now + timedelta(days=30)

        # Convertir datos a dict (manejando correctamente los UUID, floats, etc.)
        doc_data = data.model_dump(mode='json', exclude_unset=True)
        doc_data["timestamp"] = now
        doc_data["expireAt"] = expire_at

        # Guardar en la subcolección de la planta específica para separar métricas individualmente
        _, doc_ref = firebase_db.collection("plants").document(str(data.plant_id)).collection("sensor_readings").add(doc_data)

        return {
            "status": "success",
            "message": "Datos ingeridos correctamente.",
            "doc_id": doc_ref.id
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno guardando la lectura del sensor: {str(e)}"
        )
