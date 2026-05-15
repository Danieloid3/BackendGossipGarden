# Rama feature/chatbot-IA

Esta rama implementa el sistema de chatbot con IA que permite a los usuarios conversar con sus plantas.

---

## ¿Qué se implementó?

### Endpoints
- `POST /api/v1/chat/{plant_id}` — envía un mensaje y recibe la respuesta de la planta
- `GET /api/v1/chat/{plant_id}/history` — devuelve el historial completo de conversación

### Archivos nuevos
- `app/schemas/chat.py` — modelos Pydantic para request/response
- `app/services/chat_service.py` — lógica de negocio del chatbot
- `app/services/summarizer_service.py` — compactación de contexto y guardrails
- `app/api/v1/endpoints/chat.py` — endpoints REST

### Archivos modificados
- `app/api/v1/api.py` — registro del router de chat
- `app/core/config.py` — variables `OPENAI_CHAT_MODEL` y `OPENAI_PERSONALITY_MODEL`
- `app/services/openai_service.py` — usa `OPENAI_PERSONALITY_MODEL` como modelo por defecto

---

## ¿Cómo funciona?

### 1. Personalidad dinámica
Cada planta tiene una personalidad única generada por GPT almacenada en la tabla `species_ai_content` de Supabase. Esta personalidad se carga en cada conversación y define el tono, carácter, emociones y reacciones de la planta.

### 2. Estado real de la planta
En cada mensaje el bot conoce el estado actual de la planta:
- `health_score` y `health_status` desde Supabase
- Temperatura, humedad del aire, humedad del suelo y luz desde Firestore (`sensor_readings`)
- Nickname de la planta

Esto permite que la planta hable de cómo se siente basándose en datos reales.

### 3. Memoria en dos niveles
| Nivel | Tecnología | Contenido | Duración |
|---|---|---|---|
| Corto plazo | Redis | Últimos 20 mensajes | 2 horas |
| Largo plazo | Firestore | Todos los mensajes | Permanente |

El historial se carga primero desde Redis (más rápido). Si Redis no lo tiene, se recarga desde Firestore automáticamente.

### 4. Compactación de contexto
Cuando el historial activo supera **3000 tokens**, se activa la compactación:
1. Se conservan los últimos 6 mensajes íntegros
2. Los mensajes más antiguos se resumen con GPT (máx. 150 palabras)
3. El resumen se fusiona con resúmenes anteriores si existen
4. El resumen se guarda en Redis (7 días) y Firestore (permanente)
5. GPT recibe: personalidad + estado actual + resumen + mensajes recientes

Los mensajes originales **nunca se borran** de Firestore.

### 5. Guardrails
La planta solo responde desde su perspectiva. Bloquea automáticamente:
- Política y figuras públicas
- Religión
- Programación y temas académicos
- Cualquier tema ajeno a su mundo como planta

Cuando recibe una pregunta fuera de contexto, la redirige con su personalidad hacia sus cuidados.

### 6. Almacenamiento en Firestore
Un único documento por conversación identificado por `user_id`:
```
plants/{plant_id}/chat_logs/{user_id}
  ├── user_id
  ├── plant_id
  ├── updated_at
  └── messages: [{role, content, timestamp}, ...]

plants/{plant_id}/chat_meta/{user_id}
  ├── summary
  └── updated_at
```

---

## Variables de entorno requeridas

```env
OPENAI_CHAT_MODEL=gpt-4o           # modelo para el chatbot
OPENAI_PERSONALITY_MODEL=gpt-5.5   # modelo para generación de personalidades
```

---

## System prompt completo (por mensaje)

```
[personalidad de la especie — desde species_ai_content]
[guardrails — reglas de comportamiento]
[estado actual — health_score, health_status, sensores]
[resumen de conversaciones anteriores — si existe]
[historial reciente — últimos 6 mensajes]
[nuevo mensaje del usuario]
```
