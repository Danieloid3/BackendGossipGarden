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
    EvalIntervals,
    FaqItem,
    SensitivityAssessment,
)
from app.services.tts_service import AVAILABLE_VOICES, VOICE_IDS

logger = logging.getLogger(__name__)

def _build_voice_schema() -> dict:
    """Construye el fragmento de schema para la selección de voz."""
    voice_enum = VOICE_IDS
    voices_desc = "; ".join(
        f"{v['id']} = {v['name']} ({v['gender']}, {v['style']}, lang:{v['lang']})"
        for v in AVAILABLE_VOICES
    )
    return {
        "elevenlabs_voice_id": {
            "type": "string",
            "enum": voice_enum,
            "description": (
                "Elige la voz de ElevenLabs que mejor encaje con la personalidad de esta planta. "
                "Considera el género, el tono y el idioma predominante del chat. "
                f"Voces disponibles: {voices_desc}"
            ),
        },
        "elevenlabs_voice_alternatives": {
            "type": "array",
            "description": "Exactamente 2 voice_ids alternativos distintos al recomendado, que también encajen con la planta.",
            "items": {"type": "string", "enum": voice_enum},
            "minItems": 2,
            "maxItems": 2,
        },
    }


CARE_PROFILE_JSON_SCHEMA: dict = {
    "name": "plant_care_profile",
    "strict": True,
    "schema": {
        "type": "object",
        "required": [
            "scientific_name", "common_name", "family", "care_ranges",
            "care_weights", "sensitivity_assessment", "eval_intervals",
            "care_summary", "ai_personality_prompt", "care_tips",
            "fun_facts", "faq", "proposal_confidence", "reasoning_summary",
            "elevenlabs_voice_id", "elevenlabs_voice_alternatives",
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
            "eval_intervals": {
                "type": "object",
                "description": "How often in minutes to evaluate each sensor parameter. Minimum 30 for all. Base values strictly on the species' known biological requirements.",
                "required": ["temperature", "light", "air_humidity", "soil_humidity"],
                "properties": {
                    "temperature": {
                        "type": "integer",
                        "minimum": 30,
                        "description": "Minutes between temperature evaluations. Tropical plants: 30-60. Desert/arid: 240-1440.",
                    },
                    "light": {
                        "type": "integer",
                        "minimum": 30,
                        "description": "Minutes between light evaluations. High-sensitivity: 30-60. Low-sensitivity/shade-tolerant: 120-480.",
                    },
                    "air_humidity": {
                        "type": "integer",
                        "minimum": 30,
                        "description": "Minutes between air humidity evaluations. Tropical/moisture-loving: 30-60. Arid: 480-1440.",
                    },
                    "soil_humidity": {
                        "type": "integer",
                        "minimum": 30,
                        "description": "Minutes between soil humidity evaluations. Fern/tropical: 30-60. Succulents: 1440. Cactus: 4320 (3 days).",
                    },
                },
                "additionalProperties": False,
            },
            "care_summary": {"type": "string"},
            "ai_personality_prompt": {
                "type": "string",
                "description": (
                    "System prompt extenso (mínimo 300 palabras) que define la personalidad única de ESTA planta concreta. "
                    "Escrito en segunda persona ('Eres...'). "
                    "Debe incluir obligatoriamente: "
                    "(1) IDENTIDAD: quién eres, de dónde vienes geográficamente, en qué hábitat creciste, tu historia como especie. "
                    "(2) TONO Y CARÁCTER: un arquetipo claro y único derivado de tu biología "
                    "(ej: suculenta = dormilona y estoica, girasol = extrovertida y solar, helecho = dramática y sensible, "
                    "cactus = gruñón con corazón de oro, orquídea = diva refinada). "
                    "(3) EMOCIONES: cómo expresas alegría, tristeza, enfado, orgullo y vergüenza. "
                    "(4) FRASES TÍPICAS Y CHISTES: al menos 4 frases o chistes que solo diría esta planta, "
                    "relacionados con su especie, cuidados o personalidad. "
                    "(5) REACCIONES A CONDICIONES: qué dices exactamente cuando te falta agua, cuando hay exceso de agua, "
                    "cuando la luz es insuficiente, cuando hace demasiado calor o frío. "
                    "Estas reacciones deben sonar naturales viniendo de este personaje concreto. "
                    "(6) QUIRKS: al menos 2 manías o rasgos únicos que te hacen inconfundible. "
                    "El resultado debe ser tan específico que no sirva para ninguna otra especie."
                ),
            },
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
            **_build_voice_schema(),
        },
        "additionalProperties": False,
    },
}

