import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiomqtt
from app.core.config import settings
from app.db.firebase import firebase_db
from app.db.supabase import supabase
from app.services.health_service import calculate_and_save_health

logger = logging.getLogger("gossip_garden.mqtt")

async def get_plant_id_for_sensor(sensor_id: str) -> Optional[str]:
    """Busca en supabase la planta a la que está vinculado este sensor_id."""
    try:
        response = supabase.table('sensors').select('plant_id').eq('sensor_id', sensor_id).maybe_single().execute()
        if response and response.data:
            return response.data.get('plant_id')
    except Exception as e:
        logger.error(f"Error consultando el plant_id para el sensor {sensor_id}: {e}")
    return None

async def handle_sensor_message(sensor_id: str, payload_str: str):
    """Procesa el mensaje recibido por el sensor"""
    try:
        data = json.loads(payload_str)

        # MODO BROADCAST (QA): Ignoramos el plant_id que envíe el ESP32
        # y replicamos la lectura a TODAS las plantas en la base de datos.
        try:
            plants_response = supabase.table('plants').select('plant_id').execute()
            if not plants_response.data:
                logger.info("No hay plantas registradas. Se ignora la lectura del sensor.")
                return
            target_plant_ids = [p['plant_id'] for p in plants_response.data]
        except Exception as e:
            logger.error(f"Error consultando plantas para broadcast: {e}")
            return

        now = datetime.now(timezone.utc)
        expire_at = now + timedelta(days=30)

        base_doc_data = {
            "sensor_id": sensor_id,
            "mac_address": data.get("mac_address", ""),
            "temperature_c": data.get("temperature_c", 0.0),
            "humidity_pct": data.get("humidity_pct", 0.0),
            "soil_moisture_pct": data.get("soil_moisture_pct", 0.0),
            "light_lux": data.get("light_lux", 0.0),
            "timestamp": now,
            "expireAt": expire_at
        }

        # 1. Guardar la lectura global para nuevas plantas
        try:
            firebase_db.collection("global_state").document("latest_sensor_reading").set(base_doc_data)
            logger.info(f"Lectura global guardada en Firebase (Sensor: {sensor_id})")
        except Exception as e:
            logger.error(f"Error guardando lectura global: {e}")

        async def _process_broadcast():
            batch = firebase_db.batch()
            count = 0
            for pid in target_plant_ids:
                try:
                    score, status = await calculate_and_save_health(
                        str(pid),
                        base_doc_data["temperature_c"],
                        base_doc_data["light_lux"],
                        base_doc_data["humidity_pct"],
                        base_doc_data["soil_moisture_pct"]
                    )
                    
                    doc_data = base_doc_data.copy()
                    doc_data["plant_id"] = str(pid)
                    doc_data["health_score"] = score
                    doc_data["health_status"] = status

                    # Guardar en Firebase dentro de la subcolección de la planta
                    doc_ref = firebase_db.collection("plants").document(str(pid)).collection("sensor_readings").document()
                    batch.set(doc_ref, doc_data)
                    count += 1
                    
                    if count >= 400:
                        await asyncio.to_thread(batch.commit)
                        batch = firebase_db.batch()
                        count = 0
                except Exception as e:
                    logger.error(f"Error en broadcast para la planta {pid}: {e}")
            if count > 0:
                await asyncio.to_thread(batch.commit)
                logger.info(f"Guardada lectura MQTT (Broadcast) para múltiples plantas")

        asyncio.create_task(_process_broadcast())

    except json.JSONDecodeError:
        logger.error(f"Error decodificando el JSON de MQTT payload: {payload_str}")
    except Exception as e:
        logger.error(f"Error procesando mensaje de sensor MQTT: {e}")

async def mqtt_loop():
    if not settings.MQTT_ENABLED:
        logger.info("MQTT está deshabilitado por configuración.")
        return

    client_kwargs = {
        "hostname": settings.MQTT_HOST,
        "port": settings.MQTT_PORT,
        "username": settings.MQTT_USERNAME,
        "password": settings.MQTT_PASSWORD,
        "keepalive": settings.MQTT_KEEPALIVE,
    }

    if settings.MQTT_SSL:
        # aiomqtt configures TLS internally if an empty context object is provided, or you can supply custom TLS
        import ssl
        client_kwargs["tls_context"] = ssl.create_default_context()

    reconnect_interval = 3

    while True:
        try:
            logger.info(f"Conectando a broker MQTT en {settings.MQTT_HOST}...")
            async with aiomqtt.Client(**client_kwargs) as client:
                logger.info("¡Conectado exitosamente al broker MQTT!")

                await client.subscribe(settings.MQTT_TOPIC)
                logger.info(f"Suscrito a tópico {settings.MQTT_TOPIC}")

                async for message in client.messages:
                    topic = str(message.topic)
                    payload = message.payload.decode() if message.payload else ""

                    # Ejemplo de topic: plantas/id-del-sensor/sensores
                    parts = topic.split('/')
                    if len(parts) >= 3 and parts[0] == "plantas" and parts[-1] == "sensores":
                        sensor_id = parts[1]
                        # Disparar en background para no bloquear el loop de MQTT
                        asyncio.create_task(handle_sensor_message(sensor_id, payload))

        except aiomqtt.MqttError as error:
            logger.error(f"Error MQTT: {error}. Reconectando en {reconnect_interval} segundos...")
            await asyncio.sleep(reconnect_interval)
        except asyncio.CancelledError:
            logger.info("MQTT loop fue cancelado (Apagando server).")
            break
        except Exception as e:
            logger.error(f"Error inesperado en loop MQTT: {e}. Reconectando...")
            await asyncio.sleep(reconnect_interval)

# Variable global para guardar la tarea y poder cancelarla
mqtt_task = None

def start_mqtt_client():
    global mqtt_task
    if settings.MQTT_ENABLED:
        loop = asyncio.get_event_loop()
        mqtt_task = loop.create_task(mqtt_loop())

def stop_mqtt_client():
    global mqtt_task
    if mqtt_task and not mqtt_task.done():
        mqtt_task.cancel()
