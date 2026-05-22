# AGENT_SKILLS.md — Gossip Garden

> Archivo de contexto unificado para agentes de IA (Claude Code, GitHub Copilot, Cursor).
> Contiene las skills técnicas reutilizables + arquitectura completa del sistema.
> Generado desde: BackendGossipGarden · LandingGossipGarden · FrontendGossipGarden

---

## 1. SISTEMA COMPLETO — VISIÓN GENERAL

**Gossip Garden** es una plataforma de monitoreo inteligente de plantas basada en IoT + IA.

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────────┐
│  Landing Page    │    │  App Flutter     │    │  Backend FastAPI     │
│  (React CDN)     │    │  Android + iOS   │    │  Railway             │
│  Marketing       │    │  Cliente móvil   │    │  backendgossipgarden │
└──────────────────┘    └────────┬─────────┘    └──────────┬───────────┘
                                 │ REST/JWT                 │
                                 └─────────────────────────►│
                                                            │
                              ┌─────────────────────────────┤
                              │  Supabase/PostgreSQL         │ relacional
                              │  Firebase Firestore/Storage  │ IoT + chat + fotos
                              │  Redis                       │ caché chat
                              │  pgvector (RAG)              │ embeddings botánicos
                              │  OpenAI GPT-4o               │ chat + identificación
                              │  Plant.id API                │ visión por computadora
                              │  GBIF API                    │ taxonomía
                              │  HiveMQ MQTT                 │ sensores ESP32
                              └─────────────────────────────┘
```

**Hardware**: ESP32 con DHT22 (temperatura/humedad), GY-30 (luz), SEN0193 (humedad suelo).
**Backend URL producción**: `https://backendgossipgarden-production.up.railway.app`

---

## 2. SKILL: Clientes de Base de Datos

### Configuración de entorno
```python
# app/core/config.py — SIEMPRE usar pydantic-settings, NUNCA os.getenv
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWKS_URL: str
    REDIS_URL: str
    OPENAI_API_KEY: str
    FIREBASE_STORAGE_BUCKET: str  # formato: project-id.appspot.com (sin gs://)
    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()
```

### Cliente Supabase (`app/db/supabase.py`)
```python
from supabase import create_client
from app.core.config import settings

supabase = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY  # SERVICE_ROLE_KEY, no anon key
)
```

### Cliente Firebase (`app/db/firebase.py`)
```python
import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:  # CRÍTICO: evita "App already exists"
    cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)

db = firestore.client()
```

### Cliente Redis (`app/db/redis.py`)
```python
import redis.asyncio as aioredis
from app.core.config import settings

redis_pool = aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)

async def get_redis_client():
    return redis_pool
```

---

## 3. SKILL: Autenticación JWT Asimétrica (Supabase)

```python
# app/core/security.py
import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

jwk_client = PyJWKClient(settings.SUPABASE_JWKS_URL)  # instancia GLOBAL
security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    token = credentials.credentials
    try:
        signing_key = jwk_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],   # ECC P-256 — NUNCA HS256
            audience="authenticated",
        )
        return payload["sub"]       # UUID del usuario
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido.")
```

**Regla**: Siempre verificar ownership: `if resource.user_id != user_id: raise HTTPException(403)`.

---

## 4. SKILL: FastAPI Scaffolding y Lifespan

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.redis import redis_pool
from app.api.v1.api import api_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    await redis_pool.ping()
    print("✓ Redis OK")
    yield
    # SHUTDOWN
    await redis_pool.aclose()

