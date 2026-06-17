"""Tests del ConnectionManager de WebSocket."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.websocket_manager import ConnectionManager


@pytest.mark.asyncio
async def test_connect_accepts_and_registers():
    manager = ConnectionManager()
    ws = MagicMock()
    ws.accept = AsyncMock()

    await manager.connect("user-1", ws)

    ws.accept.assert_awaited_once()
    assert ws in manager._connections["user-1"]


@pytest.mark.asyncio
async def test_send_to_user_returns_zero_if_no_connections():
    manager = ConnectionManager()
    delivered = await manager.send_to_user("ghost", {"hello": "world"})
    assert delivered == 0


@pytest.mark.asyncio
async def test_send_to_user_delivers_to_all_connections():
    manager = ConnectionManager()
    ws1 = MagicMock(); ws1.accept = AsyncMock(); ws1.send_json = AsyncMock()
    ws2 = MagicMock(); ws2.accept = AsyncMock(); ws2.send_json = AsyncMock()
    await manager.connect("user-1", ws1)
    await manager.connect("user-1", ws2)

    payload = {"type": "chat_message", "message": "hola"}
    delivered = await manager.send_to_user("user-1", payload)

    assert delivered == 2
    ws1.send_json.assert_awaited_once_with(payload)
    ws2.send_json.assert_awaited_once_with(payload)


@pytest.mark.asyncio
async def test_send_to_user_cleans_dead_connections():
    manager = ConnectionManager()
    alive = MagicMock(); alive.accept = AsyncMock(); alive.send_json = AsyncMock()
    dead  = MagicMock(); dead.accept  = AsyncMock(); dead.send_json  = AsyncMock(side_effect=RuntimeError("dead"))
    await manager.connect("user-1", alive)
    await manager.connect("user-1", dead)

    delivered = await manager.send_to_user("user-1", {"x": 1})

    assert delivered == 1
    # La conexión muerta se removió, la viva sigue
    assert dead not in manager._connections.get("user-1", [])
    assert alive in manager._connections["user-1"]


@pytest.mark.asyncio
async def test_disconnect_removes_user_key_when_last_connection_gone():
    manager = ConnectionManager()
    ws = MagicMock(); ws.accept = AsyncMock()
    await manager.connect("user-1", ws)

    await manager.disconnect("user-1", ws)

    assert "user-1" not in manager._connections
