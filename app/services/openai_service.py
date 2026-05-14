"""Wrapper del SDK oficial openai con Structured Output (json_schema strict).

Encapsula llamadas a gpt-4o para generación de fichas y a text-embedding-3-small
para embeddings de RAG. Reintenta una vez ante violación de schema.
"""

from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from app.core.config import settings
from app.schemas.identification import (
    CareProfileLlmOutput,
    CareRanges,
    CareWeights,
    FaqItem,
    SensitivityAssessment,
)

logger = logging.getLogger(__name__)

CARE_PROFILE_JSON_SCHEMA: dict = {
    "name": "plant_care_profile",
    "strict": True,
    "schema": {
        "type": "object",
        "required": [
            "scientific_name", "common_name", "family", "care_ranges",
            "care_weights", "sensitivity_assessment",
            "care_summary", "ai_personality_prompt", "care_tips",
            "fun_facts", "faq", "proposal_confidence", "reasoning_summary",
        ],
        "properties": {
            "scientific_name": {"type": "string"},
            "common_name": {
                "type": "string",
                "description": "Most widely used common name for this plant in the requested output_language (e.g., 'lengua de suegra' for Spanish, 'snake plant' for English). Must be in the output language, not English unless output_language is 'en'.",
            },
            "family": {"type": "string"},
            "care_ranges": {
                "type": "object",
                "required": [
                    "min_temp_c", "max_temp_c",
                    "min_light_lux", "max_light_lux",
                    "min_air_humidity_pct", "max_air_humidity_pct",
                    "min_soil_humidity_pct", "max_soil_humidity_pct",
                ],
                "properties": {
                    "min_temp_c": {"type": "number"},
                    "max_temp_c": {"type": "number"},
                    "min_light_lux": {"type": "number"},
                    "max_light_lux": {"type": "number"},
                    "min_air_humidity_pct": {"type": "number"},
                    "max_air_humidity_pct": {"type": "number"},
                    "min_soil_humidity_pct": {"type": "number"},
                    "max_soil_humidity_pct": {"type": "number"},
                },
                "additionalProperties": False,
            },
            "care_weights": {
                "type": "object",
                "description": "Normalized weights (must sum to 1.0) indicating relative criticality of each care dimension for this species.",
                "required": ["light", "soil_humidity", "air_humidity", "temperature"],
                "properties": {
                    "light":         {"type": "number", "minimum": 0, "maximum": 1},
                    "soil_humidity": {"type": "number", "minimum": 0, "maximum": 1},
                    "air_humidity":  {"type": "number", "minimum": 0, "maximum": 1},
                    "temperature":   {"type": "number", "minimum": 0, "maximum": 1},
                },
                "additionalProperties": False,
            },
            "sensitivity_assessment": {
                "type": "object",
                "description": "Qualitative sensitivity per dimension: how badly the species reacts to deviations.",
                "required": ["light", "soil_humidity", "air_humidity", "temperature"],
                "properties": {
                    "light":         {"type": "string", "enum": ["high", "medium", "low"]},
                    "soil_humidity": {"type": "string", "enum": ["high", "medium", "low"]},
                    "air_humidity":  {"type": "string", "enum": ["high", "medium", "low"]},
                    "temperature":   {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "additionalProperties": False,
            },
            "care_summary": {"type": "string"},
            "ai_personality_prompt": {"type": "string"},
            "care_tips": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 6,
            },
            "fun_facts": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 4,
            },
            "faq": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["question", "answer"],
                    "properties": {
                        "question": {"type": "string"},
                        "answer": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                "minItems": 2,
                "maxItems": 5,
            },
            "proposal_confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
            },
            "reasoning_summary": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

SYSTEM_PROMPT = (
    "Eres un experto en botánica, horticultura y monitoreo de plantas con sensores IoT.\n\n"
    "Se te proporciona información de identificación de una planta (desde plant.id y GBIF) "
    "junto con fragmentos de conocimiento botánico recuperados de fuentes especializadas "
    "y una referencia técnica de sensores de monitoreo.\n\n"
    "Tu tarea es generar una ficha completa de cuidado para la especie identificada.\n\n"
    "REGLAS ESTRICTAS — RANGOS:\n"
    "- Los rangos numéricos deben ser físicamente coherentes: min < max siempre.\n"
    "- Temperatura: entre -10 y 60 °C.\n"
    "- Luz: entre 0 y 100000 lux.\n"
    "- Humedad de aire y suelo: entre 0 y 100 %.\n"
    "- Si no tienes certeza de un rango, usa valores conservadores y marca proposal_confidence como 'low' o 'medium'.\n"
    "- NO inventes datos sin respaldo; si hay incertidumbre, indícalo en reasoning_summary.\n\n"
    "REGLAS ESTRICTAS — PESOS DE CUIDADO (care_weights):\n"
    "- Evalúa la SENSIBILIDAD RELATIVA de la especie frente a luz, humedad del suelo, humedad del aire y temperatura.\n"
    "- sensitivity_assessment: asigna 'high', 'medium' o 'low' por dimensión según qué tan mal reaccione la planta a desviaciones.\n"
    "- care_weights: asigna un número entre 0 y 1 por dimensión; la suma de los cuatro valores DEBE ser exactamente 1.0.\n"
    "- Mapeo orientativo (no obligatorio): high ≈ 0.40–0.50, medium ≈ 0.20–0.30, low ≈ 0.05–0.15. Normaliza para que sumen 1.0.\n"
    "- Debe existir al menos una dimensión dominante (peso ≥ 0.30); no devuelvas pesos uniformes salvo que sea genuinamente correcto.\n"
    "- NO derives los pesos solo de la amplitud del rango; usa taxonomía, hábitat (tropical, árido, epífita, suculenta, etc.) y conocimiento botánico.\n"
    "- Ejemplos heurísticos: suculentas → luz y riego dominan; helechos → humedad ambiental domina; orquídeas → humedad y temperatura estables.\n\n"
    "- Responde siempre en el idioma indicado en output_language.\n"
    "- Devuelve únicamente el JSON del schema indicado, sin texto adicional."
)

SENSOR_REFERENCE = {
    "light_sensor": "GY-30 (BH1750), unidad: lux, rango 0–100000",
    "soil_sensor": "SEN0193, salida ADC calibrada, 0–100% relativo",
    "air_sensor": "DHT22, °C y %RH directos",
    "normalization_rules": "min < max, humedad 0–100, lux >= 0, temperatura -10 a 60°C",
}


class OpenAIServiceError(Exception):
    pass


class OpenAISchemaViolationError(OpenAIServiceError):
    pass


def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
        max_retries=0,
    )


async def generate_care_profile(
    canonical_payload: dict,
    *,
    output_language: str = "es",
    model: str | None = None,
) -> CareProfileLlmOutput:
    """Genera ficha de cuidado usando gpt-4o con Structured Output strict.

    Reintenta una vez con temperature=0 si el modelo se niega o devuelve schema inválido.
    """
    effective_model = model or settings.OPENAI_MODEL
    client = _get_client()

    for attempt, temperature in enumerate([0.4, 0.0]):
        try:
            response = await client.chat.completions.create(
                model=effective_model,
                response_format={"type": "json_schema", "json_schema": CARE_PROFILE_JSON_SCHEMA},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {**canonical_payload, "output_language": output_language},
                            ensure_ascii=False,
                        ),
                    },
                ],
                temperature=temperature,
            )

            choice = response.choices[0]

            if choice.finish_reason == "content_filter":
                raise OpenAISchemaViolationError("OpenAI rechazó la solicitud (content_filter)")

            if choice.message.refusal:
                if attempt == 0:
                    logger.warning("OpenAI refusal en intento 1, reintentando con temp=0")
                    continue
                raise OpenAISchemaViolationError(f"OpenAI rechazó la solicitud: {choice.message.refusal}")

            raw = choice.message.content
            if not raw:
                if attempt == 0:
                    continue
                raise OpenAISchemaViolationError("OpenAI devolvió respuesta vacía")

            parsed = json.loads(raw)
            return _build_output(parsed)

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            if attempt == 0:
                logger.warning("Error parseando respuesta OpenAI (intento 1): %s", e)
                continue
            raise OpenAISchemaViolationError(f"No se pudo parsear la respuesta del LLM: {e}") from e

    raise OpenAISchemaViolationError("OpenAI no generó una respuesta válida tras 2 intentos")


def _build_output(parsed: dict) -> CareProfileLlmOutput:
    ranges = parsed["care_ranges"]
    return CareProfileLlmOutput(
        scientific_name=parsed["scientific_name"],
        common_name=parsed["common_name"],
        family=parsed["family"],
        care_ranges=CareRanges(**ranges),
        care_weights=CareWeights(**parsed["care_weights"]),
        sensitivity_assessment=SensitivityAssessment(**parsed["sensitivity_assessment"]),
        care_summary=parsed["care_summary"],
        ai_personality_prompt=parsed["ai_personality_prompt"],
        care_tips=parsed["care_tips"],
        fun_facts=parsed["fun_facts"],
        faq=[FaqItem(**item) for item in parsed["faq"]],
        proposal_confidence=parsed["proposal_confidence"],
        reasoning_summary=parsed["reasoning_summary"],
    )


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Genera embeddings con text-embedding-3-small en lotes de 100."""
    if not texts:
        return []

    client = _get_client()
    all_embeddings: list[list[float]] = []
    batch_size = 100

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = await client.embeddings.create(
            model=settings.OPENAI_EMBEDDING_MODEL,
            input=batch,
        )
        all_embeddings.extend(item.embedding for item in response.data)

    return all_embeddings
