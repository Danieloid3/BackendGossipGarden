"""Fixtures compartidas para el suite de tests del backend GossipGarden."""

from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

# ============================================================
# BOOTSTRAP — debe ejecutarse antes de cualquier import de app.*
# Fuerza valores test-safe que sobrescriben cualquier .env real,
# garantizando que ningún test alcance Supabase/Firebase/Redis reales.
# ============================================================

os.environ["SUPABASE_URL"] = "http://localhost"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-service-role-key"
os.environ["SUPABASE_JWKS_URL"] = "http://localhost/jwks"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["FIREBASE_CREDENTIALS_JSON"] = ""
os.environ["FIREBASE_CREDENTIALS_PATH"] = "/tmp/firebase_credentials_test.json"
os.environ["MQTT_ENABLED"] = "false"
os.environ["OPENAI_API_KEY"] = "test-openai-key"
os.environ["PLANT_ID_API_KEY"] = "test-plant-id-key"

# Stub de app.db.firebase en sys.modules para evitar que credentials.Certificate(...)
# se ejecute al importar app.main (falla en CI donde no hay fichero de credenciales).
_firebase_stub = types.ModuleType("app.db.firebase")
_firebase_stub.firebase_db = MagicMock()
sys.modules["app.db.firebase"] = _firebase_stub

# ============================================================
# Imports de la app (después del bootstrap)
# ============================================================

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.security import get_current_user
from app.main import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"

FAKE_USER_ID = "00000000-0000-0000-0000-000000000001"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


@pytest.fixture
def plant_id_high():
    return load_fixture("plant_id_response_high.json")


@pytest.fixture
def plant_id_medium():
    return load_fixture("plant_id_response_medium.json")


@pytest.fixture
def plant_id_low():
    return load_fixture("plant_id_response_low.json")


@pytest.fixture
def gbif_response():
    return load_fixture("gbif_species_response.json")


@pytest.fixture
def openai_profile():
    return load_fixture("openai_care_profile.json")


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Cliente HTTP con auth sobrescrita para tests."""
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER_ID
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def mock_supabase():
    """Mock completo del cliente supabase para evitar conexiones reales."""
    with patch("app.db.supabase.supabase") as mock:
        # Cadena completa de llamadas del ORM-like de supabase-py:
        # .table().select/insert/upsert/update/delete().eq/gte/lte/in_/order/limit/maybe_single/single().execute()
        table_mock = MagicMock()
        mock.table.return_value = table_mock
        table_mock.select.return_value = table_mock
        table_mock.insert.return_value = table_mock
        table_mock.upsert.return_value = table_mock
        table_mock.update.return_value = table_mock
        table_mock.delete.return_value = table_mock
        table_mock.eq.return_value = table_mock
        table_mock.gte.return_value = table_mock
        table_mock.lte.return_value = table_mock
        table_mock.in_.return_value = table_mock
        table_mock.order.return_value = table_mock
        table_mock.limit.return_value = table_mock
        table_mock.maybe_single.return_value = table_mock
        table_mock.single.return_value = table_mock
        table_mock.execute.return_value = MagicMock(data=[])
        mock.rpc.return_value = MagicMock(execute=MagicMock(return_value=MagicMock(data=[])))
        yield mock
