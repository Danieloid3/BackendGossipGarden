"""Fixtures para tests de integración live.

Correr con:
    PYTHONPATH=. pytest tests_live/ -m live -v

NUNCA correr junto con tests/ — el conftest de tests/ sobreescribe
las env vars con valores fake.

Planta de prueba dedicada:
  - Se crea en Supabase al inicio de la sesión de tests.
  - Se borra (junto con sus logs en Firestore) al finalizar.
  - Los datos de producción no se tocan.
"""
from __future__ import annotations

import pytest
import redis.asyncio as redis_asyncio

from app.core.config import settings
from app.db.supabase import supabase

# ─── Constantes de prueba ─────────────────────────────────────────────────────

# Planta dedicada a tests — UUID fijo, nunca aparece en producción
TEST_PLANT_ID = "cafecafe-cafe-4000-a000-cafecafecafe"

# Usuario real existente en Supabase (dueño de la planta de prueba)
TEST_USER_ID = "f9c11ced-2085-4acf-996f-7c2320703132"

# Especie Árbol de caucho (Ficus elastica) — tiene ai_personality_prompt en Supabase
TEST_SPECIES_ID = "fcb9e7d4-5d4c-42f8-bebb-b4db05f4bbde"


# ─── Fixtures de sesión ───────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def test_plant():
    """Crea la planta de prueba en Supabase y la elimina con sus logs al terminar."""
    supabase.table("plants").upsert({
        "plant_id": TEST_PLANT_ID,
        "user_id": TEST_USER_ID,
        "species_id": TEST_SPECIES_ID,
        "nickname": "[TEST] Árbol de caucho",
        "health_status": "healthy",
        "health_score": 100.0,
    }).execute()

    yield TEST_PLANT_ID

    # Teardown: borrar logs de Firestore y la planta de Supabase
    try:
        from app.db.firebase import firebase_db
        firebase_db.collection("plants").document(TEST_PLANT_ID)\
            .collection("chat_logs").document(TEST_USER_ID).delete()
        firebase_db.collection("plants").document(TEST_PLANT_ID)\
            .collection("chat_meta").document(TEST_USER_ID).delete()
    except Exception:
        pass

    supabase.table("plants").delete().eq("plant_id", TEST_PLANT_ID).execute()


# ─── Fixtures de función ──────────────────────────────────────────────────────

@pytest.fixture
async def redis_client():
    """Cliente Redis real. Limpia las claves de caché del plant de prueba al terminar."""
    client = redis_asyncio.from_url(settings.REDIS_URL, decode_responses=True)
    yield client
    try:
        await client.delete(f"chat:{TEST_USER_ID}:{TEST_PLANT_ID}")
        await client.delete(f"chat:summary:{TEST_USER_ID}:{TEST_PLANT_ID}")
    except Exception:
        pass
    await client.aclose()
