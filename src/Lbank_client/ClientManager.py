import asyncio
from typing import Dict, Optional, List
import pandas as pd

# Assuming these are your custom REST client modules and utility modules
from REST import RESTAccount, RESTTrading, RESTData
from WebSockets import WebSocketClient, MessageProcessor
from .Lbank_client_utils import StateCache, load_config  # load_config for convenience
from ..utils import BaseLogger


class ClientManager(BaseLogger):
    """
    A unified manager for coordinating REST and WebSocket interactions for LBank.
    Maintains synchronized internal state for balances, open orders, and klines.
    Automatically handles reconnection and reconciliation to ensure reliability.
    """

    def __init__(self, config: Dict):
        """
        Initializes the ClientManager with a full configuration dictionary.

        Args:
            config (dict): Configuration dictionary, typically loaded via API_utils.load_config().
                           Expected to contain API_KEY, API_SECRET, URLs, etc.
        """
        super().__init__()
        self.config = config
        self.api_key = self.config.get("API_KEY")
        self.api_secret = self.config.get("API_SECRET")

        if not self.api_key or not self.api_secret:
            self.log.warning(
                "API_KEY or API_SECRET not found in config. Authenticated features will be limited."
            )

        # Initialize REST modules (passing full config for flexibility)
        self.rest_account = RESTAccount(self.api_key, self.api_secret, self.config)
        self.rest_trading = RESTTrading(self.api_key, self.api_secret, self.config)
        self.rest_data = RESTData(self.api_key, self.api_secret, self.config)

        # Internal state cache
        self.state = StateCache()

        # Initialize LBank-specific Message Processor with callbacks to update StateCache
        self.lbank_message_processor = MessageProcessor(
            on_kbar_callback=self._on_kbar_update_from_ws,
            on_order_update_callback=self._on_order_update_from_ws,
            on_asset_update_callback=self._on_asset_update_from_ws,
            on_historical_kbar_callback=self._on_historical_kbar_from_ws,
        )

        # Initialize WebSocket Client, injecting the config and the specialized message processor
        # Default pair can also come from config or be a parameter to ClientManager
        default_ws_pair = self.config.get("DEFAULT_WS_PAIR", "eth_usdt")
        self.ws_client = WebSocketClient(
            config=self.config,
            pair=default_ws_pair,
            message_processor=self.lbank_message_processor,
        )

        self._background_tasks: List[asyncio.Task] = []
        self._running = False
        self.log.info("ClientManager initialized.")

    async def start(self):
        """Starts the manager, initializes connections, and launches background tasks."""
        if self._running:
            self.log.warning("ClientManager is already running.")
            return

        self.log.info("Starting ClientManager...")
        self._running = True

        # Fetch initial state via REST before starting WebSocket
        # to have a baseline, especially if WS connection is delayed.
        await self._sync_initial_state()

        # Start WebSocket client (which handles its own connection and subscriptions)
        # Run ws_client.start() as a managed task
        ws_task = asyncio.create_task(
            self.ws_client.start(), name="WebSocketClient_MainLoop"
        )
        self._background_tasks.append(ws_task)

        # Launch other background tasks managed by ClientManager
        reconnect_task = asyncio.create_task(
            self._reconnection_watchdog(), name="CM_ReconnectionWatchdog"
        )
        reconcile_task = asyncio.create_task(
            self._periodic_reconciliation(), name="CM_PeriodicReconciliation"
        )
        self._background_tasks.extend([reconnect_task, reconcile_task])

        self.log.info("ClientManager background tasks started.")
        # To keep ClientManager running and properly handle shutdown:
        try:
            await asyncio.gather(*self._background_tasks)
        except asyncio.CancelledError:
            self.log.info("ClientManager main gather was cancelled.")
        finally:
            await self.stop()  # Ensure cleanup on exit

    async def _reconnection_watchdog(self):
        """
        Monitors WebSocket connection. If WSClient's internal reconnection fails
        or if WSClient itself stops unexpectedly, this can attempt to restart it.
        Note: WSClient and WSConnectionManager already have their own retry logic.
        This watchdog is more of a higher-level check.
        """
        while self._running:
            await asyncio.sleep(15)  # Check every 15 seconds
            if not self.ws_client.is_connected():
                self.log.warning(
                    "ClientManager Watchdog: WebSocket client is not connected."
                )
                # Potentially try to restart ws_client if it's not attempting reconnection itself
                # For now, ws_client is designed to manage its own lifecycle including reconnections.
                # This watchdog might be more useful if ws_client.start() task itself has exited.
                # Check if the ws_client.start() task is done
                ws_client_task = next(
                    (
                        task
                        for task in self._background_tasks
                        if task.get_name() == "WebSocketClient_MainLoop"
                    ),
                    None,
                )
                if ws_client_task and ws_client_task.done():
                    if ws_client_task.exception():
                        self.log.error(
                            f"WebSocketClient_MainLoop task exited with exception: {ws_client_task.exception()}"
                        )
                    else:
                        self.log.warning(
                            "WebSocketClient_MainLoop task has exited. Attempting to restart."
                        )
                    # Remove the old task
                    self._background_tasks.remove(ws_client_task)
                    # Restart the WebSocket client
                    new_ws_task = asyncio.create_task(
                        self.ws_client.start(), name="WebSocketClient_MainLoop"
                    )
                    self._background_tasks.append(new_ws_task)
                    self.log.info("Attempted to restart WebSocketClient_MainLoop task.")

    async def _periodic_reconciliation(self):
        """Periodically validates internal state (from WS) against a REST snapshot."""
        while self._running:
            await asyncio.sleep(300)  # Every 5 minutes
            if not self._running:
                break  # Exit if stopping

            try:
                self.log.info("Starting periodic state reconciliation via REST.")
                if self.api_key and self.api_secret:  # Only if authenticated
                    rest_balances = await self.rest_account.get_balances()
                    # For open orders, decide if you want all or for specific symbols
                    rest_orders = (
                        await self.rest_trading.get_open_orders()
                    )  # Fetches all open orders

                    current_balances = await self.state.get_balances()
                    current_orders = await self.state.get_orders()

                    # Basic comparison (can be made more sophisticated)
                    if rest_balances != current_balances:
                        self.log.warning(
                            "Balance discrepancy detected during reconciliation.",
                            ws_state=current_balances,
                            rest_snapshot=rest_balances,
                        )
                        await self.state.set_balances(rest_balances)
                        self.log.info("Balances state reconciled with REST snapshot.")

                    if rest_orders != current_orders:
                        self.log.warning(
                            "Open orders discrepancy detected during reconciliation.",
                            ws_state=current_orders,
                            rest_snapshot=rest_orders,
                        )
                        await self.state.set_orders(rest_orders)
                        self.log.info(
                            "Open orders state reconciled with REST snapshot."
                        )
                else:
                    self.log.info("Skipping reconciliation: API keys not configured.")
                self.log.debug("Periodic reconciliation complete.")
            except asyncio.CancelledError:
                self.log.info("Periodic reconciliation task cancelled.")
                break
            except Exception as e:
                self.log.error(
                    "Error during periodic reconciliation.", error_details=str(e)
                )

    async def _sync_initial_state(self):
        """Fetches initial balances and open orders via REST and updates internal state."""
        try:
            self.log.info("Fetching initial state snapshot via REST.")
            if self.api_key and self.api_secret:
                balances = await self.rest_account.get_balances()
                orders = await self.rest_trading.get_open_orders()  # All open orders

                await self.state.set_balances(balances if balances else {})
                await self.state.set_orders(orders if orders else {})
                self.log.info(
                    "Initial REST state snapshot fetched and applied.",
                    balances_count=len(balances if balances else {}),
                    orders_count=len(orders if orders else {}),
                )
            else:
                self.log.warning(
                    "Skipping initial state sync: API keys not configured."
                )
        except Exception as e:
            self.log.error(
                "Failed to fetch initial state snapshot from REST.",
                error_details=str(e),
            )

    # --- WebSocket Data Callbacks (called by LBank MessageProcessor) ---
    async def _on_kbar_update_from_ws(self, kbar_message: dict):
        """Handles real-time kbar updates from WebSocket."""
        # kbar_message is expected to be like {"pair": "eth_usdt", "c": 123.45, ...}
        symbol = kbar_message.get("pair")
        if symbol:
            await self.state.update_kbar(
                symbol, kbar_message
            )  # Store the whole kbar message or just relevant parts
            self.log.debug(
                f"KBar data for {symbol} updated in StateCache from WS.",
                kbar_data=kbar_message,
            )

    async def _on_historical_kbar_from_ws(self, kbar_df: pd.DataFrame):
        """Handles historical kbar data (as DataFrame) from WebSocket 'request' response."""
        # Assuming the DataFrame has a 'pair' or 'symbol' column, or it's known from the request context
        # For simplicity, let's assume the processor adds a 'pair' to the message if it's available
        # Or, the DataFrame itself might need to be processed to extract symbol if not uniform.
        # This callback might need more context if kbar_df is for multiple symbols.
        if not kbar_df.empty:
            # Example: if a 'symbol' column exists in the DataFrame (LBank might not provide this directly in records)
            # Or, if the 'pair' was part of the original request message that triggered this response.
            # For now, we'd need to know which symbol this DataFrame belongs to.
            # Let's assume the MessageProcessor could pass the pair along if known.
            # For this example, we'll log it. A real implementation would need to map it to a symbol.
            self.log.info(
                f"Received historical kbar DataFrame (shape: {kbar_df.shape}). Needs symbol association for StateCache."
            )
            # Example: If you know the symbol (e.g., self.ws_client.pair for the default requested kbar)
            # await self.state.set_kbars(self.ws_client.pair, kbar_df.to_dict('records'))

    async def _on_order_update_from_ws(self, order_message: dict):
        """Handles real-time order updates from WebSocket."""
        # order_message is expected to be like {"pair": "eth_usdt", "uuid": "...", "status": "...", ...}
        order_id = order_message.get("uuid")  # LBank uses 'uuid' for order ID in WS
        if not order_id:
            self.log.warning(
                "Order update from WS missing 'uuid'.", order_data=order_message
            )
            return

        # LBank order status: 0: Unsettled, 1: Partially filled, 2: Fully filled, 3: Cancelled,
        # 4: Partially filled and cancelled
        # We'll consider 2, 3, 4 as "closed" for cache management.
        status_code = order_message.get("status")
        is_closed = status_code in [2, 3, 4]

        if is_closed:
            await self.state.close_order(order_id)
            self.log.info(
                f"Order {order_id} closed in StateCache from WS.",
                order_data=order_message,
            )
        else:
            await self.state.update_order(order_id, order_message)
            self.log.info(
                f"Order {order_id} updated in StateCache from WS.",
                order_data=order_message,
            )

    async def _on_asset_update_from_ws(
        self, asset_data: dict
    ):  # asset_data structure depends on LBank
        """Handles real-time asset/balance updates from WebSocket."""
        # The structure of asset_data from LBank WS needs to be known.
        # Typically, it's a dictionary or a list of dictionaries,
        # e.g., {"asset": "USDT", "free": "100.0", "locked": "10.0"}
        # Or, LBank might send a snapshot like:
        # { "USDT": {"free": "100", "freeze": "10"}, "BTC": {"free":"1", "freeze":"0.5"}}
        # This handler needs to parse asset_data and update self.state.update_balances() accordingly.
        # For now, let's assume asset_data is a snapshot similar to REST get_balances response.
        if isinstance(asset_data, dict):
            await self.state.update_balances(
                asset_data
            )  # Or set_balances if it's a full snapshot
            self.log.info(
                "Balances updated in StateCache from WS asset update.",
                asset_snapshot=asset_data,
            )
        else:
            self.log.warning(
                "Received asset update in unexpected format from WS.", data=asset_data
            )

    # --- Public Methods for Interaction ---
    async def place_order(
        self,
        symbol: str,
        side: str,
        ord_type: str,
        quantity: float,
        price: Optional[float] = None,
    ):
        """
        Places an order using the REST API.

        Args:
            symbol (str): The trading pair (e.g., "eth_usdt").
            side (str): "buy" or "sell".
            ord_type (str): "limit" or "market".
            quantity (float): Amount to buy or sell.
            price (float, optional): Limit price, required for limit orders.

        Returns:
            dict: The response from the REST API, or None if failed.
        """
        if not (self.api_key and self.api_secret):
            self.log.error("Cannot place order: API_KEY or API_SECRET not configured.")
            return None
        try:
            # Assuming your RESTTrading.place_order is adapted for LBank's parameters
            # LBank uses 'type' for buy/sell and 'orderType' for limit/market (this varies by exchange)
            # The provided snippet for RESTTrading is a mock.
            # This is a conceptual call; actual parameters depend on your RESTTrading implementation.
            result = await self.rest_trading.place_order(
                symbol=symbol,
                side=side,  # Your REST client should map this to LBank's 'type'
                # type=lbank_side, # e.g. 'buy' or 'sell'
                # orderType=ord_type, # e.g. 'limitOrder' or 'marketOrder'
                quantity=quantity,
                price=price,
            )
            self.log.info("Order placed via REST.", result=result)
            # Optionally, update local order state immediately if REST returns enough info,
            # or wait for WebSocket confirmation.
            return result
        except Exception as e:
            self.log.error("Failed to place order via REST.", error_details=str(e))
            # raise # Or return a specific error object
            return None

    async def get_cached_balances(self) -> dict:
        return await self.state.get_balances()

    async def get_cached_open_orders(self, symbol: Optional[str] = None) -> dict:
        # ClientManager's StateCache stores all orders; filtering by symbol would be manual here.
        all_orders = await self.state.get_orders()
        if symbol:
            return {
                oid: odata
                for oid, odata in all_orders.items()
                if odata.get("pair") == symbol
            }
        return all_orders

    async def get_cached_kbars(self, symbol: str) -> list:
        return await self.state.get_kbars(symbol)

    async def stop(self):
        """Stops background tasks and disconnects WebSocket client."""
        if not self._running:
            self.log.info("ClientManager is not running or already stopping.")
            return

        self.log.info("Stopping ClientManager...")
        self._running = False  # Signal tasks to stop

        # Cancel all background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()

        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks = []

        # Stop the WebSocket client explicitly if it hasn't stopped
        if self.ws_client:
            await self.ws_client.stop()

        self.log.info("ClientManager stopped.")


