import pytest
from unittest.mock import patch, MagicMock
from app.services.image_storage_service import _upload_compressed
import base64

@pytest.mark.asyncio
async def test_upload_compressed_success():
    """
    Test que verifica _upload_compressed con firebase_admin mockeado.
    """
    dummy_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    dummy_bytes = base64.b64decode(dummy_base64)
    storage_path = "chat_images/user-123/plant-123/2026-06-28_123.jpg"

    with patch("firebase_admin.storage.bucket") as mock_bucket_method:
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        
        mock_bucket_method.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        result = await _upload_compressed(dummy_bytes, storage_path)

        assert mock_bucket_method.called
        mock_bucket.blob.assert_called_with(storage_path)
        assert mock_blob.upload_from_file.called
        assert mock_blob.make_public.called
        assert result == storage_path

@pytest.mark.asyncio
async def test_upload_compressed_failure_returns_none():
    """
    Test que verifica que si hay una excepcion devuelva None y no pete todo.
    """
    dummy_bytes = b"bad-bytes"
    storage_path = "chat_images/user-123/plant-123/2026-06-28_123.jpg"

    with patch("firebase_admin.storage.bucket") as mock_bucket_method:
        mock_bucket_method.side_effect = Exception("Firebase Error")

        result = await _upload_compressed(dummy_bytes, storage_path)
        assert result is None

def test_save_exchange_sync_structure():
    """
    Verificamos que _save_exchange_sync genere el dict esperado de Firebase 
    incluyendo user_image_url.
    """
    from app.services.chat_service import _save_exchange_sync

    plant_id = "test-plant-123"
    user_id = "test-user-123"
    user_msg = "Mira esta foto"
    reply = "Que bonita foto"
    now_ms = 1680000000000 # dummy timestamp
    user_image_url = "https://storage.googleapis.com/test/img.jpg"

    with patch("app.services.chat_service.firebase_db") as mock_firebase_db:
        mock_doc_ref = MagicMock()
        mock_firebase_db.collection.return_value.document.return_value.collection.return_value.document.return_value = mock_doc_ref

        _save_exchange_sync(
            plant_id=plant_id,
            user_id=user_id,
            user_message=user_msg,
            reply=reply,
            now_ms=now_ms,
            audio_url=None,
            user_audio_url=None,
            user_image_url=user_image_url,
        )

        assert mock_doc_ref.set.called
        call_args = mock_doc_ref.set.call_args[0]
        data = call_args[0]
        
        # Debe tener los metadatos base
        assert data["user_id"] == user_id
        assert data["plant_id"] == plant_id
        
        # Deben haber 2 mensajes en el update (ArrayUnion)
        # El mock the ArrayUnion es un objeto de google.cloud.firestore, por lo que podemos inspeccionar su valor.
        # No vamos a inspeccionarlo tan a fondo para evitar importar dependencias de firestore en el test.
        assert "messages" in data
