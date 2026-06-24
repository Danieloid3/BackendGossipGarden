import asyncio
import logging
from datetime import datetime, timezone, timedelta
from app.db.supabase import supabase
from app.db.firebase import firebase_db
from app.services.chat_service import _get_personality, _load_summary_from_firestore_sync
from app.services.chat_service import build_system_with_summary, chat_with_plant
from app.db.redis import redis_client

logger = logging.getLogger(__name__)

_EVAL_TASK = None

async def evaluator_loop():
    logger.info("Starting Evaluator loop...")
    while True:
        try:
            await evaluate_all_plants()
        except Exception as e:
            logger.error(f"Error in evaluator loop: {e}", exc_info=True)
        # Run every 10 minutes
        await asyncio.sleep(600)

async def evaluate_all_plants():
    # Fetch all plants
    plants_res = supabase.table("plants").select("*").execute()

    plants = plants_res.data
    now = datetime.now(timezone.utc)

    if not plants:
        return

    # Extraer unique species_ids
    species_ids = list(set(p.get('species_id') for p in plants if p.get('species_id')))

    if not species_ids:
        return

    # Fetch care profiles para todas las species involucradas
    care_profiles_res = supabase.table("species_care_profiles").select("*").in_("species_id", species_ids).execute()
    care_profiles_dict = {cp['species_id']: cp for cp in care_profiles_res.data}

    for plant in plants:
        species_id = plant.get('species_id')
        if not species_id:
            continue

        care_profile = care_profiles_dict.get(species_id)
        if not care_profile:
            continue

        await evaluate_plant_parameters(plant, care_profile, now)


async def evaluate_plant_parameters(plant: dict, care_profile: dict, now: datetime):
    plant_id = plant['plant_id']
    user_id = plant['user_id']

    params_to_check = {
        'temp': ('last_eval_temp', 'eval_interval_temp_min', 'temperature_c', 'min_temp_c', 'max_temp_c', 'temperatura'),
        'light': ('last_eval_light', 'eval_interval_light_min', 'light_lux', 'min_light_lux', 'max_light_lux', 'luz'),
        'air_hum': ('last_eval_air_hum', 'eval_interval_air_hum_min', 'humidity_pct', 'min_air_humidity_pct', 'max_air_humidity_pct', 'humedad del aire'),
        'soil_hum': ('last_eval_soil_hum', 'eval_interval_soil_hum_min', 'soil_moisture_pct', 'min_soil_humidity_pct', 'max_soil_humidity_pct', 'humedad del suelo')
    }

    updates = {}
    triggered_alerts = []

    for key, (db_last, eval_col, fb_field, min_col, max_col, param_name) in params_to_check.items():
        interval_min = care_profile.get(eval_col)
        if not interval_min:
            continue

        last_eval_str = plant.get(db_last)
        if last_eval_str:
            last_eval = datetime.fromisoformat(last_eval_str.replace('Z', '+00:00'))
            if last_eval.tzinfo is None:
                last_eval = last_eval.replace(tzinfo=timezone.utc)
        else:
            last_eval = datetime.min.replace(tzinfo=timezone.utc)
        delta_minutes = (now - last_eval).total_seconds() / 60.0

        if delta_minutes >= interval_min:
            # Time to evaluate!
            updates[db_last] = now.isoformat()

            # Query Firebase for readings since LAST EVAL (or last interval if first time)
            since = last_eval if last_eval_str else now - timedelta(minutes=interval_min)

            avg_val = await asyncio.to_thread(_get_avg_from_firebase, plant_id, fb_field, since, now)

            if avg_val is not None:
                min_val = care_profile.get(min_col)
                max_val = care_profile.get(max_col)

                if (min_val is not None and avg_val < min_val) or (max_val is not None and avg_val > max_val):
                    triggered_alerts.append(f"{param_name} promedio ({avg_val:.2f}) fuera de rango ({min_val}-{max_val})")

    if updates:
        supabase.table("plants").update(updates).eq("plant_id", plant_id).execute()

    if triggered_alerts:
        await handle_alerts(plant_id, user_id, plant.get('species_id'), triggered_alerts)

def _get_avg_from_firebase(plant_id: str, field: str, since: datetime, to_date: datetime) -> float | None:
    try:
        from google.cloud.firestore import Query as FSQuery
        docs = (
            firebase_db.collection("plants")
            .document(plant_id)
            .collection("sensor_readings")
            .where("timestamp", ">=", since)
            .where("timestamp", "<=", to_date)
            .stream()
        )

        values = []
        for doc in docs:
            d = doc.to_dict()
            if field in d and isinstance(d[field], (int, float)):
                values.append(d[field])

        if not values:
            return None

        return sum(values) / len(values)
    except Exception as e:
        logger.error(f"Error fetching avg from firebase: {e}")
        return None

async def handle_alerts(plant_id: str, user_id: str, species_id: str, alerts: list[str]):
    alert_msg = "Problemas detectados: " + ", ".join(alerts)

    # Save event
    try:
        supabase.table("events").insert({
            "plant_id": plant_id,
            "type": "chat",
            "message": alert_msg
        }).execute()

        user_message = f"{alert_msg}. Escribe un mensaje corto y natural al usuario (tu dueño) para avisarle de esto de forma urgente pero proactiva, actuando siempre bajo tu personalidad de planta, como si acabaras de notarlo."

        # Spawn background task to not block
        asyncio.create_task(
            chat_with_plant(
                plant_id=plant_id,
                user_id=user_id,
                message=user_message,
                language="es",
                redis_client=redis_client,
                is_proactive=True
            )
        )
    except Exception as e:
        logger.error(f"Error handling alerts for plant {plant_id}: {e}")

def start_evaluator():
    global _EVAL_TASK
    if _EVAL_TASK is None:
        _EVAL_TASK = asyncio.create_task(evaluator_loop())

def stop_evaluator():
    global _EVAL_TASK
    if _EVAL_TASK is not None:
        _EVAL_TASK.cancel()
        _EVAL_TASK = None
