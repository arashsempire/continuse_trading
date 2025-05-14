import websockets
import asyncio
import json
from typing import Optional
from .logger import BaseLogger


class WSConnectionManager(BaseLogger):
    def __init__(self, uri: str):
        super().__init__()
        self.log = self.log.bind(class_name="WSConnectionManager")
        self.uri = uri
        self.connection: Optional[websockets.WebSocketClientProtocol] = None
        self.keep_running: bool = True
        self.reconnect_attempts = 0

    async def connect(self) -> None:
        while self.keep_running:
            try:
                self.connection = await websockets.connect(self.uri)
                self.log.info("Connected to WebSocket")
                self.reconnect_attempts = 0
                break
            except Exception as e:
                self.log.warning("Failed to connect to WebSocket", error=str(e))
                self.reconnect_attempts += 1
                self.log.debug("Reconnect attempt", attempt=self.reconnect_attempts)
                await asyncio.sleep(min(2 ** self.reconnect_attempts, 300))

    async def check_connection(self) -> None:
        while self.keep_running:
            await asyncio.sleep(30)
            if self.connection is None or self.connection.closed:
                self.log.warning("Connection lost, attempting to reconnect")
                await self.reconnect()

    async def reconnect(self) -> None:
        self.log.info("Reconnecting")
        await self.stop()
        await self.connect()

    async def stop(self) -> None:
        self.keep_running = False
        if self.connection is not None:
            if not self.connection.closed:
                await self.connection.close()
                self.log.info("WebSocket connection closed")
            else:
                self.log.info("WebSocket connection already closed")
        else:
            self.log.warning("Connection is None, cannot stop")

    async def listen(self, message_processor) -> None:
        while self.keep_running:
            try:
                if self.connection is not None:
                    async for message in self.connection:
                        data = json.loads(message)
                        self.log.info("Received message", data=data)
                        await message_processor.process_incoming_message(data)
                else:
                    self.log.warning("Connection is None, cannot listen")
                    await self.reconnect()
            except json.JSONDecodeError as je:
                self.log.error("JSON Decode Error", error=str(je))
            except websockets.ConnectionClosed:
                self.log.warning("WebSocket connection closed, reconnecting")
                await self.reconnect()
            except Exception as e:
                self.log.error("An error occurred", error=str(e))
                await self.reconnect()
