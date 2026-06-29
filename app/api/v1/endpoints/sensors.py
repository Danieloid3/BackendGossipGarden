from fastapi import APIRouter, HTTPException, BackgroundTasks
import asyncio
from datetime import datetime, timezone, timedelta
from app.schemas.sensors import SensorDataCreate
from app.db.firebase import firebase_db
from app.services.health_service import calculate_and_save_health

router = APIRouter()

@router.post("/")
async def ingest_sensor_data(
    data: SensorDataCreate,
    background_tasks: BackgroundTasks
):
    try:
        now = datetime.now(timezone.utc)
        expire_at = now + timedelta(days=30)
        doc_data = data.model_dump(mode='json', exclude_unset=True)
        doc_data["timestamp"] = now
        doc_data["expireAt"] = expire_at

        # MODO BROADCAST (QA) - Fondo
        from app.db.supabase import supabase
        
        def _get_plants():
            return supabase.table('plants').select('plant_id').execute()
            
        plants_response = await asyncio.to_thread(_get_plants)
        if not plants_response.data:
            return {"status": "ignored", "message": "No hay plantas registradas."}
            
        target_plant_ids = [p['plant_id'] for p in plants_response.data]

        async def _process_broadcast():
            # Create a Firestore batch
            batch = firebase_db.batch()
            count = 0
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
                    
                    doc_ref = firebase_db.collection("plants").document(str(pid)).collection("sensor_readings").document()
                    batch.set(doc_ref, doc_to_save)
                    count += 1
                    
                    if count >= 400: # Firestore max batch is 500
                        await asyncio.to_thread(batch.commit)
                        batch = firebase_db.batch()
                        count = 0
                except Exception as e:
                    print(f"Error en broadcast rest para {pid}: {e}")
            if count > 0:
                await asyncio.to_thread(batch.commit)

        background_tasks.add_task(_process_broadcast)

        return {
            "status": "success",
            "message": f"Datos distribuyéndose a {len(target_plant_ids)} plantas en segundo plano.",
            "doc_id": "broadcast"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno guardando la lectura del sensor: {str(e)}"
        )
