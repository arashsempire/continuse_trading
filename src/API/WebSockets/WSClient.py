import os
import asyncio
import logging  # Import standard logging
import structlog

# from dotenv import load_dotenv

# Assuming components are in the same directory/package
from .WSConnection import WSConnectionManager
from .WSSubscription import SubscriptionManager
from .WSMessage_Processor import MessageProcessor

from ..API_utils import load_config, API_KEY, API_SECRET, WEBSOCKET_URI
from ...utils import BaseLogger, configure_logging


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
        # self.log = self.log.bind(class_name="WebSocketClient") # Redundant

        self.config = config
        self.pair = pair
        self.tasks = []  # To keep track of running asyncio tasks

        # Validate necessary config
        ws_uri = self.config.get(WEBSOCKET_URI)
        api_key = self.config.get(API_KEY)
        api_secret = self.config.get(API_SECRET)

        if not ws_uri:
            self.log.error("WebSocket URI is missing in configuration.")
            raise ValueError(
                "WebSocket URI (WEBSOCKET_URI) not found in configuration."
            )
        if not api_key or not api_secret:
            self.log.warning(
                "API Key or Secret missing. Private subscriptions will fail."
            )
            # Allow running without keys for public data, but log warning.

        # Initialize components
        self.manager = WSConnectionManager(ws_uri)
        # Pass the full config to SubscriptionManager as it needs multiple URLs
        self.subscription = SubscriptionManager(
            api_key, api_secret, self.pair, self.config
        )
        self.message_processor = MessageProcessor()

        self.log.info("WebSocketClient initialized", target_pair=self.pair)

    async def start(self) -> None:
        """Connects to the WebSocket and starts managing subscriptions and messages."""
        self.log.info(f"Starting WebSocket client for pair: {self.pair}")
        await self.manager.connect()  # Establish the initial connection

        if self.manager.connection and not self.manager.connection.closed:
            self.log.info("WebSocket connection established. Starting tasks.")
            # Create and store tasks
            self.tasks = [
                # Listens for incoming messages and passes them to the processor
                asyncio.create_task(
                    self.manager.listen(self.message_processor), name="WSListener"
                ),
                # Periodically checks connection health and triggers reconnects
                asyncio.create_task(
                    self.manager.check_connection(), name="WSConnectionCheck"
                ),
                # --- Subscription Tasks ---
                # Subscribe to public K-bar data (e.g., 1 minute)
                asyncio.create_task(
                    self.subscription.subscribe_kbar(
                        self.manager.connection, pair=self.pair, kbar="1min"
                    ),
                    name="WSSubscribeKbar",
                ),
                # Request initial historical data (e.g., daily candles)
                asyncio.create_task(
                    self.subscription.request_kbar(
                        self.manager.connection, pair=self.pair, kbar="day"
                    ),
                    name="WSRequestKbar",
                ),
                # Subscribe to private data streams (if API keys are provided)
                # These methods now handle getting/refreshing the subscribeKey internally
                asyncio.create_task(
                    self.subscription.subscribe_order_updates(
                        self.manager.connection, pair="all"
                    ),
                    name="WSSubscribeOrders",
                ),  # Subscribe to all pairs' orders
                asyncio.create_task(
                    self.subscription.subscribe_asset_updates(self.manager.connection),
                    name="WSSubscribeAssets",
                ),
            ]

            # Wait for any task to complete (or fail)
            # Using gather might hide individual task failures until all are done.
            # Using wait allows reacting when the first task finishes/errors.
            done, pending = await asyncio.wait(
                self.tasks, return_when=asyncio.FIRST_COMPLETED
            )

            # Log results of completed tasks (especially errors)
            for task in done:
                try:
                    result = task.result()
                    self.log.info(f"Task {task.get_name()} completed.", result=result)
                except Exception as e:
                    self.log.exception(
                        f"Task {task.get_name()} failed unexpectedly.", error=str(e)
                    )

            # Cancel pending tasks if one failed or completed unexpectedly
            self.log.warning(
                "One or more tasks finished. Initiating shutdown sequence."
            )
            for task in pending:
                task.cancel()
                self.log.info(f"Cancelled pending task: {task.get_name()}")

            # Optionally, attempt to restart or handle the failure gracefully
            # For now, we just let it proceed to shutdown

        else:
            self.log.error(
                "Failed to establish initial WebSocket connection. Client cannot start tasks."
            )
            # Attempt cleanup even if connection failed initially
            await self.stop()

    async def stop(self) -> None:
        """Stops all running tasks and closes connections."""
        self.log.info(f"Stopping WebSocket client for pair: {self.pair}")

        # Cancel all running asyncio tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()
                self.log.debug(f"Cancelling task: {task.get_name()}")

        # Wait briefly for tasks to acknowledge cancellation
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
            self.log.info("All tasks cancelled or finished.")
        self.tasks = []  # Clear task list

        # Delete the subscribe key (if it exists)
        await self.subscription.delete_subscribe_key()

        # Close the WebSocket connection
        await self.manager.stop()

        # Close the SubscriptionManager's HTTP client
        await self.subscription.close_client()

        self.log.info("WebSocket client stopped.")


async def main() -> None:
    """Main entry point for the WebSocket client application."""
    # Configure logging (call this early)
    # Set level via environment variable or default to INFO
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    configure_logging(log_level)

    log = structlog.get_logger("main_app")  # Get a logger for the main function

    # Load configuration
    config = load_config()

    # Get target pair from environment or use default
    target_pair = os.getenv("TARGET_PAIR", "eth_usdt")

    client = None
    try:
        # Initialize the client
        client = WebSocketClient(config, pair=target_pair)

        # Start the client and run indefinitely (or until an error stops it)
        await client.start()

    except ValueError as e:
        log.error("Configuration error during client initialization.", error=str(e))
    except Exception as e:
        log.exception(
            "An unexpected error occurred in the main execution loop.", error=str(e)
        )
    finally:
        if client:
            log.info("Initiating final client shutdown.")
            await client.stop()
        log.info("Application finished.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested by user (KeyboardInterrupt).")
        # asyncio's run loop should handle task cancellation on exit
