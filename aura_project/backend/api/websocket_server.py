"""
WebSocket Server – bridge mezi Python backendem a webovým frontendem.
"""

import asyncio
import json
from typing import Callable, Optional, Set

import websockets
from websockets.server import WebSocketServerProtocol

from backend.config.settings import Settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class WebSocketServer:
    """WebSocket server pro komunikaci s frontendem."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._clients: Set[WebSocketServerProtocol] = set()
        self._server = None
        self.on_client_command: Optional[Callable] = None

    async def start(self):
        """Spustí WebSocket server."""
        self._server = await websockets.serve(
            self._handle_client,
            self.settings.ws_host,
            self.settings.ws_port
        )
        logger.info(f"🌐 WebSocket server běží na ws://{self.settings.ws_host}:{self.settings.ws_port}")

    async def stop(self):
        """Zastaví server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_client(self, websocket: WebSocketServerProtocol, path: str):
        """Zpracuje připojeného klienta."""
        self._clients.add(websocket)
        logger.info(f"🔗 Klient připojen: {websocket.remote_address}")

        try:
            async for message in websocket:
                try:
                    command = json.loads(message)
                    if self.on_client_command:
                        await self.on_client_command(command)
                except json.JSONDecodeError:
                    logger.warning(f"Neplatný JSON: {message}")

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)
            logger.info("🔌 Klient odpojen")

    async def broadcast(self, data: dict):
        """Odešle data všem připojeným klientům."""
        if not self._clients:
            return

        message = json.dumps(data, ensure_ascii=False)
        disconnected = set()

        for client in self._clients:
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)

        self._clients -= disconnected
