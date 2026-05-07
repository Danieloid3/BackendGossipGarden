# SKILL: Generación de Clientes de Base de Datos

## Objetivo
Implementar los clientes de conexión en el directorio `app/db/` de forma robusta, asegurando que las conexiones se reutilicen eficientemente.

## Reglas de Implementación
1. **Validación de Entorno:** Usa `pydantic-settings` (`BaseSettings`) en `app/core/config.py` para cargar y tipar las variables del archivo `.env` (`SUPABASE_URL`, `FIREBASE_CREDENTIALS_PATH`, etc.). No uses `os.getenv` directamente en los clientes.
2. **Cliente Supabase (`app/db/supabase.py`):**
   - Importa `create_client` de `supabase`.
   - Inicializa el cliente usando la `SUPABASE_SERVICE_ROLE_KEY` (no la anon key, para tener permisos de backend).
   - Exporta la instancia del cliente para ser usada en los servicios.
3. **Cliente Firebase (`app/db/firebase.py`):**
   - Usa `firebase_admin.credentials.Certificate` apuntando al JSON de credenciales.
   - **Crucial:** Maneja el error de "App already exists" comprobando `if not firebase_admin._apps:` antes de llamar a `initialize_app()`.
   - Obtén el cliente llamando a `firestore.client()` y expórtalo.
4. **Cliente Redis (`app/db/redis.py`):**
   - Usa `redis.asyncio` para crear un pool de conexiones asíncrono usando `from_url(settings.REDIS_URL)`.
   - Implementa una función `get_redis_client()` para inyectar la dependencia en FastAPI.