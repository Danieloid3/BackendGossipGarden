# Gossip Garden - API Contract

Este documento describe todos los endpoints actualmente disponibles en la API de Gossip Garden, incluyendo ejemplos de los cuerpos de las peticiones (Body) y las respuestas que generan.

**URL Base:** `/api/v1` (o la que se haya configurado el router principal, generalmente la API está en `http://localhost:8000/api/v1` dependiendo de tu `main.py`).

---

## 🔐 1. Auth (Autenticación)
Gestión de usuarios y tokens. **Nota**: El sistema de autenticación usa Supabase internamente.

### 1.1 `POST /auth/register`
Registra un nuevo usuario.

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
Inicia sesión y obtiene el token JWT (`access_token`).

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

---

## 🌿 2. Plants (Plantas)
 endpoints protegidos; requieren enviar el header JWT de acceso en los request:
`Authorization: Bearer <TÚ-TOKEN>`

### 2.1 `POST /plants/`
Crea una nueva planta asociada al usuario autenticado.

**Request Body (JSON):**
```json
{
  "species_id": "4b6e50ed-3088-4f81-8d2a-4ce1f6e2bdee",
  "nickname": "Mi Rosal"
}
```

**Response (200 OK):**
```json
{
  "plant_id": "8e3fbfe9-2b4a-43c2-a4fa-1a234f2d5eab",
  "user_id": "ID-DEL-USUARIO-AUTENTICADO",
  "species_id": "4b6e50ed-3088-4f81-8d2a-4ce1f6e2bdee",
  "nickname": "Mi Rosal",
  "health_status": "healthy",
  "health_score": 100.0,
  "created_at": "2024-05-11T12:00:00Z",
  "last_health_check": null
}
```

### 2.2 `GET /plants/`
Obtiene la lista de plantas del usuario autenticado o de un amigo verificado.

**Query Parameters (Opcional):** `?target_user_id=UUID-DEL-AMIGO` (Si se omite, devuelve las plantas del usuario autenticado).

**Response (200 OK):**
```json
[
  {
    "plant_id": "8e3fbfe9-2b4a-43c2-a4fa-1a234f2d5eab",
    "user_id": "ID-DEL-USUARIO-AUTENTICADO",
    "species_id": "4b6e50ed-3088-4f81-8d2a-4ce1f6e2bdee",
    "nickname": "Mi Rosal",
    "health_status": "healthy",
    "health_score": 100.0,
    "created_at": "2024-05-11T12:00:00Z",
    "last_health_check": null
  }
]
```

### 2.3 `GET /plants/{plant_id}/sensor-data/latest`
Obtiene el último dato de sensor disponible en Firebase para una planta específica. Permite el acceso del propietario o de un amigo verificado.

**URL Path Variable:** `plant_id` (UUID de la planta)

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
Obtiene el historial de datos de la planta (por defecto los últimos 30 días). Permite el acceso del propietario o de un amigo verificado.

**Query Parameters (Opcional):** `?days=30` (Número de días hacia atrás a consultar).

**Response (200 OK):**
```json
[
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
  },
  {
    "id": "abcd1234abcd123",
    "sensor_id": "sensor_001",
    "mac_address": "00:1B:44:11:3A:B7",
    "plant_id": "8e3fbfe9-2b4a-43c2-a4fa-1a234f2d5eab",
    "temperature_c": 21.0,
    "humidity_pct": 50.1,
    "soil_moisture_pct": 42.0,
    "light_lux": 400.0,
    "timestamp": "2024-05-11T09:30:15.123Z"
  }
]
```


---

## 📡 3. Sensors / IoT (Sensores)
Endpoints generalmente usados por hardware (los ESP32) o bridges intermediarios para ingestar información en Firebase al backend.

### 3.1 `POST /sensors/`
Ingesta los datos crudos procedentes de un sensor. Genera un TTL automático en Firebase.

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

## ❤️ 4. Core API
Verifica que el sistema esté respondiendo adecuadamente y cuente con acceso a infraestructura subyacente.

### 4.1 `GET /health`

**Response (200 OK):**
```json
{
  "status": "ok",
  "db_connected": true
}
```
