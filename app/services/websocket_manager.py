"""Gestor de conexiones WebSocket activas por user_id.

Estado en memoria. Suficiente para una sola instancia del backend.
Si se escala a múltiples réplicas se debe agregar Redis pub/sub.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[user_id].append(ws)
        logger.info("WS conectado para user %s (total=%d)", user_id, len(self._connections[user_id]))

    async def disconnect(self, user_id: str, ws: WebSocket) -> None:
        async with self._lock:
            if ws in self._connections.get(user_id, []):
                self._connections[user_id].remove(ws)
                if not self._connections[user_id]:
                    del self._connections[user_id]
        logger.info("WS desconectado para user %s", user_id)

    async def send_to_user(self, user_id: str, payload: dict) -> int:
        """Envía el payload JSON a todas las conexiones activas del usuario.

        Devuelve el número de conexiones que recibieron el mensaje.
        Las conexiones muertas se limpian automáticamente.
        """
        connections = list(self._connections.get(user_id, []))
        if not connections:
            return 0

        delivered = 0
        dead: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_json(payload)
                delivered += 1
            except Exception as e:
                logger.warning("Falló envío WS a user %s: %s", user_id, e)
                dead.append(ws)

        for ws in dead:
            await self.disconnect(user_id, ws)

        return delivered


# Singleton del manager
manager = ConnectionManager()