# Example Usage (Conceptual)
async def main():
    # Load configuration (API keys, URLs, etc.)
    config = load_config()  # From API_utils.py

    # Ensure critical URLs are present, especially for WebSocket
    if not config.get("WEBSOCKET_URI"):
        print("WEBSOCKET_URI not found in configuration. Exiting.")
        return
    if not config.get("API_KEY") or not config.get("API_SECRET"):
        print(
            "Warning: API_KEY or API_SECRET not found. Authenticated features will be limited."
        )

    manager = ClientManager(config=config)
    try:
        # Start the manager (which starts ws_client and other tasks)
        # The manager.start() will now run indefinitely until an error or SIGINT
        # if its gather is awaited directly.
        # For a script, you might run it and then have a separate mechanism to stop it.

        asyncio.create_task(manager.start())

        # Keep the main function alive, e.g., to allow interaction or wait for shutdown signal
        # For demonstration, run for a short period or until Ctrl+C
        print("ClientManager starting... Press Ctrl+C to stop.")
        await asyncio.sleep(10)  # Run for 10 seconds then try to place an order

        # Example: Placing an order
        # order_result = await manager.place_order(
        #     symbol="eth_usdt", side="buy", ord_type="limit", quantity=0.01, price=1800.00
        # )
        # if order_result:
        #     print(f"Order placement attempt result: {order_result}")

        # await asyncio.sleep(30) # Wait some more

    except KeyboardInterrupt:
        print("KeyboardInterrupt received, stopping ClientManager...")
    except Exception as e:
        print(f"An error occurred in main: {e}")
    finally:
        print("Shutting down ClientManager from main...")
        await manager.stop()
        print("ClientManager shutdown complete.")


if __name__ == "__main__":
    # This example main will likely not run perfectly without the actual
    # REST client implementations and a full environment setup.
    # It's for conceptual demonstration of ClientManager usage.
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Application terminated by user.")
