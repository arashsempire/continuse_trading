import asyncio
from typing import List

# Assuming components are in the same directory/package
from .WSConnection import WSConnectionManager
from .WSSubscription import SubscriptionManager
from .WSMessage_Processor import WSMessageProcessor
from ...utils import BaseLogger


class WebSocketClient(BaseLogger):
    """
    Main WebSocket client orchestrator for LBank.

    Manages connection, subscriptions, and message processing.
    """

    def __init__(self, config: dict, pair: str = "eth_usdt"):
        """
        Initializes the WebSocket client.

        Args:
            config (dict): Configuration dictionary containing API keys, URLs.
            pair (str): The primary trading pair to monitor. Defaults to "eth_usdt".
        """
        super().__init__()
        self.config = config
        self.pair = pair
        self.tasks: List[asyncio.Task] = []

        # Validate necessary config
        ws_uri = self.config.get("WEBSOCKET_URI")
        api_key = self.config.get("API_KEY")
        api_secret = self.config.get("API_SECRET")

        if not ws_uri:
            self.log.error("WebSocket URI is missing in configuration.")
            raise ValueError(
                "WebSocket URI (WEBSOCKET_URI) not found in configuration."
            )
        if not api_key or not api_secret:
            self.log.warning(
                "API Key or Secret missing. Private subscriptions will fail."
            )

        # Initialize components
        self.manager = WSConnectionManager(ws_uri)
        self.processor = WSMessageProcessor()
        self.subscription = SubscriptionManager(
            api_key, api_secret, self.pair, self.config
        )

        # Register message handlers
        self.processor.register_handler("kbar", self._handle_kbar_message)
        self.processor.register_handler("orderUpdate", self._handle_order_update)
        self.processor.register_handler("assetUpdate", self._handle_asset_update)

        self.log.info("WebSocketClient initialized", target_pair=self.pair)

    async def start(self) -> None:
        """Connects to the WebSocket and starts managing subscriptions and messages."""
        self.log.info(f"Starting WebSocket client for pair: {self.pair}")
        await self.manager.connect()  # Establish the WebSocket connection

        if self.manager.connection and not self.manager.connection.closed:
            self.log.info("WebSocket connection established. Starting tasks.")

            # Create and start tasks for WebSocket management and subscriptions
            self.tasks = [
                asyncio.create_task(
                    self.manager.listen(self.processor), name="WSListener"
                ),
                asyncio.create_task(
                    self.manager.check_connection(), name="WSConnectionCheck"
                ),
                asyncio.create_task(
                    self._subscribe_to_streams(), name="WSSubscriptions"
                ),
            ]

            try:
                # Wait for tasks to complete or fail
                await asyncio.gather(*self.tasks)
            except asyncio.CancelledError:
                self.log.info("WebSocket tasks cancelled.")
            except Exception as e:
                self.log.exception(
                    "An unexpected error occurred in WebSocket tasks.", error=str(e)
                )
            finally:
                self.log.info("Shutting down WebSocket client.")
                await self.stop()
        else:
            self.log.error("Failed to establish WebSocket connection. Shutting down.")
            await self.stop()

    async def _subscribe_to_streams(self):
        """Handles subscriptions to WebSocket streams."""
        try:
            await self.subscription.subscribe_kbar(
                self.manager.connection, self.pair, kbar="1min"
            )
            await self.subscription.request_kbar(
                self.manager.connection, self.pair, kbar="day"
            )
            await self.subscription.subscribe_order_updates(
                self.manager.connection, pair="all"
            )
            await self.subscription.subscribe_asset_updates(self.manager.connection)
            self.log.info("Subscribed to all necessary WebSocket streams.")
        except Exception as e:
            self.log.error("Subscription to WebSocket streams failed.", error=str(e))
            raise

    async def _handle_kbar_message(self, message: dict):
        """Handles incoming kbar updates."""
        self.log.info("KBar message received.", message=message)
        # Add specific kbar processing logic here

    async def _handle_order_update(self, message: dict):
        """Handles incoming order updates."""
        self.log.info("Order update message received.", message=message)
        # Add specific order update processing logic here

    async def _handle_asset_update(self, message: dict):
        """Handles incoming asset updates."""
        self.log.info("Asset update message received.", message=message)
        # Add specific asset update processing logic here

    async def stop(self) -> None:
        """Stops all running tasks and closes connections."""
        self.log.info(f"Stopping WebSocket client for pair: {self.pair}")

        # Cancel all running tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()
                self.log.debug(f"Cancelling task: {task.get_name()}")

        # Wait for tasks to acknowledge cancellation
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []  # Clear task list

        # Cleanup resources
        await self.subscription.delete_subscribe_key()
        await self.manager.stop()
        await self.subscription.close_client()

        self.log.info("WebSocket client stopped.")