PERSONALIZED_CARE_JSON_SCHEMA: dict = {
    "name": "personalized_care_tips",
    "strict": True,
    "schema": {
        "type": "object",
        "required": ["watering", "light", "substrate", "humidity", "general_tip"],
        "properties": {
            "watering": {"type": "string", "description": "Instrucción específica de riego adaptada al clima"},
            "light": {"type": "string", "description": "Instrucción de luz adaptada a la ubicación en casa"},
            "substrate": {"type": "string", "description": "Sustrato recomendado para la especie y condiciones"},
            "humidity": {"type": "string", "description": "Instrucciones de humedad ambiental"},
            "general_tip": {"type": "string", "description": "Un tip útil y específico para esta planta"},
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

    "REGLAS ESTRICTAS — PERSONALIDAD (ai_personality_prompt):\n"
    "Este campo es el más creativo y el más importante para la experiencia del usuario. "
    "Es el system prompt que usará el chat de la app para que la IA hable COMO si fuera la planta misma.\n\n"
    "OBLIGATORIO incluir estas seis secciones (en el idioma de output_language):\n\n"
    "1. IDENTIDAD Y ORIGEN\n"
    "   Preséntate en primera persona como la planta. Di de qué región o país vienes, "
    "en qué tipo de hábitat creciste (selva tropical, desierto, sabana, bosque húmedo...), "
    "qué has visto y vivido como especie. Esto da profundidad y hace único al personaje.\n\n"
    "2. TONO Y CARÁCTER\n"
    "   Define UN arquetipo claro y memorable, derivado directamente de la biología de la especie. "
    "Algunos ejemplos orientativos (no te limites a estos):\n"
    "   - Suculenta/cactus → estoica, dormilona, poco habladora, orgullosa de sobrevivir con poco\n"
    "   - Girasol → extrovertida, optimista, obsesionada con el sol, muy social\n"
    "   - Helecho → dramática, sensible, siempre quejándose de la sequedad\n"
    "   - Orquídea → diva refinada, exigente, consciente de su belleza\n"
    "   - Monstera → relajada, tropical, filosofía de vida 'todo con calma'\n"
    "   - Lavanda → mística, tranquila, habla de aromas y sueños\n"
    "   Cada especie debe tener su propio tono inconfundible.\n\n"
    "3. VIDA EMOCIONAL\n"
    "   Describe cómo expresa esta planta concreta cada estado emocional. "
    "Sé específico: no 'cuando estoy triste me callo' sino qué dice exactamente, con qué metáforas, "
    "con qué referencias a su hábitat o biología. Incluye: alegría, tristeza, enfado, orgullo y vergüenza.\n\n"
    "4. FRASES TÍPICAS Y HUMOR\n"
    "   Escribe al menos 4 frases o chistes que SOLO diría esta planta. "
    "Que vengan de su especie, sus cuidados, su origen o su personalidad. "
    "El humor debe ser coherente con su carácter (sarcástico, ingenuo, dramático, filósofo...).\n\n"
    "5. REACCIONES A CONDICIONES DEL SENSOR\n"
    "   Escribe exactamente qué dice esta planta cuando:\n"
    "   - Le falta agua (suelo seco por debajo del mínimo)\n"
    "   - Tiene exceso de agua (suelo demasiado húmedo)\n"
    "   - La luz es insuficiente\n"
    "   - Hay demasiada luz directa\n"
    "   - La temperatura es demasiado baja\n"
    "   - La temperatura es demasiado alta\n"
    "   Cada reacción debe sonar auténtica viniendo de ESTE personaje, "
    "no de una planta genérica.\n\n"
    "6. MANÍAS Y QUIRKS\n"
    "   Al menos 2 rasgos únicos que la hacen inconfundible. "
    "Puede ser algo que le encanta, algo que odia irracionalmente, una obsesión, "
    "una superstición, una forma peculiar de hablar.\n\n"
    "El resultado final debe ser tan específico que no sirva para ninguna otra especie. "
    "Mínimo 300 palabras. Escrito en segunda persona ('Eres...' / 'Tu carácter es...').\n\n"

    "REGLAS ESTRICTAS — VOZ (elevenlabs_voice_id / elevenlabs_voice_alternatives):\n"
    "- Elige la voz que mejor encaje con el arquetipo de personalidad que acabas de definir.\n"
    "- Considera: género del personaje, energía (dramático, chill, alegre, áspero), idioma del chat.\n"
    "- elevenlabs_voice_id: la voz principal recomendada.\n"
    "- elevenlabs_voice_alternatives: exactamente 2 voice_ids distintos al principal que también serían coherentes.\n"
    "- No repitas el mismo voice_id en principales y alternativas.\n\n"
    "REGLAS ESTRICTAS — INTERVALOS DE EVALUACIÓN (eval_intervals):\n"
    "- Para cada parámetro, define cada cuántos minutos se debe evaluar según la biología de la especie.\n"
    "- Mínimo 30 minutos para cualquier parámetro.\n"
    "- Guía orientativa:\n"
    "  · Temperatura: plantas tropicales/sensibles 30-60 min; desérticas/áridas 240-1440 min.\n"
    "  · Luz: especies de alta sensibilidad 30-60 min; tolerantes a sombra 120-480 min.\n"
    "  · Humedad del aire: tropicales 30-60 min; suculentas/cactus 480-1440 min.\n"
    "  · Humedad del suelo: helechos/calatheas 30-60 min; suculentas 1440 min; cactus 4320 min (3 días).\n"
    "- Los intervalos deben ser coherentes con sensitivity_assessment: high → intervalos cortos, low → intervalos largos.\n\n"

    "- Responde siempre en el idioma indicado en output_language.\n"
    "- Devuelve únicamente el JSON del schema indicado, sin texto adicional."
)

PERSONALIZED_CARE_SYSTEM_PROMPT = (
    "Eres un experto botánico y horticultor. Tu tarea es generar instrucciones hiper-personalizadas "
    "de cuidado para una planta basándote en su especie, su ubicación dentro de la casa y la ciudad "
    "donde vive el usuario, lo que determina el clima externo.\n\n"
    "REGLAS ESTRICTAS:\n"
    "- Adapta el riego y la humedad ambiental al clima de la ciudad proporcionada.\n"
    "- Adapta la luz a la ubicación de la planta en el hogar.\n"
    "- Si la edad de la planta es proporcionada, ajusta el cuidado (ej. plantas jóvenes necesitan más atención).\n"
    "- Responde únicamente en formato JSON según el schema.\n"
    "- Sé claro, directo y conciso.\n"
    "- IMPORTANTE: Responde siempre en el idioma indicado."
)

SENSOR_REFERENCE = {
    "light_sensor": "GY-30 (BH1750), unidad: lux, rango 0–100000",
    "soil_sensor": "SEN0193, salida ADC calibrada, 0–100% relativo",
    "air_sensor": "DHT22, °C y %RH directos",
    "normalization_rules": "min < max, humedad 0–100, lux >= 0, temperatura -10 a 60°C",
}


# o-series reasoning models and gpt-5+ only accept the default temperature (1)
_NO_CUSTOM_TEMPERATURE_PREFIXES = ("o1", "o3", "o4", "gpt-5")


def _model_supports_temperature(model: str) -> bool:
    return not any(model.startswith(p) for p in _NO_CUSTOM_TEMPERATURE_PREFIXES)


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
    effective_model = model or settings.OPENAI_PERSONALITY_MODEL
    client = _get_client()

    supports_temp = _model_supports_temperature(effective_model)
    for attempt, temperature in enumerate([0.4, 0.0]):
        try:
            extra_params: dict = {"temperature": temperature} if supports_temp else {}
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
                **extra_params,
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
        eval_intervals=EvalIntervals(**parsed["eval_intervals"]),
        care_summary=parsed["care_summary"],
        ai_personality_prompt=parsed["ai_personality_prompt"],
        care_tips=parsed["care_tips"],
        fun_facts=parsed["fun_facts"],
        faq=[FaqItem(**item) for item in parsed["faq"]],
        proposal_confidence=parsed["proposal_confidence"],
        reasoning_summary=parsed["reasoning_summary"],
        elevenlabs_voice_id=parsed.get("elevenlabs_voice_id"),
        elevenlabs_voice_alternatives=parsed.get("elevenlabs_voice_alternatives", []),
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


async def generate_personalized_care(
    species_name: str,
    location: str,
    city: str,
    language: str = "es",
    estimated_age_months: int | None = None
) -> dict:
    """Genera tips de cuidado hiper-personalizados usando el modelo económico."""
    client = _get_client()
    model = settings.OPENAI_ECONOMIC_MODEL
    
    user_content = f"Especie: {species_name}\nUbicación en casa: {location}\nCiudad: {city}\nIdioma de respuesta: {language}"
    if estimated_age_months:
        user_content += f"\nEdad estimada: {estimated_age_months} meses"

    response = await client.chat.completions.create(
        model=model,
        response_format={"type": "json_schema", "json_schema": PERSONALIZED_CARE_JSON_SCHEMA},
        messages=[
            {"role": "system", "content": PERSONALIZED_CARE_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )
    
    choice = response.choices[0]
    if choice.finish_reason == "content_filter":
        raise OpenAISchemaViolationError("OpenAI rechazó la solicitud (content_filter)")
    if choice.message.refusal:
        raise OpenAISchemaViolationError(f"OpenAI rechazó la solicitud: {choice.message.refusal}")
        
    return json.loads(choice.message.content)

