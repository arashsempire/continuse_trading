import asyncio
from typing import List, Dict

# Assuming components are in the same directory/package
from .WSConnection import WSConnectionManager
from .WSSubscription import SubscriptionManager
from .WSMessage_Processor import WSMessageProcessor  # Generic base class for type hint
from .logger import BaseLogger  # Assuming BaseLogger is available


class WebSocketClient(BaseLogger):
    """
    Main WebSocket client orchestrator for LBank.
    Manages connection, subscriptions, and delegates message processing.
    """

    def __init__(self, config: Dict, pair: str, message_processor: WSMessageProcessor):
        """
        Initializes the WebSocket client.

        Args:
            config (dict): Configuration dictionary containing API keys, URLs.
            pair (str): The primary trading pair for default subscriptions.
            message_processor (WSMessageProcessor): An instance of a message processor
                                                   (e.g., the LBank-specific MessageProcessor)
                                                   to handle incoming messages.
        """
        super().__init__()
        self.config = config
        self.pair = pair  # Default pair for subscriptions
        self.message_processor = message_processor  # Injected message processor
        self.tasks: List[asyncio.Task] = []

        ws_uri = self.config.get("WEBSOCKET_URI")
        api_key = self.config.get("API_KEY")
        api_secret = self.config.get("API_SECRET")

        if not ws_uri:
            self.log.error("WebSocket URI is missing in configuration.")
            raise ValueError(
                "WebSocket URI (WEBSOCKET_URI) not found in configuration."
            )
        if not api_key or not api_secret:
            # This warning is fine, as some subscriptions (public) might still work.
            self.log.warning(
                "API Key or Secret missing. Private subscriptions will fail."
            )

        self.manager = WSConnectionManager(ws_uri)
        self.subscription = SubscriptionManager(
            api_key, api_secret, self.pair, self.config
        )

        self.log.info(
            f"WebSocketClient initialized for pair: {self.pair} with processor: "
            + f"{self.message_processor.__class__.__name__}"
        )

    async def start(self) -> None:
        """Connects to the WebSocket, starts listening, and manages subscriptions."""
        self.log.info(f"Starting WebSocket client for pair: {self.pair}")
        await self.manager.connect()

        if self.manager.connection and not self.manager.connection.closed:
            self.log.info("WebSocket connection established. Starting core tasks.")

            # The message_processor instance itself should have a method to process messages.
            # For the LBank-specific MessageProcessor, this is process_incoming_message.
            # For a generic WSMessageProcessor, it might be just 'process'.
            # We assume the injected processor has 'process_incoming_message' if it's the LBank one.
            processor_callable = getattr(
                self.message_processor, "process_incoming_message", None
            )
            if not callable(processor_callable):
                # Fallback for a generic processor that might only have `process_data_message`
                processor_callable = getattr(
                    self.message_processor, "process_data_message", None
                )
                if not callable(processor_callable):
                    self.log.error(
                        "Injected message processor does not have a callable 'process_incoming_message' or"
                        + "'process_data_message' method."
                    )
                    await self.stop()
                    return

            self.tasks = [
                asyncio.create_task(
                    self.manager.listen(processor_callable), name="WSListener"
                ),
                asyncio.create_task(
                    self.manager.check_connection(), name="WSConnectionCheck"
                ),
                asyncio.create_task(
                    self._subscribe_to_streams(), name="WSSubscriptions"
                ),
                # Add a task to periodically refresh the subscribeKey if needed
                asyncio.create_task(
                    self._maintain_subscribe_key(), name="WSSubKeyMaintenance"
                ),
            ]

            try:
                await asyncio.gather(*self.tasks)
            except asyncio.CancelledError:
                self.log.info("WebSocket tasks were cancelled.")
            except Exception as e:
                self.log.exception(
                    "An unexpected error occurred in WebSocket tasks.",
                    error_details=str(e),
                )
            finally:
                self.log.info("Shutting down WebSocket client tasks.")
                # Stop will be called by ClientManager or the main application loop
        else:
            self.log.error(
                "Failed to establish WebSocket connection. Cannot start tasks."
            )
            # await self.stop() # Avoid self-stopping if managed externally

    async def _subscribe_to_streams(self):
        """Handles initial subscriptions to WebSocket streams."""
        if not self.manager.connection or self.manager.connection.closed:
            self.log.warning("Cannot subscribe, WebSocket connection is not active.")
            return

        try:
            self.log.info(f"Subscribing to kbar (1min) for {self.pair}.")
            await self.subscription.subscribe_kbar(
                self.manager.connection, self.pair, kbar="1min"
            )

            self.log.info(f"Requesting initial kbar (day) for {self.pair}.")
            await self.subscription.request_kbar(
                self.manager.connection,
                self.pair,
                kbar="day",
                size=10,  # Request a few recent daily candles
            )

            # Example: Subscribe to kbar for another pair if needed, e.g. from config
            # additional_pairs = self.config.get("ADDITIONAL_KBAR_PAIRS", [])
            # for add_pair in additional_pairs:
            #    self.log.info(f"Subscribing to kbar (1min) for additional pair {add_pair}.")
            #    await self.subscription.subscribe_kbar(self.manager.connection, add_pair, kbar="1min")

            if self.config.get("API_KEY") and self.config.get("API_SECRET"):
                self.log.info(
                    "API keys found, attempting to subscribe to private streams."
                )
                # Subscribe to order updates for all pairs associated with the API key
                await self.subscription.subscribe_order_updates(
                    self.manager.connection,
                    pair="all",  # 'all' means all for the authenticated user
                )
                # Subscribe to asset updates
                await self.subscription.subscribe_asset_updates(self.manager.connection)
                self.log.info(
                    "Successfully initiated subscriptions to private streams."
                )
            else:
                self.log.warning(
                    "API_KEY or API_SECRET not configured. Skipping private subscriptions."
                )

            self.log.info("Initial stream subscriptions are set up.")
        except Exception as e:
            self.log.error(
                "Subscription to one or more WebSocket streams failed.",
                error_details=str(e),
            )
            # Depending on severity, might want to raise or attempt retry

    async def _maintain_subscribe_key(self):
        """Periodically extends the validity of the subscribe key."""
        if not (self.config.get("API_KEY") and self.config.get("API_SECRET")):
            self.log.info("Subscribe key maintenance skipped: API keys not configured.")
            return

        try:
            while True:
                # LBank key is valid for 24 hours. Refresh e.g., every 20 hours.
                await asyncio.sleep(20 * 60 * 60)  # 20 hours
                if self.subscription.subscribeKey:
                    self.log.info("Attempting to extend subscribe key validity.")
                    refreshed = await self.subscription.extend_subscribe_key_validity()
                    if refreshed:
                        self.log.info("Subscribe key validity extended successfully.")
                    else:
                        self.log.warning(
                            "Failed to extend subscribe key validity. It might expire soon."
                        )
                else:
                    # This case should ideally be handled by _ensure_key_for_private_subscription
                    # when a private subscription is attempted.
                    self.log.info("No active subscribe key to maintain.")
        except asyncio.CancelledError:
            self.log.info("Subscribe key maintenance task cancelled.")
        except Exception as e:
            self.log.error(f"Error in subscribe key maintenance task: {e}")

    async def stop(self) -> None:
        """Stops all running tasks and cleans up resources."""
        self.log.info(f"Stopping WebSocket client for pair: {self.pair}")

        for task in self.tasks:
            if not task.done():
                task.cancel()
                self.log.debug(f"Cancelling task: {task.get_name()}")

        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []

        # Cleanup resources
        if self.config.get("API_KEY") and self.config.get("API_SECRET"):
            await self.subscription.delete_subscribe_key()  # Attempt to delete key on server

        await self.manager.stop()  # Close WebSocket connection
        await self.subscription.close_client()  # Close HTTPX client used for key management

        self.log.info("WebSocket client stopped gracefully.")

    def is_connected(self) -> bool:
        """Checks if the WebSocket connection is active."""
        return (
            self.manager.connection is not None and not self.manager.connection.closed
        )
