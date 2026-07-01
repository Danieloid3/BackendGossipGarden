"""Tests de enrutamiento y uso de modelos en chat_service."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.chat_service import chat_with_plant

FAKE_PLANT_ID = "aaaaaaaa-0000-0000-0000-000000000001"
FAKE_USER_ID = "00000000-0000-0000-0000-000000000001"

def _make_openai_response(content: str):
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    completion = MagicMock()
    completion.choices = [choice]
    return completion

@pytest.fixture
def fake_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    return redis

@pytest.mark.asyncio
@patch("app.services.chat_service._verify_and_get_plant")
@patch("app.services.chat_service.AsyncOpenAI")
@patch("app.services.chat_service.settings")
@patch("app.services.chat_service.openai_service._model_supports_temperature")
@patch("app.services.chat_service.image_storage_service._upload_compressed")
@patch("app.services.chat_service._fetch_username_sync")
@patch("app.services.chat_service._get_personality")
@patch("app.services.chat_service._save_exchange_sync")
async def test_chat_routing_gpt55_max_completion_tokens(
    mock_save,
    mock_get_personality,
    mock_fetch_username,
    mock_upload,
    mock_supports_temp,
    mock_settings,
    mock_openai_class,
    mock_verify,
    fake_redis
):
    """Prueba que cuando se pasa una imagen, se use el vision model y max_completion_tokens."""
    # Setup
    mock_upload.return_value = "fake_path.jpg"
    mock_get_personality.return_value = ("You are a plant", "voice-123")
    mock_fetch_username.return_value = "TestUser"
    mock_verify.return_value = {
        "plant_id": FAKE_PLANT_ID,
        "user_id": FAKE_USER_ID,
        "species_id": "fake",
        "nickname": "Test",
        "elevenlabs_voice_id": None
    }
    
    mock_settings.OPENAI_PERSONALITY_MODEL = "gpt-5.5-fake"
    mock_settings.OPENAI_CHAT_MODEL = "gpt-4o-fake"
    mock_settings.FIREBASE_STORAGE_BUCKET = "test-bucket"
    mock_supports_temp.return_value = False
    
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_make_openai_response("Vision Reply"))
    mock_openai_class.return_value = mock_client
    
    # Act
    response = await chat_with_plant(
        plant_id=FAKE_PLANT_ID,
        user_id=FAKE_USER_ID,
        message="¿Qué es esto?",
        language="es",
        response_format="text",
        image_base64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
        user_audio_base64=None,
        redis_client=fake_redis
    )
    
    # Assert
    assert response.reply == "Vision Reply"
    
    # Verify OpenAI call arguments
    mock_client.chat.completions.create.assert_called_once()
    kwargs = mock_client.chat.completions.create.call_args.kwargs
    
    # Verify model is gpt-5.5-fake
    assert kwargs["model"] == "gpt-5.5-fake"
    
    # Verify max_completion_tokens is used and max_tokens is NOT used
    assert "max_completion_tokens" in kwargs
    assert "max_tokens" not in kwargs
    
    # Verify temperature is not used
    assert "temperature" not in kwargs
    
    # Verify save exchange was called with image URL
    mock_save.assert_called_once()
    save_args = mock_save.call_args.args
    # signature: plant_id, user_id, message, reply, now_ms, audio_url, user_audio_url, user_image_url
    assert save_args[7] == "https://storage.googleapis.com/test-bucket/fake_path.jpg"

@pytest.mark.asyncio
@patch("app.services.chat_service._verify_and_get_plant")
@patch("app.services.chat_service.AsyncOpenAI")
@patch("app.services.chat_service.settings")
@patch("app.services.chat_service.openai_service._model_supports_temperature")
@patch("app.services.chat_service._fetch_username_sync")
@patch("app.services.chat_service._get_personality")
@patch("app.services.chat_service._save_exchange_sync")
async def test_chat_routing_gpt4o_max_tokens(
    mock_save,
    mock_get_personality,
    mock_fetch_username,
    mock_supports_temp,
    mock_settings,
    mock_openai_class,
    mock_verify,
    fake_redis
):
    """Prueba que cuando NO se pasa imagen, se use el chat model y max_tokens."""
    # Setup
    mock_get_personality.return_value = ("You are a plant", "voice-123")
    mock_fetch_username.return_value = "TestUser"
    mock_verify.return_value = {
        "plant_id": FAKE_PLANT_ID,
        "user_id": FAKE_USER_ID,
        "species_id": "fake",
        "nickname": "Test",
        "elevenlabs_voice_id": None
    }
    
    mock_settings.OPENAI_PERSONALITY_MODEL = "gpt-5.5-fake"
    mock_settings.OPENAI_CHAT_MODEL = "gpt-4o-fake"
    mock_supports_temp.return_value = True
    
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_make_openai_response("Chat Reply"))
    mock_openai_class.return_value = mock_client
    
    # Act
    response = await chat_with_plant(
        plant_id=FAKE_PLANT_ID,
        user_id=FAKE_USER_ID,
        message="Hola",
        language="es",
        response_format="text",
        image_base64=None,
        user_audio_base64=None,
        redis_client=fake_redis
    )
    
    # Assert
    assert response.reply == "Chat Reply"
    
    # Verify OpenAI call arguments
    mock_client.chat.completions.create.assert_called_once()
    kwargs = mock_client.chat.completions.create.call_args.kwargs
    
    # Verify model is gpt-4o-fake
    assert kwargs["model"] == "gpt-4o-fake"
    
    # Verify max_tokens is used and max_completion_tokens is NOT used
    assert "max_tokens" in kwargs
    assert "max_completion_tokens" not in kwargs
    
    # Verify temperature is used
    assert "temperature" in kwargs
