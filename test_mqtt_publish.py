import asyncio
import json
import ssl
from app.core.config import settings
import aiomqtt

async def publish_test_message():
    # Usamos la misma configuración que en tu .env
    client_kwargs = {
        "hostname": settings.MQTT_HOST,
        "port": settings.MQTT_PORT,
        "username": settings.MQTT_USERNAME,
        "password": settings.MQTT_PASSWORD,
    }

    if settings.MQTT_SSL:
        client_kwargs["tls_context"] = ssl.create_default_context()

    # Simulamos el ID de un sensor
    test_sensor_id = "sensor_esp32_test_01"

    # El tópico dinámico coincidirá con 'plantas/+/sensores'
    topic = f"plantas/{test_sensor_id}/sensores"

    # Datos simulados del sensor (Puedes poner el plant_id aquí directamente para probar
    # sin necesidad de que el sensor exista en Supabase previamente)
    payload = {
        "plant_id": "00000000-0000-0000-0000-000000000000", #  <-- CAMBIA ESTO POR UN ID DE UNA PLANTA REAL TUYA
        "mac_address": "AA:BB:CC:DD:EE:FF",
        "temperature_c": 26.5,
        "humidity_pct": 45.0,
        "soil_moisture_pct": 60.2,
        "light_lux": 1500.5
    }

    print(f"Conectando a {settings.MQTT_HOST}...")
    async with aiomqtt.Client(**client_kwargs) as client:
        print(f"Conectado. Publicando en el tópico: {topic}")
        await client.publish(topic, payload=json.dumps(payload))
        print("¡Mensaje publicado con éxito!")

if __name__ == "__main__":
    asyncio.run(publish_test_message())
