"""Tests de humo de la app — verifican arranque, rutas y auth sin tocar BD."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


# ─── Salud de la app ──────────────────────────────────────────────────────────

async def test_health_endpoint_returns_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"


async def test_openapi_schema_builds():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert schema["info"]["title"] == "Gossip Garden API"


# ─── Rutas registradas ────────────────────────────────────────────────────────

def test_expected_routes_registered():
    paths = {route.path for route in app.routes}
    expected = {
        "/api/v1/health",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/plants/",
        "/api/v1/sensors/",
        "/api/v1/identify",
        "/api/v1/species/from-candidate",
    }
    missing = expected - paths
    assert not missing, f"Rutas no registradas en la app: {missing}"


# ─── Autenticación ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("method,path", [
    ("GET", "/api/v1/plants/"),
    ("POST", "/api/v1/plants/"),
])
async def test_protected_endpoints_require_auth(method, path):
    """Sin header Authorization los endpoints protegidos deben devolver 401/403."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.request(method, path)
    assert r.status_code in (401, 403), (
        f"{method} {path} devolvió {r.status_code} en lugar de 401/403"
    )


async def test_identify_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/identify")
    assert r.status_code in (401, 403, 422)


# ─── Integridad del OpenAPI ───────────────────────────────────────────────────

async def test_openapi_has_identify_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        schema = (await c.get("/openapi.json")).json()
    assert "/api/v1/identify" in schema["paths"]


async def test_openapi_has_plants_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        schema = (await c.get("/openapi.json")).json()
    assert "/api/v1/plants/" in schema["paths"]


async def test_openapi_has_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        schema = (await c.get("/openapi.json")).json()
    assert "/api/v1/health" in schema["paths"]


# ─── Rutas de chat (TTS) ──────────────────────────────────────────────────────

def test_chat_routes_registered():
    """Verifica que todas las rutas de chat documentadas en API_CONTRACT.md existen."""
    paths = {route.path for route in app.routes}
    expected_chat = {
        "/api/v1/chat/{plant_id}",
        "/api/v1/chat/{plant_id}/history",
        "/api/v1/chat/{plant_id}/voices",
        "/api/v1/chat/{plant_id}/voice",
    }
    missing = expected_chat - paths
    assert not missing, f"Rutas de chat no registradas: {missing}"


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/v1/chat/00000000-0000-0000-0000-000000000001"),
    ("GET", "/api/v1/chat/00000000-0000-0000-0000-000000000001/history"),
    ("GET", "/api/v1/chat/00000000-0000-0000-0000-000000000001/voices"),
    ("PATCH", "/api/v1/chat/00000000-0000-0000-0000-000000000001/voice"),
])
async def test_chat_endpoints_require_auth(method, path):
    """Endpoints de chat deben requerir JWT (401/403 sin Authorization header)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.request(method, path)
    assert r.status_code in (401, 403), (
        f"{method} {path} devolvió {r.status_code} en lugar de 401/403"
    )


async def test_sensors_endpoint_does_not_require_auth():
    """POST /sensors NO requiere auth (diseñado para hardware IoT ESP32).
    Documentado en API_CONTRACT.md sección 4.1."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/sensors/", json={})
    # Debe responder 422 (validation error por body vacío), NUNCA 401/403
    assert r.status_code not in (401, 403), (
        f"POST /sensors/ devolvió {r.status_code} — debería ser público para IoT"
    )
