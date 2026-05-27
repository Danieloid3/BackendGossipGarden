"""Tests del servicio de compactación de contexto (summarizer_service)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.summarizer_service import (
    MIN_RECENT_MESSAGES,
    build_system_with_summary,
    compact_if_needed,
    count_tokens,
)


def _long_messages(n: int) -> list[dict]:
    """Genera n mensajes alternados con contenido largo para superar el límite de tokens."""
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": "palabra " * 500}
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# count_tokens
# ---------------------------------------------------------------------------

def test_count_tokens_empty_returns_baseline():
    assert count_tokens([]) == 2


def test_count_tokens_nonzero_for_messages():
    msgs = [{"role": "user", "content": "Hola, ¿cómo estás hoy?"}]
    assert count_tokens(msgs) > 2


def test_count_tokens_grows_with_content():
    short = [{"role": "user", "content": "Hola"}]
    long = [{"role": "user", "content": "Hola " * 200}]
    assert count_tokens(long) > count_tokens(short)


# ---------------------------------------------------------------------------
# build_system_with_summary
# ---------------------------------------------------------------------------

def test_build_system_no_summary_no_status():
    result = build_system_with_summary("Eres una planta.", "", "")
    assert "Eres una planta." in result
    assert "Resumen" not in result


def test_build_system_with_summary_appended():
    result = build_system_with_summary("Eres una planta.", "El usuario preguntó sobre agua.", "")
    assert "El usuario preguntó sobre agua." in result
    assert "Resumen de conversaciones anteriores" in result


def test_build_system_with_plant_status():
    status = "--- Tu estado actual ---\nSalud: healthy"
    result = build_system_with_summary("Eres una planta.", "", status)
    assert "Salud: healthy" in result


def test_build_system_includes_guardrails():
    result = build_system_with_summary("Eres una planta.", "", "")
    assert "REGLAS ESTRICTAS" in result


# ---------------------------------------------------------------------------
# compact_if_needed
# ---------------------------------------------------------------------------

async def test_compact_not_needed_below_threshold():
    msgs = [
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": "Hola planta"},
    ]
    result_history, result_summary, was_compacted = await compact_if_needed(msgs, "")
    assert result_history == msgs
    assert was_compacted is False


async def test_compact_triggered_above_threshold():
    msgs = _long_messages(20)
    with patch(
        "app.services.summarizer_service._call_summarizer",
        new_callable=AsyncMock,
        return_value="Resumen generado.",
    ):
        result_history, result_summary, was_compacted = await compact_if_needed(msgs, "")

    assert was_compacted is True
    assert len(result_history) == MIN_RECENT_MESSAGES
    assert result_summary == "Resumen generado."


async def test_compact_skipped_when_nothing_to_summarize():
    # Exactamente MIN_RECENT_MESSAGES mensajes muy largos: to_summarize queda vacío
    msgs = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 10000}
        for i in range(MIN_RECENT_MESSAGES)
    ]
    with patch(
        "app.services.summarizer_service._call_summarizer",
        new_callable=AsyncMock,
    ) as mock_summarizer:
        _, _, was_compacted = await compact_if_needed(msgs, "")

    assert was_compacted is False
    mock_summarizer.assert_not_called()
