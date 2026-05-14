# Gossip Garden - API Contract

Este documento describe todos los endpoints actualmente disponibles en la API de Gossip Garden, incluyendo ejemplos de los cuerpos de las peticiones (Body) y las respuestas que generan.

**URL Base:** `/api/v1`

Todos los endpoints (excepto auth) requieren:
```
Authorization: Bearer <access_token>
```

---

## 🔐 1. Auth (Autenticación)

### 1.1 `POST /auth/register`

**Request Body (JSON):**
```json
{
  "email": "nuevo.usuario@ejemplo.com",
  "password": "mypassword123",
  "username": "GossipGardener"
}
```

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Usuario registrado exitosamente. Revisa tu correo si tienes confirmación activada.",
  "user_id": "UUID-DEL-NUEVO-USUARIO"
}
```

### 1.2 `POST /auth/login`

**Request Body (JSON):**
```json
{
  "email": "nuevo.usuario@ejemplo.com",
  "password": "mypassword123"
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer"
}
```

### 1.3 `GET /auth/google-url`

**Response (200 OK):**
```json
{
  "status": "success",
  "url": "https://<proyecto>.supabase.co/auth/v1/authorize?provider=google&redirect_to=..."
}
```

---

## 🌿 2. Plants (Plantas)

### 2.1 `POST /plants/`

**Request Body (JSON):**
```json
{
  "species_id": "4b6e50ed-3088-4f81-8d2a-4ce1f6e2bdee",
  "nickname": "Mi Rosal",
  "photo_storage_path": "plant_identifications/.../foto.jpeg"
}
```

> `photo_storage_path` es opcional. Si viene de `/identify`, usar el valor `photo_storage_path` devuelto en esa respuesta.

**Response (200 OK):**
```json
{
  "plant_id": "8e3fbfe9-2b4a-43c2-a4fa-1a234f2d5eab",
  "user_id": "UUID-DEL-USUARIO",
  "species_id": "4b6e50ed-3088-4f81-8d2a-4ce1f6e2bdee",
  "nickname": "Mi Rosal",
  "health_status": "healthy",
  "health_score": 100.0,
  "photo_storage_path": null,
  "created_at": "2024-05-11T12:00:00Z",
  "last_health_check": null
}
```

### 2.2 `GET /plants/`

**Query params opcionales:** `?target_user_id=UUID` (plantas de un amigo verificado)

**Response (200 OK):**
```json
[
  {
    "plant_id": "8e3fbfe9-2b4a-43c2-a4fa-1a234f2d5eab",
    "user_id": "UUID-DEL-USUARIO",
    "species_id": "4b6e50ed-3088-4f81-8d2a-4ce1f6e2bdee",
    "nickname": "Mi Rosal",
    "health_status": "healthy",
    "health_score": 100.0,
    "photo_storage_path": "plant_identifications/.../foto.jpeg",
    "created_at": "2024-05-11T12:00:00Z",
    "last_health_check": null
  }
]
```

### 2.3 `GET /plants/{plant_id}/sensor-data/latest`

**Response (200 OK):**
```json
{
  "id": "1m2k3j1j3k2j1k2",
  "sensor_id": "sensor_001",
  "mac_address": "00:1B:44:11:3A:B7",
  "plant_id": "8e3fbfe9-2b4a-43c2-a4fa-1a234f2d5eab",
  "temperature_c": 22.5,
  "humidity_pct": 55.2,
  "soil_moisture_pct": 45.0,
  "light_lux": 850.0,
  "timestamp": "2024-05-11T10:30:15.123Z"
}
```

### 2.4 `GET /plants/{plant_id}/sensor-data/history`

**Query params opcionales:** `?days=30`

**Response (200 OK):** array de objetos con el mismo schema que `/latest`.

### 2.5 `PUT /plants/{plant_id}/photo`

Sube o reemplaza la foto de una planta ya registrada (sin necesidad de re-identificar).

**Request:** `multipart/form-data`
- `image`: archivo JPEG/PNG/WebP (máx 8 MB)

**Response (200 OK):**
```json
{
  "plant_id": "8e3fbfe9-...",
  "photo_storage_path": "plant_photos/be4a19f3-.../20260514T185414.jpeg"
}
```

---

## 🔬 3. Identificación de Plantas

El flujo completo es: `POST /identify` → si `status=needs_user_selection`, el usuario elige → `POST /species/from-candidate` → se crea la planta con el `species_id` devuelto.

### 3.1 `POST /identify`

Identifica la planta en una foto. La imagen se comprime y sube a Firebase Storage en background.

**Request:** `multipart/form-data`
- `image`: archivo JPEG/PNG/WebP (máx 8 MB)
- `output_language` (form field, opcional, default `"es"`): idioma de la ficha — `es | en | fr | pt | de | it`
- `latitude` (opcional): float
- `longitude` (opcional): float

**Respuestas posibles (discriminadas por `status`):**

#### `status: "needs_more_photos"` — confianza < 25%
```json
{
  "status": "needs_more_photos",
  "reason": "Confianza demasiado baja para identificar la planta",
  "top_probability": 0.18
}
```

#### `status: "needs_user_selection"` — confianza 25–75%
```json
{
  "status": "needs_user_selection",
  "candidates": [
    {
      "scientific_name": "Monstera deliciosa",
      "common_names": ["Costilla de Adán"],
      "probability": 0.62,
      "gbif_id": 2684241,
      "inaturalist_id": 119838,
      "taxonomy": { "family": "Araceae", "genus": "Monstera" },
      "description": "Planta tropical con hojas perforadas..."
    }
  ]
}
```
> Devuelve hasta 3 candidatos ordenados por probabilidad. Usar `POST /species/from-candidate` con el elegido.

#### `status: "completed"` — confianza > 75%
```json
{
  "status": "completed",
  "photo_storage_path": "plant_identifications/USER_ID/20260514T185414_Monstera_deliciosa_abc123.jpeg",
  "profile": {
    "species_id": "031d4b38-d045-4297-a3e6-f5d311231921",
    "scientific_name": "Dracaena trifasciata",
    "common_name": "Lengua de suegra",
    "family": "Asparagaceae",
    "care_ranges": {
      "min_temp_c": 15.0,
      "max_temp_c": 30.0,
      "min_light_lux": 5000.0,
      "max_light_lux": 10000.0,
      "min_air_humidity_pct": 30.0,
      "max_air_humidity_pct": 50.0,
      "min_soil_humidity_pct": 20.0,
      "max_soil_humidity_pct": 40.0
    },
    "care_weights": {
      "light": 0.40,
      "soil_humidity": 0.35,
      "air_humidity": 0.05,
      "temperature": 0.20
    },
    "sensitivity_assessment": {
      "light": "high",
      "soil_humidity": "high",
      "air_humidity": "low",
      "temperature": "medium"
    },
    "care_summary": "La lengua de suegra es una planta resistente...",
    "ai_personality_prompt": "Soy una Dracaena trifasciata...",
    "care_tips": ["Riega solo cuando el suelo esté seco.", "..."],
    "fun_facts": ["Purifica el aire eliminando formaldehído.", "..."],
    "faq": [
      { "question": "¿Con qué frecuencia regarla?", "answer": "Cada 2-3 semanas." }
    ],
    "proposal_confidence": "high",
    "needs_review": false,
    "language": "es",
    "cached": false,
    "created_at": "2026-05-14T18:54:14Z"
  }
}
```

> **Nota `care_weights` y `sensitivity_assessment`:** disponibles en fichas generadas tras la migración `003_care_weights.sql`. Para fichas legacy (pre-migración) o cacheadas sin pesos, estos campos son `null`. La suma de los cuatro pesos es siempre ≈ 1.0.
>
> **Nota `cached`:** si la especie ya existía en BD, devuelve `true` y no se vuelve a llamar al LLM.
>
> **Nota `photo_storage_path`:** path en Firebase Storage. Pasarlo a `POST /plants/` al crear la planta.

### 3.2 `POST /species/from-candidate`

Completa el pipeline para un candidato elegido por el usuario (flujo `needs_user_selection`).

**Request Body (JSON):**
```json
{
  "candidate": {
    "scientific_name": "Monstera deliciosa",
    "common_names": ["Costilla de Adán"],
    "probability": 0.62,
    "gbif_id": 2684241,
    "inaturalist_id": 119838,
    "taxonomy": { "family": "Araceae" }
  },
  "output_language": "es"
}
```

**Response (200 OK):** mismo schema que `status: "completed"` de `/identify` (sin `photo_storage_path` en este caso).

---

## 📡 4. Sensors / IoT (Sensores)

### 4.1 `POST /sensors/`

Ingesta datos de un sensor (usado por hardware ESP32 o bridges).

**Request Body (JSON):**
```json
{
  "sensor_id": "sensor_001",
  "mac_address": "00:1B:44:11:3A:B7",
  "plant_id": "8e3fbfe9-2b4a-43c2-a4fa-1a234f2d5eab",
  "temperature_c": 22.5,
  "humidity_pct": 55.2,
  "soil_moisture_pct": 45.0,
  "light_lux": 850.0
}
```

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Datos ingeridos correctamente.",
  "doc_id": "ID-DEL-DOCUMENTO-EN-FIREBASE"
}
```

---

## ❤️ 5. Core

### 5.1 `GET /health`

**Response (200 OK):**
```json
{
  "status": "ok",
  "db_connected": true
}
```

---

## 📊 Referencia: campos de `care_weights` y `sensitivity_assessment`

Introducidos en la migración `003_care_weights.sql`. Expresan la **criticidad relativa** de cada dimensión de monitoreo para la especie.

| Dimensión | Campo en `care_weights` | Campo en `sensitivity_assessment` |
|---|---|---|
| Luz | `light` (float 0–1) | `light` (`"high"` \| `"medium"` \| `"low"`) |
| Humedad suelo | `soil_humidity` (float 0–1) | `soil_humidity` |
| Humedad aire | `air_humidity` (float 0–1) | `air_humidity` |
| Temperatura | `temperature` (float 0–1) | `temperature` |

Reglas:
- La suma de los 4 valores de `care_weights` es siempre ≈ 1.0.
- Un `care_weights.light = 0.40` significa que la luz es la variable más crítica para esa especie.
- `sensitivity_assessment` es el nivel cualitativo del que se derivan los pesos.
- Ambos campos son `null` para fichas generadas antes de la migración.
