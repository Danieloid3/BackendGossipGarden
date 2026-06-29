import math
from datetime import datetime, timezone
from app.db.supabase import supabase
import logging

logger = logging.getLogger(__name__)

def calculate_single_parameter_score(value, min_val, max_val):
    if value is None or min_val is None or max_val is None:
        return 100.0

    if min_val <= value <= max_val:
        return 100.0

    # Simple logic: lose points based on how far out of bounds it is.
    # For instance, if max is 30, and it's 35, it's out of bounds. Let's have a leniency.
    # Suppose a 20% deviation goes to 0 score.
    range_span = max(max_val - min_val, 1.0)

    if value < min_val:
        deviation = min_val - value
    else:
        deviation = value - max_val

    score = 100.0 - ((deviation / range_span) * 100.0)
    return max(0.0, score)

async def calculate_and_save_health(plant_id: str, temperature: float, light: float, air_humidity: float, soil_humidity: float) -> tuple[float, str]:
    """
    Calculates health score and status, saves them to supabase in plants table, and returns (score, status).
    """
    try:
        # 1. Fetch species_id for the plant
        plant_res = await asyncio.to_thread(
            lambda: supabase.table("plants").select("species_id").eq("plant_id", plant_id).maybe_single().execute()
        )
        if not plant_res or not plant_res.data:
            return 100.0, "healthy"

        species_id = plant_res.data["species_id"]

        # 2. Fetch species_care_profiles
        care_res = await asyncio.to_thread(
            lambda: supabase.table("species_care_profiles").select("*").eq("species_id", species_id).maybe_single().execute()
        )

        if not care_res or not care_res.data:
            return 100.0, "healthy"

        care = care_res.data

        # 3. Calculate score
        temp_score = calculate_single_parameter_score(temperature, care.get("min_temp_c"), care.get("max_temp_c"))
        light_score = calculate_single_parameter_score(light, care.get("min_light_lux"), care.get("max_light_lux"))
        air_score = calculate_single_parameter_score(air_humidity, care.get("min_air_humidity_pct"), care.get("max_air_humidity_pct"))
        soil_score = calculate_single_parameter_score(soil_humidity, care.get("min_soil_humidity_pct"), care.get("max_soil_humidity_pct"))

        w_temp = care.get("weight_temperature") or 0.25
        w_light = care.get("weight_light") or 0.25
        w_air = care.get("weight_air_humidity") or 0.25
        w_soil = care.get("weight_soil_humidity") or 0.25

        total_weight = w_temp + w_light + w_air + w_soil
        if total_weight <= 0:
            w_temp = w_light = w_air = w_soil = 0.25
            total_weight = 1.0

        health_score = (temp_score * w_temp + light_score * w_light + air_score * w_air + soil_score * w_soil) / total_weight

        # 4. Status mapping
        if health_score >= 80:
            status = "healthy"
        elif health_score >= 50:
            status = "warning"
        else:
            status = "critical"

        # 5. Save to supabase plants table
        await asyncio.to_thread(
            lambda: supabase.table("plants").update({
                "health_score": round(health_score, 2),
                "health_status": status,
                "sensor_status": "online"
            }).eq("plant_id", plant_id).execute()
        )

        return round(health_score, 2), status

    except Exception as e:
        logger.error(f"Error calculating health for plant {plant_id}: {e}")
        return 100.0, "healthy"
