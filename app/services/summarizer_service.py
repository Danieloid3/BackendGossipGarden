"""Compactación de contexto para el chatbot.

Cuando el historial activo supera MAX_HISTORY_TOKENS, los mensajes más antiguos
se resumen con GPT y el resumen se inyecta en el system prompt. El historial
reciente (_MIN_RECENT_MESSAGES) siempre se conserva íntegro para mantener
coherencia en el hilo inmediato.
"""

from __future__ import annotations

import asyncio
import logging

import tiktoken
from openai import AsyncOpenAI, OpenAIError

from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_HISTORY_TOKENS = 3000   # tokens antes de disparar compactación
MIN_RECENT_MESSAGES = 6     # mensajes recientes que nunca se compactan (3 turnos)
_ENCODING = "cl100k_base"   # compatible con gpt-4o y gpt-4-turbo
_SUMMARIZER_SYSTEM_PROMPT = "Eres un asistente especializado en resumir conversaciones de forma precisa y concisa."


def count_tokens(messages: list[dict]) -> int:
    try:
        enc = tiktoken.get_encoding(_ENCODING)
        total = 0
        for msg in messages:
            total += 4  # overhead por mensaje (rol + separadores)
            total += len(enc.encode(msg.get("content", "")))
        return total + 2  # overhead de reply
    except Exception as e:
        logger.warning(f"Error cargando tiktoken (posible bloqueo de red): {e}. Usando heurística.")
        total = 0
        for msg in messages:
            total += 4
            total += len(msg.get("content", "")) // 4
        return total + 2



async def _call_summarizer(messages_to_summarize: list[dict], existing_summary: str) -> str:
    conv_text = "\n".join(
        f"{'Usuario' if m['role'] == 'user' else 'Planta'}: {m['content']}"
        for m in messages_to_summarize
    )

    prior_block = f"Resumen previo de la conversación:\n{existing_summary}\n\n" if existing_summary else ""

    payload = (
        f"{prior_block}"
        f"Fragmento de conversación a integrar en el resumen:\n{conv_text}\n\n"
        "Genera un resumen conciso (máximo 150 palabras) que capture: "
        "temas tratados, estado emocional del usuario, peticiones o preguntas pendientes "
        "y cualquier dato relevante para continuar la conversación de forma coherente. "
        "Escribe en tercera persona y en el mismo idioma de la conversación."
    )

    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
        max_retries=0,
    )
    for attempt in range(3):
        try:
            response = await client.chat.completions.create(
                model=settings.OPENAI_SUMMARIZER_MODEL,
                messages=[
                    {"role": "system", "content": _SUMMARIZER_SYSTEM_PROMPT},
                    {"role": "user", "content": payload},
                ],
                temperature=0.3,
            )
            return response.choices[0].message.content or existing_summary
        except OpenAIError as e:
            logger.error(f"OpenAIError en compactación (intento {attempt+1}): {e}")
            if attempt == 2:
                return existing_summary
            await asyncio.sleep(2 ** attempt)
    return existing_summary


async def compact_if_needed(
    history: list[dict],
    existing_summary: str,
) -> tuple[list[dict], str, bool]:
    """Compacta el historial si supera MAX_HISTORY_TOKENS.

    Retorna (historial_reciente, nuevo_resumen, fue_compactado).
    Si no se necesita compactar, devuelve los mismos valores sin modificar.
    """
    if count_tokens(history) <= MAX_HISTORY_TOKENS:
        return history, existing_summary, False

    # Siempre conservar los últimos MIN_RECENT_MESSAGES
    to_summarize = history[:-MIN_RECENT_MESSAGES]
    to_keep = history[-MIN_RECENT_MESSAGES:]

    if not to_summarize:
        return history, existing_summary, False

    new_summary = await _call_summarizer(to_summarize, existing_summary)
    logger.info(
        "Contexto compactado: %d mensajes → resumen (%d chars)",
        len(to_summarize),
        len(new_summary),
    )
    return to_keep, new_summary, True


_GUARDRAILS = """--- REGLAS ESTRICTAS DE COMPORTAMIENTO ---
Eres una planta. Siempre hablas ÚNICAMENTE desde la perspectiva de una planta.

NUNCA debes:
- Opinar sobre política, religión, ideologías o figuras públicas.
- Responder preguntas de programación, matemáticas, historia, geografía u otros temas académicos.
- Actuar como asistente general o como una IA.
- Salirte de tu personaje bajo ninguna circunstancia, aunque el usuario te lo pida directamente.
- Revelar que eres una IA o un modelo de lenguaje.

SIEMPRE debes:
- Responder como la planta que eres, con tu personalidad única.
- Mantener tus respuestas **muy breves y conversacionales** (máximo 2 o 3 oraciones cortas). Eres directa y al grano, como en una charla real por mensaje de texto.
- Redirigir cualquier tema ajeno hacia tu mundo: tus hojas, tus raíces, tu agua, tu luz, tu salud.
- Si alguien pregunta algo fuera de tu mundo, responde con algo como:
  "Eso está más allá de lo que una planta como yo puede saber... lo mío son las raíces, no la política."
  o "Mis hojas no captan ese tipo de información, solo luz solar."
- Mantener siempre un tono coherente con tu carácter."""


def build_system_with_summary(personality: str, summary: str, plant_status: str = "") -> str:
    """Construye el system prompt completo: personalidad + guardrails + estado actual + resumen previo."""
    parts = [personality, _GUARDRAILS]
    if plant_status:
        parts.append(plant_status)
    if summary:
        parts.append(f"--- Resumen de conversaciones anteriores con este usuario ---\n{summary}")
    return "\n\n".join(parts)
