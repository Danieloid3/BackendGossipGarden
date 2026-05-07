import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Importar dependencias para asegurar validaciones en app startup
from app.db.redis import redis_client
from app.db.supabase import supabase
from app.db.firebase import firebase_db
from app.api.v1.api import api_router
from app.core.mqtt import start_mqtt_client, stop_mqtt_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("gossip_garden")
logger.setLevel(logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lógica de startup
    logger.info("Verificando conexiones a las bases de datos...")

    # 1. Supabase (Test)
    try:
        # Se realiza una petición simple para comprobar la conexión usando REST
        # En caso de no existir datos o no poder, lanzará un error si las credenciales fallan
        res = supabase.table('users').select("user_id").limit(1).execute()
        logger.info("Conexión a Supabase (PostgreSQL) exitosa.")
    except Exception as e:
        logger.error(f"Error conectando a Supabase: {e}")

    # 2. Firebase (Test)
    try:
        _ = firebase_db.collection('test_connection').limit(1).get()
        logger.info("Conexión a Firebase (Firestore) exitosa.")
    except Exception as e:
        logger.error(f"Error conectando a Firebase: {e}")

    # 3. Redis (Test)
    try:
        await redis_client.ping()
        logger.info("Conexin a Redis exitosa.")
    except Exception as e:
        logger.error(f"Error conectando a Redis: {e}")

    # 4. Iniciar Cliente MQTT de fondo
    start_mqtt_client()
    logger.info("Cliente MQTT de fondo iniciado.")

    yield  # La aplicacin se ejecuta aqu

    # Lgica de shutdown
    try:
        await redis_client.aclose()
        logger.info("Pool de conexiones de Redis cerrado correctamente.")
    except AttributeError:
         # Fallback por si la versin de redis no soporta aclose()
        await redis_client.close()
        logger.info("Pool de conexiones de Redis cerrado correctamente.")

    stop_mqtt_client()
    logger.info("Cliente MQTT cancelado.")

# Inicializar FastAPI con el lifespan context manager
app = FastAPI(title="Gossip Garden API", version="1.0.0", lifespan=lifespan)

# Configurar CORS para permitir la app móvil (Expo)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar el router de la v1
app.include_router(api_router, prefix="/api/v1")
