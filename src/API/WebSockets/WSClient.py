import os
import asyncio
from dotenv import load_dotenv
from .WSConnection import WSConnectionManager
from .WSSubscription import SubscriptionManager
from .WSMessage_Processor import MessageProcessor
from utils import BaseLogger

# Load environment variables from a .env file
load_dotenv()


class WebSocketClient(BaseLogger):
    def __init__(self, uri: str, api_key: str, api_secret: str, pair: str = "eth_usdt"):
        super().__init__()
        self.log = self.log.bind(class_name="WebSocketClient")
        self.manager = WSConnectionManager(uri)
        self.subscription = SubscriptionManager(api_key, api_secret, pair)
        self.message_processor = MessageProcessor()
        self.pair = pair

    async def start(self) -> None:
        self.log.info(f"Starting the client for {self.pair}")
        await self.manager.connect()
        if self.manager.connection:
            self.tasks = [
                asyncio.create_task(self.manager.listen(self.message_processor)),
                asyncio.create_task(self.manager.check_connection()),
                asyncio.create_task(self.subscription.subscribe_kbar(self.manager.connection)),
                asyncio.create_task(self.subscription.request_kbar(self.manager.connection)),
                asyncio.create_task(self.subscription.update_subscribed_order(self.manager.connection)),
                asyncio.create_task(self.subscription.update_subscribed_asset(self.manager.connection)),
            ]
            await asyncio.gather(*self.tasks)
        else:
            self.log.error("Failed to establish WebSocket connection")

    async def stop(self) -> None:
        self.log.info(f"Stopping the client for {self.pair}")
        await self.manager.stop()


async def main() -> None:
    uri = os.getenv("WEBSOCKET_URI", "wss://www.lbkex.net/ws/V2/")
    api_key = os.getenv("LBANK_API_KEY")
    api_secret = os.getenv("LBANK_API_SECRET")

    if not api_key or not api_secret:
        raise ValueError("API key and secret must be set as environment variables")

    client = WebSocketClient(uri, api_key, api_secret)
    await client.start()

if __name__ == "__main__":
    asyncio.run(main())
