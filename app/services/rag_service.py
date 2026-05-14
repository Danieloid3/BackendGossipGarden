"""Recupera fragmentos botánicos relevantes desde botanical_chunks en Supabase pgvector.

Degrada graciosamente: si RAG_ENABLED=False, si la tabla está vacía, o si
pgvector/RPC falla, devuelve [] y el pipeline continúa normalmente.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.db.supabase import supabase
from app.schemas.identification import RagChunk
from app.services.openai_service import embed_texts

logger = logging.getLogger(__name__)

_rpc_error_logged = False


async def retrieve_context(
    scientific_name: str,
    family: str | None,
    *,
    top_k: int | None = None,
    min_similarity: float | None = None,
) -> list[RagChunk]:
    """Genera embedding de la consulta y llama RPC match_botanical_chunks."""
    if not settings.RAG_ENABLED:
        return []

    k = top_k or settings.RAG_TOP_K
    min_sim = min_similarity or settings.RAG_MIN_SIMILARITY

    query_text = f"{scientific_name} ({family or 'unknown family'})"
    try:
        embeddings = await embed_texts([query_text])
        if not embeddings:
            return []
        embedding = embeddings[0]
    except Exception as e:
        logger.warning("RAG: falló generación de embedding: %s", e)
        return []

    params = {
        "query_embedding": embedding,
        "match_count": k,
        "min_similarity": min_sim,
    }
    if family:
        params["family_filter"] = family
    if scientific_name:
        params["scientific_filter"] = scientific_name

    try:
        result = await asyncio.to_thread(
            lambda: supabase.rpc("match_botanical_chunks", params).execute()
        )
        rows = result.data or []
        return [
            RagChunk(
                content=row["content"],
                source=row["source"],
                scientific_name=row.get("scientific_name"),
                family=row.get("family"),
                similarity=row["similarity"],
            )
            for row in rows
        ]
    except Exception as e:
        global _rpc_error_logged
        if not _rpc_error_logged:
            logger.warning(
                "RAG: RPC match_botanical_chunks falló (se desactiva para esta sesión): %s", e
            )
            _rpc_error_logged = True
        return []
