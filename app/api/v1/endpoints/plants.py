import urllib.parse
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from typing import List, Optional
import json
import re
from app.schemas.plants import PlantCreate, PlantResponse, PersonalizedCareRequest, PlantProfileResponse
from app.schemas.sensors import SensorDataResponse
from app.core.security import get_current_user
from app.core.config import settings
from app.db.supabase import supabase
from app.db.firebase import firebase_db
from google.cloud.firestore import Query

router = APIRouter()

def _photo_url(path: str | None) -> str | None:
    if not path or not settings.FIREBASE_STORAGE_BUCKET:
        return None
    encoded = urllib.parse.quote(path, safe='')
    return f"https://firebasestorage.googleapis.com/v0/b/{settings.FIREBASE_STORAGE_BUCKET}/o/{encoded}?alt=media"

def _flatten_species(row: dict) -> dict:
    """Extrae common_name y scientific_name del join anidado con species."""
    species_info = row.pop('species', None) or {}
    row['common_name'] = species_info.get('common_name')
    row['scientific_name'] = species_info.get('scientific_name')
    return row

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
            "health_status": "healthy",
            "health_score": 100.0,
        }
        if plant.photo_storage_path:
            plant_data["photo_storage_path"] = plant.photo_storage_path

        # Insertar en Supabase
        response = supabase.table('plants').insert(plant_data).execute()

        if not response.data:
            raise HTTPException(status_code=400, detail="No se pudo crear la planta.")

        plant_id = response.data[0]['plant_id']
        fetched = supabase.table('plants').select('*, species(common_name, scientific_name)').eq('plant_id', plant_id).execute()
        row = fetched.data[0]
        _flatten_species(row)
        row['photo_url'] = _photo_url(row.get('photo_storage_path'))
        return row

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creando la planta: {str(e)}"
        )

@router.post("/{plant_id}/personalized-care", response_model=PlantResponse)
async def generate_personalized_care_tips(
    plant_id: str,
    request: PersonalizedCareRequest,
    user_id: str = Depends(get_current_user)
):
    """Genera y guarda consejos de cuidado hiper-personalizados para una planta basándose en su especie, ubicación y ciudad (clima)."""
    # Verificar que la planta pertenece al usuario
    plant_row = supabase.table("plants").select("*, species(scientific_name)").eq("plant_id", plant_id).eq("user_id", user_id).execute()
    if not plant_row.data:
        raise HTTPException(status_code=404, detail="Planta no encontrada o no tienes acceso.")
    
    plant = plant_row.data[0]
    
    # Resolver idioma
    language = request.language
    if not language:
        language = "es"
        from app.db.supabase import supabase
        try:
            user_row = supabase.table("users").select("preferred_language").eq("user_id", user_id).execute()
            if user_row.data and user_row.data[0].get("preferred_language"):
                language = user_row.data[0]["preferred_language"]
        except Exception as e:
            import logging
            logging.warning(f"Failed to fetch preferred_language in plants.py: {e}")
    
    # Validar que tengamos la información necesaria
    if not plant.get("location"):
        raise HTTPException(status_code=400, detail="La planta no tiene una ubicación configurada (ej. 'Sala'). Configúrala primero.")
    
    scientific_name = plant["species"]["scientific_name"]
    
    from app.services.openai_service import generate_personalized_care
    
    try:
        tips = await generate_personalized_care(
            species_name=scientific_name,
            location=plant["location"],
            city=request.city,
            language=language,
            estimated_age_months=plant.get("estimated_age_months")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando tips de cuidado: {str(e)}")
        
    # Guardar los tips en la base de datos
    updated = supabase.table("plants").update({"specific_care_tips": tips}).eq("plant_id", plant_id).execute()
    
    if not updated.data:
        raise HTTPException(status_code=500, detail="Error guardando los tips de cuidado en la planta.")
        
    fetched = supabase.table("plants").select("*, species(common_name, scientific_name)").eq("plant_id", plant_id).execute()
    row = fetched.data[0]
    _flatten_species(row)
    row['photo_url'] = _photo_url(row.get('photo_storage_path'))
    return row

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

        # Obtener las plantas con nombre de especie
        response = supabase.table('plants').select('*, species(common_name, scientific_name)').eq('user_id', user_to_query).execute()

        plants = response.data
        for plant in plants:
            _flatten_species(plant)
            plant['photo_url'] = _photo_url(plant.get('photo_storage_path'))
        return plants

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo las plantas: {str(e)}"
        )

