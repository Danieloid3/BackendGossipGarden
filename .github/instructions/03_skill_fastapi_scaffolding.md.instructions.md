# SKILL: FastAPI Scaffolding y Lifespan

## Objetivo
Generar la estructura principal de la aplicación en `app/main.py` y configurar el enrutamiento.

## Reglas de Implementación
1. **Lifespan Context Manager:**
   - Utiliza el decorador `@asynccontextmanager` para gestionar el ciclo de vida de la aplicación.
   - En el `startup` (antes del `yield`), haz un log indicando que los clientes de Supabase y Firebase están listos, y ejecuta `await redis_client.ping()` para asegurar que Redis está vivo.
   - En el `shutdown` (después del `yield`), cierra ordenadamente el pool de conexiones de Redis.
2. **Instancia de FastAPI:**
   - Crea `app = FastAPI(title="Gossip Garden API", lifespan=lifespan)`.
3. **CORS Middleware:**
   - Añade `CORSMiddleware` permitiendo todos los orígenes (`allow_origins=["*"]`), credenciales, métodos y headers (listo para la app de Expo).
4. **Estructura de Routers:**
   - Crea un router global `api_router = APIRouter()` en `app/api/v1/api.py`.
   - En `main.py`, incluye el router bajo el prefijo `/api/v1`: `app.include_router(api_router, prefix="/api/v1")`.
   - Crea un endpoint básico `@app.get("/health")` que retorne `{"status": "ok", "db_connected": True}`.