# Gossip Garden — API Contract

Este documento describe **todos** los endpoints actualmente disponibles en la API de Gossip Garden, incluyendo cuerpos de petición, respuestas y errores posibles. Está sincronizado con el código fuente del backend (schemas Pydantic + routers FastAPI).

**URL Base:** `/api/v1`

Todos los endpoints (excepto `/auth/*`, `POST /sensors/` y `GET /api/v1/health`) requieren:
```
Authorization: Bearer <access_token>
```

---

## Índice

1. [Auth](#1-auth)
2. [Users (Perfil)](#2-users-perfil)
3. [Plants](#3-plants)
4. [Identificación de Plantas](#4-identificación-de-plantas)
5. [Sensors / IoT](#5-sensors--iot)
6. [Core](#6-core)
7. [Chat](#7-chat)
8. [Notifications](#8-notifications)
9. [Devices (Push Tokens)](#9-devices-push-tokens)
10. [Referencia de campos derivados](#10-referencia-de-campos-derivados)
11. [Vacíos conceptuales detectados](#11-vacíos-conceptuales-detectados)

---

## 1. Auth

### 1.1 `POST /auth/register`

Registra un nuevo usuario en Supabase Auth.

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
  "user_id": "uuid-del-nuevo-usuario"
}
```

**Errores:**
| Status | Motivo |
|---|---|
| `400 Bad Request` | Email ya registrado, contraseña inválida u otro error de Supabase Auth |

---

### 1.2 `POST /auth/login`

Inicia sesión con email y contraseña. Devuelve un JWT de Supabase para usar en `Authorization: Bearer`.

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

**Errores:**
| Status | Motivo |
|---|---|
| `400 Bad Request` | Credenciales inválidas o error de Supabase Auth |

---

### 1.3 `GET /auth/google-url`

Genera la URL de OAuth de Google para redirigir al usuario.

**Query params opcionales:**
| Param | Tipo | Default | Descripción |
|---|---|---|---|
| `redirect_to` | `string` | `http://localhost:3000/auth/callback` | URL a la que Supabase redirige tras el login |

**Response (200 OK):**
```json
{
  "status": "success",
  "url": "https://<proyecto>.supabase.co/auth/v1/authorize?provider=google&redirect_to=..."
}
```

**Errores:**
| Status | Motivo |
|---|---|
| `500 Internal Server Error` | Error obteniendo la URL de Google Auth |

---

---

## 2. Users (Perfil)

### 2.1 `GET /users/me`

Devuelve el perfil del usuario autenticado.

**Response (200 OK):**
```json
{
  "user_id": "uuid-del-usuario",
  "username": "GossipGardener",
  "email": "usuario@ejemplo.com",
  "preferred_language": "es",
  "created_at": "2024-05-11T12:00:00Z"
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `user_id` | `UUID` | Solo lectura |
| `username` | `string` | Nombre de usuario visible en la app |
| `email` | `string\|null` | Solo lectura — proviene de Supabase Auth |
| `preferred_language` | `string` | Idioma preferido para IA y alertas (`es`, `en`, `fr`, `pt`, `de`, `it`) |
| `created_at` | `datetime` | Solo lectura |

**Errores:**
| Status | Motivo |
|---|---|
| `404 Not Found` | Usuario no encontrado en la tabla `users` |

---

### 2.2 `PATCH /users/me`

Actualiza los campos editables del perfil. Enviar solo los que cambian.

**Request Body (JSON):**
```json
{
  "username": "NuevoNombre",
  "preferred_language": "en"
}
```

| Campo | Tipo | Requerido | Validaciones | Descripción |
|---|---|---|---|---|
| `username` | `string\|null` | ❌ | 1–50 chars | Nuevo nombre de usuario |
| `preferred_language` | `string\|null` | ❌ | `es\|en\|fr\|pt\|de\|it` | Nuevo idioma preferido |

> `preferred_language` afecta: las fichas de `/identify`, los tips de `/personalized-care` y los mensajes proactivos del evaluador de sensores.

**Response (200 OK):** → `UserResponse` (mismo schema que `GET /users/me`) con los campos actualizados.

**Errores:**
| Status | Motivo |
|---|---|
| `400 Bad Request` | No se enviaron campos para actualizar |
| `404 Not Found` | Usuario no encontrado |

---

## 3. Plants

### 2.1 `POST /plants/`

Registra una nueva planta para el usuario autenticado.

**Request Body (JSON):**
```json
{
  "species_id": "4b6e50ed-3088-4f81-8d2a-4ce1f6e2bdee",
  "nickname": "Mi Rosal",
  "photo_storage_path": "plant_identifications/USER_ID/20260514T185414_Rosa_gallica_abc123.jpeg",
  "estimated_age_months": 6,
  "location": "Sala"
}
```

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `species_id` | `UUID` | ✅ | UUID de la especie en la tabla `species` |
| `nickname` | `string` | ✅ | Apodo de la planta |
| `photo_storage_path` | `string\|null` | ❌ | Path en Firebase Storage devuelto por `/identify` |
| `estimated_age_months` | `int\|null` | ❌ | Edad estimada al momento de adopción (meses) |
| `location` | `string\|null` | ❌ | Ubicación en casa (ej. `"Sala"`, `"Balcón"`) |

**Response (200 OK):** → `PlantResponse` (ver sección 9)

```json
{
  "plant_id": "8e3fbfe9-2b4a-43c2-a4fa-1a234f2d5eab",
  "user_id": "uuid-del-usuario",
  "species_id": "4b6e50ed-3088-4f81-8d2a-4ce1f6e2bdee",
  "nickname": "Mi Rosal",
  "health_status": "healthy",
  "health_score": 100.0,
  "photo_storage_path": null,
  "photo_url": null,
  "common_name": "Rosa",
  "scientific_name": "Rosa gallica",
  "created_at": "2024-05-11T12:00:00Z",
  "last_health_check": null,
  "last_watered": null,
  "estimated_age_months": 6,
  "location": "Sala",
  "specific_care_tips": null
}
```

> El vínculo sensor↔planta se gestiona a través de la tabla `sensors` (columna `plant_id`). No se almacena `mac_address` en la tabla `plants`.

---

### 3.2 `GET /plants/`

Devuelve la lista de plantas del usuario autenticado (o de un amigo verificado).

**Query params opcionales:**
| Param | Tipo | Descripción |
|---|---|---|
| `target_user_id` | `UUID` | Si se provee, devuelve las plantas de ese usuario. Requiere amistad aceptada. |

**Response (200 OK):** Array de `PlantResponse`

**Errores:**
| Status | Motivo |
|---|---|
| `403 Forbidden` | `target_user_id` existe pero no hay amistad aceptada |

---

### 2.3 `PATCH /plants/{plant_id}`

Actualiza campos editables de una planta. Solo el propietario puede editarla. Enviar únicamente los campos que cambian.

**Request Body (JSON):**
```json
{
  "nickname": "Rosal del Balcón",
  "location": "Balcón"
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `nickname` | `string\|null` | Nuevo apodo |
| `location` | `string\|null` | Nueva ubicación en casa |

**Response (200 OK):** → `PlantResponse` actualizado.

**Errores:**
| Status | Motivo |
|---|---|
| `400 Bad Request` | No se enviaron campos para actualizar |
| `404 Not Found` | Planta no encontrada o no pertenece al usuario |

---

### 2.4 `POST /plants/{plant_id}/actions`

Registra una acción manual del usuario sobre la planta (regar, fertilizar, etc.). Actualiza `last_watered` y puede ajustar el `health_score`.

**Request Body (JSON):**
```json
{
  "action_type": "water"
}
```

| `action_type` | Efecto |
|---|---|
| `"water"` | Actualiza `last_watered`, sube `health_score` en +10 (máx 100) |
| Cualquier otro | Solo actualiza `last_health_check` |

**Response (200 OK):** → `PlantResponse` actualizado.

**Errores:**
| Status | Motivo |
|---|---|
| `404 Not Found` | Planta no encontrada o no pertenece al usuario |

---

### 2.5 `GET /plants/{plant_id}/profile`

Devuelve el perfil enriquecido de una planta: datos base + información de especie (personalidad, tips, rangos de cuidado). Accesible por el propietario o por amigos verificados.

**Response (200 OK):** → `PlantProfileResponse` (ver sección 9)

```json
{
  "plant_id": "8e3fbfe9-...",
  "user_id": "uuid-del-usuario",
  "species_id": "4b6e50ed-...",
  "nickname": "Mi Rosal",
  "health_status": "healthy",
  "health_score": 100.0,
  "photo_storage_path": null,
  "photo_url": null,
  "common_name": "Rosa",
  "scientific_name": "Rosa gallica",
  "created_at": "2024-05-11T12:00:00Z",
  "last_health_check": null,
  "last_watered": null,
  "estimated_age_months": 6,
  "location": "Sala",
  "specific_care_tips": null,
  "species_info": {
    "care_summary": "La rosa es una planta que requiere...",
    "ai_personality_prompt": "Soy una Rosa gallica...",
    "personality_traits": ["Apasionada", "Exigente", "Fragante"],
    "personality_description": "Eres apasionada y dramática, pero de belleza inigualable.",
    "care_tips": ["Riega profundamente 2x por semana.", "Poda ramas secas para estimular el florecimiento."],
    "fun_facts": ["Las rosas tienen más de 100 millones de años de historia.", "..."],
    "care_ranges": {
      "min_temp_c": 10,
      "max_temp_c": 28,
      "min_light_lux": 20000,
      "max_light_lux": 50000,
      "min_air_humidity_pct": 40,
      "max_air_humidity_pct": 70,
      "min_soil_humidity_pct": 30,
      "max_soil_humidity_pct": 60
    }
  }
}
```

**Errores:**
| Status | Motivo |
|---|---|
| `403 Forbidden` | La planta existe pero no pertenece al usuario ni hay amistad |
| `404 Not Found` | Planta no encontrada |

---

### 2.6 `GET /plants/{plant_id}/sensor-data/latest`

Devuelve la lectura de sensor más reciente de una planta desde Firebase.

**Response (200 OK):** → `SensorDataResponse` (ver sección 9)

```json
{
  "id": "firebase-doc-id",
  "sensor_id": "sensor_001",
  "mac_address": "00:1B:44:11:3A:B7",
  "plant_id": "8e3fbfe9-2b4a-43c2-a4fa-1a234f2d5eab",
  "temperature_c": 22.5,
  "humidity_pct": 55.2,
  "soil_moisture_pct": 45.0,
  "light_lux": 850.0,
  "health_score": 98.5,
  "health_status": "healthy",
  "timestamp": "2024-05-11T10:30:15.123Z"
}
```

**Errores:**
| Status | Motivo |
|---|---|
| `403 Forbidden` | La planta existe pero no pertenece al usuario ni hay amistad |
| `404 Not Found` | Planta no encontrada, o no hay lecturas de sensor registradas |

---

### 2.7 `GET /plants/{plant_id}/sensor-data/history`

Devuelve el historial de lecturas de sensor de una planta desde Firebase.

**Query params opcionales:**
| Param | Tipo | Default | Descripción |
|---|---|---|---|
| `days` | `int` | `30` | Número de días hacia atrás a consultar |

**Response (200 OK):** Array de `SensorDataResponse`, ordenado por timestamp descendente.

**Errores:**
| Status | Motivo |
|---|---|
| `403 Forbidden` | La planta existe pero no pertenece al usuario ni hay amistad |
| `404 Not Found` | Planta no encontrada |

---

### 2.8 `PUT /plants/{plant_id}/photo`

Sube o reemplaza la foto de una planta ya registrada (sin re-identificarla). Comprime la imagen (máx 1920px, JPEG q=85) antes de subirla a Firebase Storage.

**Request:** `multipart/form-data`
| Campo | Tipo | Descripción |
|---|---|---|
| `image` | `File` | Foto JPEG/PNG/WebP, máx 8 MB |

**Response (200 OK):** → `PlantResponse` con `photo_storage_path` y `photo_url` actualizados.

```json
{
  "plant_id": "8e3fbfe9-...",
  "photo_storage_path": "plant_photos/USER_ID/PLANT_ID/20260514T185414.jpeg",
  "photo_url": "https://firebasestorage.googleapis.com/v0/b/project.appspot.com/o/plant_photos%2F...?alt=media",
  "...": "resto de campos PlantResponse"
}
```

**Errores:**
| Status | Motivo |
|---|---|
| `404 Not Found` | Planta no encontrada o no pertenece al usuario |
| `413 Payload Too Large` | Imagen supera 8 MB |
| `415 Unsupported Media Type` | Formato no soportado (solo JPEG/PNG/WebP) |
| `503 Service Unavailable` | Error subiendo a Firebase Storage |

---

### 2.9 `POST /plants/{plant_id}/personalized-care`

Genera consejos de cuidado hiper-personalizados adaptados a la ciudad y la ubicación de la planta. Usa `gpt-4o-mini`. Requiere que la planta tenga `location` configurado.

**Request Body (JSON):**
```json
{
  "city": "Bogotá",
  "language": "es"
}
```

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `city` | `string` | ✅ | Ciudad o región para adaptar al clima local |
| `language` | `string\|null` | ❌ | Idioma de los consejos (`es`, `en`, `fr`, `pt`, `de`, `it`). Si no se provee, usa `preferred_language` del usuario o `"es"` |

**Response (200 OK):** → `PlantResponse` con `specific_care_tips` populado.

**Errores:**
| Status | Motivo |
|---|---|
| `400 Bad Request` | La planta no tiene `location` configurada |
| `404 Not Found` | Planta no encontrada o no pertenece al usuario |
| `500 Internal Server Error` | Error generando los tips con OpenAI |

---

### 2.10 `DELETE /plants/{plant_id}`

Elimina una planta del usuario autenticado.

**Response (204 No Content):** Sin cuerpo.

**Errores:**
| Status | Motivo |
|---|---|
| `403 Forbidden` | La planta existe pero pertenece a otro usuario |
| `404 Not Found` | No existe ninguna planta con ese `plant_id` |
| `500 Internal Server Error` | Error ejecutando el DELETE en Supabase |

---

## 4. Identificación de Plantas

El flujo completo de identificación es:

```
POST /identify
   |
   |-- status: "needs_more_photos"  --> Pedir otra foto al usuario
   |
   |-- status: "needs_user_selection"  --> El usuario elige de la lista de candidatos
   |          |
   |          '--> POST /species/from-candidate  --> Obtiene species_id
   |
   '--> status: "completed"  --> Ya tiene species_id en profile
              |
              '--> POST /plants/  --> Crear planta con species_id y photo_storage_path
```

---

### 3.1 `POST /identify`

Identifica la planta en una foto. La imagen se comprime y sube a Firebase Storage en background (sin latencia extra para el cliente).

El idioma de salida se determina así: si el usuario tiene `preferred_language` en su perfil, se usa ese; si no, el valor del campo `output_language`; por defecto `"es"`.

**Request:** `multipart/form-data`
| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `image` | `File` | ✅ | Foto JPEG/PNG/WebP, máx 8 MB |
| `output_language` | `string` | ❌ | Idioma de la ficha: `es\|en\|fr\|pt\|de\|it` (default `"es"`) |
| `latitude` | `float` | ❌ | Latitud GPS para contexto geográfico |
| `longitude` | `float` | ❌ | Longitud GPS para contexto geográfico |

**Respuestas discriminadas por `status`:**

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
  "photo_storage_path": "plant_identifications/USER_ID/20260514T185414_Monstera_deliciosa_abc123.jpeg",
  "candidates": [
    {
      "scientific_name": "Monstera deliciosa",
      "common_names": ["Costilla de Adán"],
      "probability": 0.62,
      "gbif_id": 2684241,
      "inaturalist_id": 119838,
      "taxonomy": { "family": "Araceae", "genus": "Monstera" },
      "watering": { "min": 7, "max": 14 },
      "description": "Planta tropical con hojas perforadas...",
      "image_url": "https://...",
      "reference_images": ["https://..."]
    }
  ]
}
```

> Devuelve hasta 3 candidatos ordenados por probabilidad. Pasar el elegido a `POST /species/from-candidate`.
> `photo_storage_path`: path en Firebase Storage. Pasarlo a `POST /plants/` al crear la planta.

#### `status: "completed"` — confianza > 75%
```json
{
  "status": "completed",
  "photo_storage_path": "plant_identifications/USER_ID/20260514T185414_Dracaena_trifasciata_abc123.jpeg",
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
    "eval_intervals": {
      "temperature": 120,
      "light": 60,
      "air_humidity": 480,
      "soil_humidity": 1440
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

> **`care_weights` y `sensitivity_assessment`:** `null` para fichas legacy previas a la migración `003_care_weights.sql`. La suma de los cuatro pesos siempre ≈ 1.0.
>
> **`eval_intervals`:** `null` para fichas legacy previas a la migración `005`. Indican cada cuántos minutos evaluar cada parámetro. Mínimo 30.
>
> **`cached`:** `true` si la especie ya existía en BD y no se volvió a llamar al LLM.

**Errores:**
| Status | Motivo |
|---|---|
| `413 Payload Too Large` | Imagen supera 8 MB |
| `415 Unsupported Media Type` | Formato no soportado (solo JPEG/PNG/WebP) |

---

### 3.2 `POST /species/from-candidate`

Completa el pipeline de identificación para un candidato elegido por el usuario (flujo `needs_user_selection`). Es idempotente: si la especie ya existe con el contenido en el idioma solicitado, devuelve la ficha cacheada.

El idioma de salida se resuelve igual que en `/identify` (preferencia del usuario → `output_language` → `"es"`).

**Request Body (JSON):**
```json
{
  "candidate": {
    "scientific_name": "Monstera deliciosa",
    "common_names": ["Costilla de Adán"],
    "probability": 0.62,
    "gbif_id": 2684241,
    "inaturalist_id": 119838,
    "taxonomy": { "family": "Araceae", "genus": "Monstera" }
  },
  "output_language": "es"
}
```

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `candidate` | `PlantIdCandidate` | ✅ | Candidato elegido por el usuario |
| `output_language` | `string` | ❌ | Idioma: `es\|en\|fr\|pt\|de\|it` (default `"es"`) |

**Response (200 OK):** Mismo schema que `status: "completed"` de `/identify`, **sin** `photo_storage_path`.

---

### 3.3 `GET /species/search`

Busca especies por nombre común o científico. Primero busca en la BD local; si hay menos de 3 resultados, hace fallback a GBIF.

**Query params:**
| Param | Tipo | Requerido | Descripción |
|---|---|---|---|
| `q` | `string` | ✅ | Término de búsqueda (nombre común o científico) |

**Response (200 OK):** Array de `PlantIdCandidate` (máx 10 + 1 de GBIF fallback)

```json
[
  {
    "scientific_name": "Monstera deliciosa",
    "common_names": ["Costilla de Adán", "Swiss Cheese Plant"],
    "probability": 1.0,
    "gbif_id": 2684241,
    "inaturalist_id": 119838,
    "taxonomy": {},
    "watering": null,
    "description": null,
    "image_url": null,
    "reference_images": []
  }
]
```

---

## 5. Sensors / IoT

### 4.1 `POST /sensors/`

Ingesta datos de un sensor IoT (ESP32 o bridge MQTT). Recalcula `health_score` y `health_status` en tiempo real comparando con los rangos óptimos de la especie, y persiste los datos en Firebase Firestore.

> **IMPORTANTE — Sin autenticación JWT.** Diseñado para hardware IoT. En producción, proteger con API key en header, validación de `mac_address` contra lista blanca, o IP whitelist del broker MQTT.

**Side effects:**
- Guarda lectura en Firebase (`plants/{plant_id}/sensor_readings`)
- Recalcula y actualiza `health_score` + `health_status` + `last_health_check` en Supabase (`plants`)
- Los datos expiran automáticamente en Firebase a los 30 días (`expireAt`)

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

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `plant_id` | `UUID` | ✅ | UUID de la planta en Supabase |
| `temperature_c` | `float` | ✅ | Temperatura en °C |
| `humidity_pct` | `float` | ✅ | Humedad relativa del aire (%) |
| `soil_moisture_pct` | `float` | ✅ | Humedad del suelo (%) |
| `light_lux` | `float` | ✅ | Intensidad lumínica en Lux |
| `sensor_id` | `string\|null` | ❌ | Identificador del sensor |
| `mac_address` | `string\|null` | ❌ | MAC Address del ESP32 |

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Datos ingeridos correctamente.",
  "doc_id": "firebase-doc-id-generado"
}
```

**Errores:**
| Status | Motivo |
|---|---|
| `500 Internal Server Error` | Error interno guardando la lectura |

---

## 6. Core

### 5.1 `GET /health`

Endpoint de liveness check. No requiere autenticación.

**Response (200 OK):**
```json
{
  "status": "ok",
  "db_connected": true
}
```

---

## 7. Chat

### 6.1 `POST /chat/{plant_id}`

Envía un mensaje al chatbot de la planta y recibe su respuesta con personalidad.

**Request Body (JSON):**
```json
{
  "message": "¿Cuánta agua necesito?",
  "language": "es",
  "response_format": "text"
}
```

| Campo | Tipo | Requerido | Validaciones | Descripción |
|---|---|---|---|---|
| `message` | `string` | ✅ | 1–2000 chars | Mensaje del usuario |
| `language` | `string` | ❌ | `es\|en\|fr\|pt\|de\|it` | Idioma de respuesta (default `"es"`) |
| `response_format` | `"text"\|"audio"` | ❌ | — | Formato de respuesta (default `"text"`) |

**Response (200 OK):**
```json
{
  "reply": "Necesito que me riegues cuando el suelo esté seco...",
  "plant_id": "8e3fbfe9-2b4a-43c2-a4fa-1a234f2d5eab",
  "timestamp": "2026-05-14T18:54:14Z",
  "audio_url": null
}
```

> `audio_url`: URL de audio en Firebase Storage. Solo presente si `response_format="audio"` y `ELEVENLABS_API_KEY` está configurado; `null` en caso contrario.

**Errores:**
| Status | Motivo |
|---|---|
| `403 Forbidden` | La planta no pertenece al usuario |
| `404 Not Found` | Planta no encontrada |

---

### 6.2 `GET /chat/{plant_id}/history`

Devuelve el historial de conversación con la planta, ordenado cronológicamente.

**Query params opcionales:**
| Param | Tipo | Default | Descripción |
|---|---|---|---|
| `limit` | `int` | `50` | Número máximo de mensajes a devolver |

**Response (200 OK):**
```json
{
  "plant_id": "8e3fbfe9-2b4a-43c2-a4fa-1a234f2d5eab",
  "messages": [
    {
      "role": "user",
      "content": "¿Cuánta agua necesito?",
      "timestamp": "2026-05-14T18:54:14Z"
    },
    {
      "role": "assistant",
      "content": "Necesito que me riegues cuando el suelo esté seco...",
      "timestamp": "2026-05-14T18:55:00Z"
    }
  ]
}
```

**Errores:**
| Status | Motivo |
|---|---|
| `403 Forbidden` | La planta no pertenece al usuario |
| `404 Not Found` | Planta no encontrada |

---

### 6.3 `GET /chat/{plant_id}/voices`

Devuelve las opciones de voz disponibles para la planta (voz recomendada + alternativas). Requiere `ELEVENLABS_API_KEY` configurado.

**Response (200 OK):**
```json
{
  "plant_id": "8e3fbfe9-2b4a-43c2-a4fa-1a234f2d5eab",
  "current_voice_id": "21m00Tcm4TlvDq8ikWAM",
  "options": [
    {
      "voice_id": "21m00Tcm4TlvDq8ikWAM",
      "name": "Rachel",
      "gender": "female",
      "style": "calm",
      "lang": "es",
      "recommended": true
    },
    {
      "voice_id": "EXAVITQu4vr4xnSDxMaL",
      "name": "Bella",
      "gender": "female",
      "style": "warm",
      "lang": "es",
      "recommended": false
    },
    {
      "voice_id": "TxGEqnHWrfWFTfGW9XjX",
      "name": "Antoni",
      "gender": "male",
      "style": "neutral",
      "lang": "es",
      "recommended": false
    }
  ]
}
```

**Errores:**
| Status | Motivo |
|---|---|
| `403 Forbidden` | La planta no pertenece al usuario |
| `404 Not Found` | Planta no encontrada |

---

### 6.4 `PATCH /chat/{plant_id}/voice`

Establece la voz elegida por el usuario para esa planta como `current_voice_id`.

**Request Body (JSON):**
```json
{
  "voice_id": "EXAVITQu4vr4xnSDxMaL"
}
```

**Response (200 OK):** Mismo schema que `GET /chat/{plant_id}/voices` con el `current_voice_id` actualizado.

**Errores:**
| Status | Motivo |
|---|---|
| `403 Forbidden` | La planta no pertenece al usuario |
| `404 Not Found` | Planta no encontrada |

---

### 6.5 `POST /chat/{plant_id}/trigger-proactive` ⚠️ Testing only

Simula el disparo del evaluador de sensores. Genera un mensaje proactivo de la planta al usuario por una condición anómala detectada. Solo para testing/debugging.

**Request Body (JSON):**
```json
{
  "alert_message": "temperatura promedio (5°C) fuera de rango (18-25)"
}
```

**Response (200 OK):**
```json
{
  "status": "success",
  "reply": "¡Uy qué frío hace! Siento mis hojitas congeladas, ¿podrías subir un poco la calefacción? 🥶"
}
```

**Side effects:** Inserta un evento en la tabla `events` (visible en `GET /notifications`) e invoca el chat con `is_proactive=true`.

**Errores:**
| Status | Motivo |
|---|---|
| `403 Forbidden` | La planta no pertenece al usuario |
| `404 Not Found` | Planta no encontrada |

---

## 8. Notifications

Sistema de notificaciones en tiempo real para mensajes proactivos de las plantas y eventos del evaluador. Usa **dos canales simultáneos**:

- **WebSocket** — cuando la app está abierta. Push instantáneo dentro de la app.
- **FCM (Firebase Cloud Messaging)** — cuando la app está cerrada o en segundo plano. Notificación del sistema operativo.

---

### 7.1 `WS /notifications/ws?token=<jwt>`

Conexión WebSocket persistente para recibir notificaciones en tiempo real. La autenticación se hace pasando el JWT como query param (los WebSocket headers no son confiables en todos los clientes).

**Autenticación:** `?token=<access_token>` (query param, no header)

**Códigos de cierre:**
| Código | Motivo |
|---|---|
| `4401` | Token inválido o expirado |

**Mensajes recibidos por el cliente (JSON):**
```json
{
  "type": "chat_message",
  "plant_id": "8e3fbfe9-...",
  "plant_nickname": "Monstera Pepito",
  "message": "¡Tengo sed! Hace 3 días que no me riegas 🌵",
  "audio_url": "plant_audio/.../msg.mp3",
  "timestamp": "2026-05-28T14:00:00+00:00"
}
```

| Campo `type` | Cuándo se emite | Canal |
|---|---|---|
| `"chat_message"` | Respuesta de la planta a un mensaje del usuario | Solo WS |
| `"proactive_alert"` | La planta avisa por iniciativa propia (evaluador) | WS + FCM |

> `audio_url`: puede ser `null` si la respuesta no incluye audio.
> El cliente no necesita enviar mensajes al servidor; solo escucha.

---

### 7.2 `GET /notifications`

Histórico de eventos de las plantas del usuario, ordenado por `created_at` descendente. Solo devuelve eventos de plantas que pertenecen al usuario autenticado.

**Query params opcionales:**
| Param | Tipo | Default | Rango | Descripción |
|---|---|---|---|---|
| `limit` | `int` | `50` | 1–200 | Número máximo de eventos a devolver |

**Response (200 OK):**
```json
{
  "events": [
    {
      "event_id": "uuid-del-evento",
      "plant_id": "8e3fbfe9-...",
      "type": "chat",
      "message": "Problemas detectados: humedad del suelo promedio (15.20) fuera de rango (30-70)",
      "created_at": "2026-05-28T14:00:00"
    }
  ]
}
```

| Valor `type` | Descripción |
|---|---|
| `"alert"` | Alerta por condición fuera de rango |
| `"insight"` | Insight o recomendación proactiva |
| `"chat"` | Evento originado desde el chatbot/evaluador |
| `"system"` | Evento del sistema |

---

## 9. Devices (Push Tokens)

Registro de tokens FCM de dispositivos para enviar push notifications cuando la app está en segundo plano.

---

### 8.1 `POST /devices`

Registra (o actualiza) un token FCM para el dispositivo actual. Si el token ya existe, actualiza el `user_id` (caso de re-login en otro usuario).

**Request Body (JSON):**
```json
{
  "token": "fGz9...token_FCM_completo",
  "platform": "android"
}
```

| Campo | Tipo | Requerido | Valores | Descripción |
|---|---|---|---|---|
| `token` | `string` | ✅ | min 1 char | Token FCM del dispositivo |
| `platform` | `string` | ✅ | `"ios"` \| `"android"` \| `"web"` | Plataforma del dispositivo |

**Response (201 Created):**
```json
{
  "id": "uuid-del-registro",
  "user_id": "uuid-del-usuario",
  "token": "fGz9...",
  "platform": "android",
  "created_at": "2026-05-28T14:00:00Z",
  "last_used_at": "2026-05-28T14:00:00Z"
}
```

**Errores:**
| Status | Motivo |
|---|---|
| `500 Internal Server Error` | Error registrando el token en Supabase |

---

### 8.2 `DELETE /devices/{token}`

Elimina un token FCM del dispositivo (logout o app desinstalada). Solo elimina tokens que pertenecen al usuario autenticado.

**Response (204 No Content):** Sin cuerpo.

**Errores:**
| Status | Motivo |
|---|---|
| `500 Internal Server Error` | Error eliminando el token |

---

## 10. Referencia de campos derivados

### `PlantResponse` schema

Devuelto por `POST /plants/`, `GET /plants/`, `PATCH /plants/{id}`, `POST /plants/{id}/actions`, `PUT /plants/{id}/photo`, `POST /plants/{id}/personalized-care`.

| Campo | Tipo | Notas |
|---|---|---|
| `plant_id` | `UUID` | |
| `user_id` | `UUID` | |
| `species_id` | `UUID` | |
| `nickname` | `string` | |
| `health_status` | `string` | `"healthy"`, `"warning"`, `"critical"` |
| `health_score` | `float` | 0–100. Calculado por el evaluador al recibir datos de sensor |
| `photo_storage_path` | `string\|null` | Path en Firebase Storage |
| `photo_url` | `string\|null` | URL pública calculada en tiempo de respuesta. No es columna de BD. Usar como `NetworkImage` |
| `common_name` | `string\|null` | Del join con tabla `species` |
| `scientific_name` | `string\|null` | Del join con tabla `species` |
| `created_at` | `datetime` | |
| `last_health_check` | `datetime\|null` | Última vez que el evaluador calculó salud |
| `last_watered` | `datetime\|null` | Última vez que se registró `action_type: "water"` |
| `estimated_age_months` | `int\|null` | Edad estimada al momento de adopción |
| `location` | `string\|null` | Ubicación en casa (requerido para `personalized-care`) |
| `specific_care_tips` | `any\|null` | Tips personalizados generados por IA. `null` hasta llamar a `personalized-care` |

### `PlantProfileResponse` schema

Extiende `PlantResponse` con el campo adicional `species_info`:

| Campo | Tipo | Notas |
|---|---|---|
| `species_info.care_summary` | `string\|null` | Resumen de cuidados generado por IA |
| `species_info.ai_personality_prompt` | `string\|null` | Prompt de personalidad del chatbot |
| `species_info.personality_traits` | `string[]` | Extraído del prompt de personalidad (máx 3 traits) |
| `species_info.personality_description` | `string\|null` | Primera oración del tono/carácter |
| `species_info.care_tips` | `string[]` | Consejos de cuidado de la especie |
| `species_info.fun_facts` | `string[]` | Datos curiosos de la especie |
| `species_info.care_ranges` | `CareRangesDTO\|null` | Rangos óptimos de la especie (valores `float`) |

### `SensorDataResponse` schema

| Campo | Tipo | Notas |
|---|---|---|
| `id` | `string` | ID del documento en Firebase |
| `sensor_id` | `string\|null` | |
| `plant_id` | `string\|null` | |
| `temperature_c` | `float\|null` | |
| `humidity_pct` | `float\|null` | Humedad del aire |
| `soil_moisture_pct` | `float\|null` | Humedad del suelo |
| `light_lux` | `float\|null` | |
| `health_score` | `float\|null` | Calculado al momento de ingestión |
| `health_status` | `string\|null` | |
| `timestamp` | `datetime` | UTC |

### `care_weights`, `sensitivity_assessment` y `eval_intervals`

Introducidos en las migraciones `003_care_weights.sql` (pesos/sensibilidad) y `005` (intervalos). `null` para fichas generadas antes de su respectiva migración.

| Dimensión | `care_weights` | `sensitivity_assessment` | `eval_intervals` |
|---|---|---|---|
| Luz | `light` (float 0–1) | `light` (`"high"` \| `"medium"` \| `"low"`) | `light` (int, minutos, mín 30) |
| Humedad suelo | `soil_humidity` (float 0–1) | `soil_humidity` | `soil_humidity` (int, minutos) |
| Humedad aire | `air_humidity` (float 0–1) | `air_humidity` | `air_humidity` (int, minutos) |
| Temperatura | `temperature` (float 0–1) | `temperature` | `temperature` (int, minutos) |

**Reglas:**
- La suma de los 4 valores de `care_weights` siempre ≈ 1.0.
- `sensitivity_assessment` es el nivel cualitativo del que se derivan los pesos.
- `eval_intervals`: `high` → intervalos cortos, `low` → intervalos largos.

---

## 11. Vacíos conceptuales detectados

### 🔴 Críticos (endpoints reales no documentados)

| # | Gap | Descripción |
|---|---|---|
| 1 | **`PATCH /plants/{plant_id}` faltante** | Endpoint real para editar `nickname` y `location`. Ya corregido en el contrato. |
| 2 | **`POST /plants/{plant_id}/actions` faltante** | Endpoint real para registrar riego y otras acciones manuales. Ausente del contrato anterior. |
| 3 | **`GET /plants/{plant_id}/profile` faltante** | Endpoint de perfil enriquecido de la planta (con `species_info`). Ausente del contrato anterior. |
| 4 | **`GET /species/search` faltante** | Endpoint de búsqueda de especies por nombre. Ausente del contrato anterior. |

### 🟡 Importantes (campos incorrectos o faltantes)

| # | Gap | Descripción |
|---|---|---|
| 5 | **`mac_address` no es columna de `plants`** | Campo eliminado de `PlantCreate`, `PlantUpdate` y `PlantResponse`. El vínculo sensor↔planta se gestiona a través de la tabla `sensors`. Ya corregido. |
| 6 | **`last_watered` en `PlantResponse` no documentado** | Campo presente en el schema Pydantic pero ausente del contrato anterior. Relevante para mostrar "Última vez regada". |
| 7 | **`photo_storage_path` en `needs_user_selection`** | La respuesta de `/identify` con `needs_user_selection` también incluye `photo_storage_path` (para el candidato principal), pero no estaba documentado. |
| 8 | **`CareRangesDTO` usa `int` pero `CareRanges` usa `float`** | ~~Resuelto~~ — `CareRangesDTO` actualizado a `float` para respetar los `FLOAT` de la BD. |

### 🟢 Vacíos de producto (funcionalidad faltante)

| # | Gap | Descripción |
|---|---|---|
| 9 | **Sin endpoint de perfil de usuario** | ~~Resuelto~~ — Ver sección 2. `GET /users/me` y `PATCH /users/me` implementados. |
| 10 | **Sin endpoints de Friendships/Social** | La lógica de amistades (`friendships` table) está implementada (plants, sensor-data, profile la consumen), pero no hay endpoints para enviar/aceptar/rechazar solicitudes de amistad. |
| 11 | **Sin endpoint de logout** | No existe `POST /auth/logout` para invalidar tokens del lado del servidor. El logout actual es solo del lado cliente. |
| 12 | **Sin paginación en `GET /plants/`** | No hay soporte de `limit`/`offset` para usuarios con muchas plantas. |
| 13 | **`type` de `NotificationEvent` subutilizado** | El schema define 4 tipos (`alert`, `insight`, `chat`, `system`) pero en la práctica el evaluador solo emite `chat`. No hay lógica que emita `alert` directamente. |
