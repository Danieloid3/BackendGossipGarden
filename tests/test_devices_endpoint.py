"""Tests del endpoint REST de devices (FCM token registration)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_register_device_returns_201_with_data(client):
    inserted_row = {
        "id": "00000000-0000-0000-0000-000000000010",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "token": "fcm-token-abc",
        "platform": "ios",
        "created_at": "2026-05-28T14:00:00",
        "last_used_at": "2026-05-28T14:00:00",
    }
    with patch("app.api.v1.endpoints.devices.supabase") as sb:
        sb.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[inserted_row])
        res = await client.post("/api/v1/devices", json={"token": "fcm-token-abc", "platform": "ios"})

    assert res.status_code == 201
    body = res.json()
    assert body["token"] == "fcm-token-abc"
    assert body["platform"] == "ios"


@pytest.mark.asyncio
async def test_register_device_rejects_invalid_platform(client):
    res = await client.post("/api/v1/devices", json={"token": "x", "platform": "windows-phone"})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_register_device_rejects_empty_token(client):
    res = await client.post("/api/v1/devices", json={"token": "", "platform": "ios"})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_unregister_device_returns_204(client):
    with patch("app.api.v1.endpoints.devices.supabase") as sb:
        sb.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        res = await client.delete("/api/v1/devices/fcm-token-abc")
    assert res.status_code == 204
