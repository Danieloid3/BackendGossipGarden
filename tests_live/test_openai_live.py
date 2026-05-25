"""Tests live de OpenAI.

Verifica conectividad y respuestas coherentes del modelo de chat.
"""
from __future__ import annotations

import pytest
from openai import AsyncOpenAI

from app.core.config import settings

pytestmark = pytest.mark.live


async def test_chat_completion_returns_text():
    """El modelo de chat responde con texto no vacío."""
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    response = await client.chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        messages=[{"role": "user", "content": "Di exactamente: 'hola planta' y nada más."}],
        max_tokens=20,
    )
    reply = response.choices[0].message.content
    assert isinstance(reply, str)
    assert len(reply.strip()) > 0


async def test_chat_completion_respects_system_prompt():
    """El modelo respeta el system prompt (persona de planta)."""
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    response = await client.chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        messages=[
            {"role": "system", "content": "Eres una planta llamada Árbol de caucho. Responde siempre en español y en primera persona como planta."},
            {"role": "user", "content": "¿Cómo te llamas?"},
        ],
        max_tokens=60,
    )
    reply = response.choices[0].message.content
    assert isinstance(reply, str)
    assert len(reply.strip()) > 0


async def test_embedding_returns_1536_dimensions():
    """embed_texts() retorna vectores de 1536 dimensiones."""
    from app.services.openai_service import embed_texts

    vectors = await embed_texts(["Árbol de caucho", "Ficus elastica"])

    assert len(vectors) == 2
    assert len(vectors[0]) == 1536
    assert len(vectors[1]) == 1536
    assert all(isinstance(v, float) for v in vectors[0])
