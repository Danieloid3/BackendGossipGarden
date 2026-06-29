from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    language: str = Field("es", pattern=r"^(es|en|fr|pt|de|it)$")
    response_format: Literal["text", "audio"] = "text"
    image_base64: str | None = Field(None, max_length=20000000, description="Imagen en Base64 para analizar")
    user_audio_base64: str | None = Field(None, description="Audio en Base64 del usuario (webm/ogg)")

class TranscribeRequest(BaseModel):
    user_audio_base64: str = Field(..., description="Audio en Base64 del usuario (webm/ogg)")

class TranscribeResponse(BaseModel):
    transcription: str
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    timestamp: str
    audio_url: str | None = None
    user_image_url: str | None = None

class ChatResponse(BaseModel):
    reply: str
    plant_id: str
    timestamp: str
    audio_url: str | None = None
    user_image_url: str | None = None
    user_audio_url: str | None = None


class ChatHistoryResponse(BaseModel):
    plant_id: str
    messages: list[ChatMessage]


class VoiceOption(BaseModel):
    voice_id: str
    name: str
    gender: str
    style: str
    lang: str
    recommended: bool = False


class VoicesResponse(BaseModel):
    plant_id: str
    current_voice_id: str
    options: list[VoiceOption]


class SetVoiceRequest(BaseModel):
    voice_id: str = Field(..., min_length=1)
