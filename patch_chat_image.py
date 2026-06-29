import re

with open("app/services/chat_service.py", "r") as f:
    content = f.read()

# 1. Add import
if "from app.services import image_storage_service" not in content:
    content = content.replace(
        "from app.services import tts_service",
        "from app.services import tts_service\nfrom app.services import image_storage_service\nimport base64\nimport uuid"
    )

# 2. Add user_image_url to _save_exchange_sync
content = content.replace(
    "def _save_exchange_sync(\n    plant_id: str,\n    user_id: str,\n    message: str | None,\n    reply: str,\n    timestamp_ms: int,\n    audio_url: str | None = None,\n    user_audio_url: str | None = None,\n) -> None:",
    "def _save_exchange_sync(\n    plant_id: str,\n    user_id: str,\n    message: str | None,\n    reply: str,\n    timestamp_ms: int,\n    audio_url: str | None = None,\n    user_audio_url: str | None = None,\n    user_image_url: str | None = None,\n) -> None:"
)
content = content.replace(
    "if user_audio_url:\n        doc[\"user_audio_url\"] = user_audio_url",
    "if user_audio_url:\n        doc[\"user_audio_url\"] = user_audio_url\n    if user_image_url:\n        doc[\"user_image_url\"] = user_image_url"
)

# 3. Add upload logic in chat_with_plant
old_audio = """    user_audio_url: str | None = None
    if user_audio_base64:
        try:
            user_audio_bytes = base64.b64decode(user_audio_base64)
            # Asumimos webm por defecto para la web, la app podría enviar m4a
            user_audio_url = await tts_service.upload_audio(
                user_audio_bytes, user_id, plant_id, now_str, extension="webm", content_type="audio/webm"
            )
        except Exception as e:
            logger.error("Error al subir audio del usuario: %s", e)"""

new_audio = """    user_audio_url: str | None = None
    if user_audio_base64:
        try:
            user_audio_bytes = base64.b64decode(user_audio_base64)
            user_audio_url = await tts_service.upload_audio(
                user_audio_bytes, user_id, plant_id, now_str, extension="webm", content_type="audio/webm"
            )
        except Exception as e:
            logger.error("Error al subir audio del usuario: %s", e)

    user_image_url: str | None = None
    if image_base64:
        try:
            image_bytes = base64.b64decode(image_base64)
            uid = str(uuid.uuid4())[:8]
            safe_ts = now_str.replace(" ", "T").replace(":", "")
            storage_path = f"chat_images/{user_id}/{plant_id}/{safe_ts}_{uid}.jpg"
            stored_path = await image_storage_service._upload_compressed(image_bytes, storage_path)
            if stored_path and settings.FIREBASE_STORAGE_BUCKET:
                user_image_url = f"https://storage.googleapis.com/{settings.FIREBASE_STORAGE_BUCKET}/{stored_path}"
        except Exception as e:
            logger.error("Error al subir imagen del chat: %s", e)"""

content = content.replace(old_audio, new_audio)

# 4. Pass user_image_url to _save_exchange_sync call
content = content.replace(
    "_save_exchange_sync, plant_id, user_id, message if not is_proactive else None, reply, now_ms, audio_url, user_audio_url\n        )",
    "_save_exchange_sync, plant_id, user_id, message if not is_proactive else None, reply, now_ms, audio_url, user_audio_url, user_image_url\n        )"
)

with open("app/services/chat_service.py", "w") as f:
    f.write(content)
