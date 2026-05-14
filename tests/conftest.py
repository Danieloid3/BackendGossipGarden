"""Fixtures compartidas para el suite de tests del backend GossipGarden."""

from __future__ import annotations

import json
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

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
    """Mock del cliente supabase para evitar conexiones reales."""
    with patch("app.db.supabase.supabase") as mock:
        # Cadena de llamadas: .table().select().eq().execute()
        table_mock = MagicMock()
        mock.table.return_value = table_mock
        table_mock.select.return_value = table_mock
        table_mock.insert.return_value = table_mock
        table_mock.upsert.return_value = table_mock
        table_mock.eq.return_value = table_mock
        table_mock.order.return_value = table_mock
        table_mock.limit.return_value = table_mock
        table_mock.execute.return_value = MagicMock(data=[])
        mock.rpc.return_value = MagicMock(execute=MagicMock(return_value=MagicMock(data=[])))
        yield mock