app = FastAPI(title="Gossip Garden API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # diseñado para clientes móviles Expo/Flutter
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")

@app.get("/health")
async def health():
    return {"status": "ok", "db_connected": True}
```

```python
# app/api/v1/api.py
from fastapi import APIRouter
from app.api.v1.endpoints import auth, plants, sensors, chat, identification

api_router = APIRouter()
api_router.include_router(auth.router,           prefix="/auth",    tags=["Auth"])
api_router.include_router(plants.router,         prefix="/plants",  tags=["Plants"])
api_router.include_router(sensors.router,        prefix="/sensors", tags=["Sensors"])
api_router.include_router(chat.router,           prefix="/chat",    tags=["Chat"])
api_router.include_router(identification.router, prefix="",         tags=["Identification"])
```

---

## 5. SKILL: Git Flow & Conventional Commits

### Ramas

| Tipo | Patrón | Ejemplo |
|------|--------|---------|
| Feature | `feat/*` | `feat/auth-google` |
| Fix | `fix/*` | `fix/health-score` |
| Bug | `bug/*` | `bug/session-expired` |
| Refactor | `refactor/*` | `refactor/chat-service` |
| Docs | `docs/*` | `docs/api-contract` |
| Test | `test/*` | `test/identification-pipeline` |
| Chore | `chore/*` | `chore/deps-update` |

### Flujo obligatorio
```
rama de trabajo → qa → main
```
**Regla crítica**: Ningún cambio llega directamente a `main`. Siempre `rama → qa → main`.

### Formato de commits
```
<type>(<scope>): <description>

feat(auth): add google oauth flow
fix(chat): prevent duplicate redis writes on compaction
refactor(identification): extract gbif lookup to service
```

### Regla de autoría para IA
**Nunca** incluir `co-authored by Claude`, `generated by AI` ni variantes en commits. Los commits reflejan únicamente el trabajo del equipo humano.

---

## 6. ARQUITECTURA BACKEND

### Estructura
```
app/
├── main.py                          — FastAPI, lifespan, CORS, routers
├── api/v1/endpoints/                — auth, plants, sensors, chat, identification
├── services/
│   ├── identification_pipeline.py   — orquestador: Plant.id → GBIF → RAG → GPT-4o
│   ├── rag_service.py               — pgvector retrieval (text-embedding-3-small 1536d)
│   ├── chat_service.py              — chat con personalidad + memoria dual
│   ├── summarizer_service.py        — compactación de contexto + guardrails
│   ├── health_service.py            — health score ponderado por especie
│   └── image_storage_service.py     — Pillow compress + Firebase Storage upload
├── schemas/                         — Pydantic v2 request/response models
├── db/                              — clientes supabase, firebase, redis
└── core/                            — config, security, mqtt
```

### Pipeline de Identificación
```
POST /api/v1/identify (imagen JPEG multipart)
  → Plant.id API (visión)
  ├── confianza < 25%  → needs_more_photos
  ├── confianza 25-75% → needs_user_selection (top 3 candidatos)
  └── confianza > 75%  → enrich_and_persist()
        ├── GBIF lookup (taxonomía por gbif_taxon_key)
        ├── Cache check (si especie ya existe → devolver cached=true)
        ├── RAG retrieval (pgvector match_botanical_chunks)
        ├── GPT-4o Structured Output (care profile + personalidad)
        ├── Validación (rangos físicos + pesos suman ≈ 1.0)
        └── Persistir → species, species_care_profiles, species_ai_content
```

### Chat con Personalidad (Memoria Dual)
```
POST /api/v1/chat/{plant_id}
  → Verificar ownership (Supabase)
  → Cargar historial Redis (TTL 2h) — fallback: Firestore
  → Cargar resumen Redis (TTL 7d)
  → Fetch paralelo: personalidad (Supabase) + sensores (Firestore)
  → > 3000 tokens → compactar (conservar últimos 6 mensajes)
  → System prompt = [personalidad] + [guardrails] + [estado sensores] + [resumen] + [historial]
  → GPT-4o chat completion
  → Persistir en Firestore + Redis
```

### Health Scoring
```python
# Ponderado por especie (weight_* en species_care_profiles)
health_score = Σ(weight_i × normalize(sensor_i, min_i, max_i)) × 100
# ≥ 80 → "healthy" | ≥ 50 → "warning" | < 50 → "critical"
# Los 4 weights suman ≈ 1.0 — null en fichas legacy (default 0.25 c/u)
```

### Esquema PostgreSQL (tablas clave)
- `species` — tarjeta taxonómica (scientific_name UNIQUE)
- `species_care_profiles` — rangos IoT + pesos ON DELETE CASCADE
- `species_ai_content` — personalidad LLM por idioma ON DELETE CASCADE
- `botanical_chunks` — embeddings vector(1536) para RAG (HNSW index)
- `plants` — instancia de especie por usuario (FK a species **sin** CASCADE)
- `sensors` — hardware ESP32 vinculado a planta
- `friendships` — relación social (user_low_id < user_high_id)

### Variables de entorno clave
```env
SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_JWKS_URL
REDIS_URL
OPENAI_API_KEY
OPENAI_MODEL=gpt-4o
OPENAI_CHAT_MODEL=gpt-4o
OPENAI_PERSONALITY_MODEL=gpt-5.5
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
FIREBASE_STORAGE_BUCKET=project-id.appspot.com
RAG_ENABLED=true, RAG_TOP_K=5, RAG_MIN_SIMILARITY=0.55
MQTT_ENABLED=false
```

### CI/CD
```yaml
# .github/workflows/ci.yml — 2 jobs paralelos en push/PR a main o qa
job: unit        → pytest -m "not dbschema" --cov=app  (mocks de externos)
job: db-schema   → postgres efímero pgvector:pg16
                   → aplica schema.sql desde cero
                   → aplica migrations.sql sobre schema legacy
package manager: uv | python: 3.12
```

---

## 7. ARQUITECTURA MOBILE (Flutter)

### Stack
- Flutter (Dart ≥3.0.0), Riverpod `^2.0.0`, HTTP `^1.2.2`
- Auth: Supabase JWT directo — **Firebase NO es intermediario de auth**
- `flutter_secure_storage ^9.2.2` — JWT guardado con clave `gg_jwt`
- `google_sign_in ^6.2.1` — account picker nativo Android

### Estructura Clean Architecture
```
lib/features/<feature>/{data,domain,presentation}
  data/       → models (DTOs), datasources (HTTP), repositories (impls)
  domain/     → interfaces, usecases
  presentation/ → screens, widgets, providers (Riverpod)
```

### Providers clave (Riverpod)
```dart
backendTokenProvider         → StateProvider<String?> — JWT disponible en toda la app
authProvider                 → AsyncNotifier<AuthSession?>
plantsProvider               → FutureProvider<List<Plant>>  GET /api/v1/plants/
plantRealtimeSensorProvider  → StreamProvider.family — polling 15s sensor-data/latest
navigationProvider           → StateProvider<int>  — tab activo (IndexedStack)
```

### Flujo de identificación (state machine)
```
CameraPreview → POST /api/v1/identify (multipart image/jpeg, ContentType EXPLÍCITO)
  needs_more_photos   → dialog + retry
  needs_user_selection → CandidateList → POST /api/v1/species/from-candidate
  completed           → ConfirmScreen → POST /api/v1/plants/
```

### ⚠️ Gotchas críticos
```dart
// 1. SIEMPRE ContentType explícito en Android (por defecto usa octet-stream)
MultipartFile.fromPath('image', path, contentType: MediaType('image', 'jpeg'))

// 2. GET /api/v1/species NO EXISTE — usar defaults hardcoded
// 3. Firebase SDK deshabilitado por defecto (ENABLE_FIREBASE=false)
// 4. Google Sign-In → intercambiar idToken directamente con Supabase, no con backend
```

### Build
```bash
flutter run --dart-define=BACKEND_TARGET=prod
flutter run --dart-define=BACKEND_TARGET=local --dart-define=BACKEND_LOCAL_URL=http://10.0.2.2:8000
flutter build apk --release --dart-define=BACKEND_TARGET=prod
```

---

## 8. DISEÑO — LANDING PAGE

### Estética: Crayon Storybook
Inspirada en Yoshi's Island + libros ilustrados para niños. **La imperfección es intencional.**

### Paleta de colores
```css
--cream:      #FAF1DA;  /* fondo principal */
--ink:        #3D2817;  /* bordes, texto, outlines — conector universal */
--pot:        #E8A95C;  /* botones neutros */
--leaf:       #8AC553;  /* CTA secundario */
--heart:      #E85D52;  /* CTA primario */
--cream-light:#FFF8E7;  /* interior tarjetas */

/* Personalidades */
--alegre:    #F4D06F;   /* girasol */
--dormilona: #B8C9E8;   /* suculenta */
--dramatica: #E0B8E0;   /* orquídea */
--exigente:  #A8C88A;   /* cactus */
```

### Reglas de diseño (OBLIGATORIAS)
1. **Nunca** usar valores hex hardcoded — siempre `PALETTE.*`
2. **Nunca** usar emoji — todos los iconos son SVG custom via `HandIcon`
3. Todo elemento con look dibujado a mano necesita `filter="url(#cr)"`
4. Sombras siempre `rgba(61,40,23,x)` — nunca negro puro
5. Easing siempre `cubic-bezier(.4,0,.2,1)`

### Tipografía
- **Quicksand** (700–900): headings
- **Nunito** (400–700): body
- **Caveat**: acento decorativo (uso limitado)
- Tamaños siempre con `clamp()` — nunca px fijos

### Filtros SVG (sistema de textura)
```
#cr         → geometric jitter (formas, SVG paths)
#cr-text    → fractal grain (texto logo, precios)
#crayon-fill → textura crayón en rellenos sólidos
```

### Stack técnico
- React 18 CDN + Babel in-browser — **sin build tools**
- Módulos globales via `window.ComponentName` (no ES modules)
- Versión activa: `crayon-v3.jsx` + `sections-v3.jsx`

---

## 9. API CONTRACT (resumen)

Base URL: `/api/v1` — todos los endpoints (excepto auth) requieren `Authorization: Bearer <jwt>`

| Endpoint | Método | Descripción |
|---|---|---|
| `/auth/register` | POST | Registro usuario |
| `/auth/login` | POST | Login → devuelve JWT |
| `/auth/google-url` | GET | URL OAuth Google |
| `/plants/` | GET | Lista plantas del usuario |
| `/plants/` | POST | Crear planta `{species_id, nickname, photo_storage_path}` |
| `/plants/{id}/sensor-data/latest` | GET | Último snapshot de sensores |
| `/plants/{id}/sensor-data/history` | GET | Histórico `?days=30` |
| `/plants/{id}/photo` | PUT | Actualizar foto (multipart) |
| `/identify` | POST | Identificar planta por foto (multipart) |
| `/species/from-candidate` | POST | Completar pipeline con candidato elegido |
| `/sensors/` | POST | Ingestar datos de sensor ESP32 |
| `/chat/{plant_id}` | POST | Enviar mensaje al chatbot de la planta |
| `/chat/{plant_id}/history` | GET | Historial de chat |
| `/health` | GET | Health check `{status: ok}` |

**Endpoint que NO existe**: `GET /api/v1/species` — no llamar desde el frontend.

---

## 10. REGLAS CROSS-REPO

| Regla | Descripción |
|---|---|
| No push directo a `main` | Siempre `rama → qa → main` |
| Firebase no es auth en Flutter | Supabase JWT directo — `google-services.json` solo para account picker |
| `GET /api/v1/species` no existe | Usar defaults hardcoded en Flutter hasta implementar |
| `plants → species` sin CASCADE | Intencional — preserva datos del usuario si se borra una especie |
| Todo texto al usuario en español | Frontend y mobile — strings en español |
| Sin emoji en landing | Solo SVG custom via HandIcon |
| Sin commits atribuidos a IA | Nunca `co-authored by Claude` ni similares |
| JWT en flutter_secure_storage | Nunca SharedPreferences — clave: `gg_jwt` |
