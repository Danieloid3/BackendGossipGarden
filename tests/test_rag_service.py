"""Tests del servicio rag_service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.rag_service import retrieve_context


async def test_retrieve_context_disabled_returns_empty(monkeypatch):
    monkeypatch.setattr("app.services.rag_service.settings.RAG_ENABLED", False)

    result = await retrieve_context("Sansevieria trifasciata", "Asparagaceae")

    assert result == []


async def test_retrieve_context_no_chunks_returns_empty():
    with (
        patch("app.services.rag_service.embed_texts") as mock_embed,
        patch("app.services.rag_service.supabase") as mock_sb,
    ):
        mock_embed.return_value = [[0.1] * 1536]
        mock_sb.rpc.return_value.execute.return_value = MagicMock(data=[])

        result = await retrieve_context("Sansevieria trifasciata", "Asparagaceae")

    assert result == []


async def test_retrieve_context_rpc_error_returns_empty_and_warns(caplog):
    import logging
    with (
        patch("app.services.rag_service.embed_texts") as mock_embed,
        patch("app.services.rag_service.supabase") as mock_sb,
        patch("app.services.rag_service._rpc_error_logged", False),
    ):
        mock_embed.return_value = [[0.1] * 1536]
        mock_sb.rpc.side_effect = Exception("pgvector not installed")

        with caplog.at_level(logging.WARNING):
            result = await retrieve_context("Sansevieria trifasciata", None)

    assert result == []


async def test_retrieve_context_returns_chunks():
    fake_chunks = [
        {
            "content": "La Sansevieria tolera luz baja.",
            "source": "RHS Encyclopedia",
            "scientific_name": "Sansevieria trifasciata",
            "family": "Asparagaceae",
            "similarity": 0.88,
        }
    ]
    with (
        patch("app.services.rag_service.embed_texts") as mock_embed,
        patch("app.services.rag_service.supabase") as mock_sb,
    ):
        mock_embed.return_value = [[0.1] * 1536]
        mock_sb.rpc.return_value.execute.return_value = MagicMock(data=fake_chunks)

        result = await retrieve_context("Sansevieria trifasciata", "Asparagaceae")

    assert len(result) == 1
    assert result[0].content == "La Sansevieria tolera luz baja."
    assert result[0].similarity == pytest.approx(0.88)