@router.get("/{plant_id}/profile", response_model=PlantProfileResponse)
async def get_plant_profile(
    plant_id: str,
    user_id: str = Depends(get_current_user)
):
    try:
        import json
        # Fetch the plant
        plant_res = supabase.table('plants').select('*, species(common_name, scientific_name)').eq('plant_id', plant_id).execute()
        if not plant_res.data:
            raise HTTPException(status_code=404, detail="Planta no encontrada.")
            
        plant_row = plant_res.data[0]
        plant_owner_id = plant_row['user_id']

        if plant_owner_id != user_id:
            user_low = min(user_id, plant_owner_id)
            user_high = max(user_id, plant_owner_id)
            friendship = supabase.table('friendships').select('status').eq('user_low_id', user_low).eq('user_high_id', user_high).eq('status', 'accepted').execute()
            if not friendship.data:
                raise HTTPException(status_code=403, detail="No tienes acceso al perfil de esta planta.")

        _flatten_species(plant_row)
        plant_row['photo_url'] = _photo_url(plant_row.get('photo_storage_path'))
        species_id = plant_row['species_id']

        # Fetch care ranges
        care_ranges_res = supabase.table('species_care_profiles').select('*').eq('species_id', species_id).execute()
        care_ranges_dto = None
        if care_ranges_res.data:
            cr = care_ranges_res.data[0]
            care_ranges_dto = {
                "min_temp_c": cr.get("min_temp_c", 0),
                "max_temp_c": cr.get("max_temp_c", 0),
                "min_light_lux": cr.get("min_light_lux", 0),
                "max_light_lux": cr.get("max_light_lux", 0),
                "min_air_humidity_pct": cr.get("min_air_humidity_pct", 0),
                "max_air_humidity_pct": cr.get("max_air_humidity_pct", 0),
                "min_soil_humidity_pct": cr.get("min_soil_humidity_pct", 0),
                "max_soil_humidity_pct": cr.get("max_soil_humidity_pct", 0),
            }

        # Fetch AI content
        ai_res = supabase.table('species_ai_content').select('*').eq('species_id', species_id).limit(1).execute()
        ai_dto = {
            "care_summary": None,
            "ai_personality_prompt": None,
            "care_tips": [],
            "fun_facts": [],
            "care_ranges": care_ranges_dto
        }
        if ai_res.data:
            ai_data = ai_res.data[0]
            ai_dto["care_summary"] = ai_data.get("care_summary")
            ai_prompt = ai_data.get("ai_personality_prompt", "")
            ai_dto["ai_personality_prompt"] = ai_prompt
            
            # Dynamic parsing for personality traits and description
            desc = "Una planta con personalidad única."
            traits = ["Única", "Misteriosa"]
            if ai_prompt:
                match = re.search(r"2\. TONO Y CARÁCTER\n(.*?)(?:\n3\.|\Z)", ai_prompt, re.DOTALL)
                if match:
                    desc_text = match.group(1).strip()
                    sentences = desc_text.split('. ')
                    desc = sentences[0] + ('.' if not sentences[0].endswith('.') else '')
                    
                    eres_match = re.search(r"[Ee]res\s+([a-záéíóúñ,\s]+)\.", desc_text)
                    if eres_match:
                        words = [w.strip() for w in eres_match.group(1).split(',')]
                        words = [w for w in words if w and len(w) > 3]
                        if words:
                            traits = []
                            for w in words:
                                for sub in w.split(' y '):
                                    clean = sub.replace('algo ', '').replace('muy ', '').strip().capitalize()
                                    if clean and len(clean) > 3:
                                        traits.append(clean)
                            traits = traits[:3]

            ai_dto["personality_description"] = desc
            ai_dto["personality_traits"] = traits

            def parse_json_list(val):
                if not val:
                    return []
                if isinstance(val, list):
                    return val
                try:
                    return json.loads(val)
                except:
                    return []
                    
            ai_dto["care_tips"] = parse_json_list(ai_data.get("care_tips"))
            ai_dto["fun_facts"] = parse_json_list(ai_data.get("fun_facts"))

        plant_row["species_info"] = ai_dto
        return plant_row

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo el perfil de la planta: {str(e)}"
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
        doc_dict["plant_id"] = plant_id
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
            doc_dict["plant_id"] = plant_id
            history.append(doc_dict)

        return history

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo el historial de los datos: {str(e)}"
        )


_ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_PHOTO_BYTES = 8 * 1024 * 1024  # 8 MB


@router.put("/{plant_id}/photo", response_model=PlantResponse)
async def update_plant_photo(
    plant_id: str,
    image: UploadFile = File(..., description="Nueva foto de la planta (JPEG/PNG/WebP, máx 8 MB)"),
    user_id: str = Depends(get_current_user),
):
    """Reemplaza la foto de una planta sin necesidad de re-identificarla.

    Comprime la imagen (máx 1920px, JPEG q=85) y la sube a Firebase Storage.
    Retorna la planta actualizada con el nuevo photo_storage_path.
    """
    if image.content_type not in _ALLOWED_PHOTO_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Formato no soportado: {image.content_type}. Usa JPEG, PNG o WebP.",
        )

    image_bytes = await image.read()
    if len(image_bytes) > _MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Imagen demasiado grande (máx 8 MB)")

    # Verificar que la planta pertenece al usuario
    plant_row = supabase.table("plants").select("*").eq("plant_id", plant_id).eq("user_id", user_id).execute()
    if not plant_row.data:
        raise HTTPException(status_code=404, detail="Planta no encontrada o no tienes acceso.")

    from app.services.image_storage_service import upload_plant_photo
    try:
        storage_path = await upload_plant_photo(image_bytes, user_id, plant_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    updated = (
        supabase.table("plants")
        .update({"photo_storage_path": storage_path})
        .eq("plant_id", plant_id)
        .execute()
    )

    if not updated.data:
        raise HTTPException(status_code=500, detail="Error actualizando la foto de la planta.")

    fetched = supabase.table("plants").select("*, species(common_name, scientific_name)").eq("plant_id", plant_id).execute()
    row = fetched.data[0]
    _flatten_species(row)
    row['photo_url'] = _photo_url(row.get('photo_storage_path'))
    return row


@router.delete("/{plant_id}", status_code=204)
async def delete_plant(
    plant_id: str,
    user_id: str = Depends(get_current_user),
):
    plant_row = supabase.table("plants").select("user_id").eq("plant_id", plant_id).execute()
    if not plant_row.data:
        raise HTTPException(status_code=404, detail="Planta no encontrada.")
    if plant_row.data[0]["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para eliminar esta planta.")

    try:
        supabase.table("plants").delete().eq("plant_id", plant_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error eliminando la planta: {str(e)}")
