from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone, timedelta
from app.schemas.sensors import SensorDataCreate
from app.db.firebase import firebase_db
from app.services.health_service import calculate_and_save_health

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

        # MODO BROADCAST (QA)
        from app.db.supabase import supabase
        plants_response = supabase.table('plants').select('plant_id').execute()
        if not plants_response.data:
            return {"status": "ignored", "message": "No hay plantas registradas."}
            
        target_plant_ids = [p['plant_id'] for p in plants_response.data]

        for pid in target_plant_ids:
            try:
                score, status = await calculate_and_save_health(
                    str(pid),
                    data.temperature_c,
                    data.light_lux,
                    data.humidity_pct,
                    data.soil_moisture_pct
                )
                
                doc_to_save = doc_data.copy()
                doc_to_save["plant_id"] = str(pid)
                doc_to_save["health_score"] = score
                doc_to_save["health_status"] = status
                
                firebase_db.collection("plants").document(str(pid)).collection("sensor_readings").add(doc_to_save)
            except Exception as e:
                print(f"Error en broadcast rest para {pid}: {e}")

        return {
            "status": "success",
            "message": f"Datos distribuidos a {len(target_plant_ids)} plantas.",
            "doc_id": "broadcast"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno guardando la lectura del sensor: {str(e)}"
        )
